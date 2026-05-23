from app.config import load_config
from app.sample_data import generate_sample_data
from app.strategy import ExitManager, ExitTracker, ReservePool, ValuationEngine, build_dashboard


def test_hard_stop_multiplier_is_zero():
    config = load_config()
    engine = ValuationEngine(config["valuation"])
    assert engine.multiplier(80) == 0
    assert engine.multiplier(92) == 0
    assert engine.multiplier(50) == 1


def test_reserve_pool_routes_overflow_to_cash_management():
    pool = ReservePool(base_amount=1000, max_months=1, cash_rate=0.02)
    pool.deposit(1500, "2025-01-01", "test")
    assert round(pool.tactical, 2) == 1000
    assert round(pool.cash_management, 2) == 500
    assert pool.withdraw(1200, "2025-01-02", "test") == 1000


def test_dashboard_has_sample_states():
    config = load_config()
    result = build_dashboard(generate_sample_data(), config)
    actions = {item["recommended_action"] for item in result["signals"]}
    assert result["portfolio"]["base_amount"] == 2000
    assert "按倍率买入" in actions or "估值硬停" in actions
    assert len(result["signals"]) == 5


def test_l4_requires_second_confirmation():
    config = load_config()
    manager = ExitManager(config["exit"])
    tracker = ExitTracker(level=3, r_peak=0.5)
    state = {
        "r_campaign": 0.25,
        "r_position": -0.01,
        "percentile": 60,
        "rs_strong": False,
        "ma_state": "下降",
        "momentum": -1,
        "gate_pass": False,
        "asi": None,
        "asi_enabled": False,
        "valuation_fell_from_extreme": False,
    }
    first = manager.update(tracker, state)
    assert first["action"] == "hold"
    assert first["pending_l4"] is True
    second = manager.update(tracker, state)
    assert second["action"] == "sell_all"
    assert second["level"] == "L4"
