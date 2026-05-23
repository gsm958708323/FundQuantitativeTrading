export type SectorSignal = {
  sector: string;
  momentum_score: number;
  momentum_rank_score: number;
  rs_score: number;
  rs_strong: boolean;
  ma_state: "上升" | "震荡" | "下降";
  gate_weight: number;
  gate_pass: boolean;
  valuation_percentile: number;
  attention_rank_pct: number;
  asi: number;
  asi_score: number;
  trend_score: number;
  multiplier: number;
  fund_nav: number;
  index_price: number;
  r_campaign: number;
  r_position: number;
  market_value: number;
  exit_level: string;
  exit_reason: string;
  pending_l4: boolean;
  recommended_action: string;
};

export type PortfolioState = {
  base_amount: number;
  tactical_reserve: number;
  cash_management: number;
  market_value: number;
  total_invested: number;
  total_planned: number;
  total_assets: number;
  total_profit: number;
  account_return: number;
  planned_profit: number;
  planned_return: number;
  deployment_ratio: number;
  cash_drag: number;
  cash_rate: number;
};

export type ExitState = {
  sector: string;
  level: string;
  reason: string;
  pending_l4: boolean;
  last_action: string;
  r_peak: number;
};

export type ReserveFlow = {
  date: string;
  type: "deposit" | "withdraw";
  amount: number;
  reason: string;
  tactical: number;
  cash_management: number;
};

export type SeriesPoint = {
  date: string;
  index_price: number;
  fund_nav: number;
  valuation_percentile: number;
  momentum_score: number;
  rs_score: number;
  r_campaign: number;
  r_position: number;
  exit_level: string;
  market_value: number;
};

export type DashboardResponse = {
  date: string;
  signals: SectorSignal[];
  portfolio: PortfolioState;
  exit_states: ExitState[];
  reserve_flows: ReserveFlow[];
  actions: Array<{
    date: string;
    signal_date?: string;
    order_date?: string;
    nav_date?: string;
    shares_confirm_date?: string;
    cash_settlement_date?: string;
    sector: string;
    action: string;
    amount: number;
    shares?: number;
    redemption_fee?: number;
    reason: string;
  }>;
};

export type SeriesResponse = {
  sector: string;
  date: string;
  points: SeriesPoint[];
  exit_state: ExitState | null;
};

export type ConfigResponse = {
  config: Record<string, unknown>;
  sectors: string[];
  benchmark: string;
  latest_date: string;
  data_source: string;
};

export type ValidationExperiment = {
  name: string;
  baseline: Record<string, number | string | boolean>;
  strategy: Record<string, number | string | boolean>;
  passed: boolean;
  reason: string;
};

export type MvbResponse = {
  stage: "mvb";
  experiments: ValidationExperiment[];
};

export type FullBacktestResponse = {
  stage: "full_backtest";
  date: string;
  summary: Record<string, number | string | boolean>;
  baselines: Record<string, Record<string, number | string | boolean>>;
  ablation: Record<string, unknown>;
  checks: Record<string, { passed: boolean; details: string }>;
  diagnostics: Record<string, { severity: string; details: string }>;
  worst_periods: Array<{ start: string; end: string; return: number }>;
};

export type TrialRunResponse = {
  stage: "trial_run";
  mode: string;
  weekly_decision_date: string;
  reserve: PortfolioState;
  recommendations: Array<{
    sector: string;
    action: string;
    suggested_amount: number;
    gate_pass: boolean;
    valuation_percentile: number;
    exit_level: string;
    reason: string;
  }>;
  manual_execution_checklist: string[];
  logs_to_keep: string[];
};
