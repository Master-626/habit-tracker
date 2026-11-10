"""Command-line interface for persistent daily habits."""

import functools

import click
from rich.console import Console
from rich.table import Table

from habit_tracker import __version__
from habit_tracker.storage import (
    HabitError,
    add_habit,
    check_in,
    default_database,
    list_habits,
)


def handle_errors(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except HabitError as exc:
            raise click.ClickException(str(exc)) from None

    return wrapped


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--database",
    "--db",
    envvar="HABIT_TRACKER_DB",
    type=click.Path(dir_okay=False),
    help="SQLite database path (default: ~/.local/share/habit-tracker/habits.sqlite3, or under XDG_DATA_HOME).",
)
@click.pass_context
def main(ctx, database):
    """Habit Tracker - Build better habits, one day at a time."""
    ctx.obj = database if database is not None else default_database()


@main.command()
@click.argument("name")
@click.pass_obj
@handle_errors
def add(database, name):
    """Add a new habit."""
    name = add_habit(database, name)
    click.echo("Added habit: {}".format(name))


@main.command()
@click.argument("name")
@click.option(
    "--date", "day", help="Check-in date YYYY-MM-DD (default: today, local time)."
)
@click.pass_obj
@handle_errors
def checkin(database, name, day):
    """Check in a known habit, once per local calendar day."""
    from datetime import date

    day = day if day is not None else date.today().isoformat()
    name, added = check_in(database, name, day)
    click.echo(
        "{}: {} ({})".format("Checked in" if added else "Already checked in", name, day)
    )


@main.command(name="list")
@click.pass_obj
@handle_errors
def list_command(database):
    """List stored habits and their actual streaks."""
    habits = list_habits(database)
    if not habits:
        click.echo("No habits yet. Add one with: habit add NAME")
        return
    table = Table(title="Habits")
    for title in ("Habit", "Streak", "Longest", "Done Today"):
        table.add_column(title)
    from rich.text import Text

    for name, current, longest, done in habits:
        table.add_row(
            Text(name),
            "{} days".format(current),
            "{} days".format(longest),
            "Yes" if done else "No",
        )
    Console().print(table)


if __name__ == "__main__":
    main()
