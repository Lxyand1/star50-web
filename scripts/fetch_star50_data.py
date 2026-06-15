import argparse
import ast
import json
import math
import time
from datetime import date, datetime, timedelta
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



SECTOR_RULES = [
    ("半导体", ["半导体", "芯片", "集成电路", "处理器", "晶圆", "封装", "刻蚀", "薄膜", "光刻", "存储", "射频"]),
    ("软件与信息服务", ["软件", "WPS", "办公", "云服务", "信息安全", "操作系统", "数据库", "人工智能", "算法"]),
    ("高端装备", ["设备", "装备", "机器人", "自动化", "机床", "激光", "测量", "检测"]),
    ("生物医药", ["医药", "医疗", "诊断", "试剂", "疫苗", "抗体", "药品", "制药", "手术"]),
    ("新能源与新材料", ["新能源", "电池", "锂", "光伏", "储能", "材料", "合金", "稀土", "碳纤维"]),
    ("轨交与基础设施", ["铁路", "轨道", "城市轨道", "交通", "信号", "工程总承包"]),
    ("航空航天与军工电子", ["航空", "航天", "卫星", "雷达", "军工", "电子元器件"]),
]


def infer_industry_track(industry, business):
    source = "；".join([str(x) for x in [industry, business] if x])
    if not source:
        return None
    sectors = []
    tracks = []
    for sector, keywords in SECTOR_RULES:
        matched = [kw for kw in keywords if kw in source]
        if matched:
            sectors.append(sector)
            tracks.extend(matched[:3])
    if not sectors and industry:
        sectors.append(str(industry))
    if not sectors:
        sectors.append("科创板成长行业")
    seen_tracks = []
    for item in tracks:
        if item not in seen_tracks:
            seen_tracks.append(item)
    if seen_tracks:
        return f"{sectors[0]} | 细分赛道：{'、'.join(seen_tracks[:5])}"
    return f"{sectors[0]} | 细分赛道：待补充"

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
    inferred_track = infer_industry_track(data.get("所属行业与细分赛道"), data.get("主营业务构成"))
    if inferred_track:
        data["所属行业与细分赛道"] = inferred_track
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



def get_recent_news(code, name, limit=10):
    fallback = [{
        "标题": f"搜索{name}相关新闻",
        "链接": f"https://so.eastmoney.com/news/s?keyword={code}",
        "时间": None,
        "来源": "东方财富搜索",
        "摘要": None,
    }]
    try:
        df = retry_call(lambda: ak.stock_news_em(symbol=code), tries=3, sleep_seconds=1.5)
    except Exception:
        return fallback
    if df is None or df.empty:
        return fallback
    if "发布时间" in df.columns:
        df = df.sort_values("发布时间", ascending=False)
    news = []
    for _, row in df.head(limit).iterrows():
        title = clean_value(row.get("新闻标题"))
        url = clean_value(row.get("新闻链接"))
        if not title or not url:
            continue
        news.append({
            "标题": title,
            "链接": url,
            "时间": clean_value(row.get("发布时间")),
            "来源": clean_value(row.get("文章来源")),
            "摘要": clean_value(row.get("新闻内容")),
        })
    return news or fallback

def get_market_history(code, days_back=260, limit=120):
    end = date.today()
    start = end - timedelta(days=days_back)
    df = ak.stock_zh_a_daily(
        symbol=f"sh{code}",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="",
    )
    if df is None or df.empty:
        return []
    work = df.sort_values("date")
    if limit:
        work = work.tail(limit)
    rows = []
    for _, row in work.iterrows():
        rows.append({label: clean_value(row[col]) if col in row.index else None for label, col in MARKET_FIELDS.items()})
    return rows


def aggregate_market_history(rows, period="W", limit=120):
    if not rows:
        return []
    groups = []
    current_key = None
    current = []
    for row in rows:
        raw_date = row.get("日期")
        try:
            dt = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except Exception:
            continue
        if period == "M":
            key = (dt.year, dt.month)
        else:
            iso = dt.isocalendar()
            key = (iso.year, iso.week)
        if current_key is None:
            current_key = key
        if key != current_key:
            groups.append(current)
            current = []
            current_key = key
        current.append(row)
    if current:
        groups.append(current)

    result = []
    for group in groups[-limit:]:
        first, last = group[0], group[-1]
        highs = [market_number(row, "最高价") for row in group]
        lows = [market_number(row, "最低价") for row in group]
        volumes = [market_number(row, "成交量") or 0 for row in group]
        amounts = [market_number(row, "成交额") or 0 for row in group]
        turnovers = [market_number(row, "换手率") or 0 for row in group]
        result.append({
            "日期": last.get("日期"),
            "开盘价": first.get("开盘价"),
            "最高价": max([value for value in highs if value is not None], default=None),
            "最低价": min([value for value in lows if value is not None], default=None),
            "收盘价": last.get("收盘价"),
            "成交量": sum(volumes),
            "成交额": sum(amounts),
            "流动股本": last.get("流动股本"),
            "换手率": sum(turnovers),
        })
    return result


def get_period_market_histories(code):
    long_history = get_market_history(code, days_back=4300, limit=None)
    return {
        "market_weekly_history": aggregate_market_history(long_history, "W", 120),
        "market_monthly_history": aggregate_market_history(long_history, "M", 120),
    }


def get_market(code, days_back=14):
    history = get_market_history(code, days_back=days_back, limit=1)
    if not history:
        return {k: None for k in MARKET_FIELDS}
    return history[-1]


def market_number(row, key):
    try:
        value = row.get(key) if row else None
        if value is None or value == "":
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except Exception:
        return None


def market_ma(history, period):
    if not history or len(history) < period:
        return None
    values = [market_number(row, "收盘价") for row in history[-period:]]
    if any(value is None for value in values):
        return None
    return sum(values) / period


def build_market_indicators(history):
    rows = [row for row in (history or []) if row]
    latest = rows[-1] if rows else {}
    prev = rows[-2] if len(rows) >= 2 else {}
    first = rows[0] if rows else {}

    close = market_number(latest, "收盘价")
    open_price = market_number(latest, "开盘价")
    high = market_number(latest, "最高价")
    low = market_number(latest, "最低价")
    prev_close = market_number(prev, "收盘价")
    first_close = market_number(first, "收盘价")
    volumes = [market_number(row, "成交量") or 0 for row in rows]
    highs = [market_number(row, "最高价") for row in rows]
    lows = [market_number(row, "最低价") for row in rows]
    highs = [value for value in highs if value is not None]
    lows = [value for value in lows if value is not None]
    period_high = max(highs) if highs else None
    period_low = min(lows) if lows else None
    avg_volume = sum(volumes) / len(volumes) if volumes else None
    latest_volume = market_number(latest, "成交量")

    change = close - prev_close if close is not None and prev_close else None
    change_pct = change / prev_close if change is not None and prev_close else None
    open_close_pct = (close - open_price) / open_price if close is not None and open_price else None
    period_change_pct = (close - first_close) / first_close if close is not None and first_close else None
    amplitude = (period_high - period_low) / period_low if period_high is not None and period_low else None
    volume_ratio = latest_volume / avg_volume if latest_volume is not None and avg_volume else None
    position_ratio = (close - period_low) / (period_high - period_low) if close is not None and period_high is not None and period_low is not None and period_high > period_low else None

    if position_ratio is None:
        position_label = "未知"
    elif position_ratio >= 0.68:
        position_label = "区间偏高位"
    elif position_ratio <= 0.32:
        position_label = "区间偏低位"
    else:
        position_label = "区间中部"

    return {
        "latest_date": latest.get("日期"),
        "previous_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "open_close_pct": open_close_pct,
        "period_days": len(rows),
        "period_start": first.get("日期"),
        "period_end": latest.get("日期"),
        "period_high": period_high,
        "period_low": period_low,
        "period_change_pct": period_change_pct,
        "period_amplitude": amplitude,
        "position_ratio": position_ratio,
        "position_label": position_label,
        "avg_volume": avg_volume,
        "volume_ratio": volume_ratio,
        "ma5": market_ma(rows, 5),
        "ma10": market_ma(rows, 10),
        "ma20": market_ma(rows, 20),
        "ma60": market_ma(rows, 60),
    }



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


POSITIVE_NEWS_KEYWORDS = [
    "增长", "大涨", "上涨", "突破", "创新高", "中标", "签约", "订单", "增持", "回购", "盈利", "净利", "业绩预增", "资金流入", "主力资金", "融资净买入", "机构调研", "国产替代", "量产", "扩产", "涨停", "全额认购", "获批",
]
NEGATIVE_NEWS_KEYWORDS = [
    "下跌", "大跌", "减持", "亏损", "预亏", "业绩下滑", "问询", "处罚", "诉讼", "风险", "解禁", "资金流出", "融资净卖出", "跌停", "终止", "撤回", "延期", "警示", "转让", "折价",
]
EVENT_RULES = [
    ("订单/中标", ["中标", "签约", "订单", "合同"], "订单或合同类消息通常代表需求端有新增验证，短期容易改善市场对收入兑现的预期。"),
    ("业绩/盈利", ["业绩", "净利", "盈利", "预增", "增长", "亏损", "预亏"], "业绩类消息直接影响市场对盈利增速和估值消化能力的判断，是短期情绪的重要来源。"),
    ("资金/机构", ["主力资金", "资金流入", "资金流出", "融资", "机构调研", "认购", "增持", "回购"], "资金和机构行为会影响短线交易热度，连续正向信号通常更容易带来关注度提升。"),
    ("股东/股份变动", ["减持", "转让", "询价转让", "解禁", "股东"], "股东或股份变动可能带来供给压力，也可能因机构承接而缓和冲击，需要看定价、规模和受让方结构。"),
    ("产业/产品", ["突破", "量产", "扩产", "国产替代", "芯片", "产品", "研发", "获批"], "产品和产业进展会影响中短期成长叙事，若与主营业务高度相关，市场关注度通常更高。"),
    ("监管/风险", ["问询", "处罚", "诉讼", "警示", "风险", "终止", "撤回", "延期"], "监管或风险事件会压制短期风险偏好，需要重点跟踪后续公告是否消除不确定性。"),
]


def classify_news_event(text):
    for event, keywords, implication in EVENT_RULES:
        hits = [kw for kw in keywords if kw in text]
        if hits:
            return event, hits[:4], implication
    return "一般新闻", [], "该消息更多体现公司日常动态，短期方向性需要结合成交量、市场风格和后续公告确认。"


def compact_summary(summary, limit=88):
    summary = " ".join(str(summary or "").split())
    if not summary:
        return "新闻摘要为空，主要依据标题判断。"
    return summary if len(summary) <= limit else summary[:limit] + "..."


def build_short_term_reference(item):
    news_items = item.get("news") or []
    score = 0
    reasons = []
    risks = []
    analyzed = 0
    positive_count = 0
    negative_count = 0
    neutral_count = 0
    event_counts = {}

    for idx, news in enumerate(news_items[:6], start=1):
        title = str(news.get("标题") or "")
        summary = str(news.get("摘要") or "")
        source = str(news.get("来源") or "未知来源")
        time = str(news.get("时间") or "时间未知")
        text = title + " " + summary
        if not title:
            continue
        analyzed += 1
        positive_hits = [kw for kw in POSITIVE_NEWS_KEYWORDS if kw in text]
        negative_hits = [kw for kw in NEGATIVE_NEWS_KEYWORDS if kw in text]
        event_type, event_hits, implication = classify_news_event(text)
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

        if positive_hits and not negative_hits:
            score += 1
            positive_count += 1
            sentiment = "偏正面"
            signal = f"出现 {'、'.join(positive_hits[:3])} 等正面关键词，短线情绪有支撑。"
        elif negative_hits and not positive_hits:
            score -= 1
            negative_count += 1
            sentiment = "偏谨慎"
            signal = f"出现 {'、'.join(negative_hits[:3])} 等压力关键词，短线需要防范情绪回落。"
        elif positive_hits and negative_hits:
            neutral_count += 1
            sentiment = "多空交织"
            signal = f"同时出现正面关键词（{'、'.join(positive_hits[:2])}）和压力关键词（{'、'.join(negative_hits[:2])}），需要观察市场如何定价。"
        else:
            neutral_count += 1
            sentiment = "中性"
            signal = "标题和摘要未出现明显多空关键词，暂按中性信息处理。"

        reasons.append(
            f"新闻{idx}｜{event_type}｜{sentiment}：{title}。来源：{source}，时间：{time}。摘要要点：{compact_summary(summary)}；事件解读：{implication}；短期影响：{signal}"
        )
        if negative_hits:
            risks.append(f"{title}：关注 {'、'.join(negative_hits[:3])} 对短期风险偏好的影响。")

    if analyzed == 0:
        return {
            "标题": "新闻数据不足，短期走势参考暂以观察为主",
            "方向": "中性",
            "置信度": "低",
            "评分": 0,
            "摘要": "最近相关新闻不足，暂不形成明确短期方向判断。",
            "主要理由": ["未获取到足够的相关新闻标题和摘要。"],
            "风险提示": ["短期走势受市场情绪、资金流向和突发事件影响较大。"],
            "生成方法": "基于最近相关新闻标题与摘要的关键词情绪分析。",
        }

    dominant_events = sorted(event_counts.items(), key=lambda x: x[1], reverse=True)
    event_text = "、".join([f"{name}{count}条" for name, count in dominant_events[:3]])
    reasons.insert(0, f"总体新闻结构：共分析最近 {analyzed} 条相关新闻，其中偏正面 {positive_count} 条、偏谨慎 {negative_count} 条、中性/多空交织 {neutral_count} 条；主要事件类型集中在 {event_text or '一般新闻'}。")
    reasons.insert(1, f"综合判断逻辑：短期走势主要看新闻是否能提升市场关注度、改善盈利预期、带来资金承接，或是否存在减持、解禁、监管、业绩下滑等压力信号；当前新闻评分为 {score}。")

    if score >= 2:
        direction = "偏积极"
        title = "新闻面偏暖，短期走势参考偏积极"
        confidence = "中等"
    elif score == 1:
        direction = "中性偏积极"
        title = "新闻面略偏正面，短期走势参考中性偏积极"
        confidence = "中低"
    elif score == 0:
        direction = "中性"
        title = "新闻面信号中性，短期走势参考以观察为主"
        confidence = "中低"
    elif score == -1:
        direction = "中性偏谨慎"
        title = "新闻面略有压力，短期走势参考中性偏谨慎"
        confidence = "中低"
    else:
        direction = "偏谨慎"
        title = "新闻面压力较多，短期走势参考偏谨慎"
        confidence = "中等"

    if not risks:
        risks.append("新闻情绪不等于股价方向，仍需结合市场风格、成交量和公告变化。")
    risks.append("如果多条新闻来自同一事件的重复报道，短期评分可能放大该事件影响，需要结合原始公告核对。")

    return {
        "标题": title,
        "方向": direction,
        "置信度": confidence,
        "评分": score,
        "摘要": f"基于最近 {analyzed} 条相关新闻的标题和摘要，新闻情绪给出“{direction}”短期参考结论。该结论不构成投资建议。",
        "主要理由": reasons[:10],
        "风险提示": risks[:7],
        "生成方法": "基于最近相关新闻标题与摘要的事件分类和关键词情绪分析，识别订单、业绩、资金、股东变动、产业进展、监管风险等短期事件信号。",
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
            period_histories = get_period_market_histories(code)
            item["market_history"] = get_market_history(code)
            item["market_weekly_history"] = period_histories["market_weekly_history"]
            item["market_monthly_history"] = period_histories["market_monthly_history"]
            item["market"] = item["market_history"][-1] if item["market_history"] else {k: None for k in MARKET_FIELDS}
            item["market_indicators"] = build_market_indicators(item["market_history"])
        except Exception as exc:
            errors.append({"code": code, "stage": "market", "error": str(exc)})
            item["market"] = {k: None for k in MARKET_FIELDS}
            item["market_history"] = []
            item["market_weekly_history"] = []
            item["market_monthly_history"] = []
            item["market_indicators"] = build_market_indicators([])
        time.sleep(sleep_seconds)
        try:
            item["news"] = get_recent_news(code, item.get("company", {}).get("公司名称") or name)
        except Exception as exc:
            errors.append({"code": code, "stage": "news", "error": str(exc)})
            item["news"] = [{
                "标题": f"搜索{name}相关新闻",
                "链接": f"https://so.eastmoney.com/news/s?keyword={code}",
                "时间": None,
                "来源": "东方财富搜索",
                "摘要": None,
            }]
        item["trend"] = build_trend_reference(item)
        item["short_term"] = build_short_term_reference(item)
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
