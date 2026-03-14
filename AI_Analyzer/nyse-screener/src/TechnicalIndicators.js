import "./TechnicalIndicators.css";

/* ── RSI Gauge ───────────────────────────────────────────────────────────── */

function RSIGauge({ rsi }) {
  if (!rsi || rsi.value == null) return null;

  const value = rsi.value;
  const label = rsi.label;

  // Color based on RSI zone
  let color, bg;
  if (value >= 70) {
    color = "#d63031"; bg = "#fdeaea"; // overbought
  } else if (value <= 30) {
    color = "#1a9d4a"; bg = "#e8f9ef"; // oversold
  } else if (value >= 60) {
    color = "#f5a623"; bg = "#fff3e0"; // bullish leaning
  } else if (value <= 40) {
    color = "#0066ff"; bg = "#eef4ff"; // bearish leaning
  } else {
    color = "#8e8e93"; bg = "#f0f0f5"; // neutral
  }

  // Gauge position (0-100 mapped to bar width)
  const position = Math.min(Math.max(value, 0), 100);

  return (
    <div className="ti-indicator">
      <div className="ti-indicator-header">
        <span className="ti-indicator-name">RSI</span>
        <span className="ti-indicator-value" style={{ color }}>{value}</span>
      </div>
      <div className="ti-rsi-bar">
        <div className="ti-rsi-zone oversold" />
        <div className="ti-rsi-zone neutral" />
        <div className="ti-rsi-zone overbought" />
        <div className="ti-rsi-needle" style={{ left: `${position}%` }} />
      </div>
      <span className="ti-indicator-label" style={{ color, background: bg }}>{label}</span>
    </div>
  );
}

/* ── MACD Badge ──────────────────────────────────────────────────────────── */

function MACDBadge({ macd }) {
  if (!macd) return null;

  const { histogram, crossover } = macd;
  const bullish = histogram > 0;

  let crossLabel = null;
  if (crossover === "BULLISH") {
    crossLabel = <span className="ti-macd-cross bullish">Bullish Cross</span>;
  } else if (crossover === "BEARISH") {
    crossLabel = <span className="ti-macd-cross bearish">Bearish Cross</span>;
  }

  return (
    <div className="ti-indicator">
      <div className="ti-indicator-header">
        <span className="ti-indicator-name">MACD</span>
        <span className="ti-indicator-value" style={{ color: bullish ? "#1a9d4a" : "#d63031" }}>
          {histogram > 0 ? "+" : ""}{histogram.toFixed(2)}
        </span>
      </div>
      <div className="ti-macd-bars">
        <div className="ti-macd-item">
          <span className="ti-macd-label">MACD</span>
          <span className="ti-macd-val">{macd.macd.toFixed(2)}</span>
        </div>
        <div className="ti-macd-item">
          <span className="ti-macd-label">Signal</span>
          <span className="ti-macd-val">{macd.signal.toFixed(2)}</span>
        </div>
        {crossLabel}
      </div>
    </div>
  );
}

/* ── Volume Badge ────────────────────────────────────────────────────────── */

function VolumeBadge({ volume }) {
  if (!volume) return null;

  const { ratio, spike, current, avg_20d } = volume;

  const formatVol = (v) => {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
    return v.toString();
  };

  return (
    <div className="ti-indicator">
      <div className="ti-indicator-header">
        <span className="ti-indicator-name">Volume</span>
        <span className="ti-indicator-value" style={{ color: spike ? "#d63031" : "#8e8e93" }}>
          {ratio}x
        </span>
      </div>
      <div className="ti-volume-info">
        <span className="ti-vol-current">{formatVol(current)}</span>
        <span className="ti-vol-vs">vs avg</span>
        <span className="ti-vol-avg">{formatVol(avg_20d)}</span>
        {spike && <span className="ti-vol-spike">SPIKE</span>}
      </div>
    </div>
  );
}

/* ── Overall Technical Signal ────────────────────────────────────────────── */

function TechSignalBadge({ techSignal, strength, volumeConfirms }) {
  if (!techSignal) return null;

  const cfg = {
    BULLISH:  { icon: "↑", color: "#1a9d4a", bg: "#e8f9ef", label: "Bullish" },
    BEARISH:  { icon: "↓", color: "#d63031", bg: "#fdeaea", label: "Bearish" },
    NEUTRAL:  { icon: "–", color: "#8e8e93", bg: "#f0f0f5", label: "Neutral" },
  };
  const c = cfg[techSignal] || cfg.NEUTRAL;

  return (
    <div className="ti-tech-signal" style={{ background: c.bg, borderColor: c.color }}>
      <span className="ti-tech-icon" style={{ color: c.color }}>{c.icon}</span>
      <div className="ti-tech-text">
        <span className="ti-tech-label" style={{ color: c.color }}>
          Tech: {c.label}
        </span>
        <span className="ti-tech-strength">{strength}% alignment</span>
      </div>
      {volumeConfirms && <span className="ti-vol-confirm">Vol Confirms</span>}
    </div>
  );
}

/* ── Main Overlay Component ──────────────────────────────────────────────── */

export default function TechnicalIndicatorsOverlay({ data }) {
  if (!data || !data.available) return null;

  return (
    <div className="ti-overlay">
      <div className="ti-overlay-header">
        <span className="ti-overlay-title">Technical Indicators</span>
        <TechSignalBadge techSignal={data.tech_signal} strength={data.strength}
          volumeConfirms={data.volume_confirms} />
      </div>
      <div className="ti-indicators-row">
        <RSIGauge rsi={data.rsi} />
        <MACDBadge macd={data.macd} />
        <VolumeBadge volume={data.volume} />
      </div>
    </div>
  );
}

/* ── Compact inline version for ticker pills ─────────────────────────────── */

export function TechMiniBadge({ data }) {
  if (!data || !data.available) return null;

  const cfg = {
    BULLISH:  { icon: "↑", color: "#1a9d4a", bg: "#e8f9ef" },
    BEARISH:  { icon: "↓", color: "#d63031", bg: "#fdeaea" },
    NEUTRAL:  { icon: "–", color: "#8e8e93", bg: "#f0f0f5" },
  };
  const c = cfg[data.tech_signal] || cfg.NEUTRAL;

  const parts = [];
  if (data.rsi?.value != null) parts.push(`RSI ${data.rsi.value}`);
  if (data.macd?.crossover && data.macd.crossover !== "NONE") parts.push(`MACD ${data.macd.crossover}`);
  if (data.volume?.spike) parts.push("Vol Spike");

  return (
    <span className="ti-mini" style={{ color: c.color, background: c.bg }}
      title={parts.join(" · ")}>
      {c.icon} {data.rsi?.value != null ? `RSI ${data.rsi.value}` : "Tech"}
      {data.volume?.spike && " ⚡"}
    </span>
  );
}
