import { useState, useEffect, useCallback } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Bar, ComposedChart,
} from "recharts";
import TechnicalIndicatorsOverlay from "./TechnicalIndicators";
import "./ExpandedEventPanel.css";

const CHART_API = "http://localhost:8766/api/chart";

const PERIODS = [
  { key: "1d",  label: "1D" },
  { key: "5d",  label: "5D" },
  { key: "1mo", label: "1M" },
  { key: "3mo", label: "3M" },
  { key: "6mo", label: "6M" },
  { key: "1y",  label: "1Y" },
  { key: "5y",  label: "5Y" },
  { key: "max", label: "MAX" },
];

/* ── helpers ─────────────────────────────────────────────────────────────── */

function formatPrice(v) {
  if (v == null) return "–";
  return `$${v.toFixed(2)}`;
}

function formatPct(v) {
  if (v == null) return "–";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function formatVol(v) {
  if (!v) return "–";
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toString();
}

function formatChartDate(ts, period) {
  const d = new Date(ts * 1000);
  if (period === "1d") return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  if (period === "5d") return d.toLocaleDateString("en-US", { weekday: "short", hour: "2-digit", minute: "2-digit" });
  if (period === "max" || period === "5y") return d.toLocaleDateString("en-US", { year: "numeric", month: "short" });
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatTimestamp(ts) {
  if (!ts) return "–";
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    year: "numeric", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function formatMarketCap(v) {
  if (!v) return "–";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

/* ── chart tooltip ───────────────────────────────────────────────────────── */

function ChartTooltip({ active, payload, period }) {
  if (!active || !payload || !payload.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="ep-chart-tooltip">
      <div className="ep-chart-tooltip-date">{formatChartDate(d.t, period)}</div>
      <div className="ep-chart-tooltip-row">
        <span>Open</span><span>{formatPrice(d.o)}</span>
      </div>
      <div className="ep-chart-tooltip-row">
        <span>High</span><span style={{ color: "#1a9d4a" }}>{formatPrice(d.h)}</span>
      </div>
      <div className="ep-chart-tooltip-row">
        <span>Low</span><span style={{ color: "#d63031" }}>{formatPrice(d.l)}</span>
      </div>
      <div className="ep-chart-tooltip-row">
        <span>Close</span><span style={{ fontWeight: 700 }}>{formatPrice(d.c)}</span>
      </div>
      <div className="ep-chart-tooltip-row">
        <span>Volume</span><span>{formatVol(d.v)}</span>
      </div>
    </div>
  );
}

/* ── stock chart section ─────────────────────────────────────────────────── */

function StockChart({ ticker }) {
  const [period, setPeriod] = useState("1mo");
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchChart = useCallback(async (p) => {
    setLoading(true);
    try {
      const res = await fetch(`${CHART_API}?ticker=${ticker}&period=${p}`);
      const data = await res.json();
      setChartData(data);
    } catch (e) {
      console.error("Chart fetch error:", e);
      setChartData(null);
    }
    setLoading(false);
  }, [ticker]);

  useEffect(() => { fetchChart(period); }, [period, fetchChart]);

  const candles = chartData?.data || [];
  const stats = chartData?.stats || {};
  const info = chartData?.info || {};
  const isUp = (stats.period_change_pct || 0) >= 0;

  // Compute Y domain with padding
  let yMin = 0, yMax = 100;
  if (candles.length > 0) {
    yMin = Math.min(...candles.map(c => c.l));
    yMax = Math.max(...candles.map(c => c.h));
    const padding = (yMax - yMin) * 0.08;
    yMin = Math.floor((yMin - padding) * 100) / 100;
    yMax = Math.ceil((yMax + padding) * 100) / 100;
  }

  // Previous close reference line
  const prevClose = info.prev_close;

  return (
    <div className="ep-chart-section">
      {/* Chart header */}
      <div className="ep-chart-header">
        <div className="ep-chart-ticker-info">
          <span className="ep-chart-ticker">${ticker}</span>
          {info.price > 0 && (
            <>
              <span className="ep-chart-price">{formatPrice(info.price)}</span>
              <span className={`ep-chart-change ${isUp ? "up" : "down"}`}>
                {formatPct(stats.period_change_pct)} ({formatPrice(Math.abs(stats.period_change))})
              </span>
            </>
          )}
          {info.market_cap && (
            <span className="ep-chart-mcap">MCap: {formatMarketCap(info.market_cap)}</span>
          )}
        </div>
        <div className="ep-period-selector">
          {PERIODS.map(p => (
            <button key={p.key}
              className={`ep-period-btn ${period === p.key ? "active" : ""}`}
              onClick={() => setPeriod(p.key)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="ep-chart-container">
        {loading ? (
          <div className="ep-chart-loading">
            <div className="ep-chart-spinner" />
          </div>
        ) : candles.length > 0 ? (
          <>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={candles} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id={`grad-${ticker}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={isUp ? "#1a9d4a" : "#d63031"} stopOpacity={0.15} />
                    <stop offset="95%" stopColor={isUp ? "#1a9d4a" : "#d63031"} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f5" />
                <XAxis dataKey="t" tickFormatter={(t) => formatChartDate(t, period)}
                  tick={{ fontSize: 10, fill: "#aeaeb2" }} interval="preserveStartEnd"
                  axisLine={{ stroke: "#e5e5ea" }} tickLine={false} />
                <YAxis domain={[yMin, yMax]} tick={{ fontSize: 10, fill: "#aeaeb2" }}
                  tickFormatter={(v) => `$${v}`} axisLine={false} tickLine={false} width={65} />
                <Tooltip content={<ChartTooltip period={period} />} />
                {prevClose > 0 && period === "1d" && (
                  <ReferenceLine y={prevClose} stroke="#aeaeb2" strokeDasharray="4 4"
                    label={{ value: `Prev $${prevClose}`, position: "right", fontSize: 10, fill: "#aeaeb2" }} />
                )}
                <Area type="monotone" dataKey="c" stroke={isUp ? "#1a9d4a" : "#d63031"}
                  strokeWidth={2} fill={`url(#grad-${ticker})`} dot={false}
                  activeDot={{ r: 4, fill: isUp ? "#1a9d4a" : "#d63031" }} />
              </ComposedChart>
            </ResponsiveContainer>

            {/* Volume bars below */}
            <ResponsiveContainer width="100%" height={60}>
              <ComposedChart data={candles} margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
                <XAxis dataKey="t" hide />
                <YAxis hide />
                <Bar dataKey="v" fill="#d1d1d6" opacity={0.5} radius={[1, 1, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          </>
        ) : (
          <div className="ep-chart-empty">No chart data available for ${ticker}</div>
        )}
      </div>

      {/* Period stats */}
      {candles.length > 0 && (
        <div className="ep-chart-stats">
          <div className="ep-chart-stat">
            <span className="ep-chart-stat-label">Period High</span>
            <span className="ep-chart-stat-value" style={{ color: "#1a9d4a" }}>{formatPrice(stats.period_high)}</span>
          </div>
          <div className="ep-chart-stat">
            <span className="ep-chart-stat-label">Period Low</span>
            <span className="ep-chart-stat-value" style={{ color: "#d63031" }}>{formatPrice(stats.period_low)}</span>
          </div>
          <div className="ep-chart-stat">
            <span className="ep-chart-stat-label">Avg Volume</span>
            <span className="ep-chart-stat-value">{formatVol(stats.avg_volume)}</span>
          </div>
          <div className="ep-chart-stat">
            <span className="ep-chart-stat-label">Total Volume</span>
            <span className="ep-chart-stat-value">{formatVol(stats.total_volume)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── signals detail table ────────────────────────────────────────────────── */

function SignalsDetailTable({ event }) {
  const allTickers = [...(event.tickers || [])];
  (event.correlated_moves || []).forEach(t => { if (!allTickers.includes(t)) allTickers.push(t); });
  Object.keys(event.ticker_signals || {}).forEach(t => { if (!allTickers.includes(t)) allTickers.push(t); });

  if (allTickers.length === 0) return null;

  return (
    <div className="ep-section">
      <h4 className="ep-section-title">All Ticker Signals</h4>
      <div className="ep-table-wrapper">
        <table className="ep-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Signal</th>
              <th>Confidence</th>
              <th>Price</th>
              <th>Change</th>
              <th>RSI</th>
              <th>MACD</th>
              <th>Volume</th>
              <th>Tech Signal</th>
              <th>Revolut</th>
              <th>XTB</th>
            </tr>
          </thead>
          <tbody>
            {allTickers.map(ticker => {
              const ts = event.ticker_signals?.[ticker];
              const signal = ts?.signal || event.buy_signal || "–";
              const confidence = ts?.confidence ?? event.buy_confidence ?? "–";
              const pd = event.price_data?.[ticker];
              const td = event.technical_data?.[ticker];
              const avail = event.stock_availability?.[ticker];
              const isCorrelated = !event.tickers?.includes(ticker);

              return (
                <tr key={ticker} className={isCorrelated ? "correlated" : ""}>
                  <td className="ep-td-ticker">
                    ${ticker}
                    {isCorrelated && <span className="ep-correlated-tag">corr</span>}
                  </td>
                  <td>
                    <span className={`ep-signal-pill ${signal.toLowerCase()}`}>{signal}</span>
                  </td>
                  <td className="ep-td-mono">
                    {confidence !== "–" ? `${confidence}%` : "–"}
                  </td>
                  <td className="ep-td-mono">
                    {pd?.price != null ? formatPrice(pd.price) : "–"}
                  </td>
                  <td className={`ep-td-mono ${pd?.change_pct >= 0 ? "up" : "down"}`}>
                    {pd?.change_pct != null ? formatPct(pd.change_pct) : "–"}
                  </td>
                  <td>
                    {td?.rsi ? (
                      <span className={`ep-rsi-badge ${td.rsi.label?.toLowerCase()}`}>
                        {td.rsi.value}
                      </span>
                    ) : "–"}
                  </td>
                  <td>
                    {td?.macd?.crossover && td.macd.crossover !== "NONE" ? (
                      <span className={`ep-macd-badge ${td.macd.crossover.toLowerCase()}`}>
                        {td.macd.crossover === "BULLISH" ? "▲ Bull" : "▼ Bear"}
                      </span>
                    ) : td?.macd ? (
                      <span className="ep-macd-neutral">{td.macd.histogram > 0 ? "+" : ""}{td.macd.histogram.toFixed(2)}</span>
                    ) : "–"}
                  </td>
                  <td>
                    {td?.volume ? (
                      <span className={td.volume.spike ? "ep-vol-spike" : ""}>
                        {td.volume.ratio}x {td.volume.spike ? "⚡" : ""}
                      </span>
                    ) : "–"}
                  </td>
                  <td>
                    {td?.tech_signal ? (
                      <span className={`ep-tech-badge ${td.tech_signal.toLowerCase()}`}>
                        {td.tech_signal === "BULLISH" ? "↑" : td.tech_signal === "BEARISH" ? "↓" : "–"} {td.strength}%
                      </span>
                    ) : "–"}
                  </td>
                  <td>{avail?.revolut ? <span className="ep-broker-yes">✓</span> : <span className="ep-broker-no">✗</span>}</td>
                  <td>{avail?.xtb ? <span className="ep-broker-yes">✓</span> : <span className="ep-broker-no">✗</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── supply chain & contagion ────────────────────────────────────────────── */

function SupplyChainSection({ event }) {
  const hasSupplyChain = event.supply_chain_exposure && event.supply_chain_exposure.length > 0;
  const hasContagion = event.contagion_tickers && event.contagion_tickers.length > 0;
  const hasCorrelated = event.correlated_moves && event.correlated_moves.length > 0;

  if (!hasSupplyChain && !hasContagion && !hasCorrelated) return null;

  return (
    <div className="ep-section">
      <h4 className="ep-section-title">Supply Chain & Contagion</h4>
      <div className="ep-contagion-grid">
        {hasCorrelated && (
          <div className="ep-contagion-block">
            <span className="ep-contagion-label">Correlated Moves</span>
            <div className="ep-contagion-tickers">
              {event.correlated_moves.map(t => {
                const ts = event.ticker_signals?.[t];
                return (
                  <span key={t} className={`ep-contagion-ticker ${ts?.signal?.toLowerCase() || ""}`}>
                    ${t}
                    {ts && <span className="ep-contagion-signal">
                      {ts.signal === "BUY" ? "▲" : ts.signal === "SELL" ? "▼" : "—"} {ts.confidence}%
                    </span>}
                  </span>
                );
              })}
            </div>
          </div>
        )}
        {hasSupplyChain && (
          <div className="ep-contagion-block">
            <span className="ep-contagion-label">Supply Chain Exposure</span>
            <div className="ep-contagion-tickers">
              {event.supply_chain_exposure.map(t => (
                <span key={t} className="ep-contagion-ticker">${t}</span>
              ))}
            </div>
          </div>
        )}
        {hasContagion && (
          <div className="ep-contagion-block">
            <span className="ep-contagion-label">Contagion Risk</span>
            <div className="ep-contagion-tickers">
              {event.contagion_tickers.map(t => (
                <span key={t} className="ep-contagion-ticker contagion">${t}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── technical indicators for all tickers ────────────────────────────────── */

function AllTickersTechnicals({ event }) {
  if (!event.technical_data) return null;

  const tickers = Object.keys(event.technical_data).filter(
    t => event.technical_data[t]?.available
  );
  if (tickers.length === 0) return null;

  return (
    <div className="ep-section">
      <h4 className="ep-section-title">Technical Indicators — All Tickers</h4>
      <div className="ep-tech-grid">
        {tickers.map(t => (
          <div key={t} className="ep-tech-card">
            <div className="ep-tech-card-header">${t}</div>
            <TechnicalIndicatorsOverlay data={event.technical_data[t]} />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── raw metadata ────────────────────────────────────────────────────────── */

function RawDataSection({ event }) {
  return (
    <div className="ep-section">
      <h4 className="ep-section-title">Event Metadata</h4>
      <div className="ep-meta-grid">
        <div className="ep-meta-item">
          <span className="ep-meta-label">Event ID</span>
          <span className="ep-meta-value mono">{event.id || "–"}</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Timestamp</span>
          <span className="ep-meta-value">{formatTimestamp(event.ts)}</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Source</span>
          <span className="ep-meta-value">{event.source || "–"} (Tier {event.tier || "–"})</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Event Type</span>
          <span className="ep-meta-value">{(event.type || "–").replace(/_/g, " ")}</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Direction</span>
          <span className="ep-meta-value">{event.direction || "–"}</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Sentiment</span>
          <span className={`ep-meta-value mono ${event.sentiment >= 0 ? "up" : "down"}`}>
            {event.sentiment != null ? event.sentiment.toFixed(2) : "–"}
          </span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Impact Score</span>
          <span className="ep-meta-value mono">{event.score || "–"} / 100</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Latency</span>
          <span className="ep-meta-value mono">{event.latency ? `${event.latency.toFixed(0)}ms` : "–"}</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Signal</span>
          <span className="ep-meta-value">{event.buy_signal || "–"} @ {event.buy_confidence || 0}%</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Time Horizon</span>
          <span className="ep-meta-value">{event.time_horizon || "–"}</span>
        </div>
        <div className="ep-meta-item">
          <span className="ep-meta-label">Feed Type</span>
          <span className="ep-meta-value">{event.ws_source ? "WebSocket (real-time)" : "RSS (polled)"}</span>
        </div>
        {event.url && (
          <div className="ep-meta-item full">
            <span className="ep-meta-label">Article URL</span>
            <a href={event.url} target="_blank" rel="noopener noreferrer" className="ep-meta-link">
              {event.url}
            </a>
          </div>
        )}
        {event.sectors && event.sectors.length > 0 && (
          <div className="ep-meta-item full">
            <span className="ep-meta-label">Sectors</span>
            <span className="ep-meta-value">{event.sectors.join(", ")}</span>
          </div>
        )}
        {event.etfs && event.etfs.length > 0 && (
          <div className="ep-meta-item full">
            <span className="ep-meta-label">ETFs</span>
            <span className="ep-meta-value">{event.etfs.join(", ")}</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── main expanded panel ─────────────────────────────────────────────────── */

export default function ExpandedEventPanel({ event, onClose }) {
  const [activeChart, setActiveChart] = useState(
    event.tickers?.length > 0 ? event.tickers[0] : null
  );

  // All chartable tickers
  const chartTickers = [...(event.tickers || [])];
  (event.correlated_moves || []).forEach(t => { if (!chartTickers.includes(t)) chartTickers.push(t); });

  return (
    <div className="ep-panel" onClick={(e) => e.stopPropagation()}>
      {/* Close bar */}
      <div className="ep-close-bar">
        <span className="ep-close-hint">Expanded View</span>
        <button className="ep-close-btn" onClick={onClose}>✕ Close</button>
      </div>

      {/* Stock Chart with ticker tabs */}
      {chartTickers.length > 0 && (
        <div className="ep-section">
          <div className="ep-chart-tabs">
            {chartTickers.map(t => (
              <button key={t}
                className={`ep-chart-tab ${activeChart === t ? "active" : ""}`}
                onClick={() => setActiveChart(t)}>
                ${t}
              </button>
            ))}
          </div>
          {activeChart && <StockChart ticker={activeChart} />}
        </div>
      )}

      {/* Signals Detail Table */}
      <SignalsDetailTable event={event} />

      {/* Technical Indicators — All Tickers */}
      <AllTickersTechnicals event={event} />

      {/* Supply Chain & Contagion */}
      <SupplyChainSection event={event} />

      {/* Raw Metadata */}
      <RawDataSection event={event} />
    </div>
  );
}
