from app.config import load_config
from app.sample_data import generate_sample_data
import pandas as pd

from app.strategy import (
    ExitManager,
    ExitTracker,
    MomentumScorer,
    Position,
    ReservePool,
    StrategyEngine,
    TrendGate,
    ValuationEngine,
    build_dashboard,
)


def test_hard_stop_multiplier_is_zero():
    config = load_config()
    engine = ValuationEngine(config["valuation"])
    assert engine.multiplier(80) == 0
    assert engine.multiplier(92) == 0
    assert engine.multiplier(50) == 1


def test_momentum_uses_6_1_and_12_1_skip_month_returns():
    values = pd.Series([100.0] * 300)
    values.iloc[-22] = 150.0
    values.iloc[-1] = 300.0
    scorer = MomentumScorer({"mode": "relative_6_1_12_1", "skip_days": 21, "weights": {"126": 0.5, "252": 0.5}})

    assert scorer.score(values) == 50.0


def test_trend_gate_returns_continuous_weight_for_partial_confirmation():
    prices = pd.Series([100.0] * 200)
    gate = TrendGate(ma_short=60, ma_long=120, slope_period=20, min_weight=0.35)

    weight = gate.weight(prices, momentum=5, rs_score=65)

    assert 0 < weight < 1
    assert gate.gate_pass(prices, momentum=5, rs_strong=True)


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


def test_l2_requires_two_consecutive_rs_weak_checks():
    config = load_config()
    manager = ExitManager(config["exit"])
    tracker = ExitTracker(level=1, r_peak=0.2)
    state = {
        "r_campaign": 0.2,
        "r_position": 0.2,
        "percentile": 70,
        "rs_strong": False,
        "ma_state": "上升",
        "momentum": 5,
        "gate_pass": True,
        "asi": None,
        "asi_enabled": False,
        "valuation_fell_from_extreme": False,
    }

    first = manager.update(tracker, state)
    second = manager.update(tracker, state)

    assert first["level"] == "L1"
    assert first["action"] == "hold"
    assert second["level"] == "L2"
    assert second["action"] == "sell_1_3"


def test_exit_reduces_to_lower_target_weight_not_fixed_fraction():
    frame = generate_sample_data()
    config = load_config({"exit": {"enabled": True}, "portfolio_limits": {"single_sector": 0.3}})
    engine = StrategyEngine(frame, config)
    positions = {sector: Position() for sector in engine.trade_sectors}
    positions["科技"].buy(10000, 1.0, "2024-01-02")
    trackers = {sector: ExitTracker(level=1, r_peak=0.4) for sector in config["sectors"]}
    reserve = ReservePool(base_amount=2000)
    actions: list[dict] = []
    nav = float(engine._series_cache["科技"].loc[:"2025-06-30"].iloc[-1]["fund_nav"])

    engine._update_exits(
        "2025-06-30",
        {
            "科技": {
                "fund_nav": nav,
                "valuation_percentile": 95,
                "rs_strong": False,
                "ma_state": "上升",
                "momentum_score": 10,
                "gate_pass": True,
                "asi": None,
            }
        },
        positions,
        trackers,
        reserve,
        actions,
    )

    assert actions[-1]["action"] == "target_weight_reduce"
    assert round(positions["科技"].market_value(nav), 2) == round(10000 * nav * 0.3 * 0.67, 2)


def test_account_profit_does_not_double_count_redeemed_cash():
    config = load_config()
    engine = StrategyEngine(generate_sample_data(), config)
    reserve = ReservePool(base_amount=1000)
    positions = {sector: Position() for sector in config["sectors"]}
    positions["科技"].buy(1000, 1.0, "2025-01-01")
    sale = positions["科技"].sell_fraction(1.0, 1.1, "2027-02-01")
    reserve.deposit(sale["net_proceeds"], "2027-02-01", "test sale")

    state = engine._portfolio_state([{"sector": "科技", "fund_nav": 1.1}], positions, reserve)

    assert state["total_assets"] == 1100
    assert state["total_profit"] == 100


def test_buy_actions_record_signal_order_nav_and_settlement_dates():
    config = load_config()
    result = build_dashboard(generate_sample_data(), config)
    buy = next(action for action in result["actions"] if action["action"] == "buy" and action["sector"] != config["benchmark"])

    assert buy["signal_date"] < buy["date"]
    assert buy["order_date"] == buy["date"]
    assert buy["nav_date"] == buy["date"]
    assert buy["shares_confirm_date"] > buy["date"]


def test_fifo_sale_uses_oldest_lots_and_redemption_fees():
    position = Position()
    position.buy(1000, 1.0, "2025-01-01")
    position.buy(1000, 2.0, "2025-03-01")

    sale = position.sell_fraction(0.5, 2.0, "2025-03-15")

    assert round(sale["gross_proceeds"], 2) == 1500
    assert round(sale["redemption_fee"], 2) == 7.5
    assert round(sale["net_proceeds"], 2) == 1492.5
    assert round(position.shares, 4) == 750
    assert [round(lot["shares"], 4) for lot in position.lots] == [250, 500]


def test_l1_exit_state_blocks_new_monthly_buying():
    frame = generate_sample_data()
    config = load_config()
    engine = StrategyEngine(frame, config)
    reserve = ReservePool(base_amount=2000)
    positions = {sector: Position() for sector in config["sectors"]}
    trackers = {sector: ExitTracker(level=1) for sector in config["sectors"]}
    actions: list[dict] = []
    date = engine.dates_until()[150]
    selected = [item for item in engine.compute_signals(date) if item["gate_pass"] and item["multiplier"] > 0][:1]

    engine._invest_month(date, selected, positions, reserve, actions, trackers)

    assert not any(action["action"] == "buy" for action in actions)
    assert round(reserve.tactical, 2) == 2000


def test_monthly_budget_flows_to_core_when_satellites_are_blocked():
    frame = generate_sample_data()
    config = load_config(
        {
            "allocation": {
                "enabled": True,
                "core_sector": "沪深300",
                "core_ratio": 0.6,
                "satellite_ratio": 0.3,
                "reserve_ratio": 0.1,
                "fallback_to_core": True,
            },
            "valuation": {"hard_stop_percentile": -1},
        }
    )

    result = build_dashboard(frame, config)
    buy_actions = [action for action in result["actions"] if action["action"] == "buy"]
    core_buys = [action for action in buy_actions if action["sector"] == "沪深300"]

    assert core_buys
    assert not [action for action in buy_actions if action["sector"] != "沪深300"]
    assert result["portfolio"]["deployment_ratio"] >= 85
    assert result["portfolio"]["cash_management"] == 0


def test_portfolio_single_sector_limit_caps_new_exposure():
    frame = generate_sample_data()
    config = load_config({"portfolio_limits": {"single_sector": 0.2}})
    engine = StrategyEngine(frame, config)
    reserve = ReservePool(base_amount=2000)
    positions = {sector: Position() for sector in config["sectors"]}
    trackers = {sector: ExitTracker() for sector in config["sectors"]}
    actions: list[dict] = []
    date = engine.dates_until()[150]
    selected = [item for item in engine.compute_signals(date) if item["gate_pass"] and item["multiplier"] > 0][:1]

    engine._invest_month(date, selected, positions, reserve, actions, trackers)

    assert actions
    assert actions[0]["amount"] <= 400
    assert round(reserve.tactical, 2) >= 1600


def test_csv_provider_audits_usable_from_and_missing_ratios(tmp_path):
    from app.data_provider import CsvDataProvider

    csv_path = tmp_path / "market.csv"
    pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "sector": "科技",
                "index_price": 1000,
                "fund_nav": 1.0,
                "valuation_percentile": 20,
                "attention_rank_pct": 30,
                "fund_start_date": "2025-01-03",
                "valuation_metric": "PB",
            },
            {
                "date": "2025-01-02",
                "sector": "科技",
                "index_price": 1001,
                "fund_nav": 1.01,
                "valuation_percentile": None,
                "attention_rank_pct": 30,
                "fund_start_date": "2025-01-03",
                "valuation_metric": "PB",
            },
        ]
    ).to_csv(csv_path, index=False, encoding="utf-8")

    provider = CsvDataProvider(csv_path)
    audit = provider.audit()

    assert audit[0]["sector"] == "科技"
    assert audit[0]["usable_from"] == "2025-01-03"
    assert audit[0]["missing_valuation_ratio"] == 0.5
    assert audit[0]["audit_status"] == "fail"


def test_engine_dates_start_after_all_sectors_have_data():
    frame = generate_sample_data()
    frame = frame[~((frame["sector"] == "半导体") & (frame["date"] < "2024-06-03"))]
    config = load_config()

    engine = StrategyEngine(frame, config)

    assert engine.dates_until()[0] >= "2024-06-03"
