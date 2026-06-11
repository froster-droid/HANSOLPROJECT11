import sqlite3
import pandas as pd
from datetime import datetime
import os

# Vercel은 /tmp 만 쓰기 가능, 로컬은 data/ 폴더 사용
if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
    DB_PATH = "/tmp/regulations.db"
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "regulations.db")

# ── 핵심 알려진 규제 (서버 시작 시 항상 DB에 보장) ───────────────────────────────
# effective_date 기준: 2026+ → 현행·예정, 2025 이하 → 기집행
_SEED_REGULATIONS = [
    {
        "source":           "CA Prop 65",
        "title":            "[CA Prop 65] BPS(비스페놀S) 발달독성물질 등재 — 경고문구 부착 의무 (집행 중)",
        "title_kr":         "캘리포니아 Prop 65: BPS(비스페놀S) 발달독성물질 등재 및 경고문구 부착 의무화",
        "url":              "https://www.p65warnings.ca.gov/chemicals/bisphenol-s",
        "published_date":   "2021-12-17",
        "effective_date":   "2026-01-01",
        "summary_kr": (
            "① BPS(비스페놀S, CAS 80-09-1)가 2021년 12월 California Prop 65 발달독성물질로 "
            "공식 등재됨. "
            "② 2022년 12월부터 BPS 함유 감열지 영수증·라벨 제품에 Prop 65 경고문구 부착 의무화 — "
            "미이행 시 민사소송 및 건당 최대 $2,500 벌금. "
            "③ 캘리포니아 내 유통 제품에 적용되므로 한국산 감열지 수출 시 BPS-free 현색제 전환 "
            "또는 경고 라벨 부착 대응 필수."
        ),
        "importance":       "🔴 긴급",
        "keywords_matched": "BPS, Bisphenol S, 80-09-1, CA Prop 65",
    },
    {
        "source":           "WA Ecology",
        "title":            "[WA WAC 173-337] 감열지 비스페놀 현색제 판매·제조 금지 — Safer Products for Washington",
        "title_kr":         "워싱턴주 WAC 173-337: 감열지 비스페놀계 현색제 제조·판매 금지 (2025-01-01 발효)",
        "url":              "https://ecology.wa.gov/waste-toxics/reducing-toxic-threats/safer-products/priority-consumer-products/thermal-paper",
        "published_date":   "2023-07-01",
        "effective_date":   "2026-01-01",
        "summary_kr": (
            "① 워싱턴주 Safer Products for Washington Act(WAC 173-337)에 따라 "
            "감열지(Thermal Paper)가 우선소비자제품(Priority Consumer Product)으로 지정됨 "
            "(규칙 발효: 2023년 7월 1일). "
            "② 2025년 1월 1일부터 BPS(비스페놀S) 등 비스페놀계 현색제 함유 감열지의 "
            "워싱턴주 내 제조·판매 제한 발효 — 현재 집행 중. "
            "③ 한국산 감열지 수출업체는 Pergafast 201 등 비스페놀-free 현색제로 전환 완료 필수, "
            "미준수 시 워싱턴주 시장 접근 불가."
        ),
        "importance":       "🔴 긴급",
        "keywords_matched": "thermal paper, BPS, bisphenol, WAC 173-337, safer consumer products",
    },
    {
        "source":           "CA Prop 65",
        "title":            "[CA AB 1604] 영수증 비스페놀 금지법(Bisphenols in Receipts Act) — 의회 심의 중",
        "title_kr":         "캘리포니아 AB 1604: 영수증 용지 비스페놀류 전면 금지법안 (2027~2028년 시행 추진)",
        "url":              "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260AB1604",
        "published_date":   "2025-01-01",
        "effective_date":   "2027-01-01",
        "summary_kr": (
            "① California AB 1604(Stefani 의원 발의, Bisphenols in Receipts Act): "
            "감열지 영수증 용지에 BPA(비스페놀A) 및 모든 비스페놀류 사용을 단계적으로 금지하는 법안. "
            "② 시행 일정(안): 2027년 1월 1일 BPA 금지 → 2028년 1월 1일 전체 비스페놀류 금지. "
            "③ 2026년 6월 기준 환경안전·사법위원회 만장일치 통과, 세출위원회 심의 중 — "
            "서명 시 한국산 감열지의 캘리포니아 수출에 직접 영향. [주의: 미서명 법안, 향후 변동 가능]"
        ),
        "importance":       "🔴 긴급",
        "keywords_matched": "AB 1604, BPS, BPA, bisphenol, thermal paper, thermal receipt",
    },
    {
        "source":           "DOC/USITC",
        "title":            "[반덤핑 A-580-911] 한국산 감열지 — 미국 DOC 반덤핑 관세 행정재심 (한솔 2023-24 덤핑마진 0%)",
        "title_kr":         "미국 DOC A-580-911: 한국산 감열지 반덤핑 관세 — 행정재심 진행중 (한솔 2023-24 덤핑마진 0% 예비판정)",
        "url":              "https://www.federalregister.gov/documents/2021/11/22/2021-25365/thermal-paper-from-germany-japan-the-republic-of-korea-and-spain-antidumping-duty-orders",
        "published_date":   "2021-11-22",
        "effective_date":   "2026-06-01",
        "summary_kr": (
            "① 미국 상무부(DOC) 케이스 A-580-911: 한국·독일·일본·스페인산 감열지 반덤핑 관세 명령 "
            "(2021년 9월 27일 발효). "
            "② 매년 행정재심(Administrative Review) 진행 중이며, "
            "2023-2024년 재심에서 한솔제지 덤핑마진 0% 예비 판정 — "
            "최종 확정 시 한솔 관세 면제 가능. "
            "③ 한솔 외 국내 수출업체는 기존 덤핑마진 관세율 계속 적용 가능성 — "
            "재심 최종 결과 및 업체별 판정에 따라 수출 단가 경쟁력 직접 영향."
        ),
        "importance":       "🟡 주목",
        "keywords_matched": "antidumping, anti-dumping, A-580-911, thermal paper, Korea",
    },
]


def seed_known_regulations():
    """서버 시작 시 핵심 규제를 DB에 직접 삽입/갱신 (AI 요약 파이프라인 우회)"""
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for data in _SEED_REGULATIONS:
        # 신규 삽입 (URL 중복 시 무시)
        conn.execute(
            """INSERT OR IGNORE INTO regulations
               (source, title, title_kr, url, published_date, scraped_date,
                original_text, summary_kr, importance, effective_date, keywords_matched)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["source"], data["title"], data["title_kr"],
                data["url"], data["published_date"], now,
                "", data["summary_kr"], data["importance"],
                data["effective_date"], data["keywords_matched"],
            ),
        )
        # 기존 레코드도 날짜·요약·중요도 항상 최신으로 갱신
        conn.execute(
            """UPDATE regulations SET
               title_kr = ?, summary_kr = ?, importance = ?, effective_date = ?
               WHERE url = ?""",
            (
                data["title_kr"], data["summary_kr"], data["importance"],
                data["effective_date"], data["url"],
            ),
        )
    conn.commit()
    conn.close()
    print(f"[DB seed] 핵심 규제 {len(_SEED_REGULATIONS)}건 보장 완료")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS regulations (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            source           TEXT    NOT NULL,
            title            TEXT    NOT NULL,
            title_kr         TEXT    DEFAULT '',
            url              TEXT    UNIQUE,
            published_date   TEXT,
            scraped_date     TEXT,
            original_text    TEXT,
            summary_kr       TEXT,
            importance       TEXT    DEFAULT '⚪ 참고',
            effective_date   TEXT,
            keywords_matched TEXT,
            is_read          INTEGER DEFAULT 0
        )
    """)
    # 기존 DB에 컬럼이 없을 경우 추가 (마이그레이션)
    try:
        c.execute("ALTER TABLE regulations ADD COLUMN title_kr TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    conn.commit()
    conn.close()


def insert_regulation(data: dict) -> bool:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT INTO regulations
               (source, title, title_kr, url, published_date, scraped_date,
                original_text, summary_kr, importance, effective_date, keywords_matched)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("source", ""),
                data.get("title", ""),
                data.get("title_kr", ""),
                data.get("url", ""),
                data.get("published_date", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                data.get("original_text", ""),
                data.get("summary_kr", ""),
                data.get("importance", "⚪ 참고"),
                data.get("effective_date", ""),
                data.get("keywords_matched", ""),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_regulations(source=None, importance=None, days=None) -> pd.DataFrame:
    """
    days=None  → 전체 기간
    days=N     → 수집일(scraped_date) 기준 최근 N일. localtime 보정 적용.
    """
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM regulations WHERE 1=1"
    params: list = []

    if source and source != "전체":
        query += " AND source = ?"
        params.append(source)
    if importance and importance != "전체":
        query += " AND importance = ?"
        params.append(importance)
    if days is not None:
        # localtime 보정으로 한국 시간 기준 날짜 필터
        query += " AND scraped_date >= datetime('now', 'localtime', ?)"
        params.append(f"-{days} days")

    query += " ORDER BY scraped_date DESC, importance ASC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def mark_as_read(reg_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE regulations SET is_read = 1 WHERE id = ?", (reg_id,))
    conn.commit()
    conn.close()


def delete_regulation(reg_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM regulations WHERE id = ?", (reg_id,))
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    total  = c.execute("SELECT COUNT(*) FROM regulations").fetchone()[0]
    urgent = c.execute("SELECT COUNT(*) FROM regulations WHERE importance = '🔴 긴급'").fetchone()[0]
    today  = c.execute("SELECT COUNT(*) FROM regulations WHERE date(scraped_date) = date('now')").fetchone()[0]
    unread = c.execute("SELECT COUNT(*) FROM regulations WHERE is_read = 0").fetchone()[0]
    conn.close()
    return {"total": total, "urgent": urgent, "today": today, "unread": unread}
