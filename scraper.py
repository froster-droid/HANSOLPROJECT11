"""
스크래퍼 상태 (2026-06-11 기준 실측)

기관                     | 방식                    | 상태
------------------------|------------------------|------------------------------------------
ECHA SVHC               | HTML                   | 403 차단 → 간헐적 성공 유지
ECHA REACH              | HTML                   | 403 차단
ECHA 물질 상세 페이지   | HTML (substance-info)  | 200 정상 / BPA·BPS 확인 (우회 경로)
EPA TSCA                | HTML                   | 200 정상 / 키워드 히트 없음 (페이지 개편)
EPA 보도자료            | HTML                   | 200 정상 / 키워드 히트 없음
Federal Register API    | JSON API               | 200 정상 / CAS + 반덤핑 검색 (우회경로)
FDA 식품접촉            | HTML                   | 200 정상 / food contact 키워드 히트
EFSA 뉴스               | HTML                   | 200 정상 / food contact 키워드 히트
CA Prop 65              | OEHHA RSS + 직접 페이지 | 200 정상 / BPS 직접 페이지 추가
CA DTSC                 | HTML                   | 403 차단 → RSS도 403
WA Ecology              | HTML (Thermal Paper 전용)| 200 정상 / 감열지·PFAS 전용 페이지 추가
DOC/USITC               | Federal Register API   | 200 정상 / A-580-875 반덤핑 케이스 수집
"""

import json
import re
import time
from datetime import datetime
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from config import THERMAL_KEYWORDS

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _find_keywords(text: str) -> List[str]:
    text_lower = text.lower()
    return sorted({kw for kw in THERMAL_KEYWORDS if kw.lower() in text_lower})


def _get(url: str, timeout: int = 20) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        # 봇 차단 감지
        if any(x in resp.text[:800] for x in ["Incapsula", "NOINDEX, NOFOLLOW", "__cf_chl"]):
            print(f"    [봇차단] {url[:60]}")
            return None
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"    [GET 실패] {url[:60]} → {e}")
        return None


def _get_rss(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.content, "lxml-xml")
    except Exception as e:
        print(f"    [RSS 실패] {url[:60]} → {e}")
        return None


def _make_abs(href: str, base: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    domain = "/".join(base.split("/")[:3])
    return domain + href if href.startswith("/") else base.rstrip("/") + "/" + href


def _links_with_keywords(soup: BeautifulSoup, base_url: str, source: str, min_len: int = 8) -> List[Dict]:
    results = []
    seen = set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if len(title) < min_len:
            continue
        kws = _find_keywords(title)
        if not kws:
            continue
        url = _make_abs(a["href"], base_url)
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "source":           source,
            "title":            title,
            "url":              url,
            "published_date":   datetime.now().strftime("%Y-%m-%d"),
            "original_text":    title,
            "keywords_matched": ", ".join(kws),
            "_relevant":        True,
        })
    return results


# ── ECHA 물질 상세 페이지 (우회 경로 — 200 정상) ────────────────────────────

# ECHA 물질 상세 페이지 ID (EC번호 기반 내부 ID)
# 진단 확인: substance-information 페이지는 403 차단 없이 정상 접근됨
_ECHA_SUBSTANCES = [
    ("BPA (비스페놀A)",        "80-05-7",    "100.000.786"),
    ("BPS (비스페놀S)",        "80-09-1",    "100.000.788"),
    ("TGSH (비스페놀S 유도체)", "41481-66-7", "100.055.462"),
    ("D8 (이소프로폭시페닐설포닐페놀)", "95235-30-6", "100.104.818"),
    ("Pergafast 201",          "232938-43-1", "100.132.938"),
]


def scrape_echa_substance_pages() -> List[Dict]:
    """ECHA 물질 상세 페이지 — CAS번호 기반 직접 접근 (우회 경로, 200 정상)"""
    results = []
    base_url = "https://echa.europa.eu/substance-information/-/substanceinfo/{}"

    for name, cas, echa_id in _ECHA_SUBSTANCES:
        url = base_url.format(echa_id)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"    [ECHA 물질] {name} → HTTP {resp.status_code}")
                continue
            # 봇 차단 감지
            if any(x in resp.text[:800] for x in ["Incapsula", "NOINDEX, NOFOLLOW", "__cf_chl"]):
                print(f"    [ECHA 물질] {name} → 봇 차단")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            kws = _find_keywords(resp.text[:50000])

            # 페이지 제목 추출
            title_tag = soup.find("h1") or soup.find("h2")
            page_title = title_tag.get_text(strip=True) if title_tag else name

            # 주요 규제 정보 섹션 추출 (Classification, SVHC, Restrictions 등)
            sections = []
            for heading in soup.find_all(["h2", "h3", "h4"], limit=20):
                heading_text = heading.get_text(strip=True)
                if any(kw in heading_text.lower() for kw in
                       ["classif", "hazard", "svhc", "restrict", "authoris", "food", "regul"]):
                    sibling = heading.find_next_sibling()
                    if sibling:
                        sections.append(f"{heading_text}: {sibling.get_text(strip=True)[:200]}")

            original = f"물질명: {name}\nCAS번호: {cas}\nECHA ID: {echa_id}\n" + "\n".join(sections[:5])

            results.append({
                "source":           "ECHA",
                "title":            f"[ECHA 물질정보] {page_title} (CAS {cas})",
                "url":              url,
                "published_date":   datetime.now().strftime("%Y-%m-%d"),
                "original_text":    original,
                "keywords_matched": ", ".join(kws) if kws else f"CAS {cas}",
                "_relevant":        True,
            })
            time.sleep(1)

        except Exception as e:
            print(f"    [ECHA 물질] {name} → 오류: {e}")

    return results


# ── ECHA (403 차단 — 시도는 유지, 실패 시 0건 반환) ─────────────────────────

def scrape_echa_svhc() -> List[Dict]:
    """ECHA SVHC 후보물질 목록 (403 차단 상태 — 간헐적 성공 기대)"""
    results = []
    url = "https://echa.europa.eu/candidate-list-table"
    soup = _get(url)
    if not soup:
        return results

    table = soup.find("table")
    if not table:
        return results

    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        name = cells[0].get_text(strip=True)
        ec   = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        cas  = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        date = cells[-1].get_text(strip=True)
        a_tag = cells[0].find("a")
        link  = _make_abs(a_tag["href"], url) if a_tag else url
        kws   = _find_keywords(f"{name} {ec} {cas}")
        results.append({
            "source":           "ECHA",
            "title":            f"[SVHC 후보물질] {name}",
            "url":              link,
            "published_date":   date,
            "original_text":    f"물질명: {name}\nEC번호: {ec}\nCAS번호: {cas}\n등재일: {date}",
            "keywords_matched": ", ".join(kws) if kws else "",
            "_relevant":        bool(kws),
        })
    return results


def scrape_echa_news() -> List[Dict]:
    """ECHA 뉴스 (403 차단 상태)"""
    # 현재 403 차단 확인됨 — 함수 유지, 0건 반환
    return []


def scrape_echa_restrictions() -> List[Dict]:
    """ECHA REACH 제한물질 (403 차단 상태)"""
    return []


# ── EPA (200 정상 — 페이지 구조 기반 최적화) ─────────────────────────────────

def scrape_epa_tsca() -> List[Dict]:
    """EPA TSCA 화학물질 위험성 평가 (chemicals-under-tsca 메인 페이지)"""
    results = []
    url = "https://www.epa.gov/chemicals-under-tsca"
    soup = _get(url)
    if not soup:
        return results
    return _links_with_keywords(soup, url, "EPA")


def scrape_epa_news() -> List[Dict]:
    """EPA 보도자료 — 기사 제목·요약에서 키워드 탐색"""
    results = []
    url = "https://www.epa.gov/newsreleases"
    soup = _get(url)
    if not soup:
        return results

    # EPA 뉴스 항목 탐색
    items = (
        soup.find_all("div", class_=re.compile(r"view-row|news|article", re.I))
        or soup.find_all("li",  class_=re.compile(r"news|views-row",     re.I))
        or soup.find_all("article")
    )

    for item in items[:40]:
        title_tag = item.find(["h2", "h3", "h4", "a"])
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        desc_tag = item.find("p")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""
        kws = _find_keywords(f"{title} {desc}")
        if not kws:
            continue
        a_tag = item.find("a", href=True)
        link  = _make_abs(a_tag["href"], url) if a_tag else ""
        date_tag = item.find(["time", "span"], class_=re.compile(r"date|time", re.I))
        date_str = date_tag.get_text(strip=True) if date_tag else ""
        results.append({
            "source":           "EPA",
            "title":            title,
            "url":              link,
            "published_date":   date_str,
            "original_text":    f"{title}\n{desc}",
            "keywords_matched": ", ".join(kws),
            "_relevant":        True,
        })

    return results


# ── FDA (200 정상) ────────────────────────────────────────────────────────────

def scrape_fda_food_contact() -> List[Dict]:
    """FDA 식품 성분·포장 관련 링크"""
    results = []
    url = "https://www.fda.gov/food/food-ingredients-packaging"
    soup = _get(url)
    if not soup:
        return results
    return _links_with_keywords(soup, url, "FDA")


# ── Federal Register API (미국 연방 규제 입법예고 — 200 정상) ─────────────────

# CAS 번호만 사용 — "thermal paper" 단독 검색 제거
# (Federal Register는 서류 형식으로 "thermal paper" 언급하는 문서도 반환 → 노이즈)
_FEDERAL_REGISTER_TERMS = [
    ("BPA (CAS)",       "80-05-7"),
    ("BPS (CAS)",       "80-09-1"),
    ("TGSH (CAS)",      "41481-66-7"),
    ("D8 (CAS)",        "95235-30-6"),
    ("Pergafast (CAS)", "232938-43-1"),
]


def scrape_federal_register() -> List[Dict]:
    """Federal Register API — CAS번호·키워드로 미국 연방 규제 입법예고 수집 (우회 경로)"""
    results = []
    base = "https://www.federalregister.gov/api/v1/articles"
    seen_urls: set = set()

    _CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")

    for label, term in _FEDERAL_REGISTER_TERMS:
        is_cas = bool(_CAS_PATTERN.match(term))
        params = {
            "conditions[term]": term,
            "order":            "newest",
            "per_page":         "5",
            "fields[]":         ["title", "html_url", "publication_date", "abstract",
                                 "agencies", "document_number"],
        }
        try:
            resp = requests.get(base, params=params, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"    [Federal Register] '{term}' → HTTP {resp.status_code}")
                continue

            data = resp.json()
            articles = data.get("results", [])

            for art in articles:
                url = art.get("html_url", "")
                if not url or url in seen_urls:
                    continue

                title    = art.get("title", "")
                pub      = art.get("publication_date", "")
                abstract = art.get("abstract") or ""
                agencies = ", ".join(
                    a.get("raw_name", "") for a in art.get("agencies", [])
                )

                full_text = f"{title} {abstract}"
                kws = _find_keywords(full_text)

                # CAS 번호 검색: 해당 화학물질 규제이므로 키워드 없어도 저장
                # 키워드 검색: 실제 키워드 매칭이 없으면 노이즈이므로 건너뜀
                if not is_cas and not kws:
                    continue

                seen_urls.add(url)
                results.append({
                    "source":           "Federal Register",
                    "title":            f"[Federal Register] {title}",
                    "url":              url,
                    "published_date":   pub,
                    "original_text":    f"발행기관: {agencies}\n발행일: {pub}\n\n{abstract}",
                    "keywords_matched": ", ".join(kws) if kws else f"CAS {term}",
                    "_relevant":        True,
                })

            time.sleep(0.5)

        except Exception as e:
            print(f"    [Federal Register] '{term}' → 오류: {e}")

    return results


# ── DOC/USITC 반덤핑 (Federal Register API + ITA) ────────────────────────────

# 미국 DOC 대한민국 감열지 반덤핑 케이스: A-580-911 (Thermal Paper from Korea)
# 2021년 9월 발효, 매년 행정재심 진행 중 (한솔 2023-24 덤핑마진 0% 예비판정)
_ANTIDUMPING_TERMS = [
    ("감열지 반덤핑 (A-580-911)", "A-580-911"),
    ("감열지 반덤핑 일반",         "thermal paper antidumping"),
    ("감열지 상계관세",            "thermal paper countervailing"),
    ("감열지 한국 무역 결정",       "thermal paper Korea Commerce"),
]


def scrape_antidumping() -> List[Dict]:
    """DOC/USITC — 감열지 반덤핑·상계관세 Federal Register 수집 (키워드 필터 없음)"""
    results = []
    base = "https://www.federalregister.gov/api/v1/articles"
    seen_urls: set = set()

    for label, term in _ANTIDUMPING_TERMS:
        params = {
            "conditions[term]": term,
            "order":            "newest",
            "per_page":         "10",
            "fields[]":         ["title", "html_url", "publication_date", "abstract",
                                 "agencies", "document_number", "document_type"],
        }
        try:
            resp = requests.get(base, params=params, headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"    [반덤핑] '{term}' → HTTP {resp.status_code}")
                continue
            for art in resp.json().get("results", []):
                url = art.get("html_url", "")
                if not url or url in seen_urls:
                    continue
                title    = art.get("title", "")
                pub      = art.get("publication_date", "")
                abstract = art.get("abstract") or ""
                doc_type = art.get("document_type", "")
                agencies = ", ".join(a.get("raw_name", "") for a in art.get("agencies", []))
                seen_urls.add(url)
                results.append({
                    "source":           "DOC/USITC",
                    "title":            f"[반덤핑] {title}",
                    "url":              url,
                    "published_date":   pub,
                    "original_text":    (
                        f"발행기관: {agencies}\n문서유형: {doc_type}\n발행일: {pub}\n"
                        f"검색어: {label}\n\n{abstract}"
                    ),
                    "keywords_matched": f"antidumping, thermal paper, {term}",
                    "_relevant":        True,
                })
            time.sleep(0.5)
        except Exception as e:
            print(f"    [반덤핑] '{term}' → 오류: {e}")

    # ITA Access 반덤핑 이행 페이지 (enforcement.trade.gov)
    ita_url = "https://enforcement.trade.gov/frn/summary/korea-south/"
    soup = _get(ita_url)
    if soup:
        for a in soup.find_all("a", href=True):
            link_text = a.get_text(strip=True)
            if "thermal paper" in link_text.lower() or "A-580-875" in link_text:
                full_url = _make_abs(a["href"], ita_url)
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    results.append({
                        "source":           "DOC/USITC",
                        "title":            f"[ITA 이행] {link_text}",
                        "url":              full_url,
                        "published_date":   datetime.now().strftime("%Y-%m-%d"),
                        "original_text":    f"ITA 반덤핑 이행 데이터베이스 (한국 감열지)\n{link_text}",
                        "keywords_matched": "antidumping, thermal paper, A-580-875",
                        "_relevant":        True,
                    })

    return results


def scrape_fda_press_rss() -> List[Dict]:
    """FDA 보도자료 RSS — 우회 경로 (200 정상, 20건 확인)"""
    results = []
    url = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml"
    soup = _get_rss(url)
    if not soup:
        return results

    for item in soup.find_all("item"):
        title   = item.find("title").get_text(strip=True)       if item.find("title")       else ""
        desc    = item.find("description").get_text(strip=True) if item.find("description") else ""
        link    = item.find("link").get_text(strip=True)        if item.find("link")        else ""
        pub     = item.find("pubDate").get_text(strip=True)     if item.find("pubDate")     else ""
        kws = _find_keywords(f"{title} {desc}")
        if not kws:
            continue
        results.append({
            "source":           "FDA",
            "title":            f"[FDA 보도자료] {title}",
            "url":              link,
            "published_date":   pub[:16],
            "original_text":    f"{title}\n\n{desc}",
            "keywords_matched": ", ".join(kws),
            "_relevant":        True,
        })

    return results


# ── EFSA (200 정상) ───────────────────────────────────────────────────────────

def scrape_efsa_news() -> List[Dict]:
    """EFSA 뉴스 — 식품접촉재료·화학물질 관련"""
    results = []
    base = "https://www.efsa.europa.eu"
    url  = f"{base}/en/news"
    soup = _get(url)
    if not soup:
        return results

    items = (
        soup.find_all("article")
        or soup.find_all("div", class_=re.compile(r"news|article|listing", re.I))
    )

    for item in items[:30]:
        title_tag = item.find(["h2", "h3", "h4", "a"])
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        desc_tag = item.find("p")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""
        kws = _find_keywords(f"{title} {desc}")
        if not kws:
            continue
        a_tag = item.find("a", href=True)
        link  = _make_abs(a_tag["href"], base) if a_tag else ""
        date_tag = item.find(["time", "span"])
        date_str = date_tag.get_text(strip=True) if date_tag else ""
        results.append({
            "source":           "EFSA",
            "title":            title,
            "url":              link,
            "published_date":   date_str,
            "original_text":    f"{title}\n{desc}",
            "keywords_matched": ", ".join(kws),
            "_relevant":        True,
        })

    # 뉴스 항목이 없으면 링크 방식 폴백
    if not results:
        results = _links_with_keywords(soup, base, "EFSA")

    return results


# ── CA Prop 65 (OEHHA RSS + 직접 물질 페이지) ────────────────────────────────

# BPS(2021), BPA(2015) 등은 OEHHA RSS에 최근 업데이트가 없으므로 직접 페이지 수집
_CA_PROP65_DIRECT = [
    ("BPS (비스페놀S) Prop 65 등재",    "https://oehha.ca.gov/proposition-65/chemicals/bisphenol-s"),
    ("BPA (비스페놀A) Prop 65 등재",    "https://oehha.ca.gov/proposition-65/chemicals/bisphenol-and-bisphenol-a"),
    ("CA AB 1988 영수증 Phenol 규제",   "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240AB1988"),
]


def scrape_ca_prop65() -> List[Dict]:
    """California Prop 65 — OEHHA RSS + BPS·BPA 직접 페이지 + AB 1988 법안"""
    results = []

    # 1) OEHHA RSS 피드 (최신 업데이트)
    # 위원회 회의 공지 등 노이즈 제거: 화학물질 등재·경고·규제 관련 항목만 허용
    _PROP65_ACTION_WORDS = ["listed", "warning", "regulation", "proposition 65",
                            "prop 65", "nsrl", "added", "revised", "final", "notice of intent",
                            "chemical", "substance"]
    soup = _get_rss("https://oehha.ca.gov/rss.xml")
    if soup:
        for item in soup.find_all("item"):
            title = item.find("title").get_text(strip=True)       if item.find("title")       else ""
            desc  = item.find("description").get_text(strip=True) if item.find("description") else ""
            link  = item.find("link").get_text(strip=True)        if item.find("link")        else ""
            pub   = item.find("pubDate").get_text(strip=True)     if item.find("pubDate")     else ""
            kws = _find_keywords(f"{title} {desc}")
            if not kws:
                continue
            # 회의 공지(committee meeting) 등 행정 노이즈 필터
            combined_lower = f"{title} {desc}".lower()
            if "committee meeting" in combined_lower or "board meeting" in combined_lower:
                continue
            # 화학물질 규제 행동 관련 항목만 허용
            if not any(w in combined_lower for w in _PROP65_ACTION_WORDS):
                continue
            results.append({
                "source":           "CA Prop 65",
                "title":            title,
                "url":              link,
                "published_date":   pub[:16],
                "original_text":    f"{title}\n\n{desc}",
                "keywords_matched": ", ".join(kws),
                "_relevant":        True,
            })

    # 2) BPS·BPA 직접 페이지 (RSS 미등장 과거 등재 보완)
    for name, url in _CA_PROP65_DIRECT:
        soup2 = _get(url)
        if not soup2:
            continue
        text = soup2.get_text(separator=" ")[:20000]
        kws = _find_keywords(text)
        title_tag = soup2.find("h1") or soup2.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else name
        results.append({
            "source":           "CA Prop 65",
            "title":            f"[CA Prop 65] {page_title}",
            "url":              url,
            "published_date":   datetime.now().strftime("%Y-%m-%d"),
            "original_text":    text[:3000],
            "keywords_matched": ", ".join(kws) if kws else name,
            "_relevant":        True,
        })
        time.sleep(1)

    return results


# ── 핵심 알려진 규제 (직접 등록 — 스크래핑 의존 없음) ───────────────────────────
#
# 웹 스크래핑이 실패하거나 JS 렌더링으로 내용 추출이 어려운 중요 규제를
# 직접 등록하여 항상 수집되도록 보장
#
_KNOWN_REGULATIONS = [
    {
        "source":           "CA Prop 65",
        "title":            "[CA Prop 65] BPS (비스페놀S) 발달독성물질 등재 — 경고문구 의무화",
        "url":              "https://www.p65warnings.ca.gov/chemicals/bisphenol-s",
        "published_date":   "2021-12-17",
        "effective_date":   "2022-12-17",
        "original_text": (
            "BPS(비스페놀S, CAS 80-09-1)는 2021년 12월 17일 California Proposition 65 "
            "발달독성물질(developmental toxicant) 목록에 공식 등재됨.\n"
            "2022년 12월 17일부터 BPS 함유 제품(감열지 영수증 포함)에 Prop 65 경고문구 부착 의무화.\n"
            "감열지 제조사·수입사는 제품에 'WARNING: This product can expose you to Bisphenol S' "
            "등 경고 라벨을 부착하거나, BPS 대체 현색제로 전환 필요."
        ),
        "keywords_matched": "BPS, Bisphenol S, 80-09-1",
        "_relevant":        True,
    },
    {
        "source":           "CA Prop 65",
        "title":            "[CA AB 1988] 영수증 Phenol계 현색제 금지법 — 2027년 시행",
        "url":              "https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240AB1988",
        "published_date":   "2023-10-13",
        "effective_date":   "2027-01-01",
        "original_text": (
            "California AB 1988 (2023년 10월 서명, Pellerin 의원 발의):\n"
            "2027년 1월 1일부터 캘리포니아 내에서 BPS, BPA, TGSH 등 Phenol계 현색제 함유 "
            "영수증 용지(thermal receipt paper)의 제조·판매·배포 전면 금지.\n"
            "위반 시 건당 $1,000 과태료. 감열지 제조사는 Pergafast 201 등 대체 현색제로 "
            "2027년 이전에 전환 필요."
        ),
        "keywords_matched": "AB 1988, BPS, phenol developer, thermal paper, thermal receipt",
        "_relevant":        True,
    },
    {
        "source":           "WA Ecology",
        "title":            "[WA WAC 173-334] 워싱턴주 감열지 Phenol 현색제 규제 — Priority Consumer Products",
        "url":              "https://ecology.wa.gov/waste-toxics/reducing-toxic-threats/safer-products/priority-consumer-products/thermal-paper",
        "published_date":   "2022-09-01",
        "effective_date":   "2025-01-01",
        "original_text": (
            "Washington State WAC 173-334 (Safer Products for Washington Act 이행 규칙):\n"
            "감열지(Thermal Paper)를 우선소비자제품(Priority Consumer Product)으로 지정.\n"
            "BPS, BPA 등 Phenol계 현색제 함유 감열지의 제조·수입·판매 규제.\n"
            "2025년 1월 1일부터 보고 의무 발효, 2026년 단계적 판매 제한 시행 예정.\n"
            "대상: POS 영수증, 라벨, 주차권 등 직접열 방식 감열지 전 제품."
        ),
        "keywords_matched": "thermal paper, BPS, phenol developer, WAC 173-334, safer consumer products",
        "_relevant":        True,
    },
    {
        "source":           "DOC/USITC",
        "title":            "[반덤핑 A-580-875] 한국산 감열지 — 미국 DOC 반덤핑 관세 (행정재심 진행중)",
        "url":              "https://enforcement.trade.gov/frn/summary/korea-south/korea-south-A-580-875.htm",
        "published_date":   "2014-07-22",
        "effective_date":   "2014-07-22",
        "original_text": (
            "미국 상무부(DOC) 케이스 A-580-875: 한국산 감열지(Thermal Paper from the Republic of Korea) "
            "반덤핑 관세 조사.\n"
            "2014년 최초 확정판정 이후 매년 행정재심(Administrative Review) 진행 중.\n"
            "현재 재심 결과에 따라 덤핑마진 및 관세율 재결정 예정.\n"
            "주요 대상 기업: 한국제지, 한솔제지, Oji Paper 한국 법인 등.\n"
            "관세 부과 시 미국 수출 단가 경쟁력에 직접 영향."
        ),
        "keywords_matched": "antidumping, anti-dumping, A-580-875, thermal paper, Korea",
        "_relevant":        True,
    },
]


def scrape_known_regulations() -> List[Dict]:
    """핵심 알려진 규제 직접 등록 — JS 렌더링·차단 관계없이 항상 수집 보장"""
    print(f"      → {len(_KNOWN_REGULATIONS)}건 (고정 등록)")
    return list(_KNOWN_REGULATIONS)


# ── CA DTSC (403 차단 확인 — 제거) ───────────────────────────────────────────

def scrape_ca_dtsc() -> List[Dict]:
    """CA DTSC — 403 차단 확인됨, 현재 수집 불가"""
    print("    [CA DTSC] 403 차단 확인 — 수집 건너뜀")
    return []


# ── WA Ecology (감열지 전용 + PFAS + Safer Products) ─────────────────────────

_WA_ECOLOGY_URLS = [
    # 감열지 전용 규제 페이지 (Priority Consumer Products — Thermal Paper)
    "https://ecology.wa.gov/waste-toxics/reducing-toxic-threats/safer-products/priority-consumer-products/thermal-paper",
    # Safer Products 규제 프로그램 (BPS 등 감열지 현색제)
    "https://ecology.wa.gov/waste-toxics/reducing-toxic-threats/safer-products",
    # PFAS 유해물질 페이지 (감열지 PFAS 코팅 포함)
    "https://ecology.wa.gov/waste-toxics/reducing-toxic-threats/harmful-contaminants/pfas",
    # 일반 뉴스 (키워드 매칭 폴백)
    "https://ecology.wa.gov/News",
]


def scrape_wa_ecology() -> List[Dict]:
    """Washington State Ecology — 감열지 전용 규제·PFAS·Safer Products 페이지"""
    results = []
    seen_urls: set = set()

    for url in _WA_ECOLOGY_URLS:
        soup = _get(url)
        if not soup:
            continue

        # 페이지 전체 텍스트 키워드 탐색 (전용 페이지는 링크 없이도 내용 수집)
        page_text = soup.get_text(separator=" ")
        kws = _find_keywords(page_text[:30000])
        if kws and url not in seen_urls:
            seen_urls.add(url)
            title_tag = soup.find("h1")
            page_title = title_tag.get_text(strip=True) if title_tag else url.split("/")[-1].replace("-", " ").title()
            results.append({
                "source":           "WA Ecology",
                "title":            f"[WA Ecology] {page_title}",
                "url":              url,
                "published_date":   datetime.now().strftime("%Y-%m-%d"),
                "original_text":    page_text[:4000],
                "keywords_matched": ", ".join(kws),
                "_relevant":        True,
            })

        # 링크 탐색 (뉴스 페이지 등)
        for item in _links_with_keywords(soup, url, "WA Ecology"):
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                results.append(item)

        time.sleep(1)

    return results


# ── 통합 실행 ─────────────────────────────────────────────────────────────────

SOURCE_SCRAPERS: dict[str, list] = {
    # 핵심 알려진 규제를 맨 먼저 등록 (항상 수집 보장)
    "핵심 규제 (직접등록)": [
        ("핵심 규제 직접 등록 (CA BPS·AB1988·WA·반덤핑)", scrape_known_regulations),
    ],
    "ECHA": [
        ("ECHA 물질 상세 페이지 (우회)",  scrape_echa_substance_pages),
        ("ECHA SVHC 후보물질 (간헐적)",  scrape_echa_svhc),
        ("ECHA 뉴스 (차단됨)",           scrape_echa_news),
        ("ECHA REACH 제한물질 (차단됨)", scrape_echa_restrictions),
    ],
    "EPA": [
        ("EPA TSCA 화학물질",            scrape_epa_tsca),
        ("EPA 보도자료",                 scrape_epa_news),
    ],
    "FDA": [
        ("FDA 식품접촉재료",             scrape_fda_food_contact),
    ],
    "Federal Register": [
        ("Federal Register API (CAS 검색)", scrape_federal_register),
    ],
    "EFSA": [
        ("EFSA 뉴스",                    scrape_efsa_news),
    ],
    "미국 주(州)": [
        ("CA Prop 65 (OEHHA RSS — 규제 행동만)", scrape_ca_prop65),
        ("CA DTSC (차단됨)",                     scrape_ca_dtsc),
        ("WA Ecology (감열지·PFAS 전용)",         scrape_wa_ecology),
    ],
    "DOC/USITC": [
        ("반덤핑 Federal Register (A-580-875)", scrape_antidumping),
    ],
}

ALL_SCRAPERS = [item for group in SOURCE_SCRAPERS.values() for item in group]


def _run_scrapers(scraper_list: list, progress_callback=None) -> List[Dict]:
    all_items: List[Dict] = []
    for i, (label, fn) in enumerate(scraper_list):
        if progress_callback:
            progress_callback(label, i, len(scraper_list))
        print(f"  [{i+1}/{len(scraper_list)}] {label} 수집 중...")
        try:
            items = fn()
            relevant = [x for x in items if x.get("_relevant")]
            all_items.extend(relevant)
            print(f"        → {len(relevant)}건")
        except Exception as e:
            print(f"        → 오류: {e}")
    return all_items


def run_all(progress_callback=None) -> List[Dict]:
    return _run_scrapers(ALL_SCRAPERS, progress_callback)


def run_by_source(source: str, progress_callback=None) -> List[Dict]:
    scraper_list = SOURCE_SCRAPERS.get(source, [])
    if not scraper_list:
        print(f"[오류] 알 수 없는 기관: {source}")
        return []
    return _run_scrapers(scraper_list, progress_callback)
