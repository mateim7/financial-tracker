import "./App.css";
import { useState, useEffect, useRef } from "react";

/* ── helpers ─────────────────────────────────────────────────────────────── */
function getSeverity(score) {
  if (score >= 80) return "critical";
  if (score >= 60) return "high";
  if (score >= 40) return "medium";
  return "low";
}

function getTimeAgo(ts) {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

const sevColor = { critical: "#eb4d3d", high: "#f5a623", medium: "#34c759", low: "#c7c7cc" };

const regimeConfig = {
  calm:     { label: "CALM",     color: "#1a9d4a", bg: "#e8f9ef" },
  normal:   { label: "NORMAL",   color: "#0066ff", bg: "#eef4ff" },
  volatile: { label: "VOLATILE", color: "#f5a623", bg: "#fff3e0" },
  crisis:   { label: "CRISIS",   color: "#eb4d3d", bg: "#fdeaea" },
};

/* ── small components ────────────────────────────────────────────────────── */
function ScoreRing({ score }) {
  const severity = getSeverity(score);
  const color = sevColor[severity];
  const r = 18, c = 2 * Math.PI * r, offset = c - (score / 100) * c;
  return (
    <div style={{ position: "relative", width: 44, height: 44, flexShrink: 0 }}>
      <svg width="44" height="44" style={{ transform: "rotate(-90deg)" }}>
        <circle cx="22" cy="22" r={r} fill="none" stroke="#f0f0f5" strokeWidth="3" />
        <circle cx="22" cy="22" r={r} fill="none" stroke={color} strokeWidth="3"
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.8s cubic-bezier(.4,0,.2,1)" }} />
      </svg>
      <span style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 13, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>{score}</span>
    </div>
  );
}

function DirectionPill({ direction }) {
  const cfg = {
    BULLISH:  { label: "Bullish",  icon: "↑", bg: "#e8f9ef", color: "#1a9d4a" },
    BEARISH:  { label: "Bearish",  icon: "↓", bg: "#fdeaea", color: "#d63031" },
    NEUTRAL:  { label: "Neutral",  icon: "–", bg: "#f0f0f5", color: "#8e8e93" },
  };
  const c = cfg[direction] || cfg.NEUTRAL;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 3, padding: "3px 10px",
      borderRadius: 20, background: c.bg, color: c.color, fontSize: 12, fontWeight: 600 }}>
      {c.icon} {c.label}
    </span>
  );
}

function SourceTag({ source, tier, wsSource }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 12, color: "#8e8e93" }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%",
        background: tier === 1 ? "#f5a623" : tier === 2 ? "#c7c7cc" : "#e5e5ea",
        display: "inline-block" }} />
      {wsSource && (
        <span style={{ fontSize: 9, fontWeight: 700, color: "#fff", background: "#0066ff",
          padding: "1px 4px", borderRadius: 3, letterSpacing: 0.5 }}>WS</span>
      )}
      {source}
    </span>
  );
}

function TickerPill({ ticker, priceData }) {
  const pd = priceData || {};
  const up = pd.change_pct >= 0;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "4px 10px",
      borderRadius: 10, background: "#f0f0f5", fontSize: 12, fontWeight: 600 }}>
      <span style={{ color: "#0066ff" }}>${ticker}</span>
      {pd.price != null && (
        <span style={{ color: up ? "#1a9d4a" : "#d63031", fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>
          {pd.price.toFixed(2)} <span style={{ fontSize: 10 }}>{up ? "+" : ""}{pd.change_pct}%</span>
        </span>
      )}
    </span>
  );
}

/* ── buy/sell signal badge ───────────────────────────────────────────────── */
function SignalBadge({ signal, confidence }) {
  if (!signal) return null;
  const cfg = {
    BUY:  { bg: "#e8f9ef", border: "#b8edca", color: "#1a9d4a", icon: "●" },
    SELL: { bg: "#fdeaea", border: "#f5c6c6", color: "#d63031", icon: "●" },
    HOLD: { bg: "#f0f0f5", border: "#e5e5ea", color: "#8e8e93", icon: "●" },
  };
  const c = cfg[signal] || cfg.HOLD;
  const label =
    signal === "BUY" ? (
      confidence >= 85 ? "Strong Buy" : confidence >= 65 ? "Buy" :
      confidence >= 50 ? "Moderate Buy" : "Speculative"
    ) : signal === "SELL" ? (
      confidence >= 75 ? "Strong Sell" : confidence >= 50 ? "Sell" : "Weak Sell"
    ) : "Hold";

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 14px",
      borderRadius: 12, background: c.bg, border: `1px solid ${c.border}` }}>
      <span style={{ fontSize: 8, color: c.color }}>{c.icon}</span>
      <span style={{ fontSize: 13, fontWeight: 700, color: c.color }}>{signal}</span>
      <span style={{ fontSize: 12, color: c.color, opacity: 0.7 }}>{confidence}%</span>
      <span style={{ fontSize: 11, color: c.color, opacity: 0.6, fontWeight: 500 }}>{label}</span>
    </div>
  );
}

/* ── event card ──────────────────────────────────────────────────────────── */
function EventCard({ event, isNew, trackedPairs, onTrack, onUntrack }) {
  const severity = getSeverity(event.score);
  const [timeAgo, setTimeAgo] = useState(getTimeAgo(event.ts));
  const [hovered, setHovered] = useState(false);
  useEffect(() => { const i = setInterval(() => setTimeAgo(getTimeAgo(event.ts)), 5000); return () => clearInterval(i); }, [event.ts]);

  const hasUrl = Boolean(event.url);

  const handleClick = () => {
    if (hasUrl) window.open(event.url, "_blank", "noopener,noreferrer");
  };

  const confidenceLabel = (signal, conf) => {
    if (signal === "BUY") {
      if (conf === 100) return "SURE PURCHASE";
      if (conf >= 95) return "VERY HIGH CONVICTION";
      if (conf >= 85) return "HIGH CONFIDENCE";
      if (conf >= 75) return "STRONG BUY";
      if (conf >= 65) return "SOLID CONVICTION";
      if (conf >= 50) return "RECOMMENDED PURCHASE";
      if (conf >= 41) return "BORDERLINE BUY";
      if (conf >= 26) return "SPECULATIVE BUY";
      if (conf >= 11) return "WEAK SIGNAL";
      return "VERY LOW CONVICTION";
    }
    if (signal === "SELL") {
      if (conf >= 85) return "STRONG SELL";
      if (conf >= 65) return "CONFIDENT SELL";
      if (conf >= 50) return "RECOMMENDED SELL";
      return "SPECULATIVE SELL";
    }
    return "NEUTRAL — HOLD";
  };

  return (
    <div style={{
      background: "#ffffff",
      borderRadius: 16,
      padding: "20px 22px",
      marginBottom: 10,
      boxShadow: isNew ? "0 0 0 2px rgba(0,102,255,0.15), 0 2px 12px rgba(0,0,0,0.06)" : "0 1px 4px rgba(0,0,0,0.04)",
      transition: "box-shadow 0.3s ease, transform 0.2s ease",
      animation: isNew ? "fadeInUp 0.4s ease" : "none",
      borderLeft: severity === "critical" ? "4px solid #eb4d3d" : severity === "high" ? "4px solid #f5a623" : "none",
      cursor: "default",
    }}
    onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 4px 20px rgba(0,0,0,0.08)"; e.currentTarget.style.transform = "translateY(-1px)"; }}
    onMouseLeave={e => { e.currentTarget.style.boxShadow = isNew ? "0 0 0 2px rgba(0,102,255,0.15), 0 2px 12px rgba(0,0,0,0.06)" : "0 1px 4px rgba(0,0,0,0.04)"; e.currentTarget.style.transform = "translateY(0)"; }}
    >
      {/* top row: direction, type, source, time, score ring */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <DirectionPill direction={event.direction} />
        <span style={{ fontSize: 11, color: "#8e8e93", background: "#f0f0f5", padding: "3px 8px", borderRadius: 6, fontWeight: 500 }}>
          {event.type.replace(/_/g, " ")}
        </span>
        <SourceTag source={event.source} tier={event.tier} wsSource={event.ws_source} />
        <span style={{ fontSize: 12, color: "#aeaeb2", marginLeft: "auto", whiteSpace: "nowrap" }}>{timeAgo}</span>
        <ScoreRing score={event.score} />
      </div>

      {/* headline */}
      <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 600, lineHeight: 1.4,
        color: severity === "critical" ? "#1c1c1e" : "#2c2c2e" }}>
        {event.url
          ? <a href={event.url} target="_blank" rel="noopener noreferrer"
              style={{ color: "inherit", textDecoration: "none" }}
              onMouseEnter={e => e.currentTarget.style.color = "#0066ff"}
              onMouseLeave={e => e.currentTarget.style.color = "inherit"}>
              {event.headline}
            </a>
          : event.headline}
      </h3>

      {/* brief */}
      {event.brief && (
        <p style={{ margin: "0 0 12px", fontSize: 13, color: "#636366", lineHeight: 1.55 }}>
          {event.brief}
        </p>
      )}

      {/* reasoning bullets */}
      {event.reasoning && event.reasoning.length > 0 && (
        <div style={{ margin: "0 0 12px", padding: "12px 16px", borderRadius: 12, background: "#fafafa" }}>
          {event.reasoning.map((r, i) => (
            <div key={i} style={{ display: "flex", gap: 8, marginBottom: i < event.reasoning.length - 1 ? 6 : 0 }}>
              <span style={{ color: "#0066ff", fontWeight: 600, fontSize: 14, lineHeight: "20px", flexShrink: 0 }}>›</span>
              <span style={{ fontSize: 13, color: "#3c3c43", lineHeight: 1.5 }}>{r}</span>
            </div>
          ))}
        </div>
      )}

      {/* time horizon + risk */}
      {(event.time_horizon || event.risk) && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
          {event.time_horizon && (
            <span style={{ fontSize: 11, padding: "4px 10px", borderRadius: 8,
              background: "#eef4ff", color: "#0066ff", fontWeight: 600 }}>
              {event.time_horizon}
            </span>
          )}
          {event.risk && (
            <span style={{ fontSize: 12, color: "#f5a623", fontWeight: 500, lineHeight: 1.4 }}>
              ⚠ {event.risk}
            </span>
          )}
        </div>
      )}

      {/* correlated moves with per-ticker signals */}
      {event.correlated_moves && event.correlated_moves.length > 0 && (
        <div style={{ display: "flex", gap: 6, marginBottom: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, color: "#aeaeb2", fontWeight: 600 }}>Also moves</span>
          {event.correlated_moves.map(t => {
            const ts = event.ticker_signals && event.ticker_signals[t];
            const sigColor = ts ? (ts.signal === "BUY" ? "#1a9d4a" : ts.signal === "SELL" ? "#e53935" : "#636366") : "#636366";
            const sigBg = ts ? (ts.signal === "BUY" ? "#e8f5e9" : ts.signal === "SELL" ? "#ffebee" : "#f0f0f5") : "#f0f0f5";
            return (
              <span key={t} style={{ fontSize: 11, padding: "3px 8px", borderRadius: 8,
                background: sigBg, color: sigColor, fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 4 }}>
                {t}
                {ts && <span style={{ fontSize: 9, opacity: 0.8 }}>{ts.signal === "BUY" ? "▲" : ts.signal === "SELL" ? "▼" : "—"}</span>}
              </span>
            );
          })}
        </div>
      )}

      {/* per-ticker signal badges + track buttons */}
      {event.buy_signal && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
          {event.ticker_signals && Object.keys(event.ticker_signals).length > 0 ? (
            /* Per-ticker signals available — show each ticker with its own signal */
            (() => {
              const allTickers = [...(event.tickers || [])];
              (event.correlated_moves || []).forEach(t => { if (!allTickers.includes(t)) allTickers.push(t); });
              const groups = { BUY: [], SELL: [], HOLD: [] };
              allTickers.forEach(ticker => {
                const ts = event.ticker_signals[ticker];
                if (ts) groups[ts.signal].push({ ticker, ...ts });
              });
              /* Also include tickers not in ticker_signals, using the blanket signal */
              allTickers.forEach(ticker => {
                if (!event.ticker_signals[ticker] && event.tickers && event.tickers.includes(ticker)) {
                  groups[event.buy_signal].push({ ticker, signal: event.buy_signal, confidence: event.buy_confidence });
                }
              });
              return ["BUY", "SELL", "HOLD"].filter(s => groups[s].length > 0).map(sig => (
                <div key={sig} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <SignalBadge signal={sig} confidence={Math.round(groups[sig].reduce((a, x) => a + x.confidence, 0) / groups[sig].length)} />
                  {groups[sig].map(({ ticker, signal, confidence }) => {
                    const isTracked = trackedPairs && trackedPairs.some(
                      tp => tp.event_id === event.id && tp.ticker === ticker
                    );
                    const isInTickers = event.tickers && event.tickers.includes(ticker);
                    const isInCorrelated = event.correlated_moves && event.correlated_moves.includes(ticker);
                    const isTradeable = isInTickers || isInCorrelated;
                    return (signal === "BUY" || signal === "SELL") && isTradeable ? (
                      isTracked ? (
                        <button key={ticker} onClick={() => onUntrack(event.id, ticker)} style={{
                          padding: "5px 12px", borderRadius: 10, border: "1px solid #e5e5ea",
                          background: "#f9f9fb", color: "#8e8e93", fontSize: 11, fontWeight: 600,
                          cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
                          transition: "all 0.15s ease",
                        }}>
                          <span style={{ color: "#1a9d4a" }}>&#10003;</span> Tracking ${ticker}
                        </button>
                      ) : (
                        <button key={ticker} onClick={() => onTrack(event.id, ticker, signal, confidence)} style={{
                          padding: "5px 12px", borderRadius: 10,
                          border: `1px solid ${signal === "BUY" ? "#1a9d4a" : "#e53935"}`,
                          background: signal === "BUY" ? "#e8f5e9" : "#ffebee",
                          color: signal === "BUY" ? "#1a9d4a" : "#e53935",
                          fontSize: 11, fontWeight: 600,
                          cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
                          transition: "all 0.15s ease",
                        }}>
                          {signal} ${ticker} <span style={{ opacity: 0.7 }}>{confidence}%</span>
                        </button>
                      )
                    ) : (
                      <span key={ticker} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 8,
                        background: "#f0f0f5", color: "#636366", fontWeight: 600 }}>
                        ${ticker} <span style={{ opacity: 0.7 }}>{confidence}%</span>
                      </span>
                    );
                  })}
                </div>
              ));
            })()
          ) : (
            /* Fallback: single blanket signal (legacy behavior) */
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <SignalBadge signal={event.buy_signal} confidence={event.buy_confidence} />
              {(event.buy_signal === "BUY" || event.buy_signal === "SELL") && event.tickers && event.tickers.length > 0 && (
                event.tickers.map(ticker => {
                  const isTracked = trackedPairs && trackedPairs.some(
                    tp => tp.event_id === event.id && tp.ticker === ticker
                  );
                  return isTracked ? (
                    <button key={ticker} onClick={() => onUntrack(event.id, ticker)} style={{
                      padding: "5px 12px", borderRadius: 10, border: "1px solid #e5e5ea",
                      background: "#f9f9fb", color: "#8e8e93", fontSize: 11, fontWeight: 600,
                      cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
                      transition: "all 0.15s ease",
                    }}>
                      <span style={{ color: "#1a9d4a" }}>&#10003;</span> Tracking ${ticker}
                    </button>
                  ) : (
                    <button key={ticker} onClick={() => onTrack(event.id, ticker, event.buy_signal, event.buy_confidence)} style={{
                      padding: "5px 12px", borderRadius: 10, border: "1px solid #0066ff",
                      background: "#eef4ff", color: "#0066ff", fontSize: 11, fontWeight: 600,
                      cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4,
                      transition: "all 0.15s ease",
                    }}>
                      Track ${ticker}
                    </button>
                  );
                })
              )}
            </div>
          )}
        </div>
      )}

      {/* availability badges — all trackable tickers (affected + correlated) */}
      {event.stock_availability && (() => {
        const allTrackable = [...(event.tickers || [])];
        (event.correlated_moves || []).forEach(t => { if (!allTrackable.includes(t)) allTrackable.push(t); });
        Object.keys(event.ticker_signals || {}).forEach(t => { if (!allTrackable.includes(t)) allTrackable.push(t); });
        const withAvail = allTrackable.filter(t => event.stock_availability[t]);
        if (withAvail.length === 0) return null;
        return (
          <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
            {withAvail.flatMap(t => {
              const info = event.stock_availability[t];
              const brokers = [
                { name: "Revolut", ok: info.revolut, color: "#7B61FF", bg: "#f0ecff" },
                { name: "XTB", ok: info.xtb, color: "#1ea83c", bg: "#e8f9ef" },
              ];
              return brokers.filter(b => b.ok).map(b => (
                <span key={`${t}-${b.name}`} style={{
                  fontSize: 11, padding: "3px 10px", borderRadius: 8, fontWeight: 600,
                  background: b.bg, color: b.color, border: `1px solid ${b.color}22`,
                }}>
                  ✓ {t} on {b.name}
                </span>
              ));
            })}
          </div>
        );
      })()}

      {/* tickers + prices + etfs row */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {event.tickers.length > 0 ? event.tickers.map(t => {
          const pd = event.price_data && event.price_data[t];
          return <TickerPill key={t} ticker={t} priceData={pd} />;
        }) : (
          <span style={{ fontSize: 12, color: "#aeaeb2", fontStyle: "italic" }}>Macro — broad market</span>
        )}
        {event.correlated_moves && event.correlated_moves.length > 0 && (
          event.correlated_moves
            .filter(t => event.price_data && event.price_data[t] && !event.tickers.includes(t))
            .map(t => {
              const pd = event.price_data[t];
              return <TickerPill key={t} ticker={t} priceData={pd} />;
            })
        )}
        {event.etfs && event.etfs.length > 0 && (
          <span style={{ fontSize: 11, color: "#aeaeb2", marginLeft: 4, fontWeight: 500 }}>
            → {event.etfs.join(", ")}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── sector heatmap ──────────────────────────────────────────────────────── */
function SectorHeatmap({ events }) {
  const sectorData = {};
  events.forEach(e => {
    (e.sectors || []).forEach(s => {
      if (!sectorData[s]) sectorData[s] = { count: 0, totalScore: 0, bullish: 0, bearish: 0 };
      sectorData[s].count++;
      sectorData[s].totalScore += e.score;
      if (e.direction === "BULLISH") sectorData[s].bullish++;
      if (e.direction === "BEARISH") sectorData[s].bearish++;
    });
  });

  const sectors = Object.entries(sectorData)
    .map(([name, d]) => ({ name, count: d.count, avg: Math.round(d.totalScore / d.count), bullish: d.bullish, bearish: d.bearish }))
    .sort((a, b) => b.count * b.avg - a.count * a.avg)
    .slice(0, 12);

  if (sectors.length === 0) return null;
  const maxHeat = Math.max(...sectors.map(s => s.count * s.avg));

  return (
    <div style={{ background: "#ffffff", borderRadius: 16, padding: "18px 20px", marginBottom: 10,
      boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
      <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: "#1c1c1e" }}>Sector Activity</span>
        <span style={{ fontSize: 11, color: "#aeaeb2" }}>{events.length} events</span>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {sectors.map(s => {
          const heat = s.count * s.avg / maxHeat;
          const dominant = s.bullish > s.bearish ? "bull" : s.bearish > s.bullish ? "bear" : "neutral";
          const colors = { bull: { bg: "#e8f9ef", text: "#1a9d4a" }, bear: { bg: "#fdeaea", text: "#d63031" }, neutral: { bg: "#eef4ff", text: "#0066ff" } };
          const c = colors[dominant];
          return (
            <div key={s.name} style={{ padding: "8px 14px", borderRadius: 12, background: c.bg,
              cursor: "default", opacity: 0.5 + heat * 0.5, transition: "transform 0.15s ease" }}
              title={`${s.count} events · avg ${s.avg} · ${s.bullish}↑ ${s.bearish}↓`}
              onMouseEnter={e => e.currentTarget.style.transform = "scale(1.04)"}
              onMouseLeave={e => e.currentTarget.style.transform = "scale(1)"}>
              <div style={{ fontSize: 12, fontWeight: 700, color: c.text }}>{s.name}</div>
              <div style={{ fontSize: 10, color: c.text, opacity: 0.6, marginTop: 2, fontFamily: "'JetBrains Mono', monospace" }}>
                {s.count}× · avg {s.avg}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── market state bar (VIX, regime, SPY, market status) ──────────────────── */
function MarketStateBar({ marketState }) {
  if (!marketState) return null;
  const regime = regimeConfig[marketState.market_regime] || regimeConfig.normal;
  const spyUp = marketState.spy_change_pct >= 0;
  const vix = marketState.vix;

  // VIX gauge: map 10–50 range to 0–100%
  const vixPct = Math.min(100, Math.max(0, ((vix - 10) / 40) * 100));

  return (
    <div style={{ background: "#ffffff", borderRadius: 14, padding: "14px 20px", marginBottom: 10,
      boxShadow: "0 1px 4px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>

      {/* VIX level + mini gauge */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div>
          <div style={{ fontSize: 10, color: "#aeaeb2", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>VIX</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: regime.color, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
            {vix.toFixed(1)}
          </div>
        </div>
        {/* mini bar gauge */}
        <div style={{ width: 60, height: 6, borderRadius: 3, background: "#f0f0f5", overflow: "hidden" }}>
          <div style={{ width: `${vixPct}%`, height: "100%", borderRadius: 3,
            background: vix < 15 ? "#1a9d4a" : vix < 20 ? "#0066ff" : vix < 30 ? "#f5a623" : "#eb4d3d",
            transition: "width 0.8s ease" }} />
        </div>
      </div>

      {/* Regime badge */}
      <span style={{ padding: "5px 14px", borderRadius: 20, background: regime.bg, color: regime.color,
        fontSize: 11, fontWeight: 700, letterSpacing: "0.06em" }}>
        {regime.label}
      </span>

      {/* Divider */}
      <div style={{ width: 1, height: 28, background: "#e5e5ea" }} />

      {/* SPY change */}
      <div>
        <div style={{ fontSize: 10, color: "#aeaeb2", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>SPY</div>
        <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace",
          color: spyUp ? "#1a9d4a" : "#d63031" }}>
          {spyUp ? "+" : ""}{marketState.spy_change_pct.toFixed(2)}%
        </div>
      </div>

      {/* Divider */}
      <div style={{ width: 1, height: 28, background: "#e5e5ea" }} />

      {/* Market status */}
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ width: 7, height: 7, borderRadius: "50%",
          background: marketState.market_open ? "#1a9d4a" : marketState.is_pre_market ? "#f5a623" : "#aeaeb2",
          animation: marketState.market_open ? "pulse 1.5s ease-in-out infinite" : "none" }} />
        <span style={{ fontSize: 12, fontWeight: 600,
          color: marketState.market_open ? "#1a9d4a" : marketState.is_pre_market ? "#f5a623" : "#8e8e93" }}>
          {marketState.market_open ? "Market Open" : marketState.is_pre_market ? "Pre-Market" : "Market Closed"}
        </span>
      </div>

      {/* Earnings season indicator */}
      {marketState.is_earnings_season && (
        <>
          <div style={{ width: 1, height: 28, background: "#e5e5ea" }} />
          <span style={{ padding: "4px 12px", borderRadius: 8, background: "#fff3e0",
            color: "#f5a623", fontSize: 11, fontWeight: 600 }}>
            Earnings Season
          </span>
        </>
      )}
    </div>
  );
}

/* ── signal performance panel ────────────────────────────────────────────── */
function SignalPerformance({ signalData }) {
  if (!signalData || !signalData.stats) return null;
  const { stats, recent } = signalData;

  const checkpoints = ["1h", "4h", "1d", "1w"];
  const cpLabels = { "1h": "1 Hour", "4h": "4 Hours", "1d": "1 Day", "1w": "1 Week" };

  const hasData = stats.total > 0;

  return (
    <div style={{ background: "#ffffff", borderRadius: 14, padding: "18px 20px", marginBottom: 10,
      boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "#1c1c1e" }}>Signal Performance</span>
          <span style={{ fontSize: 11, color: "#aeaeb2" }}>{stats.total} signals tracked</span>
        </div>
      </div>

      {!hasData ? (
        <div style={{ textAlign: "center", padding: "16px 0", color: "#aeaeb2", fontSize: 13 }}>
          No signals tracked yet — BUY/SELL signals will be verified at +1h, +4h, +1d, +1w
        </div>
      ) : (
        <>
          {/* Win rate grid — BUY signals */}
          {stats.buy && Object.values(stats.buy).some(v => v.total > 0) && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#1a9d4a", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                BUY Signals
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
                {checkpoints.map(cp => {
                  const d = stats.buy[cp] || {};
                  if (!d.total) return (
                    <div key={cp} style={{ padding: "10px 8px", borderRadius: 10, background: "#f9f9fb", textAlign: "center" }}>
                      <div style={{ fontSize: 10, color: "#aeaeb2", fontWeight: 600 }}>{cpLabels[cp]}</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: "#c7c7cc", fontFamily: "'JetBrains Mono', monospace" }}>—</div>
                    </div>
                  );
                  const winColor = d.win_rate >= 60 ? "#1a9d4a" : d.win_rate >= 45 ? "#f5a623" : "#d63031";
                  return (
                    <div key={cp} style={{ padding: "10px 8px", borderRadius: 10, background: "#f9f9fb", textAlign: "center" }}>
                      <div style={{ fontSize: 10, color: "#aeaeb2", fontWeight: 600 }}>{cpLabels[cp]}</div>
                      <div style={{ fontSize: 18, fontWeight: 800, color: winColor, fontFamily: "'JetBrains Mono', monospace" }}>
                        {d.win_rate}%
                      </div>
                      <div style={{ fontSize: 10, color: "#8e8e93", marginTop: 2 }}>
                        {d.wins}W / {d.losses}L
                      </div>
                      <div style={{ fontSize: 10, color: d.avg_return >= 0 ? "#1a9d4a" : "#d63031", fontFamily: "'JetBrains Mono', monospace" }}>
                        avg {d.avg_return >= 0 ? "+" : ""}{d.avg_return}%
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Win rate grid — SELL signals */}
          {stats.sell && Object.values(stats.sell).some(v => v.total > 0) && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#d63031", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                SELL Signals
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
                {checkpoints.map(cp => {
                  const d = stats.sell[cp] || {};
                  if (!d.total) return (
                    <div key={cp} style={{ padding: "10px 8px", borderRadius: 10, background: "#f9f9fb", textAlign: "center" }}>
                      <div style={{ fontSize: 10, color: "#aeaeb2", fontWeight: 600 }}>{cpLabels[cp]}</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: "#c7c7cc", fontFamily: "'JetBrains Mono', monospace" }}>—</div>
                    </div>
                  );
                  const winColor = d.win_rate >= 60 ? "#1a9d4a" : d.win_rate >= 45 ? "#f5a623" : "#d63031";
                  return (
                    <div key={cp} style={{ padding: "10px 8px", borderRadius: 10, background: "#f9f9fb", textAlign: "center" }}>
                      <div style={{ fontSize: 10, color: "#aeaeb2", fontWeight: 600 }}>{cpLabels[cp]}</div>
                      <div style={{ fontSize: 18, fontWeight: 800, color: winColor, fontFamily: "'JetBrains Mono', monospace" }}>
                        {d.win_rate}%
                      </div>
                      <div style={{ fontSize: 10, color: "#8e8e93", marginTop: 2 }}>
                        {d.wins}W / {d.losses}L
                      </div>
                      <div style={{ fontSize: 10, color: d.avg_return >= 0 ? "#1a9d4a" : "#d63031", fontFamily: "'JetBrains Mono', monospace" }}>
                        avg {d.avg_return >= 0 ? "+" : ""}{d.avg_return}%
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Recent outcomes list */}
          {recent && recent.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#8e8e93", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Recent Signals
              </div>
              <div style={{ maxHeight: 200, overflowY: "auto" }}>
                {recent.slice(0, 10).map((s, i) => {
                  const latestCp = ["1w", "1d", "4h", "1h"].find(cp => s[`pct_${cp}`] != null);
                  const latestPct = latestCp ? s[`pct_${latestCp}`] : null;
                  const latestOutcome = latestCp ? s[`outcome_${latestCp}`] : null;
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0",
                      borderBottom: i < recent.length - 1 ? "1px solid #f5f5f7" : "none" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 6,
                        background: s.signal === "BUY" ? "#e8f9ef" : "#fdeaea",
                        color: s.signal === "BUY" ? "#1a9d4a" : "#d63031" }}>
                        {s.signal}
                      </span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "#0066ff" }}>${s.ticker}</span>
                      <span style={{ fontSize: 11, color: "#aeaeb2", fontFamily: "'JetBrains Mono', monospace" }}>
                        @{s.entry_price?.toFixed(2)}
                      </span>
                      <span style={{ fontSize: 11, color: "#8e8e93", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {s.headline}
                      </span>
                      {latestPct != null && (
                        <span style={{ fontSize: 12, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace",
                          color: latestOutcome === "WIN" ? "#1a9d4a" : latestOutcome === "LOSS" ? "#d63031" : "#8e8e93" }}>
                          {latestPct >= 0 ? "+" : ""}{latestPct}%
                          <span style={{ fontSize: 9, marginLeft: 3, opacity: 0.6 }}>@{latestCp}</span>
                        </span>
                      )}
                      {latestPct == null && (
                        <span style={{ fontSize: 11, color: "#c7c7cc", fontStyle: "italic" }}>pending</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ── stats bar ───────────────────────────────────────────────────────────── */
function StatsBar({ events }) {
  const critical = events.filter(e => e.score >= 80).length;
  const bullish = events.filter(e => e.direction === "BULLISH").length;
  const bearish = events.filter(e => e.direction === "BEARISH").length;
  const avgScore = events.length > 0 ? Math.round(events.reduce((s, e) => s + e.score, 0) / events.length) : 0;

  const stats = [
    { label: "Events", value: events.length, color: "#1c1c1e" },
    { label: "Critical", value: critical, color: "#eb4d3d" },
    { label: "Bullish", value: bullish, color: "#1a9d4a" },
    { label: "Bearish", value: bearish, color: "#d63031" },
    { label: "Avg Score", value: avgScore, color: "#0066ff" },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 10 }}>
      {stats.map(s => (
        <div key={s.label} style={{ background: "#ffffff", borderRadius: 14, padding: "14px 12px",
          textAlign: "center", boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
          <div style={{ fontSize: 11, color: "#aeaeb2", fontWeight: 600, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>{s.label}</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: s.color, fontFamily: "'JetBrains Mono', monospace" }}>{s.value}</div>
        </div>
      ))}
    </div>
  );
}

/* ── filter bar ──────────────────────────────────────────────────────────── */
function FilterBar({ filter, setFilter, timeFilter, setTimeFilter, threshold, setThreshold }) {
  const filters = [
    { key: "all", label: "All" },
    { key: "critical", label: "Critical" },
    { key: "high", label: "High" },
    { key: "bullish", label: "↑ Bullish" },
    { key: "bearish", label: "↓ Bearish" },
    { key: "buy", label: "BUY Signals" },
  ];
  const timeFilters = [
    { key: "all", label: "All time" },
    { key: "1h", label: "1h" },
    { key: "4h", label: "4h" },
    { key: "24h", label: "24h" },
  ];

  return (
    <div style={{ background: "#ffffff", borderRadius: 14, padding: "14px 18px", marginBottom: 10,
      boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {filters.map(f => (
          <button key={f.key} onClick={() => setFilter(f.key)} style={{
            padding: "6px 16px", borderRadius: 20, border: "none", cursor: "pointer",
            fontSize: 13, fontWeight: 600,
            background: filter === f.key
              ? f.key === "buy" ? "#e8f9ef" : "#0066ff"
              : "#f0f0f5",
            color: filter === f.key
              ? f.key === "buy" ? "#1a9d4a" : "#ffffff"
              : "#8e8e93",
            transition: "all 0.2s ease",
          }}>{f.label}</button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: "#aeaeb2", fontWeight: 500 }}>Min score</span>
          <input type="range" min={0} max={100} value={threshold} onChange={e => setThreshold(Number(e.target.value))}
            style={{ width: 80, accentColor: "#0066ff" }} />
          <span style={{ fontSize: 13, fontWeight: 700, color: "#0066ff", fontFamily: "'JetBrains Mono', monospace", minWidth: 24 }}>{threshold}</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 11, color: "#aeaeb2", fontWeight: 600, marginRight: 4 }}>Time</span>
        {timeFilters.map(t => (
          <button key={t.key} onClick={() => setTimeFilter(t.key)} style={{
            padding: "4px 12px", borderRadius: 20, border: "none", cursor: "pointer",
            fontSize: 12, fontWeight: 600,
            background: timeFilter === t.key ? "#fff3e0" : "#f0f0f5",
            color: timeFilter === t.key ? "#f5a623" : "#aeaeb2",
            transition: "all 0.2s ease",
          }}>{t.label}</button>
        ))}
      </div>
    </div>
  );
}

/* ── main app ────────────────────────────────────────────────────────────── */
export default function NYSEImpactScreener() {
  const [events, setEvents] = useState([]);
  const [newIds, setNewIds] = useState(new Set());
  const [filter, setFilter] = useState("all");
  const [timeFilter, setTimeFilter] = useState("all");
  const [threshold, setThreshold] = useState(0);
  const [isLive, setIsLive] = useState(true);
  const [wsStatus, setWsStatus] = useState("connecting");
  const [marketState, setMarketState] = useState(null);
  const [signalData, setSignalData] = useState(null);
  const feedRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  // Load historical events + signal data from DB on mount
  useEffect(() => {
    fetch("http://localhost:8766/api/events?limit=100")
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data) && data.length > 0) {
          setEvents(data);
          console.log(`[Init] Loaded ${data.length} historical events from DB`);
        }
      })
      .catch(() => {});
    fetch("http://localhost:8766/api/signals")
      .then(r => r.json())
      .then(data => {
        if (data && data.stats) {
          setSignalData(data);
          console.log(`[Init] Loaded signal performance (${data.stats.total} tracked)`);
        }
      })
      .catch(() => {});
  }, []);

  // WebSocket for real-time updates
  useEffect(() => {
    let retryDelay = 1000;
    const existingIds = new Set();
    function connect() {
      const ws = new WebSocket("ws://localhost:8765");
      wsRef.current = ws;
      ws.onopen = () => { setWsStatus("live"); retryDelay = 1000; };
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "market_state") {
            setMarketState(msg);
            return;
          }
          if (msg.type === "signal_performance") {
            setSignalData(msg);
            return;
          }
          if (!isLive) return;
          // Deduplicate — don't add events already loaded from history
          if (msg.id && existingIds.has(msg.id)) return;
          existingIds.add(msg.id);
          setEvents(prev => {
            if (prev.some(e => e.id === msg.id)) return prev;
            return [msg, ...prev];
          });
          setNewIds(prev => new Set([...prev, msg.id]));
          setTimeout(() => setNewIds(prev => { const n = new Set(prev); n.delete(msg.id); return n; }), 3000);
        } catch (err) { console.warn("WS parse error", err); }
      };
      ws.onclose = () => {
        setWsStatus("disconnected");
        reconnectTimerRef.current = setTimeout(() => { retryDelay = Math.min(retryDelay * 2, 30000); connect(); }, retryDelay);
      };
      ws.onerror = () => { ws.close(); };
    }
    connect();
    return () => { clearTimeout(reconnectTimerRef.current); if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); } };
  }, []);

  const filtered = events.filter(e => {
    if (e.score < threshold) return false;
    if (timeFilter !== "all") {
      const cutoff = { "1h": 3600, "4h": 14400, "24h": 86400 }[timeFilter] * 1000;
      if (Date.now() - e.ts > cutoff) return false;
    }
    if (filter === "critical") return e.score >= 80;
    if (filter === "high") return e.score >= 60;
    if (filter === "bullish") return e.direction === "BULLISH";
    if (filter === "bearish") return e.direction === "BEARISH";
    if (filter === "buy") return e.buy_signal === "BUY";
    return true;
  });

  const trackedPairs = signalData?.tracked_ids || [];

  const handleTrack = (eventId, ticker, signal, confidence) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: "track_signal",
        event_id: eventId,
        ticker,
        signal,
        confidence,
      }));
    }
  };

  const handleUntrack = (eventId, ticker) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        action: "untrack_signal",
        event_id: eventId,
        ticker,
      }));
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f2f2f7", paddingBottom: 60 }}>

      {/* ── header ───────────────────────────────────────────────────── */}
      <div style={{ background: "#ffffff", padding: "20px 28px", marginBottom: 10,
        boxShadow: "0 1px 4px rgba(0,0,0,0.04)", position: "sticky", top: 0, zIndex: 100 }}>
        <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 40, height: 40, borderRadius: 12, background: "linear-gradient(135deg, #0066ff, #5856d6)",
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20, color: "#fff" }}>⚡</div>
            <div>
              <h1 style={{ fontSize: 20, fontWeight: 800, color: "#1c1c1e", letterSpacing: "-0.02em" }}>Impact Screener</h1>
              <p style={{ fontSize: 12, color: "#aeaeb2", fontWeight: 500, marginTop: 1 }}>Real-time market intelligence</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* live indicator */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px",
              borderRadius: 20, background: wsStatus === "live" ? "#e8f9ef" : wsStatus === "disconnected" ? "#fdeaea" : "#fff3e0" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%",
                background: wsStatus === "live" ? "#1a9d4a" : wsStatus === "disconnected" ? "#d63031" : "#f5a623",
                animation: wsStatus === "live" ? "pulse 1.5s ease-in-out infinite" : "none" }} />
              <span style={{ fontSize: 12, fontWeight: 600,
                color: wsStatus === "live" ? "#1a9d4a" : wsStatus === "disconnected" ? "#d63031" : "#f5a623" }}>
                {wsStatus === "live" ? "Live" : wsStatus === "disconnected" ? "Offline" : "Connecting..."}
              </span>
            </div>
            {/* download */}
            {["CSV", "JSON"].map(fmt => (
              <a key={fmt} href={`http://localhost:8766/download/${fmt.toLowerCase()}`} download
                style={{ padding: "7px 16px", borderRadius: 10, border: "1px solid #e5e5ea",
                  background: "#ffffff", color: "#636366", fontSize: 12, fontWeight: 600,
                  cursor: "pointer", textDecoration: "none", transition: "all 0.15s ease" }}
                onMouseEnter={e => { e.currentTarget.style.background = "#f0f0f5"; }}
                onMouseLeave={e => { e.currentTarget.style.background = "#ffffff"; }}>
                ↓ {fmt}
              </a>
            ))}
            {/* pause */}
            <button onClick={() => setIsLive(l => !l)} style={{
              padding: "7px 18px", borderRadius: 10, border: "none", cursor: "pointer",
              background: isLive ? "#f0f0f5" : "#0066ff", color: isLive ? "#636366" : "#ffffff",
              fontSize: 12, fontWeight: 600, transition: "all 0.15s ease",
            }}>
              {isLive ? "Pause" : "Resume"}
            </button>
          </div>
        </div>
      </div>

      {/* ── content ──────────────────────────────────────────────────── */}
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 16px" }}>
        <MarketStateBar marketState={marketState} />
        <StatsBar events={events} />
        <SectorHeatmap events={events} />
        <SignalPerformance signalData={signalData} />
        <FilterBar filter={filter} setFilter={setFilter} timeFilter={timeFilter}
          setTimeFilter={setTimeFilter} threshold={threshold} setThreshold={setThreshold} />

        {/* feed */}
        <div ref={feedRef}>
          {filtered.length === 0 ? (
            <div style={{ background: "#ffffff", borderRadius: 16, padding: 60, textAlign: "center",
              boxShadow: "0 1px 4px rgba(0,0,0,0.04)" }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📭</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "#3c3c43" }}>No events match your filters</div>
              <div style={{ fontSize: 13, color: "#aeaeb2", marginTop: 4 }}>Try lowering the threshold or widening your filter</div>
            </div>
          ) : (
            filtered.map(event => (
              <EventCard key={event.id} event={event} isNew={newIds.has(event.id)}
                trackedPairs={trackedPairs} onTrack={handleTrack} onUntrack={handleUntrack} />
            ))
          )}
        </div>
      </div>

      {/* ── footer ───────────────────────────────────────────────────── */}
      <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, padding: "10px 24px",
        background: "rgba(255,255,255,0.85)", backdropFilter: "blur(20px)", borderTop: "1px solid #e5e5ea",
        display: "flex", justifyContent: "center", gap: 24 }}>
        <span style={{ fontSize: 11, color: "#aeaeb2" }}>
          RSS → Entity Extraction → Scoring → Claude Sonnet → WebSocket
        </span>
        {events.some(e => e.ws_source) && (
          <span style={{ fontSize: 10, color: "#0066ff", fontWeight: 600 }}>
            WS feeds active
          </span>
        )}
        <span style={{ fontSize: 11, color: "#aeaeb2", fontFamily: "'JetBrains Mono', monospace" }}>
          {events.length > 0 ? `avg ${(events.reduce((s, e) => s + (e.latency || 0), 0) / events.length).toFixed(0)}ms` : "–"}
        </span>
      </div>
    </div>
  );
}
