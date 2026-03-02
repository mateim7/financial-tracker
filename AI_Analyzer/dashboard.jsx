import { useState, useEffect, useRef } from "react";

const DUMMY_EVENTS = [
  { id: "e001", ts: Date.now() - 2000, headline: "BREAKING: FDA approves Pfizer's new RSV vaccine for elderly adults", source: "Reuters", tier: 1, type: "FDA_APPROVAL", direction: "BULLISH", sentiment: 1.0, score: 100, tickers: ["PFE"], sectors: ["Healthcare"], etfs: ["XLV", "IBB", "XBI"], latency: 1.4 },
  { id: "e002", ts: Date.now() - 8000, headline: "JPMorgan to acquire regional bank First Republic in $10.6B deal", source: "Bloomberg", tier: 1, type: "MA_ANNOUNCED", direction: "BULLISH", sentiment: 0.0, score: 100, tickers: ["JPM"], sectors: ["Financials"], etfs: ["XLF", "KRE", "KBE"], latency: 0.9 },
  { id: "e003", ts: Date.now() - 15000, headline: "FOMC holds rate steady at 5.25-5.50%, signals hawkish stance — no cuts until Q3", source: "Federal Reserve", tier: 1, type: "MACRO_FOMC", direction: "BEARISH", sentiment: -1.0, score: 100, tickers: [], sectors: [], etfs: [], latency: 1.1 },
  { id: "e004", ts: Date.now() - 22000, headline: "Walmart beats Q3 earnings estimates, raises full-year guidance", source: "Benzinga", tier: 2, type: "EARNINGS_BEAT", direction: "BULLISH", sentiment: 1.0, score: 89, tickers: ["WMT"], sectors: ["Consumer Staples"], etfs: ["XLP"], latency: 0.8 },
  { id: "e005", ts: Date.now() - 30000, headline: "SEC charges Goldman Sachs with misleading investors on ESG fund practices", source: "SEC EDGAR", tier: 2, type: "REGULATORY_ACTION", direction: "BEARISH", sentiment: -0.5, score: 87, tickers: ["GS"], sectors: ["Financials"], etfs: ["XLF", "KRE", "KBE"], latency: 1.2 },
  { id: "e006", ts: Date.now() - 40000, headline: "CPI rises 0.6% in March, hotter than expected — core inflation surges to 4.1%", source: "BLS", tier: 1, type: "MACRO_CPI", direction: "NEUTRAL", sentiment: 0.0, score: 64, tickers: [], sectors: [], etfs: [], latency: 0.6 },
  { id: "e007", ts: Date.now() - 50000, headline: "Analyst at Morgan Stanley upgrades Caterpillar to Overweight, raises target to $380", source: "MarketWatch", tier: 2, type: "ANALYST_UPGRADE", direction: "BULLISH", sentiment: 1.0, score: 55, tickers: ["CAT"], sectors: ["Industrials"], etfs: ["XLI", "ITA"], latency: 0.5 },
  { id: "e008", ts: Date.now() - 60000, headline: "Boeing 737 MAX deliveries halted again after new quality defect found", source: "CNBC", tier: 2, type: "UNKNOWN", direction: "NEUTRAL", sentiment: 0.0, score: 23, tickers: ["BA"], sectors: ["Industrials"], etfs: ["XLI", "ITA"], latency: 0.4 },
  { id: "e009", ts: Date.now() - 72000, headline: "Disney CEO Bob Iger announces surprise departure; CFO named interim", source: "Benzinga", tier: 2, type: "CEO_DEPARTURE", direction: "BEARISH", sentiment: -0.3, score: 23, tickers: ["DIS"], sectors: ["Communication"], etfs: ["XLC"], latency: 0.7 },
  { id: "e010", ts: Date.now() - 85000, headline: "Rumor: Nike may be exploring strategic options including potential sale", source: "Twitter/X", tier: 3, type: "UNKNOWN", direction: "NEUTRAL", sentiment: 0.0, score: 17, tickers: ["NKE"], sectors: ["Consumer Disc."], etfs: ["XLY"], latency: 0.3 },
];

const INCOMING_EVENTS = [
  { id: "e011", headline: "URGENT: Exxon Mobil declares force majeure on Permian Basin operations after pipeline explosion", source: "Reuters", tier: 1, type: "GEOPOLITICAL", direction: "BEARISH", sentiment: -0.8, score: 92, tickers: ["XOM"], sectors: ["Energy"], etfs: ["XLE", "XOP", "OIH"], latency: 0.9 },
  { id: "e012", headline: "UnitedHealth Group CEO under DOJ investigation for insider trading — shares halted", source: "Bloomberg", tier: 1, type: "REGULATORY_ACTION", direction: "BEARISH", sentiment: -1.0, score: 96, tickers: ["UNH"], sectors: ["Healthcare"], etfs: ["XLV", "IBB"], latency: 1.1 },
  { id: "e013", headline: "Visa reports record Q4 transaction volume, announces $10B buyback program", source: "Benzinga", tier: 2, type: "EARNINGS_BEAT", direction: "BULLISH", sentiment: 0.8, score: 81, tickers: ["V"], sectors: ["Financials"], etfs: ["XLF"], latency: 0.7 },
];

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
            {event.headline}
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            {event.tickers.length > 0 ? event.tickers.map(t => <TickerChip key={t} ticker={t} />) : <span style={{ fontSize: 11, color: "#636366", fontStyle: "italic" }}>MACRO — Broad market</span>}
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

function FilterBar({ filter, setFilter, threshold, setThreshold }) {
  const filters = [
    { key: "all", label: "All" },
    { key: "critical", label: "Critical 80+" },
    { key: "high", label: "High 60+" },
    { key: "bullish", label: "▲ Bullish" },
    { key: "bearish", label: "▼ Bearish" },
  ];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "10px 18px", borderBottom: "1px solid #1c1c1e", flexWrap: "wrap" }}>
      {filters.map(f => (
        <button
          key={f.key}
          onClick={() => setFilter(f.key)}
          style={{
            padding: "5px 12px", borderRadius: 6, border: "none", cursor: "pointer",
            fontSize: 12, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace",
            background: filter === f.key ? "rgba(10,132,255,0.2)" : "rgba(99,99,102,0.08)",
            color: filter === f.key ? "#0a84ff" : "#8e8e93",
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
  );
}

export default function NYSEImpactScreener() {
  const [events, setEvents] = useState(DUMMY_EVENTS);
  const [newIds, setNewIds] = useState(new Set());
  const [filter, setFilter] = useState("all");
  const [threshold, setThreshold] = useState(0);
  const [isLive, setIsLive] = useState(true);
  const [incomingIdx, setIncomingIdx] = useState(0);
  const feedRef = useRef(null);

  // Simulate incoming events
  useEffect(() => {
    if (!isLive || incomingIdx >= INCOMING_EVENTS.length) return;
    const timer = setTimeout(() => {
      const newEvent = { ...INCOMING_EVENTS[incomingIdx], ts: Date.now() };
      setEvents(prev => [newEvent, ...prev]);
      setNewIds(prev => new Set([...prev, newEvent.id]));
      setIncomingIdx(i => i + 1);
      setTimeout(() => setNewIds(prev => { const n = new Set(prev); n.delete(newEvent.id); return n; }), 3000);
    }, 4000 + incomingIdx * 5000);
    return () => clearTimeout(timer);
  }, [isLive, incomingIdx]);

  const filtered = events.filter(e => {
    if (e.score < threshold) return false;
    if (filter === "critical") return e.score >= 80;
    if (filter === "high") return e.score >= 60;
    if (filter === "bullish") return e.direction === "BULLISH";
    if (filter === "bearish") return e.direction === "BEARISH";
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
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: isLive ? "#30d158" : "#ff453a", animation: isLive ? "liveDot 1.5s ease-in-out infinite" : "none" }} />
              <span style={{ fontSize: 12, fontWeight: 600, color: isLive ? "#30d158" : "#ff453a", fontFamily: "'JetBrains Mono', monospace" }}>{isLive ? "LIVE" : "PAUSED"}</span>
            </div>
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

      {/* Filters */}
      <FilterBar filter={filter} setFilter={setFilter} threshold={threshold} setThreshold={setThreshold} />

      {/* Event Feed */}
      <div ref={feedRef} style={{ maxHeight: "calc(100vh - 260px)", overflowY: "auto" }}>
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