"""Smoke-test the installed console script outside the source directory."""

import os
import subprocess
import sysconfig
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="habit-wheel-") as directory:
    root = Path(directory)
    database = root / "habits #1.sqlite3"
    scripts = Path(sysconfig.get_path("scripts"))
    entry = scripts / ("habit.exe" if os.name == "nt" else "habit")
    env = dict(
        os.environ,
        PYTHONIOENCODING="utf-8",
        PYTHONUTF8="1",
        NO_COLOR="1",
        COLUMNS="120",
    )
    env.pop("PYTHONPATH", None)

    def run(*args, success=True):
        result = subprocess.run(
            [str(entry), "--database", str(database), *args],
            cwd=str(root),
            env=env,
            encoding="utf-8",
            capture_output=True,
            timeout=20,
            check=False,
        )
        assert (result.returncode == 0) == success, (result.stdout, result.stderr)
        return result.stdout

    assert "No habits yet" in run("list")
    assert not database.exists()
    assert "Added habit" in run("add", "读书 [bold]literal[/bold]")
    assert "读书 [bold]literal[/bold]" in run("list")
    assert "Checked in:" in run("checkin", "读书 [bold]literal[/bold]")
    assert "Already checked in:" in run("checkin", "读书 [bold]literal[/bold]")
    assert "Yes" in run("list")
    assert "1 day" in run("list")
    run("checkin", "Missing", success=False)
    assert "Removed habit" in run("remove", "读书 [bold]literal[/bold]")
    assert "No habits yet" in run("list")
    run("remove", "Missing", success=False)
    assert database.exists()
print("Installed habit console: persistent add/checkin/list/remove checks passed.")
