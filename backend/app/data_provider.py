from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from .sample_data import generate_sample_data


class DataProvider(ABC):
    @abstractmethod
    def frame(self) -> pd.DataFrame:
        raise NotImplementedError

    def sectors(self) -> list[str]:
        sectors = sorted(set(self.frame()["sector"]))
        return [sector for sector in sectors if sector != "沪深300"]

    def latest_date(self) -> str:
        return str(self.frame()["date"].max())

    def audit(self) -> list[dict[str, object]]:
        frame = self.frame()
        result: list[dict[str, object]] = []
        for sector, group in frame.groupby("sector", sort=True):
            result.append(
                {
                    "sector": str(sector),
                    "index_start_date": str(group["date"].min()),
                    "fund_start_date": str(group.get("fund_start_date", group["date"]).dropna().min()),
                    "valuation_start_date": str(group.loc[group["valuation_percentile"].notna(), "date"].min()),
                    "valuation_metric": "sample",
                    "usable_from": str(group["date"].min()),
                    "missing_price_ratio": round(float(group["index_price"].isna().mean()), 4),
                    "missing_nav_ratio": round(float(group["fund_nav"].isna().mean()), 4),
                    "missing_valuation_ratio": round(float(group["valuation_percentile"].isna().mean()), 4),
                    "audit_status": "pass",
                }
            )
        return result


class SampleDataProvider(DataProvider):
    def frame(self) -> pd.DataFrame:
        return generate_sample_data().copy()


class AkshareDataProvider(DataProvider):
    def frame(self) -> pd.DataFrame:
        raise NotImplementedError("akshare provider is reserved for a future version")


class CsvDataProvider(DataProvider):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._frame: pd.DataFrame | None = None

    def frame(self) -> pd.DataFrame:
        if self._frame is None:
            self._frame = pd.read_csv(self.path, encoding="utf-8")
            self._frame["date"] = self._frame["date"].astype(str)
            self._frame = self._frame.sort_values(["sector", "date"]).reset_index(drop=True)
        return self._frame.copy()

    def audit(self) -> list[dict[str, object]]:
        frame = self.frame()
        result: list[dict[str, object]] = []
        required = ["index_price", "fund_nav", "valuation_percentile"]
        for sector, group in frame.groupby("sector", sort=True):
            index_start = str(group["date"].min())
            fund_start = str(group.get("fund_start_date", group["date"]).dropna().min())
            valuation_start = str(group.loc[group["valuation_percentile"].notna(), "date"].min())
            usable_from = max(index_start, fund_start, valuation_start)
            missing_price = float(group["index_price"].isna().mean()) if "index_price" in group else 1.0
            missing_nav = float(group["fund_nav"].isna().mean()) if "fund_nav" in group else 1.0
            missing_valuation = (
                float(group["valuation_percentile"].isna().mean()) if "valuation_percentile" in group else 1.0
            )
            has_required = all(column in group.columns for column in required)
            audit_status = "pass" if has_required and max(missing_price, missing_nav, missing_valuation) <= 0.05 else "fail"
            result.append(
                {
                    "sector": str(sector),
                    "index_start_date": index_start,
                    "fund_start_date": fund_start,
                    "valuation_start_date": valuation_start,
                    "valuation_metric": str(group.get("valuation_metric", pd.Series(["unknown"])).dropna().iloc[0]),
                    "usable_from": usable_from,
                    "missing_price_ratio": round(missing_price, 4),
                    "missing_nav_ratio": round(missing_nav, 4),
                    "missing_valuation_ratio": round(missing_valuation, 4),
                    "audit_status": audit_status,
                }
            )
        return result


def get_provider(source: str, config: dict | None = None) -> DataProvider:
    if source == "sample":
        return SampleDataProvider()
    if source == "akshare":
        return AkshareDataProvider()
    if source == "csv":
        if not config or not config.get("data_path"):
            raise ValueError("CSV data_source requires config.data_path")
        return CsvDataProvider(config["data_path"])
    raise ValueError(f"Unsupported data source: {source}")
