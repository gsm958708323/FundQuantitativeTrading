from __future__ import annotations

import math
from typing import Any

import pandas as pd


def pct(value: float) -> float:
    return round(value * 100, 2)


def max_drawdown(values: list[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1)
    return pct(abs(worst))


def account_summary(total_assets: float, total_invested: float, curve: list[float] | None = None) -> dict[str, float]:
    total_return = (total_assets - total_invested) / total_invested if total_invested else 0.0
    drawdown = max_drawdown(curve or [total_assets])
    return {
        "total_assets": round(total_assets, 2),
        "total_invested": round(total_invested, 2),
        "total_return": pct(total_return),
        "max_drawdown": drawdown,
        "calmar": round(pct(total_return) / drawdown, 4) if drawdown else 0.0,
    }


def simple_dca(
    frame: pd.DataFrame,
    sector: str,
    budget: float,
    *,
    elastic: bool = False,
    cash_rate: float = 0.02,
) -> dict[str, Any]:
    data = frame[frame["sector"] == sector].sort_values("date").reset_index(drop=True)
    if data.empty:
        return {"summary": account_summary(0, 0), "average_cost": 0.0, "curve": []}

    first_days = set()
    seen_months = set()
    for date in data["date"]:
        month = str(date)[:7]
        if month not in seen_months:
            seen_months.add(month)
            first_days.add(date)

    shares = 0.0
    invested = 0.0
    reserve = 0.0
    curve: list[float] = []
    for _, row in data.iterrows():
        reserve *= 1 + (pow(1 + cash_rate, 1 / 365) - 1)
        nav = float(row["fund_nav"])
        if row["date"] in first_days:
            multiplier = 1.0
            if elastic:
                percentile = float(row["valuation_percentile"])
                multiplier = 0.0 if percentile >= 80 else max(0.0, 2 * (1 - percentile / 100))
            desired = budget * multiplier
            if desired <= budget:
                reserve += budget - desired
                actual = desired
            else:
                extra = min(reserve, desired - budget)
                reserve -= extra
                actual = budget + extra
            if actual > 0 and nav > 0:
                shares += actual / nav
                invested += actual
        curve.append(shares * nav + reserve)

    final_nav = float(data.iloc[-1]["fund_nav"])
    total_assets = shares * final_nav + reserve
    average_cost = invested / shares if shares else 0.0
    return {
        "summary": account_summary(total_assets, invested, curve),
        "average_cost": round(average_cost, 4),
        "curve": curve,
    }


def dashboard_curve(dashboard: dict[str, Any]) -> list[float]:
    if dashboard.get("account_curve"):
        return [float(point["total_assets"]) for point in dashboard["account_curve"]]
    by_date: dict[str, float] = {}
    for points in dashboard.get("timeline", {}).values():
        for point in points:
            by_date[point["date"]] = by_date.get(point["date"], 0.0) + float(point["market_value"])
    return [by_date[date] for date in sorted(by_date)]
