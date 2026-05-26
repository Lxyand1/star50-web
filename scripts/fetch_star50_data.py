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


def retry_call(func, tries=3, sleep_seconds=1.0):
    last_exc = None
    for attempt in range(tries):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt < tries - 1:
                time.sleep(sleep_seconds * (attempt + 1))
    raise last_exc


def summarize_business_segments(code):
    df = retry_call(lambda: ak.stock_zygc_em(symbol=f"SH{code}"), tries=3, sleep_seconds=1.5)
    if df is None or df.empty:
        return None
    latest_date = str(df["报告日期"].max()) if "报告日期" in df.columns else None
    work = df[df["报告日期"].astype(str) == latest_date].copy() if latest_date else df.copy()
    if "分类类型" in work.columns:
        product = work[work["分类类型"].astype(str).str.contains("产品", na=False)]
        if not product.empty:
            work = product
    if "收入比例" in work.columns:
        work = work.sort_values("收入比例", ascending=False)
    parts = []
    for _, row in work.head(5).iterrows():
        name = clean_value(row.get("主营构成"))
        ratio = clean_value(row.get("收入比例"))
        if not name:
            continue
        if isinstance(ratio, (int, float)) and not math.isnan(ratio):
            parts.append(f"{name}（收入占比{ratio:.2%}）")
        else:
            parts.append(str(name))
    if not parts:
        return None
    prefix = f"{latest_date}：" if latest_date else ""
    return prefix + "；".join(parts)


def get_company_info(code, fallback_name):
    symbol = f"SH{code}"
    data = {
        "公司名称与代码": f"{fallback_name}（{code}）",
        "公司名称": fallback_name,
        "股票代码": code,
        "主营业务构成": None,
        "所属行业与细分赛道": None,
    }
    try:
        df = retry_call(lambda: ak.stock_individual_basic_info_xq(symbol=symbol), tries=3, sleep_seconds=1.5)
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
    except Exception:
        pass

    if not data.get("主营业务构成"):
        data["主营业务构成"] = summarize_business_segments(code)
    if not data.get("所属行业与细分赛道") and data.get("主营业务构成"):
        data["所属行业与细分赛道"] = data["主营业务构成"]
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



def as_number(value):
    try:
        if value is None or value == "":
            return None
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    except Exception:
        return None


def format_ratio(value):
    if value is None:
        return "未知"
    return f"{value:.2%}"


def build_trend_reference(item):
    company = item.get("company", {})
    financials = item.get("financials", {})
    balance = financials.get("资产负债表", {}) or {}
    income = financials.get("利润表", {}) or {}
    cashflow = financials.get("现金流量表", {}) or {}

    revenue = as_number(income.get("营业收入"))
    cost = as_number(income.get("营业成本"))
    net_profit = as_number(income.get("归母净利润") or income.get("净利润"))
    operating_profit = as_number(income.get("营业利润"))
    eps = as_number(income.get("基本每股收益"))
    operating_cash = as_number(cashflow.get("经营现金流净额"))
    cash = as_number(balance.get("货币资金"))
    short_debt = as_number(balance.get("短期借款")) or 0
    long_debt = as_number(balance.get("长期借款")) or 0
    assets = as_number(balance.get("资产总计"))
    liabilities = as_number(balance.get("负债合计"))

    score = 0
    reasons = []
    risks = []

    business = company.get("主营业务构成") or "主营业务信息不足"
    industry = company.get("所属行业与细分赛道") or "行业与细分赛道信息不足"
    reasons.append(f"主营业务/赛道：{business}")
    reasons.append(f"行业线索：{industry}")

    if revenue and cost is not None and revenue > 0:
        gross_margin = (revenue - cost) / revenue
        if gross_margin >= 0.35:
            score += 1
            reasons.append(f"毛利率约 {format_ratio(gross_margin)}，盈利空间相对较好。")
        elif gross_margin < 0.15:
            score -= 1
            risks.append(f"毛利率约 {format_ratio(gross_margin)}，盈利弹性偏弱。")
    else:
        risks.append("营业收入或营业成本缺失，无法判断毛利率。")

    if revenue and net_profit is not None and revenue > 0:
        net_margin = net_profit / revenue
        if net_profit > 0:
            score += 1
            reasons.append(f"归母/净利润为正，净利率约 {format_ratio(net_margin)}。")
            if net_margin >= 0.15:
                score += 1
        else:
            score -= 2
            risks.append("归母/净利润为负，半年走势需要偏谨慎。")
    else:
        risks.append("利润数据不足，无法判断净利率。")

    if operating_profit is not None:
        if operating_profit > 0:
            score += 1
            reasons.append("营业利润为正，主营经营结果具备支撑。")
        else:
            score -= 1
            risks.append("营业利润为负，主营经营承压。")

    if operating_cash is not None:
        if operating_cash > 0:
            score += 1
            reasons.append("经营现金流净额为正，利润质量有一定支撑。")
            if net_profit and operating_cash >= net_profit:
                score += 1
                reasons.append("经营现金流覆盖净利润，现金回收质量较好。")
        else:
            score -= 1
            risks.append("经营现金流净额为负，需关注回款和投入压力。")
    else:
        risks.append("经营现金流数据缺失。")

    if assets and liabilities is not None and assets > 0:
        debt_ratio = liabilities / assets
        if debt_ratio <= 0.4:
            score += 1
            reasons.append(f"资产负债率约 {format_ratio(debt_ratio)}，资产结构较稳健。")
        elif debt_ratio >= 0.7:
            score -= 1
            risks.append(f"资产负债率约 {format_ratio(debt_ratio)}，财务杠杆偏高。")
        else:
            reasons.append(f"资产负债率约 {format_ratio(debt_ratio)}，处于中等水平。")

    total_debt = short_debt + long_debt
    if cash is not None and total_debt > 0:
        cover = cash / total_debt
        if cover >= 2:
            score += 1
            reasons.append(f"货币资金约为有息借款的 {cover:.1f} 倍，短期偿债压力较小。")
        elif cover < 1:
            score -= 1
            risks.append("货币资金不足有息借款的 1 倍，需关注偿债压力。")
    elif cash is not None and total_debt == 0:
        score += 1
        reasons.append("未披露明显短长期借款，且账面有货币资金，财务压力较低。")

    if eps is not None:
        if eps > 0:
            reasons.append(f"基本每股收益为 {eps:.2f} 元。")
        else:
            risks.append("基本每股收益不为正。")

    if score >= 5:
        direction = "偏积极"
        title = "基本面支撑较强，半年走势参考偏积极"
        confidence = "中等"
    elif score >= 2:
        direction = "中性偏积极"
        title = "基本面具备支撑，半年走势参考中性偏积极"
        confidence = "中等"
    elif score >= 0:
        direction = "中性"
        title = "基本面信号中性，半年走势参考以观察为主"
        confidence = "中低"
    else:
        direction = "偏谨慎"
        title = "基本面存在压力，半年走势参考偏谨慎"
        confidence = "中低"

    if not risks:
        risks.append("仍需关注行业景气度、估值水平、市场风格和公司后续公告变化。")

    return {
        "标题": title,
        "方向": direction,
        "置信度": confidence,
        "评分": score,
        "依据报告期": financials.get("报告期"),
        "摘要": f"基于公司基本信息和最新三大财务报表，模型给出“{direction}”参考结论。该结论不使用实时行情，不构成投资建议。",
        "主要理由": reasons[:8],
        "风险提示": risks[:6],
        "生成方法": "基于主营业务/行业线索、盈利能力、经营现金流、资产负债率、货币资金与有息借款覆盖情况的规则化AI研判。",
    }

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
        item["trend"] = build_trend_reference(item)
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
