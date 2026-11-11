# Habit Tracker

## 简要说明

Habit Tracker 是一个本地命令行习惯打卡工具（Python 3.8+）。习惯和打卡记录保存在 SQLite 文件中，不需要账号、服务或网络。可以添加习惯、按本地日期打卡、删除习惯，并查看当前连续天数和最长连续天数。新的打卡不能晚于本地今天；如果时钟或时区回拨，已经保存的记录仍然可以读取。

## Purpose

Habit Tracker is a local daily-habit CLI. It stores habits and check-ins in a
SQLite file on this computer and prints the real current streak and the longest
streak. There is no account, service, or network access.

## Install

Python 3.8 or newer is required. From a checkout of this repository:

```sh
pip install .
habit --help
```

That installs the `habit` command.

## Usage

```sh
habit add "Exercise"
habit checkin "Exercise"
habit checkin "Exercise" --date 2024-02-29
habit list
habit remove "Exercise"
```

`add`, `checkin`, `list`, and `remove` are the commands. `habit --version`
prints the version. A name that starts with `-` has to come after `--`, for
example `habit add -- "-rest"`.

## Options

| Option | Meaning |
| --- | --- |
| `--database PATH`, `--db PATH` | SQLite file to open. Overrides `HABIT_TRACKER_DB`. |
| `--date YYYY-MM-DD` | Check-in date. Defaults to today in the local timezone. |
| `--version` | Print the version and exit. |
| `--help` | Print help and exit. |

`HABIT_TRACKER_DB` sets the database path when `--database` / `--db` is omitted.
If `XDG_DATA_HOME` is set, the default file is
`$XDG_DATA_HOME/habit-tracker/habits.sqlite3`. Otherwise it is
`~/.local/share/habit-tracker/habits.sqlite3`.

Relative paths resolve from the working directory, and `~` is expanded. Use
one path consistently. An explicit `--database` or `--db` wins over the
environment variable.

## Check-ins, names, and streaks

Names are case-sensitive, trimmed, limited to 200 characters, and cannot
contain control characters. Unicode is stored as entered. Text that looks like
Rich markup is displayed literally, and `habit list` prints the full name
instead of cutting it off with an ellipsis.

Adding a duplicate name fails with a nonzero exit status. Checking in or
removing an unknown habit fails without creating that habit or a new database.
Repeating a check-in for the same day succeeds and reports that the day was
already recorded.

A new check-in date must be a real `YYYY-MM-DD` date no later than today in
the computer's local timezone. A date already in the file is kept when it is
a real `YYYY-MM-DD` value, including one that is now after today because the
clock or timezone moved backward. Those stored dates do not make the database
unreadable.

The current streak is the consecutive run ending today, or ending yesterday
while today is still open. A gap before that day resets it to zero. A later
stored date does not erase this run and does not extend it past today. The
longest streak is the greatest consecutive run among the stored dates,
including backdated check-ins and any later date already saved. A count of
one is labeled `1 day`; every other count is labeled `N days`.

`habit remove NAME` deletes that habit and its check-ins. Other habits are
left in place.

## Storage and failures

The first successful add creates parent directories and initializes the
database. Listing an absent database reports no habits and does not create a
file. SQLite transactions serialize writes and prevent duplicate habits or
check-ins from concurrent processes. Errors, including a lock held longer
than 5 seconds, an invalid schema, damaged data, and filesystem failures,
exit nonzero and do not print a success message. An existing malformed or
unsupported database is not reset or replaced. An unsuccessful first add may
leave an empty SQLite file or a parent directory.

Keep backups while the CLI is closed. There is no automatic migration or
repair. Do not put this database on an unreliable or network filesystem.

This project's first release only printed success text and sample data; it
never saved habits, so there are no older records to migrate. Categories,
reports, calendar views, reminders, and editing are not implemented.

## Development and tests

```sh
pip install -e '.[dev]'
ruff check src tests scripts
ruff format --check src tests scripts
pytest -q
```

Build the package and smoke-test the installed command:

```sh
python -m build
pip install --force-reinstall dist/habit_tracker-*.whl
python scripts/smoke_installed.py
```

GitHub Actions runs Ruff and pytest on Python 3.8 through 3.14 on Ubuntu
24.04, and on Python 3.12 on Windows Server 2022 and macOS 15. It also
installs the minimum Click and Rich versions, builds the wheel and sdist, and
runs `scripts/smoke_installed.py`.

## License

MIT. See LICENSE.
