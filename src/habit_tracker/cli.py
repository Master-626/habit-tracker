"""CLI interface."""
import click
from rich.console import Console
from rich.table import Table

console = Console()

@click.group()
@click.version_option(version="0.1.0")
def main():
    """Habit Tracker - Build better habits, one day at a time."""
    pass

@main.command()
@click.argument("name")
def add(name):
    """Add a new habit."""
    console.print(f"✅ Added habit: [bold green]{name}[/bold green]")

@main.command()
@click.argument("name")
def checkin(name):
    """Check in a habit for today."""
    console.print(f"✅ Checked in: {name}")

@main.command()
def list():
    """List all habits."""
    table = Table(title="Habits")
    table.add_column("Habit", style="cyan")
    table.add_column("Streak", style="green")
    table.add_column("Done Today")
    table.add_row("Exercise", "7 days", "✅")
    console.print(table)

if __name__ == "__main__":
    main()
