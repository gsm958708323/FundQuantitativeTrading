import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Database,
  Gauge,
  LineChart as LineChartIcon,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Wallet
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { getConfig, getDashboard, getSeries, simulate } from "./api/client";
import type { ConfigResponse, DashboardResponse, SectorSignal, SeriesResponse } from "./types";

const levelTone: Record<string, string> = {
  NORMAL: "tone-ok",
  L1: "tone-watch",
  L2: "tone-risk",
  L3: "tone-exit",
  L4: "tone-stop"
};

function formatMoney(value: number) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
}

function formatPct(value: number) {
  return `${value.toFixed(2)}%`;
}

function latestSelectedSignal(dashboard: DashboardResponse | null, sector: string) {
  return dashboard?.signals.find((item) => item.sector === sector) ?? dashboard?.signals[0] ?? null;
}

function KpiCard({
  icon,
  label,
  value,
  meta
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  meta: string;
}) {
  return (
    <section className="kpi-card">
      <div className="kpi-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{meta}</small>
      </div>
    </section>
  );
}

function SignalTable({
  signals,
  selected,
  onSelect
}: {
  signals: SectorSignal[];
  selected: string;
  onSelect: (sector: string) => void;
}) {
  return (
    <div className="table-shell">
      <table>
        <thead>
          <tr>
            <th>板块</th>
            <th>门控</th>
            <th>动量</th>
            <th>RS</th>
            <th>Trend</th>
            <th>估值</th>
            <th>倍率</th>
            <th>退出</th>
            <th>动作</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((item) => (
            <tr
              key={item.sector}
              className={selected === item.sector ? "selected" : ""}
              onClick={() => onSelect(item.sector)}
            >
              <td>
                <button className="row-button" title={`查看${item.sector}时间线`}>
                  {item.sector}
                </button>
              </td>
              <td>
                <span className={`pill ${item.gate_pass ? "tone-ok" : "tone-muted"}`}>
                  {item.gate_pass ? "通过" : item.ma_state}
                </span>
              </td>
              <td>{item.momentum_score.toFixed(2)}</td>
              <td>
                <span className={item.rs_strong ? "text-ok" : "text-muted"}>{item.rs_score.toFixed(1)}</span>
              </td>
              <td>{item.trend_score.toFixed(1)}</td>
              <td>
                <div className="bar-cell">
                  <span style={{ width: `${Math.min(100, item.valuation_percentile)}%` }} />
                  <b>{item.valuation_percentile.toFixed(0)}%</b>
                </div>
              </td>
              <td>{item.multiplier.toFixed(2)}x</td>
              <td>
                <span className={`pill ${levelTone[item.exit_level] ?? "tone-muted"}`}>{item.exit_level}</span>
              </td>
              <td>{item.recommended_action}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ParameterPanel({
  hardStop,
  l2Drawdown,
  onHardStop,
  onL2Drawdown,
  onApply,
  loading
}: {
  hardStop: number;
  l2Drawdown: number;
  onHardStop: (value: number) => void;
  onL2Drawdown: (value: number) => void;
  onApply: () => void;
  loading: boolean;
}) {
  return (
    <section className="panel parameters">
      <div className="panel-title">
        <Settings2 size={18} />
        <h2>参数</h2>
      </div>
      <label>
        <span>硬停百分位</span>
        <input
          type="range"
          min="60"
          max="90"
          value={hardStop}
          onChange={(event) => onHardStop(Number(event.target.value))}
        />
        <b>{hardStop}%</b>
      </label>
      <label>
        <span>L2回撤阈值</span>
        <input
          type="range"
          min="4"
          max="14"
          value={l2Drawdown}
          onChange={(event) => onL2Drawdown(Number(event.target.value))}
        />
        <b>{l2Drawdown}点</b>
      </label>
      <button className="primary-button" onClick={onApply} disabled={loading} title="重新计算策略结果">
        <RefreshCw size={16} />
        {loading ? "计算中" : "应用"}
      </button>
    </section>
  );
}

function ExitPanel({ signal }: { signal: SectorSignal | null }) {
  return (
    <section className="panel exit-panel">
      <div className="panel-title">
        <ShieldCheck size={18} />
        <h2>退出状态</h2>
      </div>
      {signal ? (
        <div className="exit-grid">
          {["NORMAL", "L1", "L2", "L3", "L4"].map((level) => (
            <div key={level} className={`exit-step ${signal.exit_level === level ? "active" : ""}`}>
              <span>{level}</span>
            </div>
          ))}
          <p>{signal.exit_reason}</p>
          <dl>
            <div>
              <dt>R Campaign</dt>
              <dd>{formatPct(signal.r_campaign)}</dd>
            </div>
            <div>
              <dt>R Position</dt>
              <dd>{formatPct(signal.r_position)}</dd>
            </div>
            <div>
              <dt>市值</dt>
              <dd>{formatMoney(signal.market_value)}</dd>
            </div>
          </dl>
        </div>
      ) : null}
    </section>
  );
}

function ReserveFlows({ dashboard }: { dashboard: DashboardResponse }) {
  return (
    <section className="panel flows">
      <div className="panel-title">
        <Wallet size={18} />
        <h2>储备池流水</h2>
      </div>
      <div className="flow-list">
        {dashboard.reserve_flows.slice(-8).map((flow, index) => (
          <div key={`${flow.date}-${index}`} className="flow-row">
            <span>{flow.date}</span>
            <b className={flow.type === "deposit" ? "text-ok" : "text-risk"}>
              {flow.type === "deposit" ? "+" : "-"}
              {formatMoney(flow.amount)}
            </b>
            <small>{flow.reason}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function TimelineCharts({ series }: { series: SeriesResponse | null }) {
  const points = useMemo(() => {
    return (series?.points ?? []).map((point) => ({
      ...point,
      shortDate: point.date.slice(5)
    }));
  }, [series]);

  return (
    <section className="charts-grid">
      <div className="panel chart-panel">
        <div className="panel-title">
          <LineChartIcon size={18} />
          <h2>{series?.sector ?? "板块"} 净值/指数</h2>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={points}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="shortDate" minTickGap={28} />
            <YAxis yAxisId="left" domain={["dataMin - 20", "dataMax + 20"]} />
            <YAxis yAxisId="right" orientation="right" domain={["dataMin - 0.05", "dataMax + 0.05"]} />
            <Tooltip />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="index_price" name="指数" dot={false} stroke="#2563eb" />
            <Line yAxisId="right" type="monotone" dataKey="fund_nav" name="基金净值" dot={false} stroke="#0f766e" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="panel chart-panel">
        <div className="panel-title">
          <Gauge size={18} />
          <h2>估值与收益</h2>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={points}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="shortDate" minTickGap={28} />
            <YAxis domain={[-20, 100]} />
            <Tooltip />
            <Legend />
            <Area
              type="monotone"
              dataKey="valuation_percentile"
              name="估值百分位"
              fill="#f59e0b"
              fillOpacity={0.18}
              stroke="#d97706"
            />
            <Line type="monotone" dataKey="r_campaign" name="R Campaign" dot={false} stroke="#7c3aed" />
            <Line type="monotone" dataKey="r_position" name="R Position" dot={false} stroke="#dc2626" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function App() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [series, setSeries] = useState<SeriesResponse | null>(null);
  const [selectedSector, setSelectedSector] = useState("科技");
  const [hardStop, setHardStop] = useState(80);
  const [l2Drawdown, setL2Drawdown] = useState(8);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const [configData, dashboardData] = await Promise.all([getConfig(), getDashboard()]);
        const initialSector = dashboardData.signals[0]?.sector ?? "科技";
        const seriesData = await getSeries(initialSector);
        setConfig(configData);
        setDashboard(dashboardData);
        setSeries(seriesData);
        setSelectedSector(initialSector);
        const valuation = configData.config.valuation as { hard_stop_percentile?: number } | undefined;
        const exit = configData.config.exit as { l2_drawdown?: number } | undefined;
        setHardStop(valuation?.hard_stop_percentile ?? 80);
        setL2Drawdown(exit?.l2_drawdown ?? 8);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function selectSector(sector: string) {
    setSelectedSector(sector);
    try {
      const data = await getSeries(sector, dashboard?.date);
      setSeries(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "时间线加载失败");
    }
  }

  async function applySimulation() {
    try {
      setLoading(true);
      const result = await simulate(
        {
          valuation: { hard_stop_percentile: hardStop },
          exit: { l2_drawdown: l2Drawdown }
        },
        selectedSector,
        dashboard?.date
      );
      setDashboard(result.dashboard);
      setSeries(result.series);
    } catch (err) {
      setError(err instanceof Error ? err.message : "模拟失败");
    } finally {
      setLoading(false);
    }
  }

  const signal = latestSelectedSignal(dashboard, selectedSector);

  if (loading && !dashboard) {
    return (
      <main className="app-shell loading-shell">
        <RefreshCw className="spin" size={28} />
        <span>正在载入策略驾驶舱</span>
      </main>
    );
  }

  if (error || !dashboard) {
    return (
      <main className="app-shell loading-shell">
        <AlertTriangle size={28} />
        <span>{error ?? "暂无数据"}</span>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p>行业趋势确认型智能定投系统</p>
          <h1>策略驾驶舱</h1>
        </div>
        <div className="topbar-meta">
          <span>
            <Database size={15} />
            {config?.data_source ?? "sample"}
          </span>
          <span>{dashboard.date}</span>
        </div>
      </header>

      <section className="kpi-grid">
        <KpiCard
          icon={<Wallet size={20} />}
          label="战术储备池"
          value={formatMoney(dashboard.portfolio.tactical_reserve)}
          meta={`现金管理 ${formatMoney(dashboard.portfolio.cash_management)}`}
        />
        <KpiCard
          icon={<BarChart3 size={20} />}
          label="持仓市值"
          value={formatMoney(dashboard.portfolio.market_value)}
          meta={`累计投入 ${formatMoney(dashboard.portfolio.total_invested)}`}
        />
        <KpiCard
          icon={<Activity size={20} />}
          label="计划收益"
          value={formatPct(dashboard.portfolio.planned_return)}
          meta={`资金部署 ${formatPct(dashboard.portfolio.deployment_ratio)}`}
        />
        <KpiCard
          icon={<CheckCircle2 size={20} />}
          label="通过门控"
          value={`${dashboard.signals.filter((item) => item.gate_pass).length}/${dashboard.signals.length}`}
          meta={`现金拖累 ${formatPct(dashboard.portfolio.cash_drag)}`}
        />
      </section>

      <section className="main-grid">
        <section className="panel signal-panel">
          <div className="panel-title">
            <Activity size={18} />
            <h2>候选板块</h2>
          </div>
          <SignalTable signals={dashboard.signals} selected={selectedSector} onSelect={selectSector} />
        </section>
        <div className="side-stack">
          <ParameterPanel
            hardStop={hardStop}
            l2Drawdown={l2Drawdown}
            onHardStop={setHardStop}
            onL2Drawdown={setL2Drawdown}
            onApply={applySimulation}
            loading={loading}
          />
          <ExitPanel signal={signal} />
        </div>
      </section>

      <TimelineCharts series={series} />
      <ReserveFlows dashboard={dashboard} />
    </main>
  );
}

export default App;
