import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fetch_star50_data import build_short_term_reference, get_recent_news


def update_news(data, limit=None, sleep_seconds=1.0):
    stocks = data.get("stocks", [])
    target_stocks = stocks[:limit] if limit else stocks
    errors = []

    for index, item in enumerate(target_stocks, start=1):
        code = str(item.get("code", "")).zfill(6)
        name = item.get("company", {}).get("公司名称") or item.get("name") or code
        print(f"[{index}/{len(target_stocks)}] updating news {code} {name}", flush=True)
        try:
            item["news"] = get_recent_news(code, name)
            item["short_term"] = build_short_term_reference(item)
        except Exception as exc:
            errors.append({"code": code, "stage": "news", "error": str(exc)})
            item["news"] = item.get("news") or [{
                "标题": f"搜索{name}相关新闻",
                "链接": f"https://so.eastmoney.com/news/s?keyword={code}",
                "时间": None,
                "来源": "东方财富搜索",
                "摘要": None,
            }]
        time.sleep(sleep_seconds)

    data["news_updated_at"] = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S%z")
    if errors:
        data.setdefault("errors", []).extend(errors)
    return data, errors


def main():
    parser = argparse.ArgumentParser(description="Update STAR50 recent news only.")
    parser.add_argument("--input", default="../data/star50_data.json", help="input JSON path")
    parser.add_argument("--output", default=None, help="output JSON path; defaults to input path")
    parser.add_argument("--limit", type=int, default=None, help="limit stock count for testing")
    parser.add_argument("--sleep", type=float, default=1.0, help="sleep seconds between stocks")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.is_absolute():
        in_path = SCRIPT_DIR / in_path
    in_path = in_path.resolve()

    out_path = Path(args.output) if args.output else in_path
    if not out_path.is_absolute():
        out_path = SCRIPT_DIR / out_path
    out_path = out_path.resolve()

    data = json.loads(in_path.read_text(encoding="utf-8"))
    data, errors = update_news(data, limit=args.limit, sleep_seconds=args.sleep)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out_path}")
    if errors:
        print(f"warnings/errors: {len(errors)}")


if __name__ == "__main__":
    main()
