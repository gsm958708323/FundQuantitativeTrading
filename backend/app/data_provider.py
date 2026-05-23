from __future__ import annotations

from abc import ABC, abstractmethod

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


class SampleDataProvider(DataProvider):
    def frame(self) -> pd.DataFrame:
        return generate_sample_data().copy()


class AkshareDataProvider(DataProvider):
    def frame(self) -> pd.DataFrame:
        raise NotImplementedError("akshare provider is reserved for a future version")


class CsvDataProvider(DataProvider):
    def frame(self) -> pd.DataFrame:
        raise NotImplementedError("CSV provider is reserved for a future version")


def get_provider(source: str) -> DataProvider:
    if source == "sample":
        return SampleDataProvider()
    if source == "akshare":
        return AkshareDataProvider()
    if source == "csv":
        return CsvDataProvider()
    raise ValueError(f"Unsupported data source: {source}")
