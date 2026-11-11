import os
import random
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from click.testing import CliRunner

from habit_tracker.cli import main
from habit_tracker.storage import (
    HabitError,
    add_habit,
    check_in,
    default_database,
    list_habits,
    remove_habit,
    streaks,
)


@pytest.fixture
def db(tmp_path):
    # Windows forbids question marks in filenames; retain URI escaping coverage.
    name = "Unicode 习惯 #%.sqlite3" if os.name == "nt" else "Unicode 习惯 #?%.sqlite3"
    return tmp_path / name


def invoke(db, *args):
    return CliRunner().invoke(main, ["--database", str(db)] + list(args))


def test_empty_is_honest_and_does_not_create(db):
    result = invoke(db, "list")
    assert result.exit_code == 0
    assert "No habits yet" in result.output
    assert "Exercise" not in result.output
    assert not db.exists()


def test_persistent_add_checkin_and_list(db):
    assert invoke(db, "add", "  Exercise  ").exit_code == 0
    assert list_habits(db) == [("Exercise", 0, 0, False)]
    assert invoke(db, "checkin", "Exercise").exit_code == 0
    assert list_habits(db) == [("Exercise", 1, 1, True)]
    result = invoke(db, "list")
    assert result.exit_code == 0
    assert "Yes" in result.output


def test_duplicate_add_fails(db):
    add_habit(db, "Read")
    result = invoke(db, "add", " Read ")
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert "Added habit" not in result.output
    assert len(list_habits(db)) == 1


@pytest.mark.parametrize("name", ["", "   ", "a\nb", "a\x1bb", "a\x00b", "x" * 201])
def test_invalid_names_do_not_create(db, name):
    assert invoke(db, "add", name).exit_code != 0
    assert not db.exists()


def test_unicode_and_markup_remain_literal(db):
    name = "读书 [bold]literal[/bold]"
    add_habit(db, name)
    result = invoke(db, "list")
    assert result.exit_code == 0
    assert name in result.output


def test_unknown_checkin_fails_without_creating(db):
    result = invoke(db, "checkin", "missing")
    assert result.exit_code != 0
    assert "Unknown habit" in result.output
    assert "Checked in:" not in result.output
    assert not db.exists()


def test_repeat_checkin_is_idempotent(db):
    add_habit(db, "Read")
    assert "Checked in:" in invoke(db, "checkin", "Read").output
    result = invoke(db, "checkin", "Read")
    assert result.exit_code == 0
    assert "Already checked in:" in result.output
    with sqlite3.connect(str(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM checkins").fetchone() == (1,)


@pytest.mark.parametrize(
    "day",
    ["2024-02-30", "2023-02-29", "2024-2-03", "20240203", "bad", "", "9999-12-31"],
)
def test_invalid_dates_do_not_write(db, day):
    add_habit(db, "Read")
    before = db.read_bytes()
    result = invoke(db, "checkin", "Read", "--date", day)
    assert result.exit_code != 0
    assert "Checked in:" not in result.output
    assert db.read_bytes() == before


def test_future_date(db):
    add_habit(db, "Read")
    assert (
        invoke(
            db,
            "checkin",
            "Read",
            "--date",
            (date.today() + timedelta(days=1)).isoformat(),
        ).exit_code
        != 0
    )


@pytest.mark.parametrize(
    "offsets, expected",
    [
        ([], (0, 0, False)),
        ([0], (1, 1, True)),
        ([-1], (1, 1, False)),
        ([-2], (0, 1, False)),
        ([-4, -3, -2, 0], (1, 3, True)),
        ([-3, -2, -1], (3, 3, False)),
        ([-2, -1, 0], (3, 3, True)),
        # A later date must not clear the run ending today or yesterday.
        ([-1, 0, 1], (2, 3, True)),
        ([0, 2], (1, 1, True)),
        ([-1, 2], (1, 1, False)),
        ([1, 2], (0, 2, False)),
    ],
)
def test_streaks(offsets, expected):
    today = date(2024, 3, 1)
    assert (
        streaks([(today + timedelta(days=n)).isoformat() for n in offsets], today)
        == expected
    )


def test_backdated_leap_day(db):
    add_habit(db, "Read")
    assert invoke(db, "checkin", "Read", "--date", "2024-02-29").exit_code == 0
    assert list_habits(db)[0][2] == 1


@pytest.mark.parametrize(
    "command", [("list",), ("add", "Read"), ("checkin", "Read"), ("remove", "Read")]
)
def test_corrupt_file_preserved(db, command):
    db.write_bytes(b"not sqlite\x00data")
    before = db.read_bytes()
    result = invoke(db, *command)
    assert result.exit_code != 0
    assert "Error:" in result.output
    assert db.read_bytes() == before


@pytest.mark.parametrize(
    "schema",
    [
        "CREATE TABLE other (value TEXT)",
        "CREATE TABLE habits (name TEXT); PRAGMA user_version=1",
        "PRAGMA user_version=2",
    ],
)
def test_unknown_schema_preserved(db, schema):
    with sqlite3.connect(str(db)) as connection:
        connection.executescript(schema)
    before = db.read_bytes()
    result = invoke(db, "add", "Read")
    assert result.exit_code != 0
    assert db.read_bytes() == before


def test_invalid_stored_date_fails_closed(db):
    add_habit(db, "Read")
    with sqlite3.connect(str(db)) as connection:
        connection.execute("INSERT INTO checkins VALUES (?, ?)", ("Read", "bad"))
    before = db.read_bytes()
    assert invoke(db, "list").exit_code != 0
    assert invoke(db, "add", "New").exit_code != 0
    assert db.read_bytes() == before


def test_io_failure_has_no_success(tmp_path):
    parent = tmp_path / "file"
    parent.write_text("occupied", encoding="utf-8")
    result = invoke(parent / "database", "add", "Read")
    assert result.exit_code != 0
    assert "Added habit" not in result.output
    assert parent.read_text(encoding="utf-8") == "occupied"


def test_locked_database_has_no_success(db):
    add_habit(db, "Read")
    with sqlite3.connect(str(db)) as connection:
        connection.execute("BEGIN EXCLUSIVE")
        result = invoke(db, "checkin", "Read")
        assert result.exit_code != 0
        assert "locked" in result.output
        assert "Checked in:" not in result.output


def test_concurrent_add_and_checkin(db):
    with ThreadPoolExecutor(max_workers=8) as pool:
        names = list(pool.map(lambda n: add_habit(db, "Habit {}".format(n)), range(16)))
    assert len(list_habits(db)) == 16
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: check_in(db, names[0], date.today().isoformat()), range(16)
            )
        )
    assert sum(added for _, added in results) == 1


def test_concurrent_duplicate_add(db):
    def add(_):
        try:
            add_habit(db, "Read")
            return True
        except HabitError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(add, range(16))) == 1
    assert len(list_habits(db)) == 1


def test_env_and_flag_precedence(db, tmp_path, monkeypatch):
    monkeypatch.setenv("HABIT_TRACKER_DB", str(db))
    assert CliRunner().invoke(main, ["add", "Read"]).exit_code == 0
    other = tmp_path / "other.sqlite3"
    assert invoke(other, "add", "Walk").exit_code == 0
    assert list_habits(db)[0][0] == "Read"
    assert list_habits(other)[0][0] == "Walk"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_database() == tmp_path / "habit-tracker" / "habits.sqlite3"


def test_separate_processes(db):
    env = dict(os.environ, PYTHONPATH=os.path.abspath("src"), PYTHONIOENCODING="utf-8")
    for command in [("add", "Read"), ("checkin", "Read"), ("list",)]:
        result = subprocess.run(
            [sys.executable, "-m", "habit_tracker.cli", "--db", str(db)]
            + list(command),
            env=env,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        assert result.returncode == 0, result.stderr
    assert "Read" in result.stdout and "Yes" in result.stdout


def test_missing_foreign_key_and_orphan_preserved(db):
    with sqlite3.connect(str(db)) as connection:
        connection.executescript(
            "CREATE TABLE habits (name TEXT PRIMARY KEY NOT NULL); CREATE TABLE checkins (name TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY(name, day)); PRAGMA user_version=1; INSERT INTO checkins VALUES ('orphan', '2024-02-29');"
        )
    before = db.read_bytes()
    for command in [("list",), ("add", "Read"), ("checkin", "orphan")]:
        assert invoke(db, *command).exit_code != 0
        assert db.read_bytes() == before


def test_orphan_with_declared_foreign_key_preserved(db):
    add_habit(db, "Read")
    with sqlite3.connect(str(db)) as connection:
        connection.execute("INSERT INTO checkins VALUES ('orphan', '2024-02-29')")
    before = db.read_bytes()
    assert invoke(db, "list").exit_code != 0
    assert db.read_bytes() == before


def expected_streaks(days, today):
    present = {date.fromisoformat(day) for day in days}
    longest = 0
    for day in present:
        if day - timedelta(days=1) not in present:
            run = 0
            cursor = day
            while cursor in present:
                run += 1
                cursor += timedelta(days=1)
            longest = max(longest, run)
    if today in present:
        anchor = today
    elif today - timedelta(days=1) in present:
        anchor = today - timedelta(days=1)
    else:
        anchor = None
    current = 0
    if anchor is not None:
        cursor = anchor
        while cursor in present:
            current += 1
            cursor -= timedelta(days=1)
    return current, longest, today in present


def test_streaks_match_calendar_walk():
    today = date(2024, 3, 1)
    rng = random.Random(0)
    for _ in range(300):
        offsets = rng.sample(range(-30, 8), rng.randint(0, 10))
        days = [(today + timedelta(days=offset)).isoformat() for offset in offsets]
        if days:
            days = days + days[:2]
        rng.shuffle(days)
        assert streaks(days, today) == expected_streaks(days, today)


def test_later_stored_date_stays_readable_and_keeps_current_streak(db):
    add_habit(db, "Read")
    today = date.today()
    check_in(db, "Read", (today - timedelta(days=1)).isoformat())
    check_in(db, "Read", today.isoformat())
    later = (today + timedelta(days=1)).isoformat()
    with sqlite3.connect(str(db)) as connection:
        connection.execute(
            "INSERT INTO checkins(name, day) VALUES (?, ?)", ("Read", later)
        )
    assert list_habits(db) == [("Read", 2, 3, True)]
    listed = invoke(db, "list")
    assert listed.exit_code == 0
    assert "Read" in listed.output
    assert "2 days" in listed.output
    assert "future" not in listed.output.lower()
    assert invoke(db, "add", "Walk").exit_code == 0
    assert invoke(db, "checkin", "Walk").exit_code == 0
    assert {name for name, _, _, _ in list_habits(db)} == {"Read", "Walk"}


def test_full_habit_name_is_listed(db):
    wide = "Focus " + ("深" * 80)
    plain = "N" * 200
    add_habit(db, wide)
    add_habit(db, plain)
    result = invoke(db, "list")
    assert result.exit_code == 0
    assert wide in result.output
    assert plain in result.output
    assert "Done Today" in result.output
    assert "…" not in result.output


def test_streak_labels_use_singular_day(db):
    add_habit(db, "Read")
    check_in(db, "Read", (date.today() - timedelta(days=1)).isoformat())
    one = invoke(db, "list")
    assert one.exit_code == 0
    assert "1 day" in one.output
    assert "1 days" not in one.output
    check_in(db, "Read", date.today().isoformat())
    two = invoke(db, "list")
    assert two.exit_code == 0
    assert "2 days" in two.output


def test_remove_deletes_one_habit_and_its_checkins(db):
    add_habit(db, "Read")
    add_habit(db, "Walk")
    check_in(db, "Read", date.today().isoformat())
    result = invoke(db, "remove", "  Read  ")
    assert result.exit_code == 0
    assert result.output == "Removed habit: Read\n"
    assert list_habits(db) == [("Walk", 0, 0, False)]
    with sqlite3.connect(str(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM checkins").fetchone() == (0,)
        assert connection.execute("SELECT name FROM habits").fetchall() == [("Walk",)]
    assert remove_habit(db, "Walk") == "Walk"
    assert list_habits(db) == []
    assert db.exists()


def test_remove_unknown_does_not_create_database(db):
    result = invoke(db, "remove", "Missing")
    assert result.exit_code != 0
    assert "Unknown habit" in result.output
    assert "Removed habit" not in result.output
    assert not db.exists()


def test_remove_unknown_or_invalid_keeps_rows(db):
    add_habit(db, "Read")
    check_in(db, "Read", date.today().isoformat())
    missing = invoke(db, "remove", "Missing")
    invalid = invoke(db, "remove", "bad\nname")
    assert missing.exit_code != 0 and invalid.exit_code != 0
    assert "Removed habit" not in missing.output
    assert "Removed habit" not in invalid.output
    assert list_habits(db) == [("Read", 1, 1, True)]
    with sqlite3.connect(str(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM checkins").fetchone() == (1,)


def test_unexpected_unique_constraint_is_not_repeat_success(db):
    add_habit(db, "Read")
    add_habit(db, "Walk")
    check_in(db, "Read", date.today().isoformat())
    with sqlite3.connect(str(db)) as connection:
        connection.execute("CREATE UNIQUE INDEX unexpected_day ON checkins(day)")
    before = db.read_bytes()
    result = invoke(db, "checkin", "Walk")
    assert result.exit_code != 0
    assert "Already checked in" not in result.output
    assert "Checked in:" not in result.output
    assert db.read_bytes() == before
