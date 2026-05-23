from __future__ import annotations

import copy
from typing import Any

import pandas as pd

from .metrics import dashboard_curve, simple_dca
from .strategy import StrategyEngine


def run_mvb(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": "mvb",
        "experiments": [
            _valuation_elasticity(frame, config),
            _trend_gate(frame, config),
            _tiered_exit(frame, config),
        ],
    }


def _valuation_elasticity(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    sector = config.get("benchmark", "沪深300")
    budget = float(config["base_amount"])
    baseline = simple_dca(frame, sector, budget, elastic=False)
    strategy = simple_dca(frame, sector, budget, elastic=True, cash_rate=float(config["cash_rate"]))
    cost_delta = baseline["average_cost"] - strategy["average_cost"]
    passed = strategy["summary"]["total_return"] >= baseline["summary"]["total_return"] and cost_delta >= 0
    return {
        "name": "valuation_elasticity",
        "baseline": {**baseline["summary"], "average_cost": baseline["average_cost"]},
        "strategy": {**strategy["summary"], "average_cost": strategy["average_cost"]},
        "passed": passed,
        "reason": f"弹性平均成本差 {round(cost_delta, 4)}，收益差 {round(strategy['summary']['total_return'] - baseline['summary']['total_return'], 2)} 个百分点",
    }


def _trend_gate(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    engine = StrategyEngine(frame, config)
    dates = engine.dates_until()
    horizon = 60
    opened: list[float] = []
    closed: list[float] = []
    for index, date in enumerate(dates[:-horizon]):
        future_date = dates[index + horizon]
        signal_map = {item["sector"]: item for item in engine.compute_signals(date)}
        for sector in config["sectors"]:
            series = engine._series_cache[sector]
            now = float(series.loc[:date].iloc[-1]["index_price"])
            future = float(series.loc[:future_date].iloc[-1]["index_price"])
            future_return = (future - now) / now * 100
            if signal_map[sector]["gate_pass"]:
                opened.append(future_return)
            else:
                closed.append(future_return)
    open_avg = sum(opened) / len(opened) if opened else 0.0
    closed_avg = sum(closed) / len(closed) if closed else 0.0
    open_positive = sum(1 for item in opened if item > 0) / len(opened) * 100 if opened else 0.0
    closed_positive = sum(1 for item in closed if item > 0) / len(closed) * 100 if closed else 0.0
    return {
        "name": "trend_gate",
        "baseline": {"future_60d_avg": round(closed_avg, 2), "positive_ratio": round(closed_positive, 2)},
        "strategy": {"future_60d_avg": round(open_avg, 2), "positive_ratio": round(open_positive, 2)},
        "passed": open_avg > closed_avg or open_positive > closed_positive,
        "reason": f"门控通过未来60日均值 {round(open_avg, 2)}%，关闭均值 {round(closed_avg, 2)}%",
    }


def _tiered_exit(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    full = StrategyEngine(frame, config).run_simulation()
    no_exit_config = copy.deepcopy(config)
    no_exit_config["exit"] = {
        **no_exit_config["exit"],
        "l1_percentile": 101,
        "l1_profit": 999,
        "l2_percentile": 101,
        "l2_drawdown": 999,
        "l3_drawdown": 999,
        "l4_drawdown": 999,
    }
    baseline = StrategyEngine(frame, no_exit_config).run_simulation()
    full_curve = dashboard_curve(full)
    baseline_curve = dashboard_curve(baseline)
    strategy = {**full["portfolio"], "max_drawdown": _curve_drawdown(full_curve)}
    base = {**baseline["portfolio"], "max_drawdown": _curve_drawdown(baseline_curve)}
    return {
        "name": "tiered_exit",
        "baseline": base,
        "strategy": strategy,
        "passed": strategy["max_drawdown"] <= base["max_drawdown"] or strategy["account_return"] >= base["account_return"],
        "reason": f"四级退出回撤 {strategy['max_drawdown']}%，无止盈回撤 {base['max_drawdown']}%",
    }


def _curve_drawdown(curve: list[float]) -> float:
    from .metrics import max_drawdown

    return max_drawdown(curve)
