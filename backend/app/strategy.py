from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


EXIT_LABELS = ["NORMAL", "L1", "L2", "L3", "L4"]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def pct(value: float) -> float:
    return round(value * 100, 2)


def first_business_days(dates: list[str]) -> set[str]:
    result: set[str] = set()
    seen: set[str] = set()
    for date in dates:
        month = date[:7]
        if month not in seen:
            seen.add(month)
            result.add(date)
    return result


def weekly_check_days(dates: list[str]) -> set[str]:
    result: set[str] = set()
    for date in dates:
        if pd.Timestamp(date).weekday() == 0:
            result.add(date)
    if dates:
        result.add(dates[-1])
    return result


def add_business_days(date: str, days: int) -> str:
    return pd.bdate_range(pd.Timestamp(date), periods=days + 1)[-1].date().isoformat()


def redemption_fee_rate(buy_date: str, sell_date: str) -> float:
    holding_days = max(0, (pd.Timestamp(sell_date) - pd.Timestamp(buy_date)).days)
    if holding_days < 7:
        return 0.015
    if holding_days < 30:
        return 0.01
    if holding_days < 180:
        return 0.005
    if holding_days < 730:
        return 0.0025
    return 0.0


class MomentumScorer:
    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = {int(k): float(v) for k, v in (weights or {"20": 0.2, "60": 0.3, "120": 0.5}).items()}

    def score(self, prices: pd.Series) -> float:
        values = prices.dropna().astype(float)
        if len(values) < max(self.weights) + 1:
            return 0.0
        latest = values.iloc[-1]
        score = 0.0
        for days, weight in self.weights.items():
            past = values.iloc[-days - 1]
            if past:
                score += weight * ((latest - past) / past * 100)
        return round(score, 4)


class RSAnalyzer:
    def __init__(self, ma_period: int = 60):
        self.ma_period = ma_period

    def _ratio(self, sector: pd.Series, benchmark: pd.Series) -> pd.Series:
        aligned = pd.concat([sector.astype(float), benchmark.astype(float)], axis=1).dropna()
        if aligned.empty:
            return pd.Series(dtype=float)
        return aligned.iloc[:, 0] / aligned.iloc[:, 1]

    def is_strong(self, sector: pd.Series, benchmark: pd.Series) -> bool:
        ratio = self._ratio(sector, benchmark)
        if len(ratio) < self.ma_period:
            return False
        ma = ratio.rolling(self.ma_period).mean().iloc[-1]
        return bool(ratio.iloc[-1] > ma)

    def score(self, sector: pd.Series, benchmark: pd.Series) -> float:
        ratio = self._ratio(sector, benchmark)
        if len(ratio) < self.ma_period:
            return 50.0
        ma = ratio.rolling(self.ma_period).mean().iloc[-1]
        if ma == 0 or math.isnan(ma):
            return 50.0
        deviation = ratio.iloc[-1] / ma - 1
        return round(clamp(50 + deviation * 900), 2)


class TrendGate:
    def __init__(self, ma_short: int = 60, ma_long: int = 120, slope_period: int = 20):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.slope_period = slope_period

    def state(self, prices: pd.Series) -> str:
        values = prices.dropna().astype(float)
        if len(values) < self.ma_long + self.slope_period:
            return "震荡"
        ma_short = values.rolling(self.ma_short).mean()
        ma_long = values.rolling(self.ma_long).mean()
        price = values.iloc[-1]
        short_now = ma_short.iloc[-1]
        long_now = ma_long.iloc[-1]
        short_past = ma_short.iloc[-self.slope_period]
        slope_positive = short_now > short_past
        if price > short_now > long_now and slope_positive:
            return "上升"
        if price < short_now < long_now:
            return "下降"
        return "震荡"

    def gate_pass(self, prices: pd.Series, momentum: float, rs_strong: bool) -> bool:
        return self.state(prices) == "上升" and momentum > 0 and rs_strong


class ValuationEngine:
    def __init__(self, config: dict[str, Any]):
        self.hard_stop = float(config.get("hard_stop_percentile", 80))
        self.k = float(config.get("k", 1.0))

    def multiplier(self, percentile: float) -> float:
        if percentile >= self.hard_stop:
            return 0.0
        return round(max(0.0, 2 * math.pow(1 - percentile / 100, self.k)), 4)


@dataclass
class ReservePool:
    base_amount: float
    max_months: int = 6
    cash_rate: float = 0.02
    tactical: float = 0.0
    cash_management: float = 0.0
    flows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def cap(self) -> float:
        return self.base_amount * self.max_months

    def accrue(self) -> None:
        daily_rate = math.pow(1 + self.cash_rate, 1 / 365) - 1
        self.tactical *= 1 + daily_rate
        self.cash_management *= 1 + daily_rate

    def deposit(self, amount: float, date: str, reason: str) -> None:
        if amount <= 0:
            return
        room = max(0.0, self.cap - self.tactical)
        to_tactical = min(amount, room)
        overflow = amount - to_tactical
        self.tactical += to_tactical
        self.cash_management += overflow
        self.flows.append(
            {
                "date": date,
                "type": "deposit",
                "amount": round(amount, 2),
                "reason": reason,
                "tactical": round(self.tactical, 2),
                "cash_management": round(self.cash_management, 2),
            }
        )

    def withdraw(self, amount: float, date: str, reason: str) -> float:
        if amount <= 0:
            return 0.0
        actual = min(amount, self.tactical)
        self.tactical -= actual
        if actual:
            self.flows.append(
                {
                    "date": date,
                    "type": "withdraw",
                    "amount": round(actual, 2),
                    "reason": reason,
                    "tactical": round(self.tactical, 2),
                    "cash_management": round(self.cash_management, 2),
                }
            )
        return actual


@dataclass
class Position:
    shares: float = 0.0
    cumulative_invested: float = 0.0
    cost_remaining: float = 0.0
    realized_cash: float = 0.0
    redemption_fees: float = 0.0
    lots: list[dict[str, Any]] = field(default_factory=list)

    def buy(self, amount: float, nav: float, date: str = "", fee_rate: float = 0.0) -> dict[str, float]:
        if amount <= 0 or nav <= 0:
            return {"shares": 0.0, "fee": 0.0, "net_amount": 0.0}
        fee = amount * max(0.0, fee_rate)
        net_amount = max(0.0, amount - fee)
        shares = net_amount / nav
        self.shares += shares
        self.cumulative_invested += amount
        self.cost_remaining += net_amount
        self.lots.append({"date": date, "shares": shares, "cost": net_amount, "nav": nav})
        return {"shares": shares, "fee": fee, "net_amount": net_amount}

    def sell_fraction(self, fraction: float, nav: float, date: str = "") -> dict[str, float]:
        fraction = max(0.0, min(1.0, fraction))
        return self.sell_shares(self.shares * fraction, nav, date)

    def sell_shares(self, shares: float, nav: float, date: str = "") -> dict[str, float]:
        shares_to_sell = min(max(0.0, shares), self.shares)
        remaining = shares_to_sell
        gross_proceeds = 0.0
        redemption_fee = 0.0
        cost_reduced = 0.0
        updated_lots: list[dict[str, Any]] = []

        for lot in self.lots:
            lot_shares = float(lot["shares"])
            if remaining <= 1e-12:
                updated_lots.append(lot)
                continue
            sold = min(lot_shares, remaining)
            kept = lot_shares - sold
            lot_gross = sold * nav
            fee_rate = redemption_fee_rate(str(lot.get("date", date)), date) if date else 0.0
            gross_proceeds += lot_gross
            redemption_fee += lot_gross * fee_rate
            cost_reduced += float(lot["cost"]) * (sold / lot_shares) if lot_shares else 0.0
            remaining -= sold
            if kept > 1e-12:
                kept_ratio = kept / lot_shares
                updated_lots.append({**lot, "shares": kept, "cost": float(lot["cost"]) * kept_ratio})

        net_proceeds = gross_proceeds - redemption_fee
        self.lots = updated_lots
        self.shares -= shares_to_sell
        self.realized_cash += net_proceeds
        self.redemption_fees += redemption_fee
        self.cost_remaining = max(0.0, self.cost_remaining - cost_reduced)
        return {
            "shares": shares_to_sell,
            "gross_proceeds": gross_proceeds,
            "redemption_fee": redemption_fee,
            "net_proceeds": net_proceeds,
        }

    def market_value(self, nav: float) -> float:
        return self.shares * nav

    def r_campaign(self, nav: float) -> float:
        if self.cumulative_invested <= 0:
            return 0.0
        return (self.realized_cash + self.market_value(nav) - self.cumulative_invested) / self.cumulative_invested

    def r_position(self, nav: float) -> float:
        if self.cost_remaining <= 0:
            return 0.0
        return (self.market_value(nav) - self.cost_remaining) / self.cost_remaining


@dataclass
class ExitTracker:
    level: int = 0
    r_peak: float = 0.0
    pending_l4: bool = False
    recovery_count: int = 0
    rs_weak_count: int = 0
    extreme_valuation_seen: bool = False
    reason: str = "正常持有"
    last_action: str = "hold"


class ExitManager:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def update(self, tracker: ExitTracker, state: dict[str, Any]) -> dict[str, Any]:
        r_campaign = float(state["r_campaign"])
        tracker.r_peak = max(tracker.r_peak, r_campaign)
        drawdown = (tracker.r_peak - r_campaign) * 100
        percentile = float(state["percentile"])
        rs_strong = bool(state["rs_strong"])
        ma_state = str(state["ma_state"])
        momentum = float(state["momentum"])
        r_position = float(state["r_position"])
        asi = state.get("asi")
        asi_enabled = bool(state.get("asi_enabled"))
        if percentile >= float(self.config.get("l2_percentile", 90)):
            tracker.extreme_valuation_seen = True
        tracker.rs_weak_count = tracker.rs_weak_count + 1 if not rs_strong else 0

        action = "hold"
        reason = tracker.reason

        if tracker.level in (1, 2):
            recovered = self._recovered(tracker.level, percentile, rs_strong, drawdown, asi, asi_enabled)
            if recovered:
                tracker.recovery_count += 1
            else:
                tracker.recovery_count = 0
            if tracker.recovery_count >= int(self.config.get("recovery_weeks", 2)):
                tracker.level = 0 if tracker.level == 1 else 1
                tracker.pending_l4 = False
                tracker.recovery_count = 0
                tracker.reason = "恢复条件连续成立"
                tracker.last_action = "hold"
                return self._result(tracker, "hold", tracker.reason)

        hard_risk = ma_state == "下降"
        if tracker.level < 2 and hard_risk:
            tracker.level = 2
            tracker.reason = "硬风控：均线进入下降"
            tracker.last_action = "sell_1_3"
            return self._result(tracker, "sell_1_3", tracker.reason)

        if tracker.level == 0 and self._l1(percentile, r_campaign, asi, asi_enabled):
            tracker.level = 1
            action = "stop_invest"
            reason = "L1：高估/注意力饱和/收益保护"
        elif tracker.level == 1 and self._l2(percentile, drawdown, tracker.r_peak, tracker.rs_weak_count):
            tracker.level = 2
            action = "sell_1_3"
            reason = "L2：RS走弱、极端高估或收益回撤"
        elif tracker.level == 2 and self._l3(state, drawdown):
            tracker.level = 3
            action = "sell_1_2_remaining"
            reason = "L3：趋势门控失效或回撤扩大"
        elif tracker.level == 3 and self._l4(ma_state, drawdown, r_position):
            if tracker.pending_l4:
                tracker.level = 4
                action = "sell_all"
                reason = "L4：二次确认后清仓"
            else:
                tracker.pending_l4 = True
                action = "hold"
                reason = "L4待确认"
        elif tracker.level == 3 and tracker.pending_l4:
            tracker.pending_l4 = False
            reason = "L4条件解除"

        tracker.reason = reason
        tracker.last_action = action
        return self._result(tracker, action, reason)

    def _l1(self, percentile: float, r_campaign: float, asi: float | None, asi_enabled: bool) -> bool:
        if percentile >= float(self.config.get("l1_percentile", 80)):
            return True
        if r_campaign * 100 >= float(self.config.get("l1_profit", 50)):
            return True
        return asi_enabled and asi is not None and asi <= 0

    def _l2(self, percentile: float, drawdown: float, r_peak: float, rs_weak_count: int) -> bool:
        if rs_weak_count >= 2:
            return True
        if percentile >= float(self.config.get("l2_percentile", 90)):
            return True
        return drawdown >= float(self.config.get("l2_drawdown", 8)) and r_peak * 100 >= float(
            self.config.get("l2_min_peak", 30)
        )

    def _l3(self, state: dict[str, Any], drawdown: float) -> bool:
        if not bool(state["gate_pass"]):
            return True
        if drawdown >= float(self.config.get("l3_drawdown", 15)):
            return True
        return bool(state.get("valuation_fell_from_extreme")) and float(state["momentum"]) < 0

    def _l4(self, ma_state: str, drawdown: float, r_position: float) -> bool:
        return (
            ma_state == "下降"
            or drawdown >= float(self.config.get("l4_drawdown", 20))
            or r_position < 0
        )

    def _recovered(
        self,
        level: int,
        percentile: float,
        rs_strong: bool,
        drawdown: float,
        asi: float | None,
        asi_enabled: bool,
    ) -> bool:
        lag = float(self.config.get("recovery_lag", 5))
        if level == 1:
            asi_ok = True if not asi_enabled else asi is not None and asi > 10
            return percentile < float(self.config.get("l1_percentile", 80)) - lag and rs_strong and asi_ok
        if level == 2:
            return percentile < float(self.config.get("l2_percentile", 90)) - lag and rs_strong and drawdown < 4
        return False

    def _result(self, tracker: ExitTracker, action: str, reason: str) -> dict[str, Any]:
        return {
            "level": EXIT_LABELS[tracker.level],
            "level_value": tracker.level,
            "action": action,
            "reason": reason,
            "pending_l4": tracker.pending_l4,
            "r_peak": round(tracker.r_peak, 4),
        }


class StrategyEngine:
    def __init__(self, frame: pd.DataFrame, config: dict[str, Any]):
        self.frame = frame.copy()
        self.config = config
        self.sectors = list(config["sectors"])
        self.benchmark = str(config["benchmark"])
        self.scorer = MomentumScorer(config["momentum"]["weights"])
        self.rs = RSAnalyzer(int(config["rs"]["ma_period"]))
        self.gate = TrendGate(
            int(config["gate"]["ma_short"]),
            int(config["gate"]["ma_long"]),
            int(config["gate"]["slope_period"]),
        )
        self.valuation = ValuationEngine(config["valuation"])
        self.exit_manager = ExitManager(config["exit"])
        self._signal_cache: dict[str, list[dict[str, Any]]] = {}
        self._series_cache = {
            sector: self.frame[self.frame["sector"] == sector].set_index("date").sort_index()
            for sector in [self.benchmark, *self.sectors]
        }

    def dates_until(self, end_date: str | None = None) -> list[str]:
        start_dates = [
            str(self._series_cache[sector].index.min())
            for sector in [self.benchmark, *self.sectors]
            if not self._series_cache[sector].empty
        ]
        common_start = max(start_dates) if start_dates else ""
        dates = sorted(date for date in self.frame["date"].unique().tolist() if date >= common_start)
        if end_date:
            dates = [date for date in dates if date <= end_date]
        return dates

    def compute_signals(self, date: str) -> list[dict[str, Any]]:
        if date in self._signal_cache:
            return copy.deepcopy(self._signal_cache[date])

        benchmark_frame = self._series_cache[self.benchmark].loc[:date]
        benchmark_series = benchmark_frame["index_price"].astype(float)
        raw: list[dict[str, Any]] = []
        for sector in self.sectors:
            sector_frame = self._series_cache[sector].loc[:date]
            prices = sector_frame["index_price"]
            momentum = self.scorer.score(prices)
            rs_strong = self.rs.is_strong(prices, benchmark_series)
            rs_score = self.rs.score(prices, benchmark_series)
            ma_state = self.gate.state(prices)
            gate_pass = self.gate.gate_pass(prices, momentum, rs_strong)
            latest = sector_frame.iloc[-1]
            raw.append(
                {
                    "sector": sector,
                    "momentum_score": momentum,
                    "rs_strong": rs_strong,
                    "rs_score": rs_score,
                    "ma_state": ma_state,
                    "gate_pass": gate_pass,
                    "valuation_percentile": float(latest["valuation_percentile"]),
                    "attention_rank_pct": float(latest["attention_rank_pct"]),
                    "fund_nav": float(latest["fund_nav"]),
                    "index_price": float(latest["index_price"]),
                }
            )

        ranked = sorted(raw, key=lambda row: row["momentum_score"], reverse=True)
        n = max(1, len(ranked))
        momentum_pct: dict[str, float] = {}
        for rank, item in enumerate(ranked, start=1):
            momentum_pct[item["sector"]] = (n - rank + 1) / n * 100

        for item in raw:
            item["momentum_rank_score"] = round(momentum_pct[item["sector"]], 2)
            item["asi"] = round(item["momentum_rank_score"] - item["attention_rank_pct"], 2)
            item["asi_score"] = round(clamp(item["asi"] + 50), 2)
            if self.config.get("asi_enabled"):
                trend = 0.45 * item["momentum_rank_score"] + 0.35 * item["rs_score"] + 0.2 * item["asi_score"]
            else:
                trend = 0.55 * item["momentum_rank_score"] + 0.45 * item["rs_score"]
            item["trend_score"] = round(trend if item["gate_pass"] else 0.0, 2)
            item["multiplier"] = self.valuation.multiplier(item["valuation_percentile"])
        result = sorted(raw, key=lambda row: row["trend_score"], reverse=True)
        self._signal_cache[date] = copy.deepcopy(result)
        return result

    def run_simulation(self, end_date: str | None = None) -> dict[str, Any]:
        dates = self.dates_until(end_date)
        month_days = first_business_days(dates)
        check_days = weekly_check_days(dates)
        reserve = ReservePool(
            base_amount=float(self.config["base_amount"]),
            max_months=6,
            cash_rate=float(self.config["cash_rate"]),
        )
        positions = {sector: Position() for sector in self.sectors}
        trackers = {sector: ExitTracker() for sector in self.sectors}
        timeline: dict[str, list[dict[str, Any]]] = {sector: [] for sector in self.sectors}
        account_curve: list[dict[str, Any]] = []
        planned_contribution = 0.0
        actions_by_date: list[dict[str, Any]] = []

        for index, date in enumerate(dates):
            reserve.accrue()
            signals = self.compute_signals(date)
            signal_map = {item["sector"]: item for item in signals}
            signal_date = dates[index - 1] if index > 0 else None
            decision_signals = self._execution_signals(signal_date, date) if signal_date else []
            decision_signal_map = {item["sector"]: item for item in decision_signals}

            if date in check_days and decision_signal_map:
                self._update_exits(date, decision_signal_map, positions, trackers, reserve, actions_by_date)

            if date in month_days:
                planned_contribution += float(self.config["base_amount"])
                selected = [
                    item
                    for item in decision_signals
                    if item["gate_pass"] and item["multiplier"] > 0
                ][: int(self.config["max_selected_sectors"])]
                if not selected:
                    reserve.deposit(float(self.config["base_amount"]), date, "门控未通过或估值硬停")
                else:
                    self._invest_month(date, selected, positions, reserve, actions_by_date, trackers)

            for sector in self.sectors:
                signal = signal_map[sector]
                nav = signal["fund_nav"]
                position = positions[sector]
                tracker = trackers[sector]
                timeline[sector].append(
                    {
                        "date": date,
                        "index_price": round(signal["index_price"], 4),
                        "fund_nav": round(nav, 4),
                        "valuation_percentile": round(signal["valuation_percentile"], 2),
                        "momentum_score": round(signal["momentum_score"], 2),
                        "rs_score": round(signal["rs_score"], 2),
                        "r_campaign": pct(position.r_campaign(nav)),
                        "r_position": pct(position.r_position(nav)),
                        "exit_level": EXIT_LABELS[tracker.level],
                        "market_value": round(position.market_value(nav), 2),
                    }
                )
            nav_map = {sector: signal_map[sector]["fund_nav"] for sector in self.sectors}
            market_value = sum(positions[sector].market_value(nav_map[sector]) for sector in self.sectors)
            total_invested = sum(position.cumulative_invested for position in positions.values())
            total_assets = market_value + reserve.tactical + reserve.cash_management
            account_curve.append(
                {
                    "date": date,
                    "market_value": round(market_value, 2),
                    "tactical_reserve": round(reserve.tactical, 2),
                    "cash_management": round(reserve.cash_management, 2),
                    "total_assets": round(total_assets, 2),
                    "total_invested": round(total_invested, 2),
                    "total_planned": round(planned_contribution, 2),
                    "account_return": pct((total_assets - total_invested) / total_invested) if total_invested else 0.0,
                    "planned_return": pct((total_assets - planned_contribution) / planned_contribution)
                    if planned_contribution
                    else 0.0,
                }
            )

        latest = dates[-1]
        latest_signals = self.compute_signals(latest)
        self._attach_latest_state(latest_signals, positions, trackers)
        return {
            "date": latest,
            "signals": latest_signals,
            "portfolio": self._portfolio_state(latest_signals, positions, reserve, planned_contribution),
            "exit_states": self._exit_states(trackers),
            "reserve_flows": reserve.flows[-16:],
            "timeline": timeline,
            "account_curve": account_curve,
            "actions": actions_by_date[-24:],
        }

    def _execution_signals(self, signal_date: str | None, order_date: str) -> list[dict[str, Any]]:
        if not signal_date:
            return []
        signals = self.compute_signals(signal_date)
        result: list[dict[str, Any]] = []
        for item in signals:
            executed = copy.deepcopy(item)
            frame = self._series_cache[item["sector"]].loc[:order_date]
            if frame.empty:
                continue
            latest = frame.iloc[-1]
            executed["fund_nav"] = float(latest["fund_nav"])
            executed["index_price"] = float(latest["index_price"])
            executed["signal_date"] = signal_date
            executed["order_date"] = order_date
            executed["nav_date"] = order_date
            executed["shares_confirm_date"] = add_business_days(order_date, 1)
            executed["cash_settlement_date"] = add_business_days(order_date, 3)
            result.append(executed)
        return result

    def _invest_month(
        self,
        date: str,
        selected: list[dict[str, Any]],
        positions: dict[str, Position],
        reserve: ReservePool,
        actions: list[dict[str, Any]],
        trackers: dict[str, ExitTracker] | None = None,
    ) -> None:
        budget = float(self.config["base_amount"])
        selected = [item for item in selected if trackers is None or trackers[item["sector"]].level == 0]
        if not selected:
            reserve.deposit(budget, date, "退出状态禁止加仓")
            return
        score_sum = sum(max(0.01, item["trend_score"]) for item in selected)
        desired: list[tuple[dict[str, Any], float]] = []
        account_base = budget + reserve.tactical + reserve.cash_management + sum(
            positions[sector].market_value(
                float(self._series_cache[sector].loc[:date].iloc[-1]["fund_nav"])
            )
            for sector in self.sectors
        )
        single_limit = float(self.config.get("portfolio_limits", {}).get("single_sector", 1.0))
        for item in selected:
            base_alloc = budget * max(0.01, item["trend_score"]) / score_sum
            current_value = positions[item["sector"]].market_value(item["fund_nav"])
            cap_amount = max(0.0, account_base * single_limit - current_value)
            desired.append((item, min(base_alloc * item["multiplier"], cap_amount)))
        desired_total = sum(amount for _, amount in desired)
        if desired_total <= budget:
            reserve.deposit(budget - desired_total, date, "估值倍率低于预算")
            scale = 1.0
            total_available = desired_total
        else:
            extra = reserve.withdraw(desired_total - budget, date, "低估加码")
            total_available = budget + extra
            scale = total_available / desired_total if desired_total else 0
        for item, amount in desired:
            actual = amount * scale
            if actual <= 0:
                continue
            buy_result = positions[item["sector"]].buy(actual, item["fund_nav"], date)
            actions.append(
                {
                    "date": date,
                    "signal_date": item.get("signal_date", date),
                    "order_date": date,
                    "nav_date": item.get("nav_date", date),
                    "shares_confirm_date": item.get("shares_confirm_date", add_business_days(date, 1)),
                    "sector": item["sector"],
                    "action": "buy",
                    "amount": round(actual, 2),
                    "shares": round(buy_result["shares"], 4),
                    "reason": f"门控通过，倍率 {item['multiplier']:.2f}",
                }
            )

    def _update_exits(
        self,
        date: str,
        signals: dict[str, dict[str, Any]],
        positions: dict[str, Position],
        trackers: dict[str, ExitTracker],
        reserve: ReservePool,
        actions: list[dict[str, Any]],
    ) -> None:
        if not bool(self.config.get("exit", {}).get("enabled", True)):
            return
        for sector, position in positions.items():
            if position.cumulative_invested <= 0 or position.shares <= 0:
                continue
            signal = signals[sector]
            nav = signal["fund_nav"]
            state = {
                "r_campaign": position.r_campaign(nav),
                "r_position": position.r_position(nav),
                "percentile": signal["valuation_percentile"],
                "rs_strong": signal["rs_strong"],
                "ma_state": signal["ma_state"],
                "momentum": signal["momentum_score"],
                "gate_pass": signal["gate_pass"],
                "asi": signal.get("asi"),
                "asi_enabled": self.config.get("asi_enabled"),
                "valuation_fell_from_extreme": (
                    signal["valuation_percentile"] < 70 and trackers[sector].extreme_valuation_seen
                ),
            }
            result = self.exit_manager.update(trackers[sector], state)
            if result["action"] == "sell_1_3":
                sale = position.sell_fraction(1 / 3, nav, date)
                reserve.deposit(sale["net_proceeds"], date, "L2卖出回收")
            elif result["action"] == "sell_1_2_remaining":
                sale = position.sell_fraction(1 / 2, nav, date)
                reserve.deposit(sale["net_proceeds"], date, "L3卖出回收")
            elif result["action"] == "sell_all":
                seed = float(self.config["exit"].get("seed_position", 0))
                sale = position.sell_fraction(1 - seed, nav, date)
                reserve.deposit(sale["net_proceeds"], date, "L4清仓回收")
            else:
                sale = {"net_proceeds": 0.0, "shares": 0.0, "redemption_fee": 0.0}
            if result["action"] != "hold":
                actions.append(
                    {
                        "date": date,
                        "signal_date": signal.get("signal_date", date),
                        "order_date": date,
                        "nav_date": signal.get("nav_date", date),
                        "cash_settlement_date": signal.get("cash_settlement_date", add_business_days(date, 3)),
                        "sector": sector,
                        "action": result["action"],
                        "amount": round(sale["net_proceeds"], 2),
                        "shares": round(sale["shares"], 4),
                        "redemption_fee": round(sale["redemption_fee"], 2),
                        "reason": result["reason"],
                    }
                )

    def _attach_latest_state(
        self,
        signals: list[dict[str, Any]],
        positions: dict[str, Position],
        trackers: dict[str, ExitTracker],
    ) -> None:
        for item in signals:
            position = positions[item["sector"]]
            tracker = trackers[item["sector"]]
            nav = item["fund_nav"]
            item["r_campaign"] = pct(position.r_campaign(nav))
            item["r_position"] = pct(position.r_position(nav))
            item["market_value"] = round(position.market_value(nav), 2)
            item["exit_level"] = EXIT_LABELS[tracker.level]
            item["exit_reason"] = tracker.reason
            item["pending_l4"] = tracker.pending_l4
            if not item["gate_pass"]:
                item["recommended_action"] = "禁止买入"
            elif item["multiplier"] == 0:
                item["recommended_action"] = "估值硬停"
            elif tracker.level >= 2:
                item["recommended_action"] = "减仓观察"
            elif tracker.level == 1:
                item["recommended_action"] = "停止加仓"
            else:
                item["recommended_action"] = "按倍率买入"

    def _portfolio_state(
        self,
        signals: list[dict[str, Any]],
        positions: dict[str, Position],
        reserve: ReservePool,
        total_planned: float | None = None,
    ) -> dict[str, Any]:
        nav_map = {item["sector"]: item["fund_nav"] for item in signals}
        for sector in self.sectors:
            if sector not in nav_map:
                nav_map[sector] = float(self._series_cache[sector].iloc[-1]["fund_nav"])
        market_value = sum(positions[sector].market_value(nav_map[sector]) for sector in self.sectors)
        invested = sum(position.cumulative_invested for position in positions.values())
        total_assets = market_value + reserve.tactical + reserve.cash_management
        total_profit = total_assets - invested
        planned = invested if total_planned is None else total_planned
        planned_profit = total_assets - planned
        return {
            "base_amount": float(self.config["base_amount"]),
            "tactical_reserve": round(reserve.tactical, 2),
            "cash_management": round(reserve.cash_management, 2),
            "market_value": round(market_value, 2),
            "total_invested": round(invested, 2),
            "total_planned": round(planned, 2),
            "total_assets": round(total_assets, 2),
            "total_profit": round(total_profit, 2),
            "account_return": pct(total_profit / invested) if invested else 0.0,
            "planned_profit": round(planned_profit, 2),
            "planned_return": pct(planned_profit / planned) if planned else 0.0,
            "cash_rate": float(self.config["cash_rate"]),
        }

    def _exit_states(self, trackers: dict[str, ExitTracker]) -> list[dict[str, Any]]:
        return [
            {
                "sector": sector,
                "level": EXIT_LABELS[tracker.level],
                "reason": tracker.reason,
                "pending_l4": tracker.pending_l4,
                "last_action": tracker.last_action,
                "r_peak": pct(tracker.r_peak),
            }
            for sector, tracker in trackers.items()
        ]

    def _series(self, frame: pd.DataFrame, sector: str, column: str) -> pd.Series:
        return frame[frame["sector"] == sector].set_index("date")[column].astype(float)


def build_dashboard(frame: pd.DataFrame, config: dict[str, Any], date: str | None = None) -> dict[str, Any]:
    engine = StrategyEngine(frame, config)
    return engine.run_simulation(date)


def build_series(frame: pd.DataFrame, config: dict[str, Any], sector: str, date: str | None = None) -> dict[str, Any]:
    result = build_dashboard(frame, config, date)
    if sector not in result["timeline"]:
        raise KeyError(sector)
    return {
        "sector": sector,
        "date": result["date"],
        "points": result["timeline"][sector],
        "exit_state": next((item for item in result["exit_states"] if item["sector"] == sector), None),
    }


def apply_overrides(config: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    from .config import deep_merge

    return deep_merge(copy.deepcopy(config), overrides or {})
