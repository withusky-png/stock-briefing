"""
아침 브리핑용 데이터 로더.
market_data.json (GitHub Actions가 생성) → 브리핑에 사용할 변수를 stdout으로 출력.
"""
import json, sys, subprocess

result = subprocess.run(
    ["python3", "scripts/read_market.py"],
    capture_output=True, text=True
)
if result.returncode != 0 or not result.stdout.strip():
    print(json.dumps({"error": "read_market.py 실패", "stderr": result.stderr[:200]}))
    sys.exit(1)

d = json.loads(result.stdout)
src = d.get("_load_source", "unknown")

def fmt_price(v, prefix="₩"):
    if v is None: return "?"
    return f"{prefix}{int(v):,}"

def fmt_chg(pct, arrow=True):
    if pct is None: return "?"
    sign = "▲" if pct >= 0 else "▼"
    cls = "up" if pct >= 0 else "down"
    s = f"{sign} {abs(pct):.2f}%" if arrow else f"{pct:+.2f}%"
    return s, cls

def fmt_flow(n):
    if n is None: return ("?", "flat")
    if n > 0: return (f"+{n:,}", "up")
    if n < 0: return (f"{n:,}", "down")
    return ("0", "flat")

out = {"source": src, "generated": d.get("generated"), "stocks": {}, "index": {}, "fx": {}, "sector": {}}

for code, sv in d.get("stocks", {}).items():
    chg_pct = sv.get("change_pct")
    chg_dir = "up" if (chg_pct or 0) >= 0 else "down"
    out["stocks"][code] = {
        **sv,
        "close_fmt": fmt_price(sv.get("close")),
        "prev_close_fmt": fmt_price(sv.get("prev_close")),
        "chg_str": f"{'+' if (chg_pct or 0)>=0 else ''}{chg_pct:.2f}%" if chg_pct is not None else "?",
        "chg_dir": chg_dir,
        "foreign_fmt": fmt_flow(sv.get("foreign_net")),
        "inst_fmt": fmt_flow(sv.get("inst_net")),
    }

for name, iv in d.get("index", {}).items():
    out["index"][name] = {**iv}

for name, fv in d.get("fx", {}).items():
    out["fx"][name] = {**fv}

out["sector"] = d.get("sector", {})

print(json.dumps(out, ensure_ascii=False, indent=2))
