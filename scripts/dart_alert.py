#!/usr/bin/env python3
"""DART 긴급 공시 알림 — 공식 XML API 기반."""
import json
import os
import re
import datetime
import urllib.request
import xml.etree.ElementTree as ET

KEY = os.environ["DART_KEY"]
KST = datetime.timezone(datetime.timedelta(hours=9))

# stock_code → corp_code 매핑은 최초 1회만 fetch, 이후 alerts.json에 캐시
WATCH = [
    ("005930", "삼성전자"),
    ("023160", "태광"),
    ("034020", "두산에너빌리티"),
    ("071970", "HD현대마린엔진"),
    ("083450", "GST"),
]


def load_state():
    if os.path.exists("alerts.json"):
        with open("alerts.json") as f:
            return json.load(f)
    return {"seen": [], "corp_codes": {}}


def save_state(state):
    with open("alerts.json", "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def fetch_corp_codes(state):
    """stock_code → corp_code 매핑 확보 (캐시)."""
    cache = state.get("corp_codes", {})
    need = [s for s, _ in WATCH if s not in cache]
    if not need:
        return cache

    import zipfile
    import io

    url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={KEY}"
    with urllib.request.urlopen(url, timeout=30) as r:
        zbytes = r.read()
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        with z.open("CORPCODE.xml") as f:
            tree = ET.parse(f)
    for c in tree.getroot().findall("list"):
        stock = (c.findtext("stock_code") or "").strip()
        corp = (c.findtext("corp_code") or "").strip()
        name = (c.findtext("corp_name") or "").strip()
        if stock in need:
            cache[stock] = {"corp_code": corp, "name": name}
    state["corp_codes"] = cache
    return cache


def fetch_disclosures(corp_codes, seen):
    """최근 2일 공시 중 미확인 건만 반환."""
    today = datetime.datetime.now(KST)
    bgn = (today - datetime.timedelta(days=2)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    new = []
    for stock_code, info in corp_codes.items():
        url = (
            f"https://opendart.fss.or.kr/api/list.xml"
            f"?crtfc_key={KEY}&corp_code={info['corp_code']}"
            f"&bgn_de={bgn}&end_de={end}&page_count=20"
        )
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"[WARN] {info['name']} fetch fail: {e}")
            continue
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            print(f"[WARN] {info['name']} parse fail: {e}")
            continue
        status = root.findtext("status")
        if status != "000":
            msg = root.findtext("message", "no data")
            print(f"[INFO] {info['name']}: {status} - {msg}")
            continue
        count = 0
        for item in root.findall("list"):
            rcept_no = (item.findtext("rcept_no") or "").strip()
            if not rcept_no or rcept_no in seen:
                continue
            title = (item.findtext("report_nm") or "").strip()
            date = (item.findtext("rcept_dt") or "").strip()
            date_disp = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 else date
            new.append(
                {
                    "id": rcept_no,
                    "stock_code": stock_code,
                    "name": info["name"],
                    "title": title,
                    "date": date_disp,
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                }
            )
            count += 1
        print(f"{info['name']}: +{count} new")
    return new


def render_alert_card(a):
    return (
        f"<div class='alert'>"
        f"<div><span class='stock'>{a['name']} [{a['stock_code']}]</span>"
        f"<span class='time'>{a['date']} · NEW</span></div>"
        f"<div class='title'>{a['title']}</div>"
        f"<a href='{a['url']}' target='_blank'>DART 원문 →</a>"
        f"</div>"
    )


HEAD = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
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


def render_page(new_alerts, prev_alerts_html, now_str):
    parts = [HEAD]
    parts.append("<h1>\U0001f6a8 Disclosure Alerts</h1>")
    parts.append(
        f"<div class='sub'>마지막 체크: {now_str} · 5분마다 자동 새로고침 · 신규 {len(new_alerts)}건</div>"
    )
    parts.append("<div class='nav'><a href='index.html'>← 일일 브리핑</a></div>")
    parts.append("<!--ALERT_START-->")
    for a in new_alerts:
        parts.append(render_alert_card(a))
    if prev_alerts_html:
        parts.append(prev_alerts_html)
    parts.append("<!--ALERT_END-->")
    if not new_alerts and not prev_alerts_html.strip():
        parts.append("<div class='empty'>최근 2일 내 신규 공시 없음</div>")
    parts.append(f"<footer>Generated at {now_str} — Source: DART OpenAPI</footer>")
    parts.append("</div></body></html>")
    return "\n".join(parts)


def extract_prev_alerts():
    if not os.path.exists("alerts.html"):
        return ""
    with open("alerts.html") as f:
        body = f.read()
    m = re.search(r"<!--ALERT_START-->(.*?)<!--ALERT_END-->", body, re.S)
    return m.group(1).strip() if m else ""


def main():
    state = load_state()
    seen = set(state.get("seen", []))
    corp_codes = fetch_corp_codes(state)
    new = fetch_disclosures(corp_codes, seen)
    now = datetime.datetime.now(KST)
    now_str = now.strftime("%Y-%m-%d %H:%M KST")

    if new:
        prev = extract_prev_alerts()
        html = render_page(new, prev, now_str)
        with open("alerts.html", "w") as f:
            f.write(html)
    elif os.path.exists("alerts.html"):
        # 타임스탬프만 갱신
        with open("alerts.html") as f:
            body = f.read()
        body = re.sub(r"마지막 체크:[^·]*·", f"마지막 체크: {now_str} ·", body, count=1)
        with open("alerts.html", "w") as f:
            f.write(body)
    else:
        # 첫 실행 + 공시 없음
        html = render_page([], "", now_str)
        with open("alerts.html", "w") as f:
            f.write(html)

    # state 업데이트
    state["seen"] = list(set(list(seen) + [a["id"] for a in new]))[-500:]
    state["last_check"] = now_str
    state["last_new_count"] = len(new)
    save_state(state)
    print(f"DONE: {len(new)} new, {len(seen)} seen")


if __name__ == "__main__":
    main()
