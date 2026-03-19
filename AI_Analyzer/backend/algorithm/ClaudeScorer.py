import hashlib
import json
import re
import time
from backend.algorithm.Direction import Direction
from backend.algorithm.EventType import EventType
from backend.algorithm.ScoredEvent import ScoredEvent

class ClaudeScorer:
    # â”€â”€ Headlines that are almost never market-moving (skip Claude entirely) â”€â”€
    SKIP_PATTERNS = re.compile(
        r'(?i)('
        r'\d+\s+(best|top|worst)\s+(stock|etf|fund|pick)|'       # "10 best stocks to buy"
        r'(morning|evening|daily|weekly)\s+(brief|recap|wrap|roundup)|'  # newsletters
        r'(opinion|editorial|column|commentary)\s*[:\-â€“â€”]|'      # opinion pieces
        r'(things|reasons|tips|ways)\s+(to|you)|'                 # listicles
        r'should\s+you\s+(buy|sell|invest)|'                      # clickbait advice
        r'(what\s+is|how\s+to|beginner|explained|101)|'           # educational
        r'(podcast|video|interview|transcript|webinar)|'          # media formats
        r'(sponsored|promoted|partner\s+content|advertisement)'   # ads
        r')'
    )

    def __init__(self, known_tickers: set[str] = None, db=None):
        import os
        self._known_tickers = known_tickers or set()
        self._db = db  # Reference to database for historical context
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("  [Claude] ANTHROPIC_API_KEY not set â€” falling back to keyword scoring")
            self.client = None
        else:
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
            print("  [Claude] AsyncAnthropic loaded â€” truly async scoring enabled")

        # Token usage tracking
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_calls = 0
        self._calls_skipped = 0

        # Recent headline cache â€” avoid calling Claude for very similar headlines
        self._recent_headline_hashes: dict[str, float] = {}  # hash -> timestamp
        self._recent_headlines_semantic: dict[str, tuple[set, float]] = {}  # headline -> (ngrams, timestamp)

        # Calibration cache â€” refreshed every 30 min from signal outcomes DB
        self._calibration_cache: str = ""
        self._calibration_ts: float = 0

    def _get_calibration_context(self) -> str:
        """Build calibration feedback from historical signal outcomes.
        Tells Claude how well its previous confidence levels actually performed,
        so it can auto-tune its confidence scale."""
        now = time.time()
        # Refresh every 30 minutes
        if now - self._calibration_ts < 1800 and self._calibration_cache:
            return self._calibration_cache
        if not self._db:
            return ""
        try:
            # Query calibration by confidence bucket at 1d checkpoint
            buckets = {}
            if hasattr(self._db, 'con'):
                # SQLite path
                rows = self._db.con.execute(
                    "SELECT signal, confidence, pct_1d, outcome_1d "
                    "FROM signal_outcomes WHERE pct_1d IS NOT NULL"
                ).fetchall()
                for signal, conf, pct, outcome in rows:
                    bucket = (conf // 10) * 10  # 0-9, 10-19, ..., 90-100
                    key = (signal, bucket)
                    if key not in buckets:
                        buckets[key] = {"total": 0, "wins": 0, "sum_pct": 0.0}
                    buckets[key]["total"] += 1
                    if outcome == "WIN":
                        buckets[key]["wins"] += 1
                    buckets[key]["sum_pct"] += pct
            elif hasattr(self._db, 'client'):
                # Supabase path
                result = self._db.client.table("signal_outcomes").select(
                    "signal, confidence, pct_1d, outcome_1d"
                ).not_.is_("pct_1d", "null").execute()
                for row in (result.data or []):
                    bucket = (row["confidence"] // 10) * 10
                    key = (row["signal"], bucket)
                    if key not in buckets:
                        buckets[key] = {"total": 0, "wins": 0, "sum_pct": 0.0}
                    buckets[key]["total"] += 1
                    if row["outcome_1d"] == "WIN":
                        buckets[key]["wins"] += 1
                    buckets[key]["sum_pct"] += row["pct_1d"]

            if not buckets or sum(b["total"] for b in buckets.values()) < 10:
                return ""  # Not enough data yet

            lines = ["Historical confidence calibration (your past signals vs actual 1-day outcomes):"]
            for (signal, bucket), data in sorted(buckets.items()):
                if data["total"] < 3:
                    continue  # Skip buckets with too few samples
                win_rate = round(data["wins"] / data["total"] * 100, 1)
                avg_ret = round(data["sum_pct"] / data["total"], 2)
                expected = bucket + 5  # midpoint of bucket
                drift = round(win_rate - expected, 1)
                drift_str = f"{'overconfident' if drift < -5 else 'underconfident' if drift > 5 else 'calibrated'}"
                lines.append(
                    f"  {signal} {bucket}-{bucket+9}% confidence: actual win rate {win_rate}% "
                    f"(avg return {'+' if avg_ret >= 0 else ''}{avg_ret}%) "
                    f"[{data['total']} signals, {drift_str}]"
                )
            if len(lines) <= 1:
                return ""
            lines.append("Adjust your confidence scale based on this data. If you are overconfident in a range, lower your scores. If underconfident, raise them.")
            self._calibration_cache = "\n".join(lines)
            self._calibration_ts = now
            print(f"  [Calibration] Updated with {sum(b['total'] for b in buckets.values())} signal outcomes")
            return self._calibration_cache
        except Exception as e:
            print(f"  [Calibration] Error building calibration context: {e}")
            return ""

    def _headline_sim_hash(self, headline: str) -> str:
        """Coarse hash: strip numbers/punctuation so 'NVDA up 5%' and 'NVDA up 3%' match."""
        coarse = re.sub(r'[^a-z\s]', '', headline.lower())
        coarse = re.sub(r'\s+', ' ', coarse).strip()
        return hashlib.md5(coarse.encode()).hexdigest()

    def _headline_ngrams(self, headline: str) -> set[str]:
        """Extract word bigrams for semantic similarity comparison."""
        words = re.sub(r'[^a-z\s]', '', headline.lower()).split()
        # Remove common stop words that add noise to similarity
        stops = {"the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "for",
                 "on", "at", "by", "and", "or", "as", "its", "it", "this", "that", "with"}
        words = [w for w in words if w not in stops and len(w) > 1]
        if len(words) < 2:
            return set(words)
        return {f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)} | set(words)

    def _semantic_similarity(self, headline: str) -> tuple[float, str | None]:
        """Check if headline is semantically similar to any recent headline.
        Returns (max_similarity, matched_headline) using Jaccard similarity on word ngrams.
        Threshold: 0.55 = same story from different source."""
        ngrams = self._headline_ngrams(headline)
        if not ngrams:
            return 0.0, None
        best_sim = 0.0
        best_match = None
        for cached_headline, (cached_ngrams, _ts) in self._recent_headlines_semantic.items():
            if not cached_ngrams:
                continue
            intersection = len(ngrams & cached_ngrams)
            union = len(ngrams | cached_ngrams)
            sim = intersection / union if union > 0 else 0
            if sim > best_sim:
                best_sim = sim
                best_match = cached_headline
        return best_sim, best_match

    def _should_skip(self, headline: str, scored: ScoredEvent) -> str | None:
        """Return a skip reason string, or None if Claude should run."""
        # Skip listicles, opinion pieces, sponsored content, etc.
        if self.SKIP_PATTERNS.search(headline):
            return "headline matches skip pattern (opinion/listicle/ad)"

        now = time.time()

        # Clean old entries (30 min window)
        self._recent_headline_hashes = {k: v for k, v in self._recent_headline_hashes.items() if now - v < 1800}
        self._recent_headlines_semantic = {
            k: v for k, v in self._recent_headlines_semantic.items() if now - v[1] < 1800
        }

        # Skip if exact coarse hash match (existing behavior)
        h = self._headline_sim_hash(headline)
        if h in self._recent_headline_hashes:
            return "similar headline already scored in last 30 min"

        # Skip if semantically similar (new: catches same story from different sources)
        sim, matched = self._semantic_similarity(headline)
        if sim >= 0.55:
            return f"semantic duplicate (similarity {sim:.0%}) of: {matched[:60]}..."

        # Skip UNKNOWN event type with low automated score (borderline, likely noise)
        if scored.event_type == EventType.UNKNOWN and scored.impact_score < 50:
            return "UNKNOWN event type with low auto-score"

        return None

    def _get_historical_context(self, tickers: list[str]) -> str:
        """Query database for prior events mentioning the same tickers (last 30 days)."""
        if not self._db or not tickers:
            return ""
        try:
            cutoff = time.time() - (30 * 86400)  # 30 days
            prior_events = []
            if hasattr(self._db, 'client'):
                # Supabase path
                for ticker in tickers[:3]:  # limit to top 3 tickers
                    result = self._db.client.table("events").select(
                        "headline, event_type, direction, buy_signal, impact_score, timestamp"
                    ).ilike("affected_tickers", f"%{ticker}%").gte(
                        "timestamp", cutoff
                    ).order("timestamp", desc=True).limit(5).execute()
                    for row in (result.data or []):
                        prior_events.append(row)
            elif hasattr(self._db, 'con'):
                # SQLite path
                for ticker in tickers[:3]:
                    rows = self._db.con.execute(
                        "SELECT headline, event_type, direction, buy_signal, impact_score, timestamp "
                        "FROM events WHERE affected_tickers LIKE ? AND timestamp >= ? "
                        "ORDER BY timestamp DESC LIMIT 5",
                        (f"%{ticker}%", cutoff)
                    ).fetchall()
                    for row in rows:
                        prior_events.append({
                            "headline": row[0], "event_type": row[1], "direction": row[2],
                            "buy_signal": row[3], "impact_score": row[4], "timestamp": row[5],
                        })

            if not prior_events:
                return ""

            # Deduplicate by headline
            seen = set()
            unique = []
            for e in prior_events:
                h = e.get("headline", "")
                if h not in seen:
                    seen.add(h)
                    unique.append(e)

            if not unique:
                return ""

            # Format context
            lines = ["\nHistorical context (prior events for these tickers in the last 30 days):"]
            for e in unique[:5]:
                import datetime
                ts = e.get("timestamp", 0)
                date_str = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "?"
                lines.append(
                    f"  [{date_str}] {e.get('event_type', '?')} | {e.get('direction', '?')} | "
                    f"Score {e.get('impact_score', '?')} | {e.get('headline', '?')[:80]}"
                )
            lines.append("Use this context to avoid treating old/known events as new information.")
            return "\n".join(lines)
        except Exception as ex:
            print(f"  [Claude] Historical context lookup failed: {ex}")
            return ""

    @property
    def usage_stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "calls_skipped": self._calls_skipped,
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
            "estimated_cost_usd": round(
                (self._total_input_tokens * 3.0 / 1_000_000) +
                (self._total_output_tokens * 15.0 / 1_000_000), 4
            ),
        }

    async def enhance(self, scored: ScoredEvent, headline: str, body: str) -> ScoredEvent:
        """Call Claude to improve scoring fields. Falls back to original if unavailable."""
        if not self.client:
            return scored
        if scored.impact_score < 40:
            return scored

        # â”€â”€ Pre-Claude skip checks (saves tokens) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        skip_reason = self._should_skip(headline, scored)
        if skip_reason:
            self._calls_skipped += 1
            print(f"  [Claude] Skipped: {skip_reason}")
            return scored

        valid_types = [e.value for e in EventType]
        tickers_str = ", ".join(scored.affected_tickers) if scored.affected_tickers else "MACRO"

        # Build live price + volume context string for Claude
        price_context_parts = []
        if scored.price_data:
            for t, pd in scored.price_data.items():
                if pd.get("price") and pd.get("change_pct") is not None:
                    line = f"  {t}: ${pd['price']} ({pd['change_pct']:+.2f}% today)"
                    if pd.get("rvol") is not None:
                        rvol_label = "SURGING" if pd["rvol"] >= 2.0 else "HIGH" if pd["rvol"] >= 1.5 else "NORMAL" if pd["rvol"] >= 0.8 else "LOW"
                        line += f" | RVOL: {pd['rvol']}x ({rvol_label})"
                    price_context_parts.append(line)
        price_context = "\n".join(price_context_parts) if price_context_parts else "  (prices unavailable)"

        # Fetch historical context for these tickers
        historical_ctx = self._get_historical_context(scored.affected_tickers)

        # Build insider activity context for Claude â€” grouped by ticker with clear boundaries
        insider_parts = []
        if scored.insider_activity:
            for t, txs in scored.insider_activity.items():
                tx_lines = []
                for tx in txs[:3]:  # top 3 per ticker by value
                    val_str = f"${tx['value']:,.0f}" if tx['value'] else "N/A"
                    tx_lines.append(
                        f"    - {tx['name']} ({tx['title']}) â€” {tx['type']} â€” "
                        f"{tx['shares']:,} shares worth {val_str} â€” {tx['days_ago']}d ago"
                        f"{' [C-SUITE]' if tx['is_csuite'] else ''}"
                    )
                insider_parts.append(f"  [{t}] insider filings:\n" + "\n".join(tx_lines))
            # Also list tickers with NO insider activity so Claude doesn't cross-contaminate
            tickers_with_data = set(scored.insider_activity.keys())
            tickers_without = [t for t in (scored.affected_tickers or []) if t not in tickers_with_data]
            for t in tickers_without:
                insider_parts.append(f"  [{t}] insider filings: None")
        insider_context = "\n".join(insider_parts) if insider_parts else "  None (no recent Form 4 filings in last 14 days)"

        prompt = f"""You are a financial news analyst. Analyze this news headline and return ONLY a JSON object.

Headline: {headline}
Body: {body[:400] if body else "N/A"}
Affected tickers: {tickers_str}

Live market data (today's price action):
{price_context}

Recent SEC Form 4 insider activity (last 14 days):
{insider_context}
{historical_ctx}
{self._get_calibration_context()}

Current automated scoring:
- event_type: {scored.event_type.value}
- sentiment: {scored.sentiment}
- impact_score: {scored.impact_score}
- direction: {scored.direction.value}

Return JSON with these exact fields:
{{
  "event_type": one of {valid_types},
  "sentiment": float from -1.0 to 1.0,
  "impact_score": integer from 1 to 100,
  "direction": "BULLISH" or "BEARISH" or "NEUTRAL",
  "brief": one sentence summary of the market impact,
  "buy_signal": "BUY" or "HOLD" or "SELL",
  "buy_confidence": integer from 1 to 100. Be precise and granular â€” every value from 1 to 100 is valid. Do NOT round to multiples of 5 or 10. Think carefully and pick the exact number that reflects your conviction. Scale:
    1-10: extremely low conviction, near noise
    11-25: weak signal, high uncertainty
    26-40: below average conviction, significant risk
    41-49: borderline, slight lean
    50-64: moderate confidence, recommended consideration
    65-74: solid conviction, good risk/reward
    75-84: strong conviction, favorable setup
    85-94: high confidence, strong opportunity
    95-99: very high conviction, near certain
    100: absolute certainty (reserve only for unambiguous catalysts like FDA approval of blockbuster drug)
  "reasoning": array of 2-3 short strings, each one specific reason why this is a BUY/SELL/HOLD. Be concrete â€” mention numbers, catalysts, or comparisons. E.g. ["Revenue beat of 12% vs estimates signals demand inflection", "Guidance raised â€” rare for this sector in current macro environment"],
  "risk": one sentence on the single biggest risk that could invalidate this signal,
  "time_horizon": one of "intraday" or "swing (1-3d)" or "medium-term (1-4w)",
  "correlated_moves": array of up to 4 ticker strings (beyond the primary tickers) that are likely to move in sympathy or inverse â€” e.g. sector peers, suppliers, competitors. Only include real NYSE/NASDAQ tickers.
  "ticker_signals": object mapping each affected ticker AND each correlated_moves ticker to its own signal direction. CRITICAL: In macro/geopolitical events, different assets move in OPPOSITE directions due to capital rotation. You MUST analyze each ticker independently based on the ACTUAL content of the headline â€” not your assumptions about what "should" happen. Follow the COMMODITY CORRELATION CHAIN carefully:
   - Oil RISING â†’ BEARISH airlines (fuel costs up), BULLISH energy (XOM, CVX, OXY)
   - Oil FALLING â†’ BULLISH airlines (fuel costs down, DAL/UAL/AAL benefit), BEARISH energy
   - Dollar RISING â†’ BEARISH exporters/commodities, BULLISH importers
   - Interest rates RISING â†’ BEARISH growth/tech, BULLISH banks
   - Gold RISING â†’ risk-off signal, BEARISH equities broadly
   READ THE HEADLINE DIRECTION CAREFULLY: "Oil Falls" means oil is GOING DOWN, which is BULLISH for airlines. "Oil Surges" means oil is GOING UP, which is BEARISH for airlines. Do NOT confuse the direction.
   Format: {{"TICKER": {{"signal": "BUY" or "SELL" or "HOLD", "confidence": 1-100}}}}. If all tickers move the same direction, they should still each have an entry. Never apply a blanket signal to all tickers without considering how the event specifically impacts each one.
  "momentum_context": a short (1-2 sentence) explanation of how volume (RVOL) and price action align or conflict with the news signal. Example: "RVOL 2.3x confirms institutional buying pressure on bullish catalyst â€” high conviction move." or "Price down but RVOL low â€” market not reacting, signal may be noise." If RVOL data is unavailable, say "Volume data unavailable â€” signal based on news alone."
  "insider_context": a short (1-2 sentence) explanation of how SEC Form 4 insider activity (above) influenced your final signal. Example: "CEO open-market buy of $2.5M within 3 days of bullish catalyst â€” strong insider conviction confirms BUY thesis." or "CFO sold $4M while news is bullish â€” insider exit divergence, capping conviction." If no insider data is available, return an empty string "".
}}

CRITICAL RULES:

1. "Don't shoot the messenger": If the article is a macroeconomic warning, market commentary, analyst note, research report, or rating change, DO NOT include the ticker of the investment bank or analyst firm that authored the report. Examples:
- "Goldman Sachs warns of GDP drag" â†’ DO NOT include $GS.
- "JPMorgan downgrades VMC" â†’ DO NOT include $JPM.
- "Morgan Stanley expects rate cuts" â†’ DO NOT include $MS.

2. "No hallucinated associations": ONLY include tickers for companies that are explicitly mentioned in the article OR are direct competitors/suppliers/customers of the primary company. Do NOT include tickers just because you associate them with a concept in the article. Examples of what NOT to do:
- Article about "open-weight AI models" â†’ Do NOT add Hugging Face or any AI platform ticker that isn't mentioned.
- Article about "cloud computing" â†’ Do NOT add random cloud companies that aren't discussed.
- A person endorsing a company â†’ Do NOT add that person's company unless the article discusses impact on it.

3. "Respect the tape": The live market data above shows how each stock is ACTUALLY trading right now. If a stock is up significantly (+3% or more) today, do NOT issue a SELL signal on it unless you have extremely high conviction (85%+) â€” you would be telling someone to short a stock with strong buying momentum, which is extremely dangerous. Conversely, if a stock is down significantly (-3% or more), be cautious about issuing a BUY signal. Price action reflects information you may not have. When the tape contradicts your thesis, default to HOLD or reduce confidence substantially.

4. "Tape Validation Matrix" â€” Cross-reference the news sentiment against BOTH price action AND volume (RVOL) to validate or invalidate signals:
   - BULLISH news + Price UP + RVOL HIGH (â‰¥1.5x): CONFIRMED momentum â€” increase confidence by 10-15 points. Institutional money is backing the move.
   - BULLISH news + Price UP + RVOL LOW (<0.8x): WEAK confirmation â€” reduce confidence by 5-10 points. Move lacks volume conviction, could be retail-driven.
   - BULLISH news + Price DOWN + RVOL HIGH: DIVERGENCE â€” default to HOLD. Smart money may be selling into the news. Flag as contrarian risk.
   - BULLISH news + Price DOWN + RVOL LOW: NO REACTION â€” reduce confidence by 15-20 points. Market doesn't care about this catalyst.
   - BEARISH news + Price DOWN + RVOL HIGH: CONFIRMED selloff â€” increase confidence for SELL. Institutional distribution confirmed.
   - BEARISH news + Price DOWN + RVOL LOW: Orderly decline, may be priced in. Moderate confidence.
   - BEARISH news + Price UP + RVOL HIGH: DIVERGENCE â€” default to HOLD. Market disagrees with the bearish thesis.
   - BEARISH news + Price UP + RVOL LOW: Ignore the dip-buyer noise, but don't fight confirmed uptrend.

5. "The C-Suite Multiplier" â€” If the news is BULLISH and the SEC Form 4 data above shows a significant (> $250,000) Open-Market BUY from a C-Level executive (CEO, CFO, COO, President) within the last 14 days, this is a "Holy Grail" setup. Upgrade buy_confidence heavily to 85-100 range. C-suite insiders buying with their own money on the open market, timed with a bullish catalyst, is one of the strongest confirming signals in finance.

6. "The Contrarian Red Flag" â€” If the news is BULLISH but the SEC Form 4 data shows massive (> $500,000) Open-Market SELLS from C-suite or multiple insiders, this is an "Insider Exit Divergence." Cap buy_confidence at 60 maximum, and add a warning in the insider_context about insider selling contradicting the bullish narrative. Insiders know their company better than any analyst â€” if they're dumping while headlines are positive, respect their actions over the words.

7. "No Insider Cross-Contamination" â€” The SEC insider data above is grouped by ticker in [TICKER] brackets. Each insider is an executive of THAT specific company ONLY. Do NOT attribute one company's insider activity to a different company. For example, if [AI] shows "Thomas Siebel (CEO) sold $6.8M," that is the CEO of C3.ai ($AI) â€” it has ZERO relevance to Palantir ($PLTR) or any other ticker. Only apply insider data to the EXACT ticker it is filed under. If a ticker shows "None," it means that company has NO recent insider activity.

8. "Symmetrical Volume Veto" â€” RVOL is the ultimate arbiter of institutional conviction for BOTH bullish AND bearish signals. If a ticker's RVOL < 0.8x, the market exhibits "Dead Tape" (no institutional participation). You MUST default to HOLD with confidence between 20-45 for that ticker. Do NOT issue BUY or SELL on dead tape. The ONLY exception is Tier-1 hard catalysts: unexpected Earnings Beat/Miss, unannounced M&A, FDA approval/rejection, or bankruptcy.

9. "Global Score Aggregator" â€” Your impact_score must be the mathematical average of the individual ticker_signals confidence scores, NOT a qualitative mood score of the headline text. If two tickers score 74 and 30, the impact_score must be 52, not 74.

10. "BUY on Red Tape" â€” NEVER issue a BUY on a stock that is currently DOWN. A falling price means the market is telling you something. Rules:
   - Price DOWN more than -3%: HOLD, max confidence 30. This is a falling knife.
   - Price DOWN -1% to -3% + RVOL HIGH (â‰¥1.5x): HOLD, max confidence 25. High volume selling = confirmed institutional distribution. This is the WORST setup for a BUY.
   - Price DOWN -1% to -3% + RVOL NORMAL (0.8-1.5x): HOLD, max confidence 40. Declining on real participation.
   - Price DOWN 0% to -1% + RVOL HIGH (â‰¥1.5x): HOLD, max confidence 50. Mild red but institutions may be distributing.
   - Price DOWN 0% to -1% + RVOL NORMAL: BUY allowed but cap confidence at 55.
   There are NO exceptions â€” even Tier-1 catalysts (earnings beat, FDA approval) can be "sell the news" events where institutions dump into retail buying liquidity. The tape is always the final arbiter.

Only include the tickers of companies, sectors, commodities, or ETFs that are actually AFFECTED by the news.

Only correct other scoring fields where automated scoring is clearly wrong. Return valid JSON only."""

        try:
            response = await self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )

            # Track token usage with per-call cost breakdown
            self._total_calls += 1
            call_in = 0
            call_out = 0
            if hasattr(response, 'usage'):
                call_in = getattr(response.usage, 'input_tokens', 0)
                call_out = getattr(response.usage, 'output_tokens', 0)
                self._total_input_tokens += call_in
                self._total_output_tokens += call_out
            call_cost = (call_in * 3.0 / 1_000_000) + (call_out * 15.0 / 1_000_000)
            total_cost = (self._total_input_tokens * 3.0 / 1_000_000) + (self._total_output_tokens * 15.0 / 1_000_000)

            # Detect truncation â€” if stop_reason is "max_tokens", output was cut off
            stop_reason = getattr(response, 'stop_reason', None)
            was_truncated = stop_reason == "max_tokens"
            trunc_tag = " [TRUNCATED!]" if was_truncated else ""

            print(f"  [Claude] Call #{self._total_calls} | {call_in:,} in + {call_out:,} out = ${call_cost:.4f}{trunc_tag} | "
                  f"Session total: ${total_cost:.4f} ({self._total_calls} calls) | "
                  f"{headline[:50]}...")

            # Cache this headline to avoid duplicate calls
            self._recent_headline_hashes[self._headline_sim_hash(headline)] = time.time()
            self._recent_headlines_semantic[headline] = (self._headline_ngrams(headline), time.time())

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            # â”€â”€ Truncation recovery â”€â”€
            # If the JSON was cut off mid-generation, try to salvage it by closing
            # open braces/brackets. This recovers partial but usable data.
            data = None
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                if was_truncated:
                    print(f"  [Claude] Attempting truncation recovery...")
                    # Try closing the JSON by appending missing brackets
                    repaired = text.rstrip().rstrip(",")
                    # Count unclosed braces and brackets
                    open_braces = repaired.count("{") - repaired.count("}")
                    open_brackets = repaired.count("[") - repaired.count("]")
                    # Check if we're inside a string (odd number of unescaped quotes)
                    if repaired.count('"') % 2 != 0:
                        repaired += '"'
                    repaired += "]" * max(0, open_brackets)
                    repaired += "}" * max(0, open_braces)
                    try:
                        data = json.loads(repaired)
                        print(f"  [Claude] Truncation recovery succeeded â€” partial data extracted")
                    except json.JSONDecodeError:
                        print(f"  [Claude] Truncation recovery failed â€” using automated scores")
                else:
                    raise

            if data is None:
                raise ValueError("Could not parse Claude response")

            if data.get("event_type") in valid_types:
                scored.event_type = EventType(data["event_type"])
            if isinstance(data.get("sentiment"), (int, float)):
                scored.sentiment = max(-1.0, min(1.0, float(data["sentiment"])))
            if isinstance(data.get("impact_score"), (int, float)):
                scored.impact_score = max(1, min(100, int(data["impact_score"])))
            if data.get("direction") in ("BULLISH", "BEARISH", "NEUTRAL"):
                scored.direction = Direction(data["direction"])
            if data.get("brief"):
                scored.brief = str(data["brief"])
            if data.get("buy_signal") in ("BUY", "HOLD", "SELL"):
                scored.buy_signal = data["buy_signal"]
            if isinstance(data.get("buy_confidence"), (int, float)):
                scored.buy_confidence = max(0, min(100, int(data["buy_confidence"])))
            if isinstance(data.get("reasoning"), list):
                scored.reasoning = [str(r) for r in data["reasoning"][:3]]
            if data.get("risk"):
                scored.risk = str(data["risk"])
            if data.get("time_horizon"):
                scored.time_horizon = str(data["time_horizon"])
            if isinstance(data.get("correlated_moves"), list):
                validated = []
                for t in data["correlated_moves"][:6]:
                    t = str(t).upper()
                    if self._known_tickers and t not in self._known_tickers:
                        print(f"  [Claude] Rejected hallucinated ticker: {t}")
                        continue
                    validated.append(t)
                scored.correlated_moves = validated[:4]
            if isinstance(data.get("ticker_signals"), dict):
                ts = {}
                for t, v in data["ticker_signals"].items():
                    t = str(t).upper()
                    if self._known_tickers and t not in self._known_tickers:
                        print(f"  [Claude] Rejected hallucinated ticker signal: {t}")
                        continue
                    if isinstance(v, dict) and v.get("signal") in ("BUY", "SELL", "HOLD"):
                        ts[t] = {
                            "signal": v["signal"],
                            "confidence": max(1, min(100, int(v.get("confidence", scored.buy_confidence)))),
                        }
                if ts:
                    scored.ticker_signals = ts
            if data.get("momentum_context"):
                scored.momentum_context = str(data["momentum_context"])
            if data.get("insider_context"):
                ic = str(data["insider_context"]).strip()
                # Strip useless "no data" responses â€” frontend doesn't need them
                if ic and "no recent insider" not in ic.lower() and "none" != ic.lower():
                    scored.insider_context = ic

            # â”€â”€ FIRST-PASS SCORE AGGREGATOR â”€â”€
            # Enforce Rule 9 immediately: impact_score = avg(ticker_signals confidences)
            # so all downstream logic uses the corrected score, not Claude's raw guess.
            if scored.ticker_signals:
                confs = [sig.get("confidence", 50) for sig in scored.ticker_signals.values()]
                enforced_score = round(sum(confs) / len(confs))
                if enforced_score != scored.impact_score:
                    print(f"  [Rule9] First-pass score correction: {scored.impact_score} â†’ {enforced_score} "
                          f"(avg of {len(confs)} ticker confidences: {confs})")
                    scored.impact_score = enforced_score

        except Exception as e:
            print(f"  [Claude] Scoring error: {e}")

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        # POST-CLAUDE HARD ENFORCEMENT â€” overrides Claude when data contradicts
        # These are programmatic safety nets that cannot be ignored by the LLM.
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

        # â”€â”€ INSIDER RED FLAG ENFORCEMENT â”€â”€
        # If insiders are dumping heavily while Claude says BUY, cap confidence
        if scored.insider_activity and scored.buy_signal == "BUY":
            total_insider_sells = 0
            has_csuite_sell = False
            for t, txs in scored.insider_activity.items():
                for tx in txs:
                    if tx.get("type") == "Open-Market Sale":
                        total_insider_sells += tx.get("value", 0)
                        if tx.get("is_csuite"):
                            has_csuite_sell = True

            if total_insider_sells > 500_000:
                old_conf = scored.buy_confidence
                scored.buy_confidence = min(scored.buy_confidence, 60)
                if old_conf > 60:
                    print(f"  [Enforce] Insider Red Flag: ${total_insider_sells:,.0f} in insider sells "
                          f"â†’ capped BUY confidence {old_conf} â†’ {scored.buy_confidence}")
                    if not scored.insider_context or "divergence" not in scored.insider_context.lower():
                        scored.insider_context = (
                            f"INSIDER EXIT DIVERGENCE: ${total_insider_sells:,.0f} in open-market insider "
                            f"sales detected in last 14 days while news is bullish. "
                            f"{'C-suite executives are among the sellers. ' if has_csuite_sell else ''}"
                            f"Conviction capped â€” insiders know their company better than headlines."
                        )
                # Also cap per-ticker signals
                for tk, sig in scored.ticker_signals.items():
                    if sig.get("signal") == "BUY" and sig.get("confidence", 0) > 60:
                        scored.ticker_signals[tk]["confidence"] = min(sig["confidence"], 60)

            # If total sells > $2M, downgrade to HOLD entirely
            if total_insider_sells > 2_000_000 and scored.buy_signal == "BUY":
                old_signal = scored.buy_signal
                scored.buy_signal = "HOLD"
                scored.buy_confidence = min(scored.buy_confidence, 45)
                print(f"  [Enforce] Massive insider dump ${total_insider_sells:,.0f} â†’ downgraded {old_signal} â†’ HOLD")
                scored.insider_context = (
                    f"CRITICAL INSIDER EXIT: ${total_insider_sells:,.0f} in insider sales over 14 days. "
                    f"Signal forcibly downgraded to HOLD â€” when C-suite dumps this aggressively "
                    f"while headlines are bullish, it's a classic retail trap."
                )
                for tk, sig in scored.ticker_signals.items():
                    if sig.get("signal") == "BUY":
                        scored.ticker_signals[tk] = {"signal": "HOLD", "confidence": min(sig.get("confidence", 45), 45)}

        # â”€â”€ C-SUITE MULTIPLIER ENFORCEMENT â”€â”€
        # If insiders are buying heavily alongside bullish news, boost confidence
        if scored.insider_activity and scored.buy_signal == "BUY":
            total_csuite_buys = 0
            for t, txs in scored.insider_activity.items():
                for tx in txs:
                    if tx.get("type") == "Open-Market Buy" and tx.get("is_csuite"):
                        total_csuite_buys += tx.get("value", 0)

            if total_csuite_buys > 250_000:
                old_conf = scored.buy_confidence
                scored.buy_confidence = max(scored.buy_confidence, 85)
                if old_conf < 85:
                    print(f"  [Enforce] C-Suite Multiplier: ${total_csuite_buys:,.0f} C-suite buys "
                          f"â†’ boosted BUY confidence {old_conf} â†’ {scored.buy_confidence}")

        # â”€â”€ TAPE CONTRADICTION ENFORCEMENT â”€â”€
        # Checks ALL tickers with signals (affected + correlated + ticker_signals)
        all_signal_tickers = set(scored.affected_tickers)
        all_signal_tickers.update(scored.ticker_signals.keys())

        if scored.price_data:
            for t in all_signal_tickers:
                pd = scored.price_data.get(t)
                if not pd:
                    continue
                change = pd.get("change_pct")
                rvol = pd.get("rvol")
                ts = scored.ticker_signals.get(t, {})
                ticker_signal = ts.get("signal", scored.buy_signal if t in scored.affected_tickers else None)
                ticker_conf = ts.get("confidence", scored.buy_confidence)

                # â”€â”€ SELL on green stock: don't short a stock that's rising â”€â”€
                if ticker_signal == "SELL" and change is not None and change > 0:
                    # Aggressive override for strong runners (+3%+), softer for mild green
                    if change >= 3.0:
                        new_conf = min(ticker_conf, 30)
                    elif change >= 1.0:
                        new_conf = min(ticker_conf, 40)
                    else:
                        new_conf = min(ticker_conf, 50)
                    print(f"  [Enforce] Fighting the tape: SELL {t} at {change:+.2f}% "
                          f"â†’ overriding to HOLD (conf {ticker_conf} â†’ {new_conf})")
                    if t in scored.ticker_signals:
                        scored.ticker_signals[t] = {"signal": "HOLD", "confidence": new_conf}
                    if t in scored.affected_tickers and scored.buy_signal == "SELL":
                        scored.buy_signal = "HOLD"
                        scored.buy_confidence = new_conf

                # â”€â”€ Tier-1 catalyst exception (shared by BUY-on-red and Volume Veto) â”€â”€
                TIER1_CATALYSTS = {
                    "EARNINGS_BEAT", "EARNINGS_MISS", "FDA_APPROVAL", "FDA_REJECTION",
                    "MA_ANNOUNCED", "MA_COMPLETED", "MA_BLOCKED", "BANKRUPTCY",
                    "STOCK_SPLIT", "BUYBACK_ANNOUNCED",
                }
                is_tier1 = scored.event_type in TIER1_CATALYSTS if hasattr(scored, 'event_type') else False

                # â”€â”€ BUY on red stock: don't buy a stock that's falling â”€â”€
                # High RVOL on a red stock is WORSE â€” it confirms institutional distribution
                # NO EXCEPTIONS â€” even Tier-1 catalysts (earnings, FDA) can be "sell the news"
                # events where institutions dump into retail buying liquidity
                if ticker_signal == "BUY" and change is not None and change < 0:
                    if change <= -3.0:
                        # Deep red: never BUY regardless of volume
                        new_conf = min(ticker_conf, 30)
                    elif change <= -1.0:
                        if rvol is not None and rvol >= 1.5:
                            # Red + high volume = confirmed institutional selling
                            new_conf = min(ticker_conf, 25)
                        elif rvol is not None and rvol >= 0.8:
                            # Red + normal volume = declining on real participation
                            new_conf = min(ticker_conf, 40)
                        else:
                            # Red + low volume = drift, caught by volume veto too
                            new_conf = min(ticker_conf, 35)
                    else:
                        # Mild red (0 to -1%)
                        if rvol is not None and rvol >= 1.5:
                            # Mild red + high volume = caution, institutions may be selling
                            new_conf = min(ticker_conf, 50)
                        elif rvol is not None and rvol >= 0.8:
                            # Mild red + normal volume = soft weakness
                            new_conf = min(ticker_conf, 55)
                        else:
                            # Mild red + low volume â†’ volume veto handles this
                            new_conf = min(ticker_conf, 45)
                    print(f"  [Enforce] BUY on red tape: {t} at {change:+.2f}% RVOL {rvol}x "
                          f"â†’ overriding to HOLD (conf {ticker_conf} â†’ {new_conf})")
                    if t in scored.ticker_signals:
                        scored.ticker_signals[t] = {"signal": "HOLD", "confidence": new_conf}
                    if t in scored.affected_tickers and scored.buy_signal == "BUY":
                        scored.buy_signal = "HOLD"
                        scored.buy_confidence = new_conf

                # â”€â”€ SYMMETRICAL VOLUME VETO â”€â”€
                # RVOL < 0.8x = Dead Tape â†’ force HOLD, cap 45, floor 20
                # Exception: Tier-1 hard catalysts (uses is_tier1 from above)
                if rvol is not None and rvol < 0.8 and not is_tier1:
                    if ticker_signal in ("BUY", "SELL"):
                        new_conf = max(20, min(ticker_conf, 45))
                        print(f"  [Enforce] Symmetrical Volume Veto for {t}: RVOL {rvol}x < 0.8 "
                              f"â†’ {ticker_signal} overridden to HOLD (conf {ticker_conf} â†’ {new_conf})")
                        if t in scored.ticker_signals:
                            scored.ticker_signals[t] = {"signal": "HOLD", "confidence": new_conf}
                        if t in scored.affected_tickers:
                            scored.buy_signal = "HOLD"
                            scored.buy_confidence = new_conf
                        if not scored.momentum_context or "dead tape" not in scored.momentum_context.lower():
                            scored.momentum_context = (
                                f"Dead tape on {t}: RVOL {rvol}x â€” no institutional participation. "
                                f"Price moves are noise, not conviction. Signal vetoed to HOLD."
                            )

        # Fix "Missing Main Character": if entity extraction found no primary tickers
        # but Claude identified tickers in correlated_moves/ticker_signals, promote
        # the highest-confidence ticker to affected_tickers (primary).
        if not scored.affected_tickers and scored.correlated_moves:
            if scored.ticker_signals:
                # Sort by confidence descending, promote the top ticker
                ranked = sorted(
                    scored.ticker_signals.items(),
                    key=lambda x: x[1].get("confidence", 0),
                    reverse=True,
                )
                if ranked:
                    primary = ranked[0][0]
                    scored.affected_tickers = [primary]
                    # Remove from correlated_moves so it's not listed twice
                    scored.correlated_moves = [t for t in scored.correlated_moves if t != primary]
                    print(f"  [Fix] Promoted {primary} from correlated to primary ticker")
            elif scored.correlated_moves:
                # No ticker_signals, just promote the first correlated move
                primary = scored.correlated_moves[0]
                scored.affected_tickers = [primary]
                scored.correlated_moves = scored.correlated_moves[1:]
                print(f"  [Fix] Promoted {primary} from correlated to primary ticker (no signals)")

        return scored

    async def validate_buy(self, scored: ScoredEvent, corroborating: list[dict]) -> ScoredEvent:
        """Second Claude call to validate BUY signal using corroborating sources.
        Uses Haiku for this simple yes/no task â€” ~20x cheaper than Sonnet."""
        if not self.client or not corroborating:
            return scored
        headlines = "\n".join(f"- [{a['source']}] {a['headline']}" for a in corroborating[:3])
        prompt = f"""A financial screener flagged this as a BUY at {scored.buy_confidence}% confidence:

Primary article: {scored.headline}
Affected tickers: {', '.join(scored.affected_tickers) or 'MACRO'}

Other sources covering the same story:
{headlines}

Return ONLY JSON:
{{
  "adjusted_confidence": integer 1-100 (adjust up if sources confirm, down if they contradict or add risk),
  "validation_note": one sentence on what the other sources add or change
}}"""
        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",  # Haiku: cheaper for simple validation
                max_tokens=120,
                messages=[{"role": "user", "content": prompt}]
            )
            # Track tokens with per-call cost (Haiku pricing: $0.80/$4.00 per 1M tokens)
            self._total_calls += 1
            call_in = 0
            call_out = 0
            if hasattr(response, 'usage'):
                call_in = getattr(response.usage, 'input_tokens', 0)
                call_out = getattr(response.usage, 'output_tokens', 0)
                self._total_input_tokens += call_in
                self._total_output_tokens += call_out
            call_cost = (call_in * 0.80 / 1_000_000) + (call_out * 4.0 / 1_000_000)
            total_cost = (self._total_input_tokens * 3.0 / 1_000_000) + (self._total_output_tokens * 15.0 / 1_000_000)
            print(f"  [Claude] Validation call #{self._total_calls} (Haiku) | {call_in:,} in + {call_out:,} out = ${call_cost:.4f} | "
                  f"Session total: ${total_cost:.4f}")
            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            if isinstance(data.get("adjusted_confidence"), (int, float)):
                scored.buy_confidence = max(1, min(100, int(data["adjusted_confidence"])))
            if data.get("validation_note"):
                scored.brief = (scored.brief + " | " + data["validation_note"]) if scored.brief else data["validation_note"]
        except Exception as e:
            print(f"  [Claude] Validation error: {e}")
        return scored


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# STOCK AVAILABILITY CHECKER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


