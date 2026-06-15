#!/usr/bin/env python3
"""
apt2.me에서 서울특별시 강서구 아파트 실거래가 크롤링.
"""

from __future__ import annotations

import html as html_lib
import re
import ssl
import urllib.request
from dataclasses import dataclass, field

ssl._create_default_https_context = ssl._create_unverified_context

BASE_URL = "https://apt2.me/apt/AptDaily.jsp"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# 강서구 전체: 강서구(11500), bubdong 없음
PARAMS = "area=11500&pages=1&ord=1&bubdong="


@dataclass
class AptDeal:
    name: str                # 단지명
    dong: str                # 동 이름 (예: 가양동)
    year_built: str          # 건축연도
    area_m2: str             # 전용면적(㎡)
    pyeong: str              # 평
    floor: str               # 층
    contract_date: str       # 계약일
    price_만원: int          # 실거래가 (만원)
    price_str: str           # 표시용 (억/천)
    peak_price_str: str      # 평형 최고가 (표시용)
    type_peak_str: str       # 타입 최고가 (표시용)
    peak_ratio: str          # 최고가 대비 % (예: "93.9%")
    recent_prices: list[int] = field(default_factory=list)


def clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return html_lib.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_korean_price(text: str) -> int:
    """'11억6천', '7억', '12억3천500' 등 → 만원 정수 반환."""
    # 숫자와 단위만 남기기
    text = re.sub(r"[^\d억천백]", "", text)
    total = 0

    m_억 = re.search(r"(\d+)억", text)
    if m_억:
        total += int(m_억.group(1)) * 10000
        remainder = text[m_억.end():]
    else:
        remainder = text

    m_천 = re.search(r"(\d+)천", remainder)
    if m_천:
        total += int(m_천.group(1)) * 1000
        after_천 = remainder[m_천.end():]
        m_rest = re.match(r"(\d+)", after_천)
        if m_rest:
            total += int(m_rest.group(1))
    elif remainder.isdigit():
        total += int(remainder)

    return total


def won_str(만원: int) -> str:
    억 = 만원 // 10000
    천 = (만원 % 10000) // 1000
    if 억 and 천:
        return f"{억}억 {천}천"
    elif 억:
        return f"{억}억"
    else:
        return f"{만원:,}만"


def fetch_html(create_dt: str) -> str:
    url = f"{BASE_URL}?{PARAMS}&createDt={create_dt}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_deals(html: str) -> list[AptDeal]:
    deals = []
    cards = re.findall(r'<article class="card[^"]*"[^>]*>.*?</article>', html, re.DOTALL)

    for card in cards:
        # 단지명
        name_m = re.search(r'class="nm">([^<]+)', card)
        if not name_m:
            continue
        name = name_m.group(1).strip()

        # 동 이름 (meta에서 강서구 다음 단어)
        dong_m = re.search(r"강서구\s+(\S+동)", card)
        dong = dong_m.group(1) if dong_m else ""

        # 건축연도
        year_m = re.search(r"(\d{4})년", card)
        year_built = year_m.group(1) + "년" if year_m else ""

        # 거래가
        price_m = re.search(r'class="won">([^<]+)', card)
        if not price_m:
            continue
        price_만원 = parse_korean_price(price_m.group(1))
        if price_만원 == 0:
            continue

        # 면적 및 평
        area_m = re.search(r"([\d.]+)㎡\s*([\d]+)평", card)
        area_m2 = area_m.group(1) if area_m else ""
        pyeong = area_m.group(2) if area_m else ""

        # 층
        floor_m = re.search(r"(\d+)층", card)
        floor = floor_m.group(1) if floor_m else ""

        # 계약일 (YY.MM.DD 패턴)
        date_m = re.search(r"(\d{2}\.\d{2}\.\d{2})\s*계약", card)
        contract_date = date_m.group(1) if date_m else "-"

        # 타입 최고가
        type_peak_m = re.search(r'<span class="rk">타입최고</span><span[^>]*>([^<]+)', card)
        type_peak_str = clean(type_peak_m.group(1)) if type_peak_m else ""

        # 평형 최고가
        peak_m = re.search(r'<span class="rk">평형최고</span><span[^>]*>([^<]+)', card)
        peak_price_str = clean(peak_m.group(1)) if peak_m else ""

        # 최고가 대비 %
        ratio_m = re.search(r'<span class="rk">최고가대비</span><span[^>]*>([\d.]+%)', card)
        peak_ratio = ratio_m.group(1) if ratio_m else ""

        # 가격 이력 (sparkline)
        spark_m = re.search(r'data-vals="([\d,]+)"', card)
        recent_prices = []
        if spark_m:
            prices = [int(p) for p in spark_m.group(1).split(",") if p.strip().isdigit()]
            recent_prices = prices[-10:]

        deals.append(AptDeal(
            name=name,
            dong=dong,
            year_built=year_built,
            area_m2=area_m2,
            pyeong=pyeong,
            floor=floor,
            contract_date=contract_date,
            price_만원=price_만원,
            price_str=won_str(price_만원),
            peak_price_str=peak_price_str,
            type_peak_str=type_peak_str,
            peak_ratio=peak_ratio,
            recent_prices=recent_prices,
        ))

    deals.sort(key=lambda d: (d.name != "대림경동아파트", -d.price_만원))
    return deals


def get_강서구_deals(create_dt: str = "") -> list[AptDeal]:
    from datetime import datetime
    if not create_dt:
        create_dt = datetime.now().strftime("%Y%m%d")
    return parse_deals(fetch_html(create_dt))


if __name__ == "__main__":
    from datetime import datetime
    deals = get_강서구_deals()
    print(f"\n📍 서울 강서구 아파트 실거래가 ({datetime.now().strftime('%Y-%m-%d')})\n")
    print(f"{'단지명':<20} {'동':>8} {'면적':>8} {'층':>4} {'계약일':>10} {'거래가':>14} {'타입최고가':>14} {'평형최고가':>14} {'최고가대비':>10}")
    print("-" * 110)
    for d in deals:
        print(f"{d.name:<20} {d.dong:>8} {d.area_m2+'㎡':>8} {d.floor+'층':>4} {d.contract_date:>10} {d.price_str:>14} {d.type_peak_str:>14} {d.peak_price_str:>14} {d.peak_ratio:>10}")
    print(f"\n총 {len(deals)}건")
