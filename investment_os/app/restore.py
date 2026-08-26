import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3

from investment_os.app.backup import backup_database, verify_backup
from investment_os.app.config import get_settings


def restore_database(backup: Path, destination: Path, safety_dir: Path, now: datetime | None = None) -> Path | None:
    verify_backup(backup)
    current_time = now or datetime.now(UTC)
    safety_path = backup_database(destination, safety_dir, current_time) if destination.exists() else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.restore-{current_time.strftime('%Y%m%dT%H%M%SZ')}.tmp"
    try:
        with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as source, sqlite3.connect(temporary) as target:
            source.backup(target)
        verify_backup(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return safety_path


def main() -> None:
    parser = argparse.ArgumentParser(description="从已验证备份恢复 Investment Research OS 数据库")
    parser.add_argument("backup", type=Path, help="要恢复的 .db 备份文件")
    parser.add_argument("--confirm", required=True, help="必须输入 RESTORE 才会执行")
    args = parser.parse_args()
    if args.confirm != "RESTORE":
        raise SystemExit("未执行恢复：--confirm 必须准确输入 RESTORE。")
    settings = get_settings()
    backup = settings.absolute_path(args.backup)
    destination = settings.absolute_path(settings.database_path)
    safety_dir = settings.absolute_path(Path("backups/before-restore"))
    try:
        safety_path = restore_database(backup, destination, safety_dir)
    except (FileNotFoundError, ValueError, sqlite3.DatabaseError) as exc:
        raise SystemExit(f"恢复失败，当前数据库未主动删除：{exc}")
    if safety_path:
        print(f"恢复前的当前数据库已备份：{safety_path}")
    print(f"数据库恢复完成：{destination}")
    print("请重新生成组合综合复核，确认持仓与研究记录符合预期。")


if __name__ == "__main__":
    main()
