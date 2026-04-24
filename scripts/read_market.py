"""
Claude Code 환경에서 market_data.json을 읽는 스크립트.
1순위: 로컬 파일 (git pull 후)
2순위: GitHub raw API (네트워크 허용)
3순위: WebSearch 결과 수동 입력용 폴백 구조 출력
"""
import json, sys, urllib.request
from datetime import datetime, timedelta

LOCAL_PATH = "market_data.json"
RAW_URL = "https://raw.githubusercontent.com/withusky-png/stock-briefing/main/market_data.json"
GH_API_URL = "https://api.github.com/repos/withusky-png/stock-briefing/contents/market_data.json"

def load_local():
    try:
        with open(LOCAL_PATH, encoding="utf-8") as f:
            d = json.load(f)
        age_ok = True
        gen = d.get("generated", "")
        if gen:
            dt = datetime.fromisoformat(gen)
            age_h = (datetime.utcnow() + timedelta(hours=9) - dt).total_seconds() / 3600
            age_ok = age_h < 24
        if age_ok and d.get("stocks", {}).get("005930", {}).get("close"):
            return d, "local"
    except Exception:
        pass
    return None, None

def load_github_raw():
    try:
        req = urllib.request.Request(RAW_URL, headers={"User-Agent": "stock-briefing/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
        if d.get("stocks", {}).get("005930", {}).get("close"):
            return d, "github-raw"
    except Exception:
        pass
    return None, None

def load_github_api():
    import base64
    try:
        req = urllib.request.Request(GH_API_URL, headers={
            "User-Agent": "stock-briefing/1.0",
            "Accept": "application/vnd.github.v3+json",
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            meta = json.load(r)
        content = base64.b64decode(meta["content"]).decode("utf-8")
        d = json.loads(content)
        if d.get("stocks", {}).get("005930", {}).get("close"):
            return d, "github-api"
    except Exception:
        pass
    return None, None

data, source = load_local()
if not data:
    data, source = load_github_raw()
if not data:
    data, source = load_github_api()

if not data:
    print(json.dumps({"error": "market_data.json 없음 — GitHub Actions fetch-market workflow 실행 필요"}))
    sys.exit(1)

data["_load_source"] = source
print(json.dumps(data, ensure_ascii=False))
