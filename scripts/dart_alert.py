#!/usr/bin/env python3
"""DART 긴급 공시 알림 — dart.fss.or.kr HTML 스크래핑 (OpenDart API 불가 대비)."""
import json
import os
import re
import datetime
import html
import urllib.request
import urllib.parse

KST = datetime.timezone(datetime.timedelta(hours=9))

WATCH = [
    ("005930", "삼성전자"),
    ("023160", "태광"),
    ("034020", "두산에너빌리티"),
    ("071970", "HD현대마린엔진"),
    ("083450", "GST"),
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"


def load_state():
    if os.path.exists("alerts.json"):
        with open("alerts.json") as f:
            return json.load(f)
    return {"seen": [], "corp_codes": {}}


def save_state(state):
    with open("alerts.json", "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── Step 2A: dart.fss.or.kr POST 스크래핑 ──────────────────────────────────

def scrape_dart(name, code, bgn, end, seen):
    params = {
        "currentPage": "1", "maxResults": "15", "maxLinks": "10",
        "sort": "date", "series": "desc",
        "textCrpCik": "", "textCrpNm": name, "textPresenterNm": "",
        "finalReport": "recent", "startDate": bgn, "endDate": end,
        "publicType": "", "publicType1": "", "publicType2": "", "publicType3": "",
        "publicType4": "", "publicType5": "", "publicType6": "", "publicType7": "",
        "publicType8": "", "publicType9": "", "publicType10": "", "publicType11": "",
        "publicType12": "", "publicType13": "",
        "reportName": "", "reportNamePopYn": "N",
        "examinObj": "", "relationWith": "", "relationPopYn": "N",
        "textCorporationType": "",
    }
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        "https://dart.fss.or.kr/dsac001/search.ax", data=data,
        headers={"User-Agent": UA, "Referer": "https://dart.fss.or.kr/dsac001/mainAll.do"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode("utf-8", "replace")

    rows = re.findall(r"<tr[^>]*>.*?</tr>", body, re.S)
    new = []
    for row in rows:
        m_id = re.search(r"rcpNo=(\d+)", row)
        if not m_id:
            continue
        rcpt = m_id.group(1)
        m_ttl = re.search(r'<a[^>]*id="r_\d+"[^>]*>(.*?)</a>', row, re.S)
        if not m_ttl:
            m_ttl = re.search(r"rcpNo=\d+[^>]*>(.*?)</a>", row, re.S)
        title = re.sub(r"<[^>]+>", "", m_ttl.group(1)).strip() if m_ttl else "(제목 파싱 실패)"
        title = html.unescape(title)
        m_dt = re.search(r"(\d{4}\.\d{2}\.\d{2})", row)
        date = m_dt.group(1).replace(".", "-") if m_dt else ""
        if name not in row:
            continue
        if rcpt in seen:
            continue
        new.append({
            "id": rcpt, "stock_code": code, "name": name,
            "title": title, "date": date,
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcpt}",
        })
    return new


# ── Step 2B: finance.naver.com 폴백 ─────────────────────────────────────────

def scrape_naver(name, code, seen):
    url = f"https://finance.naver.com/item/news_notice.naver?code={code}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode("euc-kr", "replace")

    new = []
    for m in re.finditer(
        r'<td[^>]*class="title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<td[^>]*class="date"[^>]*>(.*?)</td>',
        body, re.S
    ):
        href, ttl, date = m.groups()
        ttl = html.unescape(re.sub(r"<[^>]+>", "", ttl)).strip()
        date = re.sub(r"<[^>]+>", "", date).strip()
        fid = re.search(r"(\d{8,})", href)
        uid = fid.group(1) if fid else f"{code}_{ttl[:20]}"
        if uid in seen:
            continue
        new.append({
            "id": uid, "stock_code": code, "name": name,
            "title": ttl, "date": date,
            "url": "https://finance.naver.com" + href if href.startswith("/") else href,
        })
    return new


# ── 공통 로직 ────────────────────────────────────────────────────────────────

def fetch_disclosures(seen):
    now = datetime.datetime.now(KST)
    bgn = (now - datetime.timedelta(days=2)).strftime("%Y.%m.%d")
    end = now.strftime("%Y.%m.%d")
    new = []
    source_used = None

    for code, name in WATCH:
        # 2A 시도
        try:
            items = scrape_dart(name, code, bgn, end, seen)
            print(f"{name}: +{len(items)} new (dart)")
            new.extend(items)
            if source_used is None:
                source_used = "dart"
        except Exception as e:
            print(f"[WARN] {name} dart fail: {e}, trying naver...")
            # 2B 폴백
            try:
                items = scrape_naver(name, code, seen)
                print(f"{name}: +{len(items)} new (naver fallback)")
                new.extend(items)
                if source_used is None:
                    source_used = "naver"
            except Exception as e2:
                print(f"[WARN] {name} naver fail: {e2}")

    return new, source_used or "none"


def render_alert_card(a):
    return (
        f"<div class='alert'>"
        f"<div><span class='stock'>{a['name']} [{a['stock_code']}]</span>"
        f"<span class='time'>{a['date']} · NEW</span></div>"
        f"<div class='title'>{a['title']}</div>"
        f"<a href='{a['url']}' target='_blank'>원문 →</a>"
        f"</div>"
    )


HEAD = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600">
<title>\U0001f6a8 Disclosure Alerts</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;line-height:1.6}
.wrap{max-width:720px;margin:0 auto;padding:24px 16px}
h1{font-size:22px;margin:0 0 4px;color:#f85149}
.sub{color:#8b949e;font-size:13px;margin-bottom:8px}
.nav{margin-bottom:16px}
.nav a{color:#58a6ff;font-size:13px;text-decoration:none;margin-right:12px}
.alert{background:#161b22;border-left:3px solid #f85149;border-radius:8px;padding:14px 16px;margin-bottom:10px}
.alert .stock{font-weight:600;color:#ffd966;font-size:14px}
.alert .time{color:#6e7681;font-size:12px;font-family:ui-monospace,monospace;margin-left:8px}
.alert .title{color:#f0f6fc;font-size:15px;margin:6px 0}
.alert a{color:#58a6ff;font-size:12px;text-decoration:none}
.empty{color:#6e7681;text-align:center;padding:40px;font-size:14px;background:#161b22;border-radius:8px}
footer{color:#6e7681;font-size:11px;text-align:center;margin-top:24px}
</style></head><body><div class="wrap">
"""


def render_page(new_alerts, prev_alerts_html, now_str, source):
    parts = [HEAD]
    parts.append("<h1>\U0001f6a8 Disclosure Alerts</h1>")
    parts.append(
        f"<div class='sub'>마지막 체크: {now_str} · 1시간마다 자동 새로고침 · 신규 {len(new_alerts)}건</div>"
    )
    parts.append("<div class='nav'><a href='index.html'>← 일일 브리핑</a></div>")
    parts.append("<!--ALERT_START-->")
    for a in new_alerts:
        parts.append(render_alert_card(a))
    if prev_alerts_html:
        parts.append(prev_alerts_html)
    parts.append("<!--ALERT_END-->")
    if not new_alerts and not (prev_alerts_html or "").strip():
        parts.append("<div class='empty'>최근 2일 내 신규 공시 없음</div>")
    src_label = "dart.fss.or.kr" if source == "dart" else "finance.naver.com" if source == "naver" else "N/A"
    parts.append(f"<footer>Generated at {now_str} — Source: {src_label}</footer>")
    parts.append("</div></body></html>")
    return "\n".join(parts)


def extract_prev_alerts():
    """이전 alerts.html에서 ALERT 구간을 추출하되, 오늘 기준 2일 이내의 카드만 유지."""
    if not os.path.exists("alerts.html"):
        return ""
    with open("alerts.html") as f:
        body = f.read()
    m = re.search(r"<!--ALERT_START-->(.*?)<!--ALERT_END-->", body, re.S)
    if not m:
        return ""
    inner = m.group(1).strip()
    if not inner:
        return ""

    today = datetime.datetime.now(KST).date()
    cutoff = today - datetime.timedelta(days=2)  # 오늘 포함 최근 3일 (오늘/어제/그제)

    # 각 카드는 `<div class='alert'>...</a></div>` 형태.
    cards = re.findall(r"<div class='alert'>.*?</a>\s*</div>", inner, re.S)
    kept = []
    for c in cards:
        m_dt = re.search(r"(\d{4}-\d{2}-\d{2})", c)
        if not m_dt:
            continue
        try:
            d = datetime.date.fromisoformat(m_dt.group(1))
        except ValueError:
            continue
        if d >= cutoff:
            kept.append(c)
    return "\n".join(kept)


def main():
    state = load_state()
    seen = set(state.get("seen", []))

    new, source = fetch_disclosures(seen)
    now = datetime.datetime.now(KST)
    now_str = now.strftime("%Y-%m-%d %H:%M KST")

    if new:
        prev = extract_prev_alerts()
        page = render_page(new, prev, now_str, source)
        with open("alerts.html", "w") as f:
            f.write(page)
    elif os.path.exists("alerts.html"):
        with open("alerts.html") as f:
            body = f.read()
        body = re.sub(
            r"마지막 체크:[^<]*건</div>",
            f"마지막 체크: {now_str} · 1시간마다 자동 새로고침 · 신규 0건</div>",
            body, count=1,
        )
        src_label = "dart.fss.or.kr" if source == "dart" else "finance.naver.com" if source == "naver" else "N/A"
        body = re.sub(
            r"<footer>Generated at[^<]*</footer>",
            f"<footer>Generated at {now_str} — Source: {src_label}</footer>",
            body, count=1,
        )
        with open("alerts.html", "w") as f:
            f.write(body)
    else:
        page = render_page([], "", now_str, source)
        with open("alerts.html", "w") as f:
            f.write(page)

    state["seen"] = list(set(list(seen) + [a["id"] for a in new]))[-500:]
    state["last_check"] = now_str
    state["last_new_count"] = len(new)
    state["sources_checked"] = ["dart", "naver_fallback"]
    save_state(state)
    print(f"DONE: {len(new)} new | source={source}")


if __name__ == "__main__":
    main()
