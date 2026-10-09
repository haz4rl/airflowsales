import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DOMAIN_TABLES = {
    "campaigns",
    "companies",
    "prospects",
    "evidence",
    "qualifications",
    "workflow_runs",
    "workflow_events",
}


def _run_alembic(db_path, *args):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _tables(db_path):
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_initial_migration_upgrades_and_downgrades(tmp_path):
    db_path = tmp_path / "migration.db"

    _run_alembic(db_path, "upgrade", "head")
    assert DOMAIN_TABLES <= _tables(db_path)

    _run_alembic(db_path, "downgrade", "base")
    assert not DOMAIN_TABLES & _tables(db_path)
