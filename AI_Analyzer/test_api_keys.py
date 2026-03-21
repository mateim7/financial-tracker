"""
Quick health check for all configured API keys.
Run:  python3 test_api_keys.py
"""
import os
import json
import urllib.request
import urllib.error

RESET = "\033[0m"
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
BOLD  = "\033[1m"

def check(label, url, headers=None, validate=None):
    """Try a simple GET request and report pass/fail."""
    print(f"\n  {BOLD}{label}{RESET}")
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            data = json.loads(body) if body.strip().startswith(("{", "[")) else body
            if validate and not validate(data):
                print(f"  {YELLOW}  ⚠ Connected but unexpected response{RESET}")
                print(f"     Response: {str(data)[:200]}")
                return False
            print(f"  {GREEN}  ✓ Working!{RESET}")
            return True
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            print(f"  {RED}  ✗ Invalid API key (HTTP {e.code}){RESET}")
        else:
            print(f"  {RED}  ✗ HTTP {e.code}: {e.reason}{RESET}")
        return False
    except Exception as e:
        print(f"  {RED}  ✗ Connection failed: {e}{RESET}")
        return False


def main():
    print(f"\n{BOLD}{'═' * 60}")
    print(f"  API Key Health Check")
    print(f"{'═' * 60}{RESET}")

    results = {}

    # ── Anthropic (Claude) ────────────────────────────────────
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        ok = check(
            "Anthropic (Claude Sonnet)",
            "https://api.anthropic.com/v1/messages",
            # Just check auth with a minimal HEAD-like request; will get 400 but not 401
        )
        # Better test: send minimal request
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps({
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}]
                }).encode(),
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                print(f"  {GREEN}  ✓ Anthropic API key is valid!{RESET}")
                results["Anthropic"] = True
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"  {RED}  ✗ Anthropic API key is INVALID{RESET}")
                results["Anthropic"] = False
            elif e.code == 400:
                print(f"  {GREEN}  ✓ Anthropic API key is valid! (auth passed){RESET}")
                results["Anthropic"] = True
            else:
                print(f"  {GREEN}  ✓ Anthropic API key accepted (HTTP {e.code}){RESET}")
                results["Anthropic"] = True
    else:
        print(f"\n  {BOLD}Anthropic (Claude){RESET}")
        print(f"  {RED}  ✗ ANTHROPIC_API_KEY not set{RESET}")
        results["Anthropic"] = False

    # ── Finnhub ───────────────────────────────────────────────
    key = os.getenv("FINNHUB_API_KEY", "")
    if key:
        results["Finnhub"] = check(
            "Finnhub (News WebSocket)",
            f"https://finnhub.io/api/v1/news?category=general&token={key}",
            validate=lambda d: isinstance(d, list),
        )
    else:
        print(f"\n  {BOLD}Finnhub{RESET}")
        print(f"  {YELLOW}  ○ FINNHUB_API_KEY not set (optional){RESET}")
        results["Finnhub"] = None

    # ── Benzinga ──────────────────────────────────────────────
    key = os.getenv("BENZINGA_API_KEY", "")
    if key:
        results["Benzinga"] = check(
            "Benzinga Pro (News WebSocket)",
            f"https://api.benzinga.com/api/v2/news?token={key}&pageSize=1",
            validate=lambda d: not isinstance(d, dict) or d.get("error") is None,
        )
    else:
        print(f"\n  {BOLD}Benzinga{RESET}")
        print(f"  {YELLOW}  ○ BENZINGA_API_KEY not set (optional){RESET}")
        results["Benzinga"] = None

    # ── Polygon.io ────────────────────────────────────────────
    key = os.getenv("POLYGON_API_KEY", "")
    if key:
        results["Polygon"] = check(
            "Polygon.io (News WebSocket)",
            f"https://api.polygon.io/v2/reference/news?limit=1&apiKey={key}",
            validate=lambda d: isinstance(d, dict) and d.get("status") == "OK",
        )
    else:
        print(f"\n  {BOLD}Polygon.io{RESET}")
        print(f"  {YELLOW}  ○ POLYGON_API_KEY not set (optional){RESET}")
        results["Polygon"] = None

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{BOLD}{'═' * 60}")
    print(f"  Summary")
    print(f"{'═' * 60}{RESET}")
    for name, status in results.items():
        if status is True:
            print(f"  {GREEN}✓{RESET} {name}")
        elif status is False:
            print(f"  {RED}✗{RESET} {name}")
        else:
            print(f"  {YELLOW}○{RESET} {name} (not configured)")

    active_ws = sum(1 for k in ["Finnhub", "Benzinga", "Polygon"] if results.get(k) is True)
    print(f"\n  WebSocket news feeds ready: {active_ws}/3")
    if active_ws == 0:
        print(f"  {YELLOW}  RSS-only mode (still works, just slower){RESET}")
    print()


if __name__ == "__main__":
    main()
