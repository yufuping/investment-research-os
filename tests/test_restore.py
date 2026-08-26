from datetime import UTC, datetime
import sqlite3

from investment_os.app.restore import restore_database


def _database(path, value):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES (?)", (value,))


def test_restore_database_preserves_current_copy_and_restores_backup(tmp_path):
    backup = tmp_path / "backup.db"
    destination = tmp_path / "current.db"
    _database(backup, "备份内容")
    _database(destination, "当前内容")
    safety = restore_database(backup, destination, tmp_path / "safety", datetime(2026, 8, 23, tzinfo=UTC))
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "备份内容"
    assert safety is not None
    with sqlite3.connect(safety) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "当前内容"
    assert safety.with_suffix(".db.sha256").exists()


def test_restore_rejects_invalid_backup_without_changing_current(tmp_path):
    backup = tmp_path / "broken.db"
    backup.write_text("损坏", encoding="utf-8")
    destination = tmp_path / "current.db"
    _database(destination, "保持不变")
    try:
        restore_database(backup, destination, tmp_path / "safety")
    except ValueError:
        pass
    else:
        raise AssertionError("损坏备份应被拒绝")
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "保持不变"
