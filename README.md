# Habit Tracker

A local, SQLite-backed daily habit CLI for Python 3.8+. Add habits, check in,
and list real current/longest streaks. No account, service, or network is needed.

## Install and use

```sh
pip install .
habit add "Exercise"
habit checkin "Exercise"
habit list
habit checkin "Exercise" --date 2024-02-29
```

The original `add NAME`, `checkin NAME`, and `list` commands remain available.
Names are case-sensitive, trimmed, limited to 200 characters, and cannot contain
control characters. Unicode and Rich-looking markup are displayed literally.
Duplicate names fail with a nonzero exit status; check-ins for unknown habits fail
without creating them. Repeating a check-in for the same day is a successful,
explicitly reported no-op. Check-in dates must be real `YYYY-MM-DD` dates no later
than today in the computer's local timezone.

Current streak counts consecutive days ending today or yesterday (today is still
available to complete). A gap before yesterday resets it to zero. Longest streak
counts the greatest consecutive run, including backdated check-ins.

## Storage and failures

By default, the database is `~/.local/share/habit-tracker/habits.sqlite3`.
If `XDG_DATA_HOME` is set, it is `$XDG_DATA_HOME/habit-tracker/habits.sqlite3`.
Override with `HABIT_TRACKER_DB` or `habit --database PATH ...` (`--db` is an alias).
The explicit option wins over the environment. Relative paths resolve from the
working directory; `~` is expanded. Use one consistent path across invocations.

The first successful add creates parent directories and initializes the database.
Listing an absent database reports no habits without creating it. SQLite
transactions serialize writes and prevent duplicate habits/check-ins during
concurrent invocations. Errors, including lock timeouts (5 seconds), invalid
schemas, damaged data, and filesystem failures, exit nonzero with no success
message. Existing malformed or unsupported databases are not reset or replaced.
An unsuccessful first add may leave an empty SQLite file or parent directory.
Keep backups while the CLI is closed; no automatic migration or repair is offered.
Do not share this local database on an unreliable/network filesystem.

The previous release only printed success and sample data; it never saved habits,
so there are no previous habit records to migrate. Categories, reports, calendar
views, reminders, deletion, and editing are **not implemented**.

## Development

```sh
pip install -e '.[dev]'
ruff check src tests scripts
ruff format --check src tests scripts
pytest -q
python -m build
pip install --force-reinstall dist/habit_tracker-0.1.0-py3-none-any.whl
python scripts/smoke_installed.py
```

CI is configured for Python 3.8–3.14 on Ubuntu 24.04 and Python 3.12 on Windows
2022 and macOS 15. It includes minimum Click/Rich dependency checks, source and
wheel build/install smoke checks. A configured matrix is not proof of passing
hosted runs; local validation evidence accompanies this repair candidate.

## License

MIT. See LICENSE.
