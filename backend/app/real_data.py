from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class RealInstrument:
    sector: str
    index_symbol: str
    fund_code: str
    fund_name: str
    valuation_symbol: str
    valuation_metric: str = "PRICE_PERCENTILE"


REAL_UNIVERSE = [
    RealInstrument("沪深300", "sh000300", "000051", "华夏沪深300ETF联接A", "lg_pe:沪深300", "PE"),
    RealInstrument("科技", "sz399006", "110026", "易方达创业板ETF联接A", "399006", "PE"),
    RealInstrument("半导体", "sz399995", "008887", "华夏国证半导体芯片ETF联接A", "399995", "PB"),
    RealInstrument("消费", "sh000932", "000248", "汇添富中证主要消费ETF联接A", "000932", "PE"),
    RealInstrument("医药", "sh000933", "007076", "汇添富中证医药ETF联接A", "000933", "PE"),
    RealInstrument("新能源", "sz399417", "009067", "国泰中证新能源汽车ETF联接A", "399417", "PB"),
]


def build_sector_frame(
    *,
    sector: str,
    index_frame: pd.DataFrame,
    nav_frame: pd.DataFrame,
    fund_start_date: str,
    valuation_metric: str,
    valuation_frame: pd.DataFrame | None = None,
    start_date: str | None = None,
) -> pd.DataFrame:
    index_data = index_frame.rename(columns={"close": "index_price"}).copy()
    index_data["date"] = pd.to_datetime(index_data["date"]).dt.date.astype(str)
    index_data = index_data[["date", "index_price"]]

    nav_data = nav_frame.rename(columns={"净值日期": "date", "单位净值": "fund_nav"}).copy()
    nav_data["date"] = pd.to_datetime(nav_data["date"]).dt.date.astype(str)
    nav_data = nav_data[["date", "fund_nav"]]

    merged = pd.merge(index_data, nav_data, on="date", how="inner").sort_values("date")
    if start_date:
        merged = merged[merged["date"] >= start_date]
    merged["sector"] = sector
    valuation_series = normalize_valuation_series(valuation_frame, valuation_metric)
    if valuation_series is not None:
        merged = pd.merge(merged, valuation_series, on="date", how="left")
        merged["valuation_value"] = merged["valuation_value"].ffill()
        if merged["valuation_value"].notna().mean() >= 0.5:
            merged["valuation_percentile"] = rolling_percentile(merged["valuation_value"])
        else:
            merged["valuation_percentile"] = rolling_percentile(merged["index_price"])
            valuation_metric = "PRICE_PERCENTILE"
    else:
        merged["valuation_percentile"] = rolling_percentile(merged["index_price"])
        valuation_metric = "PRICE_PERCENTILE"
    merged["attention_rank_pct"] = 50.0
    merged["fund_start_date"] = fund_start_date
    merged["valuation_metric"] = valuation_metric
    return merged[
        [
            "date",
            "sector",
            "index_price",
            "fund_nav",
            "valuation_percentile",
            "attention_rank_pct",
            "fund_start_date",
            "valuation_metric",
        ]
    ].reset_index(drop=True)


def normalize_valuation_series(valuation_frame: pd.DataFrame | None, metric: str) -> pd.DataFrame | None:
    if valuation_frame is None or valuation_frame.empty:
        return None
    data = valuation_frame.copy()
    date_column = _find_column(data, ["date", "日期", "交易日期", "时间"])
    value_column = _valuation_column(data, metric)
    if not date_column or not value_column:
        return None
    result = data[[date_column, value_column]].rename(columns={date_column: "date", value_column: "valuation_value"})
    result["date"] = pd.to_datetime(result["date"]).dt.date.astype(str)
    result["valuation_value"] = pd.to_numeric(result["valuation_value"], errors="coerce")
    return result.dropna(subset=["valuation_value"]).sort_values("date")


def _find_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(column).lower().replace(" ", "").replace("_", ""): str(column) for column in frame.columns}
    for candidate in candidates:
        key = candidate.lower().replace(" ", "").replace("_", "")
        if key in normalized:
            return normalized[key]
    return None


def _valuation_column(frame: pd.DataFrame, metric: str) -> str | None:
    metric = metric.upper()
    candidates = {
        "PE": ["pe", "pettm", "pe_ttm", "市盈率", "市盈率1", "市盈率2", "市盈率ttm", "滚动市盈率", "pe1", "pe2"],
        "PB": ["pb", "市净率", "市净率1", "市净率2", "pb_lf"],
        "PS": ["ps", "市销率", "市销率1", "市销率2", "ps_ttm"],
    }.get(metric, [])
    found = _find_column(frame, candidates)
    if found:
        return found
    for column in frame.columns:
        text = str(column).lower().replace(" ", "").replace("_", "")
        if metric.lower() in text and "percent" not in text and "分位" not in text:
            return str(column)
    return None


def rolling_percentile(values: pd.Series, window: int = 252 * 5) -> pd.Series:
    numeric = values.astype(float)
    actual_window = min(window, len(numeric))

    def percentile(window_values: pd.Series) -> float:
        current = window_values.iloc[-1]
        return round((window_values <= current).mean() * 100, 2)

    return numeric.rolling(window=actual_window, min_periods=1).apply(percentile).fillna(50.0)


def fetch_real_market_frame(
    *,
    start_date: str = "2020-01-01",
    universe: list[RealInstrument] | None = None,
    index_fetcher: Callable[[str], pd.DataFrame] | None = None,
    nav_fetcher: Callable[[str], pd.DataFrame] | None = None,
    valuation_fetcher: Callable[[str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if index_fetcher is None or nav_fetcher is None:
        import akshare as ak

        index_fetcher = index_fetcher or ak.stock_zh_index_daily
        nav_fetcher = nav_fetcher or (lambda code: ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势", period="成立来"))
        valuation_fetcher = valuation_fetcher or default_valuation_fetcher

    frames: list[pd.DataFrame] = []
    for item in universe or REAL_UNIVERSE:
        index_frame = index_fetcher(item.index_symbol)
        nav_frame = nav_fetcher(item.fund_code)
        fund_start_date = pd.to_datetime(nav_frame["净值日期"]).dt.date.astype(str).min()
        valuation_frame = None
        if valuation_fetcher:
            try:
                valuation_frame = valuation_fetcher(item.valuation_symbol)
            except Exception:
                valuation_frame = None
        frames.append(
            build_sector_frame(
                sector=item.sector,
                index_frame=index_frame,
                nav_frame=nav_frame,
                fund_start_date=fund_start_date,
                valuation_metric=item.valuation_metric,
                valuation_frame=valuation_frame,
                start_date=start_date,
            )
        )
    return pd.concat(frames, ignore_index=True).sort_values(["date", "sector"]).reset_index(drop=True)


def write_real_market_csv(path: str | Path, frame: pd.DataFrame) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding="utf-8")


def default_valuation_fetcher(symbol: str) -> pd.DataFrame:
    import akshare as ak

    if symbol.startswith("lg_pe:"):
        return ak.stock_index_pe_lg(symbol.split(":", 1)[1])
    if symbol.startswith("lg_pb:"):
        return ak.stock_index_pb_lg(symbol.split(":", 1)[1])
    return ak.stock_zh_index_value_csindex(symbol)
