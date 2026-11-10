"""Transactional, local habit storage (Python 3.8+)."""

import os
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path


class HabitError(Exception):
    """An expected input or storage failure."""


def default_database():
    root = os.environ.get("XDG_DATA_HOME")
    return (
        Path(root).expanduser() / "habit-tracker" / "habits.sqlite3"
        if root
        else Path.home() / ".local" / "share" / "habit-tracker" / "habits.sqlite3"
    )


def validate_name(name):
    name = name.strip()
    if (
        not name
        or len(name) > 200
        or any(unicodedata.category(c).startswith("C") for c in name)
    ):
        raise HabitError(
            "Habit names must contain 1–200 characters and no control characters."
        )
    return name


def validate_day(value):
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HabitError("Date must be a real date in YYYY-MM-DD format.") from None
    if day.isoformat() != value:
        raise HabitError("Date must use YYYY-MM-DD format.")
    if day > date.today():
        raise HabitError("Cannot check in for a future date.")
    return day


@contextmanager
def database(path, create=False):
    path = Path(path).expanduser()
    connection = None
    try:
        if not create and not path.exists():
            yield None
            return
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        # URI mode prevents a read/check-in from recreating a missing database.
        connection = sqlite3.connect(
            path.resolve().as_uri() + ("?mode=rwc" if create else "?mode=rw"),
            uri=True,
            timeout=5,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if version == 0 and not tables and create:
            connection.execute("CREATE TABLE habits (name TEXT PRIMARY KEY NOT NULL)")
            connection.execute(
                "CREATE TABLE checkins (name TEXT NOT NULL REFERENCES habits(name), day TEXT NOT NULL, PRIMARY KEY(name, day))"
            )
            connection.execute("PRAGMA user_version = 1")
        elif version != 1 or tables != {"habits", "checkins"}:
            raise HabitError("Unsupported habit database schema; no data was changed.")
        expected = {
            "habits": [("name", "TEXT", 1, 1)],
            "checkins": [("name", "TEXT", 1, 1), ("day", "TEXT", 1, 2)],
        }
        for table, columns in expected.items():
            actual = [
                (row[1], row[2], row[3], row[5])
                for row in connection.execute("PRAGMA table_info(" + table + ")")
            ]
            if actual != columns:
                raise HabitError(
                    "Unsupported habit database schema; no data was changed."
                )
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('trigger', 'view')"
        ).fetchone():
            raise HabitError("Unsupported habit database objects; no data was changed.")
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(checkins)"
        ).fetchall()
        if foreign_keys != [
            (0, 0, "habits", "name", "name", "NO ACTION", "NO ACTION", "NONE")
        ]:
            raise HabitError(
                "Unsupported habit database references; no data was changed."
            )
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise HabitError("Invalid habit database references; no data was changed.")
        # Validate existing rows rather than printing misleading reports from damaged data.
        for (name,) in connection.execute("SELECT name FROM habits"):
            if validate_name(name) != name:
                raise HabitError("Invalid stored habit name; no data was changed.")
        for (day,) in connection.execute("SELECT day FROM checkins"):
            validate_day(day)
        yield connection
        connection.commit()
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise HabitError("Cannot use habit database: {}".format(exc)) from None
    finally:
        if connection is not None:
            connection.close()


def add_habit(path, name):
    name = validate_name(name)
    with database(path, create=True) as connection:
        if connection.execute(
            "SELECT 1 FROM habits WHERE name = ?", (name,)
        ).fetchone():
            raise HabitError("Habit already exists: {}".format(name))
        connection.execute("INSERT INTO habits(name) VALUES (?)", (name,))
    return name


def check_in(path, name, day):
    name = validate_name(name)
    day = validate_day(day).isoformat()
    with database(path) as connection:
        if (
            connection is None
            or not connection.execute(
                "SELECT 1 FROM habits WHERE name = ?", (name,)
            ).fetchone()
        ):
            raise HabitError("Unknown habit: {}. Add it first.".format(name))
        added = (
            connection.execute(
                "SELECT 1 FROM checkins WHERE name = ? AND day = ?", (name, day)
            ).fetchone()
            is None
        )
        if added:
            connection.execute(
                "INSERT INTO checkins(name, day) VALUES (?, ?)", (name, day)
            )
    return name, added


def streaks(days, today):
    completed = sorted(set(date.fromisoformat(day) for day in days))
    longest = run = 0
    previous = None
    for day in completed:
        run = (
            run + 1
            if previous is not None and day - previous == timedelta(days=1)
            else 1
        )
        longest = max(longest, run)
        previous = day
    current = (
        run if completed and completed[-1] in (today, today - timedelta(days=1)) else 0
    )
    return current, longest, today in completed


def list_habits(path):
    with database(path) as connection:
        if connection is None:
            return []
        rows = connection.execute(
            "SELECT habits.name, checkins.day FROM habits LEFT JOIN checkins USING(name) ORDER BY habits.name, checkins.day"
        ).fetchall()
    grouped = {}
    for name, day in rows:
        grouped.setdefault(name, [])
        if day is not None:
            grouped[name].append(day)
    return [(name,) + streaks(days, date.today()) for name, days in grouped.items()]
