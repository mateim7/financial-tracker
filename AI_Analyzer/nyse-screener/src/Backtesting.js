import { useState, useEffect, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, AreaChart, Area, Legend, Cell, ReferenceLine,
} from "recharts";
import "./Backtesting.css";

const API = "http://localhost:8766/api/backtesting";

const CHECKPOINTS = [
  { key: "1h", label: "1 Hour" },
  { key: "4h", label: "4 Hours" },
  { key: "1d", label: "1 Day" },
  { key: "1w", label: "1 Week" },
];

/* ── helpers ─────────────────────────────────────────────────────────────── */

function formatDate(ts) {
  if (!ts) return "–";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatPct(v) {
  if (v == null) return "–";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

/* ── stat card ───────────────────────────────────────────────────────────── */

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bt-stat-card">
      <div className="bt-stat-label">{label}</div>
      <div className="bt-stat-value" style={{ color: color || "#1c1c1e" }}>{value}</div>
      {sub && <div className="bt-stat-sub">{sub}</div>}
    </div>
  );
}

/* ── checkpoint selector ─────────────────────────────────────────────────── */

function CheckpointSelector({ selected, onChange }) {
  return (
    <div className="bt-cp-selector">
      {CHECKPOINTS.map(cp => (
        <button key={cp.key}
          className={`bt-cp-btn ${selected === cp.key ? "active" : ""}`}
          onClick={() => onChange(cp.key)}>
          {cp.label}
        </button>
      ))}
    </div>
  );
}

/* ── custom tooltip ──────────────────────────────────────────────────────── */

function WinRateTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="bt-tooltip">
      <div className="bt-tooltip-title">{label}</div>
      <div className="bt-tooltip-row">
        <span>Win Rate</span><span style={{ color: "#1a9d4a" }}>{d.win_rate}%</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Avg Return</span><span style={{ color: d.avg_return >= 0 ? "#1a9d4a" : "#d63031" }}>{formatPct(d.avg_return)}</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Signals</span><span>{d.total} ({d.wins}W / {d.losses}L)</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Avg Confidence</span><span>{d.avg_confidence}%</span>
      </div>
    </div>
  );
}

function PnlTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="bt-tooltip">
      <div className="bt-tooltip-title">{d.ticker} — {d.signal}</div>
      <div className="bt-tooltip-row">
        <span>Return</span><span style={{ color: d.pct_return >= 0 ? "#1a9d4a" : "#d63031" }}>{formatPct(d.pct_return)}</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Cumulative</span><span style={{ color: d.cumulative_pct >= 0 ? "#1a9d4a" : "#d63031" }}>{formatPct(d.cumulative_pct)}</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Confidence</span><span>{d.confidence}%</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Win Rate</span><span>{d.running_win_rate}%</span>
      </div>
      {d.headline && <div className="bt-tooltip-headline">{d.headline.slice(0, 80)}</div>}
    </div>
  );
}

function CalibrationTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="bt-tooltip">
      <div className="bt-tooltip-title">Confidence {label}</div>
      <div className="bt-tooltip-row">
        <span>Expected</span><span>{d.expected_midpoint}%</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Actual Win Rate</span>
        <span style={{ color: d.actual_win_rate >= d.expected_midpoint ? "#1a9d4a" : "#d63031" }}>
          {d.actual_win_rate}%
        </span>
      </div>
      <div className="bt-tooltip-row">
        <span>Signals</span><span>{d.total}</span>
      </div>
      <div className="bt-tooltip-row">
        <span>Avg Return</span><span style={{ color: d.avg_return >= 0 ? "#1a9d4a" : "#d63031" }}>{formatPct(d.avg_return)}</span>
      </div>
    </div>
  );
}

/* ── main backtesting dashboard ──────────────────────────────────────────── */

export default function Backtesting({ onBack }) {
  const [checkpoint, setCheckpoint] = useState("1d");
  const [overview, setOverview] = useState(null);
  const [byEventType, setByEventType] = useState([]);
  const [calibration, setCalibration] = useState([]);
  const [pnlCurve, setPnlCurve] = useState([]);
  const [byTicker, setByTicker] = useState([]);
  const [history, setHistory] = useState([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const PAGE_SIZE = 50;

  const fetchData = useCallback(async (cp) => {
    setLoading(true);
    setError(null);
    try {
      const [ovRes, etRes, calRes, pnlRes, tkRes, hisRes] = await Promise.all([
        fetch(`${API}/overview`),
        fetch(`${API}/by-event-type?checkpoint=${cp}`),
        fetch(`${API}/confidence-calibration?checkpoint=${cp}`),
        fetch(`${API}/pnl-curve?checkpoint=${cp}`),
        fetch(`${API}/by-ticker?checkpoint=${cp}`),
        fetch(`${API}/signal-history?limit=${PAGE_SIZE}&offset=0`),
      ]);

      const [ov, et, cal, pnl, tk, his] = await Promise.all([
        ovRes.json(), etRes.json(), calRes.json(), pnlRes.json(), tkRes.json(), hisRes.json(),
      ]);

      setOverview(ov);
      setByEventType(et.data || []);
      setCalibration((cal.data || []).filter(b => b.total > 0));
      setPnlCurve(pnl.data || []);
      setByTicker(tk.data || []);
      setHistory(his.data || []);
      setHistoryTotal(his.total || 0);
      setHistoryPage(0);
    } catch (e) {
      setError("Failed to load backtesting data. Is the backend running?");
      console.error("Backtesting fetch error:", e);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(checkpoint); }, [checkpoint, fetchData]);

  const loadMoreHistory = async () => {
    const nextOffset = (historyPage + 1) * PAGE_SIZE;
    try {
      const res = await fetch(`${API}/signal-history?limit=${PAGE_SIZE}&offset=${nextOffset}`);
      const data = await res.json();
      setHistory(prev => [...prev, ...(data.data || [])]);
      setHistoryPage(p => p + 1);
    } catch (e) {
      console.error("Failed to load more history:", e);
    }
  };

  // Auto-refresh every 60 seconds
  useEffect(() => {
    const interval = setInterval(() => fetchData(checkpoint), 60000);
    return () => clearInterval(interval);
  }, [checkpoint, fetchData]);

  if (loading && !overview) {
    return (
      <div className="bt-container">
        <div className="bt-loading">
          <div className="bt-loading-spinner" />
          <p>Loading backtesting data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bt-container">
        <div className="bt-error">
          <p>{error}</p>
          <button className="bt-retry-btn" onClick={() => fetchData(checkpoint)}>Retry</button>
        </div>
      </div>
    );
  }

  const cpData = overview?.checkpoints?.[checkpoint] || {};
  const lastPnl = pnlCurve.length > 0 ? pnlCurve[pnlCurve.length - 1] : null;

  return (
    <div className="bt-container">
      {/* Header */}
      <div className="bt-header">
        <div className="bt-header-left">
          <button className="bt-back-btn" onClick={onBack}>← Back</button>
          <div>
            <h1 className="bt-title">Backtesting Dashboard</h1>
            <p className="bt-subtitle">Signal accuracy & performance analytics</p>
          </div>
        </div>
        <CheckpointSelector selected={checkpoint} onChange={setCheckpoint} />
      </div>

      {/* Overview Stats */}
      <div className="bt-stats-grid">
        <StatCard label="Total Signals" value={overview?.total_signals || 0}
          sub={`${overview?.completed_signals || 0} completed · ${overview?.pending_signals || 0} pending`} />
        <StatCard label="Win Rate" value={`${cpData.win_rate || 0}%`}
          color={cpData.win_rate >= 50 ? "#1a9d4a" : "#d63031"}
          sub={`${cpData.wins || 0}W / ${cpData.losses || 0}L / ${cpData.flats || 0}F`} />
        <StatCard label="Avg Return" value={formatPct(cpData.avg_return)}
          color={cpData.avg_return >= 0 ? "#1a9d4a" : "#d63031"}
          sub={`Best: ${formatPct(cpData.max_return)} · Worst: ${formatPct(cpData.min_return)}`} />
        <StatCard label="Cumulative P&L" value={lastPnl ? formatPct(lastPnl.cumulative_pct) : "–"}
          color={lastPnl?.cumulative_pct >= 0 ? "#1a9d4a" : "#d63031"}
          sub={lastPnl ? `Running WR: ${lastPnl.running_win_rate}%` : ""} />
      </div>

      {/* Buy vs Sell breakdown */}
      <div className="bt-signal-breakdown">
        <div className="bt-breakdown-item buy">
          <span className="bt-breakdown-label">BUY signals</span>
          <span className="bt-breakdown-count">{overview?.by_signal?.buy?.count || 0}</span>
          <span className="bt-breakdown-conf">avg conf: {overview?.by_signal?.buy?.avg_confidence || 0}%</span>
        </div>
        <div className="bt-breakdown-item sell">
          <span className="bt-breakdown-label">SELL signals</span>
          <span className="bt-breakdown-count">{overview?.by_signal?.sell?.count || 0}</span>
          <span className="bt-breakdown-conf">avg conf: {overview?.by_signal?.sell?.avg_confidence || 0}%</span>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="bt-charts-grid">

        {/* Win Rate by Event Type */}
        <div className="bt-chart-card">
          <h3 className="bt-chart-title">Win Rate by Event Type</h3>
          <p className="bt-chart-desc">How well signals perform per event category</p>
          {byEventType.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={byEventType} margin={{ top: 10, right: 20, left: 0, bottom: 60 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f5" />
                <XAxis dataKey="event_type" angle={-45} textAnchor="end" tick={{ fontSize: 11 }}
                  interval={0} height={80} />
                <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
                <Tooltip content={<WinRateTooltip />} />
                <Bar dataKey="win_rate" radius={[4, 4, 0, 0]} maxBarSize={40}>
                  {byEventType.map((entry, i) => (
                    <Cell key={i} fill={entry.win_rate >= 50 ? "#1a9d4a" : "#d63031"} opacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="bt-chart-empty">No event type data available yet</div>
          )}
        </div>

        {/* Confidence Calibration */}
        <div className="bt-chart-card">
          <h3 className="bt-chart-title">Confidence Calibration</h3>
          <p className="bt-chart-desc">Expected confidence vs actual win rate — perfect calibration follows the diagonal</p>
          {calibration.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={calibration} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f5" />
                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
                <Tooltip content={<CalibrationTooltip />} />
                <Legend />
                <Line type="monotone" dataKey="expected_midpoint" name="Expected (perfect)"
                  stroke="#c7c7cc" strokeWidth={2} strokeDasharray="6 4" dot={false} />
                <Line type="monotone" dataKey="actual_win_rate" name="Actual Win Rate"
                  stroke="#0066ff" strokeWidth={2.5} dot={{ fill: "#0066ff", r: 4 }}
                  activeDot={{ r: 6, fill: "#0066ff" }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="bt-chart-empty">No calibration data available yet</div>
          )}
        </div>
      </div>

      {/* P&L Curve — full width */}
      <div className="bt-chart-card bt-chart-full">
        <h3 className="bt-chart-title">Cumulative P&L Curve</h3>
        <p className="bt-chart-desc">
          Cumulative percentage return if you followed every signal
          {lastPnl && <span className="bt-pnl-summary" style={{ color: lastPnl.cumulative_pct >= 0 ? "#1a9d4a" : "#d63031" }}>
            {" "}— Total: {formatPct(lastPnl.cumulative_pct)} over {pnlCurve.length} trades
          </span>}
        </p>
        {pnlCurve.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
            <AreaChart data={pnlCurve} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
              <defs>
                <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0066ff" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#0066ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f5" />
              <XAxis dataKey="entry_time" tickFormatter={formatDate} tick={{ fontSize: 10 }}
                interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11 }} unit="%" />
              <Tooltip content={<PnlTooltip />} />
              <ReferenceLine y={0} stroke="#aeaeb2" strokeDasharray="3 3" />
              <Area type="monotone" dataKey="cumulative_pct" stroke="#0066ff" strokeWidth={2}
                fill="url(#pnlGrad)" dot={false} activeDot={{ r: 5, fill: "#0066ff" }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="bt-chart-empty">No P&L data available yet — track some signals to see results</div>
        )}
      </div>

      {/* Top / Bottom Tickers */}
      <div className="bt-charts-grid">
        <div className="bt-chart-card">
          <h3 className="bt-chart-title">Best Performing Tickers</h3>
          <p className="bt-chart-desc">Ranked by total return</p>
          <div className="bt-ticker-list">
            {byTicker.filter(t => t.total_return >= 0).slice(0, 10).map((t, i) => (
              <div key={t.ticker} className="bt-ticker-row">
                <span className="bt-ticker-rank">#{i + 1}</span>
                <span className="bt-ticker-name">${t.ticker}</span>
                <span className="bt-ticker-wr" style={{ color: t.win_rate >= 50 ? "#1a9d4a" : "#d63031" }}>
                  {t.win_rate}% WR
                </span>
                <span className="bt-ticker-ret positive">{formatPct(t.total_return)}</span>
                <span className="bt-ticker-count">{t.total} trades</span>
              </div>
            ))}
            {byTicker.filter(t => t.total_return >= 0).length === 0 && (
              <div className="bt-chart-empty">No winning tickers yet</div>
            )}
          </div>
        </div>

        <div className="bt-chart-card">
          <h3 className="bt-chart-title">Worst Performing Tickers</h3>
          <p className="bt-chart-desc">Tickers with negative total return</p>
          <div className="bt-ticker-list">
            {byTicker.filter(t => t.total_return < 0).slice(-10).reverse().map((t, i) => (
              <div key={t.ticker} className="bt-ticker-row">
                <span className="bt-ticker-rank">#{i + 1}</span>
                <span className="bt-ticker-name">${t.ticker}</span>
                <span className="bt-ticker-wr" style={{ color: t.win_rate >= 50 ? "#1a9d4a" : "#d63031" }}>
                  {t.win_rate}% WR
                </span>
                <span className="bt-ticker-ret negative">{formatPct(t.total_return)}</span>
                <span className="bt-ticker-count">{t.total} trades</span>
              </div>
            ))}
            {byTicker.filter(t => t.total_return < 0).length === 0 && (
              <div className="bt-chart-empty">No losing tickers yet</div>
            )}
          </div>
        </div>
      </div>

      {/* Signal History Table */}
      <div className="bt-chart-card bt-chart-full">
        <h3 className="bt-chart-title">Signal History</h3>
        <p className="bt-chart-desc">{historyTotal} total tracked signals</p>
        <div className="bt-table-wrapper">
          <table className="bt-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticker</th>
                <th>Signal</th>
                <th>Conf</th>
                <th>Entry</th>
                <th>1h</th>
                <th>4h</th>
                <th>1d</th>
                <th>1w</th>
                <th>Event Type</th>
                <th>Headline</th>
              </tr>
            </thead>
            <tbody>
              {history.map((s, i) => (
                <tr key={`${s.event_id}-${s.ticker}-${i}`} className={s.completed ? "" : "pending"}>
                  <td className="bt-td-date">{formatDate(s.entry_time)}</td>
                  <td className="bt-td-ticker">${s.ticker}</td>
                  <td>
                    <span className={`bt-signal-pill ${s.signal.toLowerCase()}`}>{s.signal}</span>
                  </td>
                  <td className="bt-td-mono">{s.confidence}%</td>
                  <td className="bt-td-mono">${s.entry_price?.toFixed(2)}</td>
                  {["1h", "4h", "1d", "1w"].map(cp => {
                    const cpd = s.checkpoints[cp];
                    return (
                      <td key={cp} className={`bt-td-outcome ${cpd.outcome === "WIN" ? "win" : cpd.outcome === "LOSS" ? "loss" : ""}`}>
                        {cpd.pct != null ? formatPct(cpd.pct) : "..."}
                      </td>
                    );
                  })}
                  <td className="bt-td-type">{s.event_type || "–"}</td>
                  <td className="bt-td-headline" title={s.headline}>{s.headline?.slice(0, 50) || "–"}{s.headline?.length > 50 ? "..." : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {history.length < historyTotal && (
          <button className="bt-load-more" onClick={loadMoreHistory}>
            Load more ({historyTotal - history.length} remaining)
          </button>
        )}
      </div>
    </div>
  );
}
