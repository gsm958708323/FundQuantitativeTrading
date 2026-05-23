from __future__ import annotations

import math
from functools import lru_cache

import pandas as pd


SECTOR_PROFILES = {
    "科技": {"amplitude": 0.035, "phase": 0.0, "bias": 0.002, "valuation_shift": 5},
    "半导体": {"amplitude": 0.048, "phase": 0.8, "bias": 0.003, "valuation_shift": 12},
    "消费": {"amplitude": 0.022, "phase": 1.8, "bias": 0.001, "valuation_shift": -8},
    "医药": {"amplitude": 0.026, "phase": 2.6, "bias": -0.001, "valuation_shift": -2},
    "新能源": {"amplitude": 0.044, "phase": 3.2, "bias": 0.0005, "valuation_shift": 4},
}


def _piecewise_trend(t: int, total: int, sector: str) -> float:
    x = t / max(total - 1, 1)
    if sector == "科技":
        if x < 0.22:
            return -0.12 + x * 0.15
        if x < 0.72:
            return -0.09 + (x - 0.22) * 0.88
        return 0.35 - (x - 0.72) * 0.42
    if sector == "半导体":
        if x < 0.55:
            return 0.02 + x * 0.62
        return 0.36 - (x - 0.55) * 0.62
    if sector == "消费":
        return 0.03 + x * 0.24 + math.sin(x * math.pi * 2) * 0.035
    if sector == "医药":
        return 0.08 - x * 0.25 + math.sin(x * math.pi * 4) * 0.03
    if sector == "新能源":
        if x < 0.35:
            return -0.18 + x * 0.36
        if x < 0.68:
            return -0.05 + (x - 0.35) * 0.55
        return 0.13 - (x - 0.68) * 0.18
    return 0.0


def _valuation_curve(t: int, total: int, sector: str) -> float:
    x = t / max(total - 1, 1)
    if sector == "科技":
        value = 18 + x * 72
    elif sector == "半导体":
        value = 58 + math.sin(x * math.pi * 1.2) * 36
    elif sector == "消费":
        value = 35 + x * 38 + math.sin(x * math.pi * 3) * 8
    elif sector == "医药":
        value = 58 - x * 30 + math.sin(x * math.pi * 2) * 6
    elif sector == "新能源":
        value = 22 + math.sin(x * math.pi * 1.6) * 36 + x * 20
    else:
        value = 50
    return max(2.0, min(98.0, value + SECTOR_PROFILES[sector]["valuation_shift"]))


def _attention_curve(t: int, total: int, sector: str) -> float:
    x = t / max(total - 1, 1)
    if sector == "科技":
        value = 20 + x * 78
    elif sector == "半导体":
        value = 45 + math.sin(x * math.pi * 1.4) * 42
    elif sector == "消费":
        value = 35 + x * 28
    elif sector == "医药":
        value = 48 - x * 12
    elif sector == "新能源":
        value = 30 + math.sin(x * math.pi * 1.8) * 38
    else:
        value = 50
    return max(1.0, min(99.0, value))


@lru_cache(maxsize=1)
def generate_sample_data() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", "2025-06-30")
    total = len(dates)
    rows: list[dict[str, object]] = []

    benchmark_values: list[float] = []
    for i, date in enumerate(dates):
        x = i / max(total - 1, 1)
        benchmark = 1000 * (1 + 0.16 * x + math.sin(x * math.pi * 3.4) * 0.035)
        benchmark_values.append(benchmark)
        rows.append(
            {
                "date": date.date().isoformat(),
                "sector": "沪深300",
                "index_price": round(benchmark, 4),
                "fund_nav": round(1.0 * benchmark / 1000, 4),
                "valuation_percentile": round(max(8, min(92, 42 + x * 28)), 2),
                "attention_rank_pct": round(50 + math.sin(x * math.pi * 2) * 8, 2),
                "benchmark_price": round(benchmark, 4),
            }
        )

    for sector, profile in SECTOR_PROFILES.items():
        for i, date in enumerate(dates):
            cycle = math.sin(i / 18 + profile["phase"]) * profile["amplitude"]
            micro = math.sin(i / 5.5 + profile["phase"] * 1.7) * 0.006
            trend = _piecewise_trend(i, total, sector)
            index_price = 1000 * (1 + trend + cycle + micro + profile["bias"] * i / 20)
            fund_nav = 1.0 * index_price / 1000 * (1 - 0.0015 * i / total)
            rows.append(
                {
                    "date": date.date().isoformat(),
                    "sector": sector,
                    "index_price": round(index_price, 4),
                    "fund_nav": round(fund_nav, 4),
                    "valuation_percentile": round(_valuation_curve(i, total, sector), 2),
                    "attention_rank_pct": round(_attention_curve(i, total, sector), 2),
                    "benchmark_price": round(benchmark_values[i], 4),
                }
            )

    return pd.DataFrame(rows)
