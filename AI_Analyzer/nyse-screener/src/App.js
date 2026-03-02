import { useState, useEffect, useRef } from "react";

const DUMMY_EVENTS = [];

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

function ScoreBar({ score }) {
  const severity = getSeverity(score);
  const colors = { critical: "#ff2d55", high: "#ff9500", medium: "#30d158", low: "#636366" };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: 80, height: 6, background: "#1c1c1e", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${score}%`, height: "100%", background: colors[severity], borderRadius: 3, transition: "width 0.6s cubic-bezier(.4,0,.2,1)" }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', 'SF Mono', monospace", fontSize: 13, fontWeight: 700, color: colors[severity] }}>{score}</span>
    </div>
  );
}

function DirectionBadge({ direction }) {
  const config = {
    BULLISH: { symbol: "▲", color: "#30d158", bg: "rgba(48,209,88,0.12)" },
    BEARISH: { symbol: "▼", color: "#ff453a", bg: "rgba(255,69,58,0.12)" },
    NEUTRAL: { symbol: "●", color: "#8e8e93", bg: "rgba(142,142,147,0.12)" },
  };
  const c = config[direction] || config.NEUTRAL;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 4, background: c.bg, color: c.color, fontSize: 11, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", letterSpacing: "0.03em" }}>
      {c.symbol} {direction}
    </span>
  );
}

function SeverityDot({ score }) {
  const severity = getSeverity(score);
  const colors = { critical: "#ff2d55", high: "#ff9500", medium: "#30d158", low: "#48484a" };
  const pulse = severity === "critical";
  return (
    <span style={{ position: "relative", display: "inline-block", width: 10, height: 10 }}>
      {pulse && <span style={{ position: "absolute", inset: -3, borderRadius: "50%", background: colors[severity], opacity: 0.3, animation: "pulse 1.5s ease-in-out infinite" }} />}
      <span style={{ position: "relative", display: "block", width: 10, height: 10, borderRadius: "50%", background: colors[severity] }} />
    </span>
  );
}

function TickerChip({ ticker }) {
  return (
    <span style={{ display: "inline-block", padding: "1px 6px", borderRadius: 3, background: "rgba(10,132,255,0.15)", color: "#0a84ff", fontSize: 11, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", letterSpacing: "0.04em" }}>
      ${ticker}
    </span>
  );
}

function SourceBadge({ source, tier }) {
  const tierColors = { 1: "#ffd60a", 2: "#8e8e93", 3: "#48484a" };
  return (
    <span style={{ fontSize: 11, color: "#8e8e93", display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: tierColors[tier] || "#48484a", display: "inline-block" }} />
      {source}
    </span>
  );
}

function EventRow({ event, isNew }) {
  const severity = getSeverity(event.score);
  const borderColors = { critical: "rgba(255,45,85,0.4)", high: "rgba(255,149,0,0.2)", medium: "rgba(48,209,88,0.1)", low: "transparent" };
  const [timeAgo, setTimeAgo] = useState(getTimeAgo(event.ts));
  useEffect(() => { const i = setInterval(() => setTimeAgo(getTimeAgo(event.ts)), 5000); return () => clearInterval(i); }, [event.ts]);

  return (
    <div style={{
      padding: "14px 18px",
      borderBottom: "1px solid #1c1c1e",
      borderLeft: `3px solid ${borderColors[severity]}`,
      background: isNew ? "rgba(255,214,10,0.04)" : "transparent",
      transition: "background 1.5s ease",
      animation: isNew ? "slideIn 0.4s cubic-bezier(.4,0,.2,1)" : "none",
      cursor: "pointer",
    }}
    onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.03)"}
    onMouseLeave={e => e.currentTarget.style.background = isNew ? "rgba(255,214,10,0.02)" : "transparent"}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{ paddingTop: 5 }}><SeverityDot score={event.score} /></div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
            <DirectionBadge direction={event.direction} />
            <span style={{ fontSize: 11, color: "#636366", fontFamily: "'JetBrains Mono', monospace", background: "rgba(99,99,102,0.12)", padding: "1px 6px", borderRadius: 3 }}>
              {event.type.replace(/_/g, " ")}
            </span>
            <SourceBadge source={event.source} tier={event.tier} />
            <span style={{ fontSize: 11, color: "#48484a", marginLeft: "auto", whiteSpace: "nowrap" }}>{timeAgo}</span>
          </div>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.45, color: severity === "critical" ? "#f5f5f7" : severity === "low" ? "#8e8e93" : "#d1d1d6", fontWeight: severity === "critical" ? 600 : 400 }}>
            {event.url
              ? <a href={event.url} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", textDecoration: "none" }}
                  onMouseEnter={e => e.currentTarget.style.textDecoration = "underline"}
                  onMouseLeave={e => e.currentTarget.style.textDecoration = "none"}>
                  {event.headline}
                </a>
              : event.headline}
          </p>
          {event.brief && (
            <p style={{ margin: "6px 0 0", fontSize: 12, color: "#8e8e93", lineHeight: 1.4, fontStyle: "italic" }}>
              {event.brief}
            </p>
          )}
          {event.reasoning && event.reasoning.length > 0 && (
            <ul style={{ margin: "6px 0 0", padding: "0 0 0 14px", listStyle: "none" }}>
              {event.reasoning.map((r, i) => (
                <li key={i} style={{ fontSize: 12, color: "#aeaeb2", lineHeight: 1.45, marginBottom: 2, display: "flex", gap: 6 }}>
                  <span style={{ color: "#636366", flexShrink: 0 }}>›</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          )}
          {(event.risk || event.time_horizon) && (
            <div style={{ display: "flex", gap: 10, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
              {event.time_horizon && (
                <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 3,
                  background: "rgba(10,132,255,0.1)", color: "#0a84ff",
                  border: "1px solid rgba(10,132,255,0.2)", fontFamily: "'JetBrains Mono', monospace" }}>
                  ⏱ {event.time_horizon}
                </span>
              )}
              {event.risk && (
                <span style={{ fontSize: 11, color: "#ff9f0a", lineHeight: 1.35 }}>
                  ⚠ {event.risk}
                </span>
              )}
            </div>
          )}
          {event.correlated_moves && event.correlated_moves.length > 0 && (
            <div style={{ display: "flex", gap: 5, marginTop: 6, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 10, color: "#48484a", fontFamily: "'JetBrains Mono', monospace" }}>MOVES WITH:</span>
              {event.correlated_moves.map(t => (
                <span key={t} style={{ fontSize: 10, padding: "1px 6px", borderRadius: 3,
                  background: "rgba(99,99,102,0.15)", color: "#8e8e93",
                  border: "1px solid rgba(99,99,102,0.25)", fontFamily: "'JetBrains Mono', monospace" }}>
                  {t}
                </span>
              ))}
            </div>
          )}
          {event.buy_signal && (
            <div style={{ marginTop: 6, display: "inline-flex", alignItems: "center", gap: 6,
              padding: "3px 10px", borderRadius: 4,
              background: event.buy_signal === "BUY" ? "rgba(48,209,88,0.12)" : event.buy_signal === "SELL" ? "rgba(255,69,58,0.12)" : "rgba(99,99,102,0.12)",
              border: `1px solid ${event.buy_signal === "BUY" ? "rgba(48,209,88,0.3)" : event.buy_signal === "SELL" ? "rgba(255,69,58,0.3)" : "rgba(99,99,102,0.3)"}`,
            }}>
              <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace",
                color: event.buy_signal === "BUY" ? "#30d158" : event.buy_signal === "SELL" ? "#ff453a" : "#8e8e93" }}>
                {event.buy_signal}
              </span>
              <span style={{ fontSize: 11, color: "#636366", fontFamily: "'JetBrains Mono', monospace" }}>
                {event.buy_confidence}% · {
                  event.buy_signal === "BUY" ? (
                    event.buy_confidence === 100 ? "SURE PURCHASE" :
                    event.buy_confidence >= 95 ? "VERY HIGH CONVICTION" :
                    event.buy_confidence >= 85 ? "HIGH CONFIDENCE" :
                    event.buy_confidence >= 75 ? "STRONG BUY" :
                    event.buy_confidence >= 65 ? "SOLID CONVICTION" :
                    event.buy_confidence >= 50 ? "RECOMMENDED PURCHASE" :
                    event.buy_confidence >= 41 ? "BORDERLINE BUY" :
                    event.buy_confidence >= 26 ? "SPECULATIVE BUY" :
                    event.buy_confidence >= 11 ? "WEAK SIGNAL" : "VERY LOW CONVICTION"
                  ) : event.buy_signal === "SELL" ? (
                    event.buy_confidence >= 85 ? "STRONG SELL" :
                    event.buy_confidence >= 65 ? "CONFIDENT SELL" :
                    event.buy_confidence >= 50 ? "RECOMMENDED SELL" : "SPECULATIVE SELL"
                  ) : "NEUTRAL — HOLD"
                }
              </span>
            </div>
          )}
          {event.stock_availability && event.tickers && event.tickers.length > 0 && (
            <div style={{ display: "flex", gap: 5, marginTop: 5, flexWrap: "wrap" }}>
              {event.tickers.map(t => {
                const info = event.stock_availability[t];
                if (!info) return null;
                const platforms = [info.revolut && "Revolut", info.xtb && "XTB"].filter(Boolean);
                return (
                  <span key={t} style={{
                    fontSize: 10, padding: "2px 6px", borderRadius: 3,
                    background: platforms.length ? "rgba(48,209,88,0.1)" : "rgba(255,69,58,0.1)",
                    color: platforms.length ? "#30d158" : "#ff453a",
                    border: `1px solid ${platforms.length ? "rgba(48,209,88,0.2)" : "rgba(255,69,58,0.2)"}`,
                    fontFamily: "'JetBrains Mono', monospace",
                  }}>
                    {t}: {platforms.length ? platforms.join(" · ") : "unavailable"}
                  </span>
                );
              })}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            {event.tickers.length > 0 ? event.tickers.map(t => {
              const pd = event.price_data && event.price_data[t];
              return (
                <span key={t} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  <TickerChip ticker={t} />
                  {pd && pd.price != null && (
                    <span style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", color: pd.change_pct >= 0 ? "#30d158" : "#ff453a" }}>
                      ${pd.price} {pd.change_pct != null ? `(${pd.change_pct >= 0 ? "+" : ""}${pd.change_pct}%)` : ""}
                    </span>
                  )}
                </span>
              );
            }) : <span style={{ fontSize: 11, color: "#636366", fontStyle: "italic" }}>MACRO — Broad market</span>}
            {event.etfs.length > 0 && (
              <span style={{ fontSize: 11, color: "#48484a", marginLeft: 4 }}>
                → {event.etfs.join(", ")}
              </span>
            )}
            <div style={{ marginLeft: "auto" }}>
              <ScoreBar score={event.score} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

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
    <div style={{ padding: "10px 18px 0" }}>
      <div style={{ marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 10, color: "#636366", fontWeight: 600, letterSpacing: "0.1em", fontFamily: "'JetBrains Mono', monospace" }}>SECTOR HEAT</span>
        <span style={{ fontSize: 10, color: "#3a3a3c", fontFamily: "'JetBrains Mono', monospace" }}>last {events.length} events</span>
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
        {sectors.map(s => {
          const heat = s.count * s.avg / maxHeat;
          const dominant = s.bullish > s.bearish ? "bull" : s.bearish > s.bullish ? "bear" : "neutral";
          const baseColor = dominant === "bull" ? [48, 209, 88] : dominant === "bear" ? [255, 69, 58] : [10, 132, 255];
          const bg = `rgba(${baseColor[0]},${baseColor[1]},${baseColor[2]},${0.06 + heat * 0.2})`;
          const border = `rgba(${baseColor[0]},${baseColor[1]},${baseColor[2]},${0.15 + heat * 0.35})`;
          const textColor = `rgba(${baseColor[0]},${baseColor[1]},${baseColor[2]},${0.6 + heat * 0.4})`;
          return (
            <div key={s.name} style={{ padding: "5px 10px", borderRadius: 5, background: bg, border: `1px solid ${border}`, cursor: "default" }}
              title={`${s.count} events · avg score ${s.avg} · ${s.bullish}↑ ${s.bearish}↓`}>
              <div style={{ fontSize: 11, fontWeight: 700, color: textColor, fontFamily: "'JetBrains Mono', monospace", whiteSpace: "nowrap" }}>
                {s.name}
              </div>
              <div style={{ fontSize: 9, color: "#48484a", fontFamily: "'JetBrains Mono', monospace", marginTop: 1 }}>
                {s.count}× · {s.avg}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StatsBar({ events }) {
  const critical = events.filter(e => e.score >= 80).length;
  const bullish = events.filter(e => e.direction === "BULLISH").length;
  const bearish = events.filter(e => e.direction === "BEARISH").length;
  const avgScore = events.length > 0 ? Math.round(events.reduce((s, e) => s + e.score, 0) / events.length) : 0;
  const topSectors = [...new Set(events.flatMap(e => e.sectors))].slice(0, 4);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 1, background: "#1c1c1e", borderRadius: 10, overflow: "hidden", marginBottom: 2 }}>
      {[
        { label: "EVENTS", value: events.length, color: "#f5f5f7" },
        { label: "CRITICAL", value: critical, color: "#ff2d55" },
        { label: "BULLISH", value: bullish, color: "#30d158" },
        { label: "BEARISH", value: bearish, color: "#ff453a" },
        { label: "AVG SCORE", value: avgScore, color: "#0a84ff" },
      ].map(s => (
        <div key={s.label} style={{ padding: "12px 16px", background: "#0d0d0d", textAlign: "center" }}>
          <div style={{ fontSize: 10, color: "#636366", letterSpacing: "0.1em", fontWeight: 600, marginBottom: 4, fontFamily: "'JetBrains Mono', monospace" }}>{s.label}</div>
          <div style={{ fontSize: 22, fontWeight: 800, color: s.color, fontFamily: "'JetBrains Mono', monospace" }}>{s.value}</div>
        </div>
      ))}
    </div>
  );
}

function FilterBar({ filter, setFilter, timeFilter, setTimeFilter, threshold, setThreshold }) {
  const filters = [
    { key: "all", label: "All" },
    { key: "critical", label: "Critical 80+" },
    { key: "high", label: "High 60+" },
    { key: "bullish", label: "▲ Bullish" },
    { key: "bearish", label: "▼ Bearish" },
    { key: "buy", label: "BUY signals" },
  ];
  const timeFilters = [
    { key: "all", label: "All time" },
    { key: "1h", label: "1h" },
    { key: "4h", label: "4h" },
    { key: "24h", label: "24h" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", borderBottom: "1px solid #1c1c1e" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 18px 4px", flexWrap: "wrap" }}>
        {filters.map(f => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            style={{
              padding: "5px 12px", borderRadius: 6, border: "none", cursor: "pointer",
              fontSize: 12, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace",
              background: filter === f.key
                ? f.key === "buy" ? "rgba(48,209,88,0.2)" : "rgba(10,132,255,0.2)"
                : "rgba(99,99,102,0.08)",
              color: filter === f.key
                ? f.key === "buy" ? "#30d158" : "#0a84ff"
                : "#8e8e93",
              transition: "all 0.15s ease",
            }}
          >
            {f.label}
          </button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 11, color: "#636366", fontFamily: "'JetBrains Mono', monospace" }}>THRESHOLD</span>
          <input type="range" min={0} max={100} value={threshold} onChange={e => setThreshold(Number(e.target.value))}
            style={{ width: 80, accentColor: "#ff2d55" }} />
          <span style={{ fontSize: 12, fontWeight: 700, color: "#ff2d55", fontFamily: "'JetBrains Mono', monospace", minWidth: 24 }}>{threshold}</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 18px 8px" }}>
        <span style={{ fontSize: 10, color: "#48484a", fontFamily: "'JetBrains Mono', monospace", marginRight: 4 }}>TIME</span>
        {timeFilters.map(t => (
          <button key={t.key} onClick={() => setTimeFilter(t.key)} style={{
            padding: "3px 10px", borderRadius: 5, border: "none", cursor: "pointer",
            fontSize: 11, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace",
            background: timeFilter === t.key ? "rgba(255,214,10,0.15)" : "rgba(99,99,102,0.08)",
            color: timeFilter === t.key ? "#ffd60a" : "#636366",
            transition: "all 0.15s ease",
          }}>{t.label}</button>
        ))}
      </div>
    </div>
  );
}

export default function NYSEImpactScreener() {
  const [events, setEvents] = useState(DUMMY_EVENTS);
  const [newIds, setNewIds] = useState(new Set());
  const [filter, setFilter] = useState("all");
  const [timeFilter, setTimeFilter] = useState("all");
  const [threshold, setThreshold] = useState(0);
  const [isLive, setIsLive] = useState(true);
  const [wsStatus, setWsStatus] = useState("connecting");
  const feedRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  // WebSocket connection to Python backend
  useEffect(() => {
    let retryDelay = 1000;

    function connect() {
      const ws = new WebSocket("ws://localhost:8765");
      wsRef.current = ws;

      ws.onopen = () => {
        setWsStatus("live");
        retryDelay = 1000;
      };

      ws.onmessage = (e) => {
        if (!isLive) return;
        try {
          const event = JSON.parse(e.data);
          setEvents(prev => [event, ...prev]);
          setNewIds(prev => new Set([...prev, event.id]));
          setTimeout(() => setNewIds(prev => { const n = new Set(prev); n.delete(event.id); return n; }), 3000);
        } catch (err) {
          console.warn("Failed to parse WebSocket message", err);
        }
      };

      ws.onclose = () => {
        setWsStatus("disconnected");
        reconnectTimerRef.current = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 30000);
          connect();
        }, retryDelay);
      };

      ws.onerror = () => { ws.close(); };
    }

    connect();

    return () => {
      clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
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

  return (
    <div style={{ minHeight: "100vh", background: "#000000", color: "#f5f5f7", fontFamily: "'SF Pro Display', -apple-system, 'Helvetica Neue', sans-serif" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700;800&display=swap');
        @keyframes pulse { 0%, 100% { transform: scale(1); opacity: 0.3; } 50% { transform: scale(1.8); opacity: 0; } }
        @keyframes slideIn { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes liveDot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #2c2c2e; border-radius: 3px; }
        * { box-sizing: border-box; }
      `}</style>

      {/* Header */}
      <div style={{ padding: "20px 24px 16px", borderBottom: "1px solid #1c1c1e" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: "linear-gradient(135deg, #ff2d55, #ff6b35)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, fontWeight: 800 }}>⚡</div>
            <div>
              <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: "-0.02em", color: "#f5f5f7" }}>NYSE Impact Screener</h1>
              <p style={{ margin: 0, fontSize: 12, color: "#636366", fontFamily: "'JetBrains Mono', monospace" }}>Real-Time Market-Moving News Intelligence</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: wsStatus === "live" ? "#30d158" : wsStatus === "disconnected" ? "#ff453a" : "#ff9500", animation: wsStatus === "live" ? "liveDot 1.5s ease-in-out infinite" : "none" }} />
              <span style={{ fontSize: 12, fontWeight: 600, color: wsStatus === "live" ? "#30d158" : wsStatus === "disconnected" ? "#ff453a" : "#ff9500", fontFamily: "'JetBrains Mono', monospace" }}>{wsStatus === "live" ? "LIVE" : wsStatus === "disconnected" ? "DISCONNECTED" : "CONNECTING..."}</span>
            </div>
            {["csv", "json"].map(fmt => (
              <a key={fmt} href={`http://localhost:8766/download/${fmt}`} download
                style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid #2c2c2e",
                  background: "transparent", color: "#8e8e93", fontSize: 12, fontWeight: 600,
                  cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
                  textDecoration: "none", display: "inline-flex", alignItems: "center" }}>
                ↓ {fmt.toUpperCase()}
              </a>
            ))}
            <button onClick={() => setIsLive(l => !l)} style={{
              padding: "6px 14px", borderRadius: 6, border: "1px solid #2c2c2e", background: "transparent",
              color: "#8e8e93", fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "'JetBrains Mono', monospace",
            }}>
              {isLive ? "Pause" : "Resume"}
            </button>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div style={{ padding: "12px 18px 0" }}>
        <StatsBar events={events} />
      </div>

      {/* Sector Heatmap */}
      <SectorHeatmap events={events} />

      {/* Filters */}
      <FilterBar filter={filter} setFilter={setFilter} timeFilter={timeFilter} setTimeFilter={setTimeFilter} threshold={threshold} setThreshold={setThreshold} />

      {/* Event Feed */}
      <div ref={feedRef} style={{ maxHeight: "calc(100vh - 320px)", overflowY: "auto" }}>
        {filtered.length === 0 ? (
          <div style={{ padding: 60, textAlign: "center", color: "#48484a" }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🔇</div>
            <div style={{ fontSize: 14, fontWeight: 500 }}>No events match current filters</div>
            <div style={{ fontSize: 12, color: "#3a3a3c", marginTop: 4 }}>Try lowering the threshold or changing the filter</div>
          </div>
        ) : (
          filtered.map(event => (
            <EventRow key={event.id} event={event} isNew={newIds.has(event.id)} />
          ))
        )}
      </div>

      {/* Footer */}
      <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, padding: "8px 18px", borderTop: "1px solid #1c1c1e", background: "rgba(0,0,0,0.9)", backdropFilter: "blur(20px)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, color: "#3a3a3c", fontFamily: "'JetBrains Mono', monospace" }}>
          Pipeline: Kafka → FinBERT → XGBoost → Claude Sonnet
        </span>
        <span style={{ fontSize: 11, color: "#3a3a3c", fontFamily: "'JetBrains Mono', monospace" }}>
          Avg latency: {(events.reduce((s, e) => s + e.latency, 0) / events.length).toFixed(1)}ms
        </span>
      </div>
    </div>
  );
}