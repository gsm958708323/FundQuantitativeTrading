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
    valuation_metric: str = "PRICE_PERCENTILE"


REAL_UNIVERSE = [
    RealInstrument("沪深300", "sh000300", "000051", "华夏沪深300ETF联接A"),
    RealInstrument("科技", "sz399006", "110026", "易方达创业板ETF联接A"),
    RealInstrument("半导体", "sz399995", "008887", "华夏国证半导体芯片ETF联接A"),
    RealInstrument("消费", "sh000932", "000248", "汇添富中证主要消费ETF联接A"),
    RealInstrument("医药", "sh000933", "007076", "汇添富中证医药ETF联接A"),
    RealInstrument("新能源", "sz399417", "009067", "国泰中证新能源汽车ETF联接A"),
]


def build_sector_frame(
    *,
    sector: str,
    index_frame: pd.DataFrame,
    nav_frame: pd.DataFrame,
    fund_start_date: str,
    valuation_metric: str,
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
    merged["valuation_percentile"] = rolling_percentile(merged["index_price"])
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


def rolling_percentile(values: pd.Series, window: int = 252 * 5) -> pd.Series:
    numeric = values.astype(float)
    actual_window = min(window, len(numeric))
    min_periods = min(20, actual_window)

    def percentile(window_values: pd.Series) -> float:
        current = window_values.iloc[-1]
        return round((window_values <= current).mean() * 100, 2)

    return numeric.rolling(window=actual_window, min_periods=min_periods).apply(percentile).fillna(50.0)


def fetch_real_market_frame(
    *,
    start_date: str = "2020-01-01",
    universe: list[RealInstrument] | None = None,
    index_fetcher: Callable[[str], pd.DataFrame] | None = None,
    nav_fetcher: Callable[[str], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    if index_fetcher is None or nav_fetcher is None:
        import akshare as ak

        index_fetcher = index_fetcher or ak.stock_zh_index_daily
        nav_fetcher = nav_fetcher or (lambda code: ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势", period="成立来"))

    frames: list[pd.DataFrame] = []
    for item in universe or REAL_UNIVERSE:
        index_frame = index_fetcher(item.index_symbol)
        nav_frame = nav_fetcher(item.fund_code)
        fund_start_date = pd.to_datetime(nav_frame["净值日期"]).dt.date.astype(str).min()
        frames.append(
            build_sector_frame(
                sector=item.sector,
                index_frame=index_frame,
                nav_frame=nav_frame,
                fund_start_date=fund_start_date,
                valuation_metric=item.valuation_metric,
                start_date=start_date,
            )
        )
    return pd.concat(frames, ignore_index=True).sort_values(["date", "sector"]).reset_index(drop=True)


def write_real_market_csv(path: str | Path, frame: pd.DataFrame) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False, encoding="utf-8")
