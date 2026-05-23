from fastapi.testclient import TestClient

from app.config import load_config
from app.main import app
from app.sample_data import generate_sample_data


client = TestClient(app)


def test_mvb_runner_returns_three_stage_gate_experiments():
    from app.experiments import run_mvb

    result = run_mvb(generate_sample_data(), load_config())

    assert result["stage"] == "mvb"
    assert [item["name"] for item in result["experiments"]] == [
        "valuation_elasticity",
        "trend_gate",
        "tiered_exit",
    ]
    for experiment in result["experiments"]:
        assert isinstance(experiment["passed"], bool)
        assert "baseline" in experiment
        assert "strategy" in experiment
        assert "reason" in experiment


def test_full_backtest_report_contains_baselines_ablation_and_checks():
    from app.backtest import run_full_backtest

    report = run_full_backtest(generate_sample_data(), load_config())

    assert report["stage"] == "full_backtest"
    assert {"智能定投", "无脑等额定投", "沪深300定投", "动量前3等权"} <= set(report["baselines"])
    assert {"no_lookahead", "accounting_identity", "fund_start_filter"} <= set(report["checks"])
    assert {"valuation", "exit"} <= set(report["ablation"])
    assert report["worst_periods"]


def test_trial_run_plan_produces_manual_execution_checklist():
    from app.trial import build_trial_run

    trial = build_trial_run(generate_sample_data(), load_config(), mode="paper")

    assert trial["stage"] == "trial_run"
    assert trial["mode"] == "paper"
    assert trial["weekly_decision_date"]
    assert trial["recommendations"]
    assert "manual_execution_checklist" in trial
    assert "数据更新时间" in trial["manual_execution_checklist"]


def test_validation_stage_api_endpoints():
    for path in ["/api/mvb", "/api/backtest", "/api/trial-run"]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["stage"]
