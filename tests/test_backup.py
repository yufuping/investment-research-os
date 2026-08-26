from datetime import UTC, datetime
import sqlite3

from investment_os.app.backup import backup_database, verify_backup


def test_backup_database_creates_consistent_copy(tmp_path):
    source = tmp_path / "investment.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('保留数据')")
    destination = backup_database(source, tmp_path / "backups", datetime(2026, 8, 23, tzinfo=UTC))
    assert destination.name == "investment-20260823T000000Z.db"
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone()[0] == "保留数据"
    assert destination.with_suffix(".db.sha256").exists()
    assert verify_backup(destination)["integrity"] == "ok"
    assert verify_backup(destination)["table_count"] == 1


def test_backup_database_rejects_missing_source(tmp_path):
    try:
        backup_database(tmp_path / "missing.db", tmp_path / "backups")
    except FileNotFoundError as exc:
        assert "数据库不存在" in str(exc)
    else:
        raise AssertionError("缺失数据库应报错")


def test_verify_backup_rejects_non_database_file(tmp_path):
    invalid = tmp_path / "invalid.db"
    invalid.write_text("不是数据库", encoding="utf-8")
    try:
        verify_backup(invalid)
    except ValueError as exc:
        assert "有效的 SQLite" in str(exc)
    else:
        raise AssertionError("损坏备份应被拒绝")
