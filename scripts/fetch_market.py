"""
GitHub Actions에서 실행 — yfinance로 시장 데이터 수집 후 market_data.json 저장
Claude Code 환경에서는 GitHub raw로 읽음 (직접 외부 호출 불가)
"""
import json, sys, time, re, urllib.request
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed"); sys.exit(1)

t0 = time.time()
KST_NOW = datetime.utcnow() + timedelta(hours=9)
DATE_KST = KST_NOW.strftime("%Y-%m-%d")
HDR = {"User-Agent": "Mozilla/5.0 (compatible; stock-briefing-bot/1.0)"}

TICKERS = {
    "005930": {"name": "삼성전자",    "yf": "005930.KS"},
    "034020": {"name": "두산에너빌리티","yf": "034020.KS"},
    "023160": {"name": "태광",        "yf": "023160.KQ"},
    "062040": {"name": "산일전기",    "yf": "062040.KS"},
    "006400": {"name": "삼성SDI",     "yf": "006400.KS"},
}

result = {
    "generated": KST_NOW.isoformat(),
    "date": DATE_KST,
    "stocks": {c: {"name": v["name"], "code": c} for c, v in TICKERS.items()},
    "index": {},
    "fx": {},
    "sector": {},
    "source": "yfinance (GitHub Actions)",
}


def fetch_stock(code_info):
    code, info = code_info
    try:
        tk = yf.Ticker(info["yf"])
        hist = tk.history(period="5d")
        if len(hist) >= 2:
            l, p = hist.iloc[-1], hist.iloc[-2]
            chg = float(l["Close"] - p["Close"])
            chg_pct = round(chg / p["Close"] * 100, 2)
            return code, {
                "close": round(float(l["Close"])),
                "prev_close": round(float(p["Close"])),
                "change": round(chg),
                "change_pct": chg_pct,
                "volume": int(l["Volume"]),
                "high": round(float(l["High"])),
                "low": round(float(l["Low"])),
                "as_of": hist.index[-1].strftime("%Y-%m-%d"),
            }
    except Exception as e:
        return code, {"err": str(e)[:80]}
    return code, {}


def fetch_index(sym_name):
    sym, name = sym_name
    try:
        tk = yf.Ticker(sym)
        hist = tk.history(period="5d")
        if len(hist) >= 2:
            l, p = hist.iloc[-1], hist.iloc[-2]
            return name, {
                "close": round(float(l["Close"]), 2),
                "change_pct": round((l["Close"] - p["Close"]) / p["Close"] * 100, 2),
                "as_of": hist.index[-1].strftime("%Y-%m-%d"),
            }
    except Exception:
        pass
    return name, {}


def naver_frgn(code):
    """Naver 외국인/기관 순매수 (GitHub Actions는 Naver 접근 가능)"""
    url = f"https://finance.naver.com/item/frgn.naver?code={code}"
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("euc-kr", errors="ignore")
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL)
        for row in rows:
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if len(cells) >= 8:
                txts = [re.sub(r"<[^>]+>", "", x).replace(",", "").strip() for x in cells]
                if not txts[0] or not re.match(r"\d{4}", txts[0]):
                    continue
                try:
                    inst = int(txts[5]) if re.match(r"^-?\d+$", txts[5]) else None
                    frg = int(txts[6]) if re.match(r"^-?\d+$", txts[6]) else None
                    if inst is not None and frg is not None:
                        return code, {"inst_net": inst, "foreign_net": frg, "date": txts[0]}
                except Exception:
                    continue
    except Exception as e:
        return code, {"err": str(e)[:60]}
    return code, {}


with ThreadPoolExecutor(max_workers=16) as ex:
    fs = [ex.submit(fetch_stock, x) for x in TICKERS.items()]
    fi = [
        ex.submit(fetch_index, x)
        for x in [
            ("^KS11", "KOSPI"),
            ("^KQ11", "KOSDAQ"),
            ("^KS200", "KOSPI200"),
        ]
    ]
    ffx = [
        ex.submit(fetch_index, x)
        for x in [("USDKRW=X", "USDKRW"), ("CL=F", "WTI")]
    ]
    ffr = [ex.submit(naver_frgn, c) for c in TICKERS]

    for f in as_completed(fs):
        code, data = f.result()
        if data and "err" not in data:
            result["stocks"][code].update(data)
        elif data:
            result["stocks"][code]["err"] = data.get("err", "unknown")

    for f in as_completed(fi):
        name, data = f.result()
        if data:
            result["index"][name] = data

    for f in as_completed(ffx):
        name, data = f.result()
        if data:
            result["fx"][name] = data

    for f in as_completed(ffr):
        code, data = f.result()
        if data and "err" not in data:
            result["stocks"][code]["foreign_net"] = data.get("foreign_net")
            result["stocks"][code]["inst_net"] = data.get("inst_net")

result["elapsed"] = round(time.time() - t0, 2)

ok_count = sum(1 for v in result["stocks"].values() if "close" in v)
print(f"OK {ok_count}/{len(TICKERS)} stocks | elapsed={result['elapsed']}s")
k = result["index"].get("KOSPI", {})
print(f"KOSPI={k.get('close','?')} ({k.get('change_pct','?')}%)")

with open("market_data.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("market_data.json saved")
