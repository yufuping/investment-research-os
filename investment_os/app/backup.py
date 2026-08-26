import argparse
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3

from investment_os.app.config import get_settings


def backup_database(source: Path, output_dir: Path, now: datetime | None = None) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"数据库不存在：{source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    destination = output_dir / f"investment-{timestamp}.db"
    with sqlite3.connect(source) as source_connection, sqlite3.connect(destination) as destination_connection:
        source_connection.backup(destination_connection)
    verify_backup(destination)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".db.sha256").write_text(f"{checksum}  {destination.name}\n", encoding="utf-8")
    return destination


def verify_backup(path: Path) -> dict[str, int | str]:
    if not path.exists():
        raise FileNotFoundError(f"备份文件不存在：{path}")
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            table_count = connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"备份不是有效的 SQLite 数据库：{path}") from exc
    if integrity != "ok":
        raise ValueError(f"数据库完整性检查失败：{integrity}")
    return {"integrity": integrity, "table_count": table_count, "size_bytes": path.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description="备份 Investment Research OS 本地数据库")
    parser.add_argument("--output", type=Path, default=Path("backups"), help="备份目录，默认 backups")
    parser.add_argument("--verify", type=Path, help="只校验指定备份文件，不创建新备份")
    args = parser.parse_args()
    settings = get_settings()
    if args.verify:
        try:
            result = verify_backup(settings.absolute_path(args.verify))
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc))
        print(f"备份校验通过：完整性 {result['integrity']}，数据表 {result['table_count']} 个，文件 {result['size_bytes']} 字节")
        return
    source = settings.absolute_path(settings.database_path)
    output = settings.absolute_path(args.output)
    try:
        path = backup_database(source, output)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc))
    print(f"数据库备份已保存：{path}")
    print(f"校验文件已保存：{path.with_suffix('.db.sha256')}")
    result = verify_backup(path)
    print(f"完整性检查：通过（{result['table_count']} 个数据表）")
    print("备份不包含 .env.local 或任何 API Key。")


if __name__ == "__main__":
    main()
