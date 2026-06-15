#!/usr/bin/env python3
"""
매일 아침 Google 뉴스 RSS로 인기 경제뉴스를 수집하여 Gmail로 발송하는 스크립트.
"""
from __future__ import annotations

import html as html_lib
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
import os
import re
import smtplib
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from real_estate import get_강서구_deals

# ── 환경변수 ──────────────────────────────────────────────
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PW = os.environ.get("GMAIL_APP_PW")
TO_ADDRESS = os.environ.get("TO_ADDRESS", GMAIL_ADDRESS)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q={query}"

SEARCH_QUERIES = {
    "🇺🇸 미국 증시": ["나스닥 지수", "S&P500 지수"],
    "🇰🇷 국내 경제": ["코스피 코스닥", "한국 경제", "한국은행 금리"],
    "🌐 글로벌 경제": ["미국 경제 연준", "글로벌 경제 무역"],
    "📊 환율·원자재": ["달러 원 환율", "국제유가 금값"],
}


def strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return html_lib.unescape(text).strip()


def fetch_google_news(query: str, count: int = 5) -> list[dict]:
    """Google 뉴스 RSS에서 인기 뉴스 수집."""
    url = GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        root = ET.fromstring(resp.read())

    items = []
    for item in root.findall(".//item")[:count]:
        title = strip_tags(item.findtext("title", ""))
        link = item.findtext("link", "#")
        source = item.findtext("source", "")
        pub_date = item.findtext("pubDate", "")[:16]
        items.append({"title": title, "link": link, "source": source, "pub_date": pub_date})
    return items


def build_stock_html() -> str:
    """네이버 금융에서 6개 종목 현재가 조회 후 HTML 섹션 생성."""
    print("📈 주식 현황 수집 중...")
    stocks = [
        ('카카오', '035720'),
        ('NAVER', '035420'),
        ('TIGER 미국나스닥100', '133690'),
        ('TIGER 미국S&P500', '360750'),
        ('TIGER 미국테크TOP10채권혼합', '441680'),
        ('스튜디오드래곤', '253450'),
    ]
    ua_headers = [
        '-H', 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        '-H', 'Accept-Language: ko-KR,ko;q=0.9',
    ]
    rows_html = ''
    for name, code in stocks:
        try:
            r = subprocess.run(
                ['curl', '-s', f'https://finance.naver.com/item/main.naver?code={code}'] + ua_headers,
                capture_output=True, timeout=10
            )
            page = r.stdout.decode('utf-8', errors='replace')
            nums = re.findall(r'<span class="blind">([^<]+)</span>', page)
            nums = [n for n in nums if re.match(r'^[0-9,]+$', n)]

            price      = nums[0] if len(nums) > 0 else '-'
            change     = nums[1] if len(nums) > 1 else '-'
            prev_close = nums[2] if len(nums) > 2 else '-'
            day_high   = nums[3] if len(nums) > 3 else '-'
            day_low    = nums[4] if len(nums) > 4 else '-'
            open_      = nums[7] if len(nums) > 7 else '-'

            p  = int(price.replace(',', '')) if price != '-' else 0
            pc = int(prev_close.replace(',', '')) if prev_close != '-' else 0
            c  = int(change.replace(',', '')) if change != '-' else 0
            if p < pc:
                sign, pct, color = '▼', f'-{c/pc*100:.2f}%' if pc else '-', '#e53935'
            elif p > pc:
                sign, pct, color = '▲', f'+{c/pc*100:.2f}%' if pc else '-', '#1a73e8'
            else:
                sign, pct, color = '-', '0.00%', '#888'

            # 52주 고저가
            r2 = subprocess.run(
                ['curl', '-s',
                 f'https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=260&requestType=0']
                + ua_headers[:2],
                capture_output=True, timeout=10
            )
            chart = r2.stdout.decode('euc-kr', errors='replace')
            items = re.findall(r'<item data="([^"]+)"', chart)
            w52 = []
            for item in items:
                parts = item.split('|')
                if len(parts) >= 5:
                    try:
                        w52.append((parts[0], int(parts[2]), int(parts[3])))
                    except ValueError:
                        pass
            if w52:
                max_p = max(w52, key=lambda x: x[1])
                min_p = min(w52, key=lambda x: x[2])
                w52_hi = f"{max_p[1]:,}원 ({max_p[0][:4]}.{max_p[0][4:6]}.{max_p[0][6:8]})"
                w52_lo = f"{min_p[2]:,}원 ({min_p[0][:4]}.{min_p[0][4:6]}.{min_p[0][6:8]})"
                hi_val, lo_val = max_p[1], min_p[2]
                bar_pos = round((p - lo_val) / (hi_val - lo_val) * 100, 1) if hi_val != lo_val else 50
            else:
                w52_hi = w52_lo = '-'
                bar_pos = 50

            rows_html += f"""
          <tr style="border-bottom:1px solid #f0f0f0;">
            <td style="padding:8px 10px;font-weight:bold;font-size:13px;">{name}<br>
              <span style="font-weight:normal;color:#aaa;font-size:11px;">{code}</span></td>
            <td style="padding:8px 10px;text-align:right;font-size:14px;font-weight:bold;">{price}원<br>
              <span style="color:{color};font-size:12px;">{sign} {change}원 ({pct})</span></td>
            <td style="padding:8px 10px;text-align:right;color:#555;font-size:12px;">
              전일 {prev_close}원<br>시가 {open_}원</td>
            <td style="padding:8px 10px;text-align:right;font-size:12px;">
              <span style="color:#e53935;">▲ {day_high}원</span><br>
              <span style="color:#1a73e8;">▼ {day_low}원</span></td>
            <td style="padding:8px 10px;text-align:right;font-size:11px;color:#555;">
              <div style="color:#e53935;">{w52_hi}</div>
              <div style="margin:4px 0;background:#eee;border-radius:3px;height:5px;position:relative;">
                <div style="position:absolute;left:{bar_pos}%;top:0;width:7px;height:5px;background:{color};transform:translateX(-50%);border-radius:3px;"></div>
              </div>
              <div style="color:#1a73e8;">{w52_lo}</div>
            </td>
          </tr>"""
        except Exception as e:
            rows_html += f'<tr><td colspan="5" style="padding:8px 10px;color:red;">{name} 조회 실패: {e}</td></tr>'

    return f"""
    <h3 style="border-bottom:2px solid #eee;padding-bottom:6px;">📈 주식 현황</h3>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f8f8f8;">
          <th style="padding:7px 10px;text-align:left;color:#888;font-weight:normal;">종목</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">현재가 / 등락</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">전일 / 시가</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">고가 / 저가</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">52주 범위</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>"""


def build_realestate_html(deals: list) -> str:
    """강서구 실거래가 섹션 HTML 생성 (deals는 미리 조회된 목록)."""
    if not deals:
        return '<p style="color:#aaa;">오늘 가양동 실거래 데이터 없음</p>'

    rows_html = ""
    for d in deals:
        try:
            ratio_val = float(d.peak_ratio.replace("%", ""))
            ratio_color = "#e53935" if ratio_val >= 100 else "#1a73e8"
        except (ValueError, AttributeError):
            ratio_color = "#555"

        is_mine = d.name == "대림경동아파트"
        row_bg = "background:#fff8e1;border-left:4px solid #f9a825;" if is_mine else ""
        name_style = "font-weight:bold;color:#f57f17;" if is_mine else "font-weight:bold;"

        rows_html += f"""
        <tr style="{row_bg}">
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;{name_style}">{d.name}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#555;">{d.dong}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#555;">{d.area_m2}㎡ ({d.pyeong}평)</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#555;">{d.floor}층</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#555;">{d.contract_date}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#e53935;font-weight:bold;text-align:right;">{d.price_str}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#888;text-align:right;">{d.type_peak_str}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;color:#888;text-align:right;">{d.peak_price_str}</td>
          <td style="padding:7px 10px;border-bottom:1px solid #f0f0f0;font-weight:bold;text-align:right;color:{ratio_color};">{d.peak_ratio}</td>
        </tr>"""

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="background:#f8f8f8;">
          <th style="padding:7px 10px;text-align:left;color:#888;font-weight:normal;">단지명</th>
          <th style="padding:7px 10px;text-align:left;color:#888;font-weight:normal;">동</th>
          <th style="padding:7px 10px;text-align:left;color:#888;font-weight:normal;">면적</th>
          <th style="padding:7px 10px;text-align:left;color:#888;font-weight:normal;">층</th>
          <th style="padding:7px 10px;text-align:left;color:#888;font-weight:normal;">계약일</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">거래가</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">타입최고가</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">평형최고가</th>
          <th style="padding:7px 10px;text-align:right;color:#888;font-weight:normal;">최고가대비</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>"""


def build_html() -> str:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    print(f"🔍 뉴스 수집 중... ({datetime.now().strftime('%H:%M:%S')})")

    # 부동산 데이터 먼저 조회 → 대림경동아파트 거래 여부로 섹션 순서 결정
    print("🏠 부동산 시세 수집 중...")
    try:
        deals = get_강서구_deals()
    except Exception as e:
        deals = []
        print(f"⚠️ 부동산 데이터 수집 실패: {e}")

    has_daelim = any(d.name == "대림경동아파트" for d in deals)

    realestate_html = (
        f'<h3 style="border-bottom:2px solid #eee;padding-bottom:6px;">🏠 서울 강서구 아파트 실거래가</h3>'
        + build_realestate_html(deals)
    )
    stock_html = build_stock_html()

    if has_daelim:
        # 대림경동아파트 거래 있음 → 부동산 먼저
        sections_html = realestate_html + stock_html
    else:
        # 거래 없음 → 주식 먼저
        sections_html = stock_html + realestate_html

    for section, queries in SEARCH_QUERIES.items():
        seen_titles = set()
        items_html = ""

        for query in queries:
            for item in fetch_google_news(query, count=5):
                title = item["title"]
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                items_html += f"""
        <li style="margin-bottom:14px;">
          <a href="{item['link']}" style="font-weight:bold;color:#1a73e8;text-decoration:none;">{title}</a>
          <br><span style="color:#aaa;font-size:11px;">{item['source']} · {item['pub_date']}</span>
        </li>"""

        sections_html += f"""
    <h3 style="border-bottom:2px solid #eee;padding-bottom:6px;">{section}</h3>
    <ul style="list-style:none;padding:0;">{items_html}
    </ul>"""

    return f"""<!DOCTYPE html>
<html><body style="font-family:Apple SD Gothic Neo,sans-serif;max-width:680px;margin:auto;padding:20px;color:#333;">
  <h2 style="color:#1a73e8;">📰 오늘의 경제뉴스 — {today}</h2>
  {sections_html}
  <p style="color:#aaa;font-size:11px;margin-top:30px;">자동 발송 — {today}</p>
</body></html>"""


def send_email(html_body: str) -> None:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    subject = f"[경제뉴스] {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = TO_ADDRESS
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print("📧 이메일 발송 중...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PW)
        server.sendmail(GMAIL_ADDRESS, TO_ADDRESS, msg.as_string())

    print(f"✅ 이메일 발송 완료 → {TO_ADDRESS}")


def validate_env() -> None:
    missing = [
        name
        for name, val in [
            ("GMAIL_ADDRESS", GMAIL_ADDRESS),
            ("GMAIL_APP_PW", GMAIL_APP_PW),
        ]
        if not val
    ]
    if missing:
        print(f"❌ 환경변수 누락: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    validate_env()
    html = build_html()
    send_email(html)
