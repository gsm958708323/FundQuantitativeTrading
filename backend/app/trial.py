from __future__ import annotations

from typing import Any

import pandas as pd

from .strategy import StrategyEngine


def build_trial_run(frame: pd.DataFrame, config: dict[str, Any], mode: str = "paper") -> dict[str, Any]:
    dashboard = StrategyEngine(frame, config).run_simulation()
    recommendations = []
    for signal in dashboard["signals"]:
        if signal["recommended_action"] == "按倍率买入":
            amount = round(float(config["base_amount"]) * float(signal["multiplier"]), 2)
        else:
            amount = 0.0
        recommendations.append(
            {
                "sector": signal["sector"],
                "action": signal["recommended_action"],
                "suggested_amount": amount,
                "gate_pass": signal["gate_pass"],
                "valuation_percentile": signal["valuation_percentile"],
                "exit_level": signal["exit_level"],
                "reason": signal["exit_reason"] if signal["exit_level"] != "NORMAL" else f"TrendScore {signal['trend_score']}",
            }
        )
    return {
        "stage": "trial_run",
        "mode": mode,
        "weekly_decision_date": dashboard["date"],
        "reserve": dashboard["portfolio"],
        "recommendations": recommendations,
        "manual_execution_checklist": [
            "数据更新时间",
            "信号日/下单日/确认净值日",
            "建议金额与实际下单金额",
            "实际确认净值与份额",
            "申购费/赎回费",
            "到账日与储备池对账",
            "是否发生人工干预及原因",
        ],
        "logs_to_keep": [
            "strategy_signal_log",
            "order_intent_log",
            "manual_execution_log",
            "portfolio_reconcile_log",
            "exception_log",
        ],
    }
