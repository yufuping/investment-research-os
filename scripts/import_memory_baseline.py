import argparse
import json
from pathlib import Path

from investment_os.knowledge.database import create_knowledge_repository
from investment_os.knowledge.importer import import_company_baseline


def main() -> None:
    parser = argparse.ArgumentParser(description="导入经过人工复核的公司投资记忆基线")
    parser.add_argument("path", type=Path, help="基线 JSON 文件")
    args = parser.parse_args()
    payload = json.loads(args.path.read_text(encoding="utf-8"))
    result = import_company_baseline(create_knowledge_repository(), payload)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
