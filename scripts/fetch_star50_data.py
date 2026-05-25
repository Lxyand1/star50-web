import argparse
import ast
import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

BALANCE_FIELDS = {
    "货币资金": "货币资金",
    "应收账款": "应收账款",
    "存货": "存货",
    "固定资产": "固定资产净额",
    "商誉": "商誉",
    "短期借款": "短期借款",
    "长期借款": "长期借款",
    "实收资本": "实收资本(或股本)",
    "资本公积": "资本公积",
    "未分配利润": "未分配利润",
    "资产总计": "资产总计",
    "负债合计": "负债合计",
    "所有者权益合计": "所有者权益(或股东权益)合计",
}

INCOME_FIELDS = {
    "营业收入": "营业收入",
    "营业成本": "营业成本",
    "销售费用": "销售费用",
    "管理费用": "管理费用",
    "财务费用": "财务费用",
    "投资收益": "投资收益",
    "营业利润": "营业利润",
    "利润总额": "利润总额",
    "净利润": "净利润",
    "归母净利润": "归属于母公司所有者的净利润",
    "扣非净利润": "扣除非经常性损益后的净利润",
    "基本每股收益": "基本每股收益",
    "稀释每股收益": "稀释每股收益",
}

CASH_FIELDS = {
    "销售商品收到的现金": "销售商品、提供劳务收到的现金",
    "购买商品支付的现金": "购买商品、接受劳务支付的现金",
    "经营现金流净额": "经营活动产生的现金流量净额",
    "投资现金流净额": "投资活动产生的现金流量净额",
    "筹资现金流净额": "筹资活动产生的现金流量净额",
    "期末现金余额": "期末现金及现金等价物余额",
}

MARKET_FIELDS = {
    "日期": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "成交额": "amount",
    "流动股本": "outstanding_share",
    "换手率": "turnover",
}


def clean_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (pd.Timestamp,)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def latest_report_row(df):
    if df is None or df.empty:
        return None, None
    work = df.copy()
    if "报告日" in work.columns:
        work["__report_date"] = pd.to_numeric(work["报告日"], errors="coerce")
        work = work.sort_values("__report_date", ascending=False)
        row = work.iloc[0]
        return str(int(row["__report_date"])), row
    return None, work.iloc[0]


def extract_fields(row, mapping):
    if row is None:
        return {k: None for k in mapping}
    result = {}
    for label, column in mapping.items():
        result[label] = clean_value(row[column]) if column in row.index else None
    return result


def parse_industry(value):
    value = clean_value(value)
    if not value:
        return None
    if isinstance(value, dict):
        return value.get("ind_name") or value.get("name") or str(value)
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, dict):
                return parsed.get("ind_name") or parsed.get("name") or value
        except Exception:
            return value
    return str(value)


def get_company_info(code, fallback_name):
    symbol = f"SH{code}"
    data = {
        "公司名称与代码": f"{fallback_name}（{code}）",
        "公司名称": fallback_name,
        "股票代码": code,
        "主营业务构成": None,
        "所属行业与细分赛道": None,
    }
    df = ak.stock_individual_basic_info_xq(symbol=symbol)
    kv = dict(zip(df["item"], df["value"]))
    name = clean_value(kv.get("org_short_name_cn") or kv.get("org_name_cn") or fallback_name)
    full_name = clean_value(kv.get("org_name_cn") or name)
    industry = parse_industry(kv.get("affiliate_industry"))
    business = clean_value(kv.get("main_operation_business") or kv.get("operating_scope") or kv.get("org_cn_introduction"))
    data.update({
        "公司名称与代码": f"{name}（{code}）",
        "公司名称": name,
        "公司全称": full_name,
        "主营业务构成": business,
        "所属行业与细分赛道": industry,
    })
    return data


def get_financials(code):
    result = {
        "报告期": None,
        "资产负债表": {k: None for k in BALANCE_FIELDS},
        "利润表": {k: None for k in INCOME_FIELDS},
        "现金流量表": {k: None for k in CASH_FIELDS},
    }
    reports = [
        ("资产负债表", BALANCE_FIELDS),
        ("利润表", INCOME_FIELDS),
        ("现金流量表", CASH_FIELDS),
    ]
    report_dates = []
    for report_name, mapping in reports:
        df = ak.stock_financial_report_sina(stock=code, symbol=report_name)
        report_date, row = latest_report_row(df)
        if report_date:
            report_dates.append(report_date)
        result[report_name] = extract_fields(row, mapping)
        time.sleep(0.8)
    if report_dates:
        result["报告期"] = max(report_dates)
    return result


def get_market(code, days_back=14):
    end = date.today()
    start = end - timedelta(days=days_back)
    df = ak.stock_zh_a_daily(
        symbol=f"sh{code}",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="",
    )
    if df is None or df.empty:
        return {k: None for k in MARKET_FIELDS}
    row = df.sort_values("date").iloc[-1]
    return {label: clean_value(row[col]) if col in row.index else None for label, col in MARKET_FIELDS.items()}


def fetch(limit=None, sleep_seconds=1.0):
    cons_df = ak.index_stock_cons_csindex(symbol="000688")
    rows = cons_df[["成分券代码", "成分券名称"]].drop_duplicates().sort_values("成分券代码")
    if limit:
        rows = rows.head(limit)

    stocks = []
    errors = []
    for index, row in rows.iterrows():
        code = str(row["成分券代码"]).zfill(6)
        name = str(row["成分券名称"])
        print(f"[{len(stocks)+1}/{len(rows)}] fetching {code} {name}", flush=True)
        item = {"code": code, "name": name}
        try:
            item["company"] = get_company_info(code, name)
        except Exception as exc:
            errors.append({"code": code, "stage": "company", "error": str(exc)})
            item["company"] = {
                "公司名称与代码": f"{name}（{code}）",
                "公司名称": name,
                "股票代码": code,
                "主营业务构成": None,
                "所属行业与细分赛道": None,
            }
        time.sleep(sleep_seconds)
        try:
            item["financials"] = get_financials(code)
        except Exception as exc:
            errors.append({"code": code, "stage": "financials", "error": str(exc)})
            item["financials"] = {
                "报告期": None,
                "资产负债表": {k: None for k in BALANCE_FIELDS},
                "利润表": {k: None for k in INCOME_FIELDS},
                "现金流量表": {k: None for k in CASH_FIELDS},
            }
        time.sleep(sleep_seconds)
        try:
            item["market"] = get_market(code)
        except Exception as exc:
            errors.append({"code": code, "stage": "market", "error": str(exc)})
            item["market"] = {k: None for k in MARKET_FIELDS}
        stocks.append(item)
        time.sleep(sleep_seconds)

    return {
        "index": "科创50",
        "index_code": "000688",
        "generated_at": pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S%z"),
        "source": "AKShare：中证指数成分股、雪球公司信息、新浪财经财报与行情",
        "stocks": stocks,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch STAR 50 company, financial statement and market data.")
    parser.add_argument("--output", default="../data/star50_data.json", help="output JSON path")
    parser.add_argument("--limit", type=int, default=None, help="limit stock count for testing")
    parser.add_argument("--sleep", type=float, default=1.0, help="sleep seconds between stocks")
    args = parser.parse_args()

    data = fetch(limit=args.limit, sleep_seconds=args.sleep)
    out = Path(args.output)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent / out
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")
    if data["errors"]:
        print(f"warnings/errors: {len(data['errors'])}")


if __name__ == "__main__":
    main()
