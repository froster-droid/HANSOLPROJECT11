import os
import streamlit as st
import pandas as pd
from datetime import datetime, date
from PIL import Image

import database as db
import scraper
import summarizer

# ── 페이지 설정 ────────────────────────────────────────────────────────────────
_icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
_page_icon = Image.open(_icon_path) if os.path.exists(_icon_path) else "📋"

st.set_page_config(
    page_title="감열지 규제 모니터",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

db.init_db()

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 16px 20px;
        text-align: center;
    }
    .urgent-badge  { color: #d32f2f; font-weight: 700; }
    .notice-badge  { color: #f57c00; font-weight: 700; }
    .info-badge    { color: #757575; }
    .tag {
        display: inline-block;
        background: #e3f2fd;
        color: #1565c0;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.8em;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)


# ── 사이드바 ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📋 감열지 규제 모니터")
    st.caption("POS·라벨 감열지 | 미국·유럽")
    st.divider()

    st.subheader("🔎 필터")
    source_filter     = st.selectbox("기관",   ["전체", "ECHA", "EPA", "FDA", "EFSA", "CA Prop 65", "CA DTSC", "WA Ecology"])
    importance_filter = st.selectbox("중요도", ["전체", "🔴 긴급", "🟡 주목", "⚪ 참고"])

    # 기간 필터 — 실제 날짜 범위를 라벨에 표시
    today = datetime.now()
    PERIOD_OPTIONS = {
        "전체 기간": None,
        f"최근 7일  ({(today - pd.Timedelta(days=7)).strftime('%m/%d')} ~ 오늘)": 7,
        f"최근 30일  ({(today - pd.Timedelta(days=30)).strftime('%m/%d')} ~ 오늘)": 30,
        f"최근 90일  ({(today - pd.Timedelta(days=90)).strftime('%m/%d')} ~ 오늘)": 90,
        f"최근 1년  ({(today - pd.Timedelta(days=365)).strftime('%Y/%m/%d')} ~ 오늘)": 365,
    }
    period_label  = st.selectbox("📅 수집 기간", list(PERIOD_OPTIONS.keys()))
    days_filter   = PERIOD_OPTIONS[period_label]

    # 선택된 범위를 날짜로 명시
    if days_filter is None:
        st.caption("🗓 전체 수집 기록을 표시합니다.")
    else:
        from_date = (today - pd.Timedelta(days=days_filter)).strftime("%Y년 %m월 %d일")
        st.caption(f"🗓 **{from_date}** 이후 수집된 항목을 표시합니다.")

    st.divider()
    st.subheader("⚙️ 수집 실행")

    # ── 전체 통합 수집 ──
    run_all_btn = st.button("🔄 전체 통합 수집", type="primary", use_container_width=True,
                            help="ECHA · EPA · FDA · EFSA 전체 기관을 한 번에 수집합니다.")

    # ── 기관별 개별 수집 ──
    st.caption("🌐 연방 기관")
    col_a, col_b = st.columns(2)
    with col_a:
        btn_echa = st.button("ECHA ↗️", use_container_width=True,
                             help="물질 상세 페이지 우회 수집 (BPA·BPS 등 5종) + SVHC 간헐 시도")
        btn_fda  = st.button("FDA ✅",  use_container_width=True,
                             help="Federal Register API + FDA RSS 우회 수집 정상")
    with col_b:
        btn_epa  = st.button("EPA",     use_container_width=True)
        btn_efsa = st.button("EFSA ✅", use_container_width=True,
                             help="정상 수집 중")

    st.caption("🏛 미국 주(州) 규제")
    btn_state = st.button("CA Prop 65 ✅ · WA", use_container_width=True,
                          help="CA Prop 65 RSS 정상 수집 / CA DTSC 차단됨")

    # 어떤 버튼이 눌렸는지 판별
    selected_source = None
    if run_all_btn:
        selected_source = "ALL"
    elif btn_echa:
        selected_source = "ECHA"
    elif btn_epa:
        selected_source = "EPA"
    elif btn_fda:
        selected_source = "FDA"
    elif btn_efsa:
        selected_source = "EFSA"
    elif btn_state:
        selected_source = "미국 주(州)"

    if selected_source:
        label_text = "전체 기관" if selected_source == "ALL" else selected_source
        status_box  = st.empty()
        progress    = st.progress(0)

        def scraper_progress(label, i, total):
            status_box.caption(f"수집 중: {label}")
            progress.progress((i + 1) / total * 0.6)

        with st.spinner(f"{label_text} 수집 중..."):
            if selected_source == "ALL":
                items = scraper.run_all(progress_callback=scraper_progress)
            else:
                items = scraper.run_by_source(selected_source, progress_callback=scraper_progress)

        if not items:
            st.warning(f"{label_text}: 감열지 관련 신규 문서 없음")
            progress.empty()
        else:
            status_box.caption(f"AI 요약 중... ({len(items)}건)")
            ai_progress = st.progress(0)

            def ai_prog(done, total):
                ai_progress.progress(done / total)

            summarized = summarizer.batch_summarize(items, progress_callback=ai_prog)

            new_count = sum(1 for item in summarized if db.insert_regulation(item))
            progress.progress(1.0)
            ai_progress.empty()
            status_box.success(f"✅ [{label_text}] 신규 {new_count}건 저장 / 중복 {len(summarized) - new_count}건 제외")
            st.rerun()

    st.divider()
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')} 기준")


# ── 메인 화면 ──────────────────────────────────────────────────────────────────
st.title("🌐 글로벌 감열지 규제 모니터링 대시보드")
st.caption("ECHA · EPA · FDA · EFSA | BPA / BPS / 식품접촉재료 / SVHC 중심")

# 통계 카드
stats = db.get_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("📂 전체 수집", f"{stats['total']}건")
c2.metric("🔴 긴급",      f"{stats['urgent']}건")
c3.metric("📅 오늘 신규", f"{stats['today']}건")
c4.metric("👁 미확인",    f"{stats['unread']}건")

st.divider()

# 데이터 로드
df = db.get_regulations(
    source=source_filter,
    importance=importance_filter,
    days=days_filter,
)

if df.empty:
    if stats["total"] == 0:
        # DB 자체가 비어있음 → 한 번도 수집 안 한 상태
        st.warning(
            "#### 📭 아직 수집된 데이터가 없습니다\n\n"
            "왼쪽 사이드바에서 **🔄 전체 통합 수집** 또는 기관별 버튼을 눌러 "
            "처음 수집을 시작해주세요.\n\n"
            "> 최초 수집은 1~3분 정도 소요됩니다."
        )
    else:
        # DB에 데이터는 있지만 현재 필터 조건에 맞는 결과가 없음
        st.info(
            f"#### 🔍 현재 필터 조건에 해당하는 데이터가 없습니다\n\n"
            f"- 기관: **{source_filter}** · 중요도: **{importance_filter}** · 기간: **{period_label}**\n\n"
            f"필터를 조정하거나, 사이드바에서 수집을 다시 실행해보세요.\n\n"
            f"*(전체 DB에는 현재 **{stats['total']}건** 저장되어 있습니다)*"
        )
    st.stop()

# 탭 구성
tab_list, tab_tracker, tab_export, tab_sources = st.tabs(["📋 규제 목록", "📅 D-day 트래커", "📥 내보내기", "🔗 규제 사이트"])


# ── 공통 함수: 규제 항목 카드 렌더링 ─────────────────────────────────────────
def _render_regulation_card(row, idx_prefix: str):
    imp = str(row.get("importance", "⚪ 참고"))
    expanded = imp == "🔴 긴급"

    title_kr  = str(row.get("title_kr") or "").strip()
    title_en  = str(row.get("title")    or "").strip()
    display_title = title_kr if title_kr else title_en
    display_short = display_title[:90] + ("..." if len(display_title) > 90 else "")
    header = f"{imp} &nbsp; [{row['source']}] &nbsp; {display_short}"

    with st.expander(header, expanded=expanded):
        left, right = st.columns([3, 1])

        with left:
            if title_kr:
                st.markdown(f"**📌 {title_kr}**")
            if title_en:
                st.caption(f"원문 제목: {title_en}")
            st.markdown("**📝 AI 요약**")
            summary = str(row.get("summary_kr") or "요약 없음")
            st.write(summary)

            kws = str(row.get("keywords_matched") or "")
            if kws:
                tags_html = " ".join(f'<span class="tag">{k.strip()}</span>'
                                     for k in kws.split(",") if k.strip())
                st.markdown(f"**감지 키워드:** {tags_html}", unsafe_allow_html=True)

        with right:
            st.markdown(f"**출처:** `{row['source']}`")
            st.markdown(f"**수집:** {str(row.get('scraped_date',''))[:16]}")

            pub = str(row.get("published_date") or "")
            if pub:
                st.markdown(f"**발행:** {pub}")

            eff = str(row.get("effective_date") or "")
            if eff and eff not in ("", "미확인"):
                try:
                    eff_dt    = datetime.strptime(eff, "%Y-%m-%d")
                    days_left = (eff_dt - datetime.now()).days
                    d_label   = f"D-{days_left}" if days_left >= 0 else f"D+{abs(days_left)} (시행됨)"
                    st.markdown(f"**⏰ 시행일:** {eff}  \n`{d_label}`")
                except Exception:
                    st.markdown(f"**⏰ 시행일:** {eff}")

            url = str(row.get("url") or "")
            if url:
                st.markdown(f"[🔗 원문 보기]({url})")

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if not int(row.get("is_read", 0)):
                    if st.button("✅ 확인", key=f"read_{idx_prefix}_{row['id']}"):
                        db.mark_as_read(int(row["id"]))
                        st.rerun()
            with btn_col2:
                if st.button("🗑 삭제", key=f"del_{idx_prefix}_{row['id']}"):
                    db.delete_regulation(int(row["id"]))
                    st.rerun()


def _classify_row(row) -> str:
    """
    시행일 기준으로 분류:
    - effective_date가 있으면 그 연도로 판단
    - 없으면 published_date 연도로 판단
    - 날짜 파싱 실패 시 'current' 취급
    """
    for field in ("effective_date", "published_date"):
        val = str(row.get(field) or "").strip()
        if not val or val in ("미확인", ""):
            continue
        # 다양한 날짜 형식 처리
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%B %d, %Y", "%b %d, %Y", "%d %b %Y"):
            try:
                dt = datetime.strptime(val[:10], fmt[:len(val[:10])])
                return "past" if dt.year <= 2025 else "current"
            except Exception:
                pass
        # 연도만 있는 경우
        if val[:4].isdigit():
            return "past" if int(val[:4]) <= 2025 else "current"
    return "current"


# ── 탭 1: 규제 목록 ────────────────────────────────────────────────────────────
with tab_list:

    # 2025 이전 / 2026 이후 분류
    df_current = df[df.apply(lambda r: _classify_row(r) == "current", axis=1)].copy()
    df_past    = df[df.apply(lambda r: _classify_row(r) == "past",    axis=1)].copy()

    # ── 섹션 1: 현행·예정 (2026~) ──────────────────────────────────────────────
    st.markdown(
        "<div style='background:#e8f4fd;border-left:4px solid #1976d2;"
        "padding:10px 16px;border-radius:4px;margin-bottom:8px'>"
        "<b style='color:#1976d2'>📌 현행·예정 규제 (2026년~)</b>"
        f"<span style='color:#555;font-size:0.88em;margin-left:12px'>{len(df_current)}건</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    if df_current.empty:
        st.info("2026년 이후 해당하는 규제가 없습니다. 수집을 실행하거나 필터를 조정해보세요.")
    else:
        for _, row in df_current.iterrows():
            _render_regulation_card(row, "cur")

    st.divider()

    # ── 섹션 2: 기집행 규제 (~2025) ────────────────────────────────────────────
    with st.expander(
        f"📁 기집행 규제 (~2025년)  —  {len(df_past)}건  ·  참고용",
        expanded=False,
    ):
        st.caption("이미 시행된 규제입니다. 히스토리 참고 및 규정 준수 확인용으로 활용하세요.")
        if df_past.empty:
            st.info("2025년 이전 기집행 규제가 없습니다.")
        else:
            for _, row in df_past.iterrows():
                _render_regulation_card(row, "past")


# ── 탭 2: D-day 트래커 ─────────────────────────────────────────────────────────
with tab_tracker:
    eff_df = df[df["effective_date"].notna() & (df["effective_date"] != "") & (df["effective_date"] != "미확인")].copy()

    if eff_df.empty:
        st.info("시행 예정일이 확인된 규제가 없습니다.")
    else:
        now = datetime.now()

        def calc_dday(date_str):
            try:
                return (datetime.strptime(str(date_str), "%Y-%m-%d") - now).days
            except Exception:
                return None

        eff_df["D-day"] = eff_df["effective_date"].apply(calc_dday)
        eff_df = eff_df.dropna(subset=["D-day"]).sort_values("D-day")

        for _, row in eff_df.iterrows():
            d = int(row["D-day"])
            if d >= 0:
                label = f"🔴 D-{d}" if d <= 30 else f"🟡 D-{d}" if d <= 90 else f"⚪ D-{d}"
            else:
                label = f"✅ 시행됨 (D+{abs(d)})"

            st.markdown(
                f"**{label}** &nbsp; [{row['source']}] &nbsp; {str(row['title'])[:70]}  \n"
                f"시행일: `{row['effective_date']}`"
            )
            st.divider()


# ── 탭 3: 내보내기 ─────────────────────────────────────────────────────────────
with tab_export:
    st.subheader("CSV 내보내기")

    export_df = df[[
        "source", "importance", "title", "summary_kr",
        "keywords_matched", "published_date", "effective_date", "url"
    ]].rename(columns={
        "source":           "기관",
        "importance":       "중요도",
        "title":            "제목",
        "summary_kr":       "한국어 요약",
        "keywords_matched": "감지 키워드",
        "published_date":   "발행일",
        "effective_date":   "시행 예정일",
        "url":              "원문 링크",
    })

    st.dataframe(export_df, use_container_width=True, height=300)

    csv_data = export_df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="⬇️ CSV 다운로드",
        data=csv_data,
        file_name=f"감열지_규제모니터_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

    st.subheader("주간 브리핑 텍스트")
    urgent_items = df[df["importance"] == "🔴 긴급"]
    notice_items = df[df["importance"] == "🟡 주목"]

    report_lines = [
        f"# 감열지 규제 주간 브리핑 — {datetime.now().strftime('%Y년 %m월 %d일')}",
        "",
        f"## 🔴 긴급 ({len(urgent_items)}건)",
    ]
    for _, r in urgent_items.iterrows():
        report_lines.append(f"- [{r['source']}] {r['title']}")
        report_lines.append(f"  → {r.get('summary_kr','')}")
        report_lines.append("")

    report_lines += [f"## 🟡 주목 ({len(notice_items)}건)"]
    for _, r in notice_items.iterrows():
        report_lines.append(f"- [{r['source']}] {r['title']}")
        report_lines.append(f"  → {r.get('summary_kr','')}")
        report_lines.append("")

    report_text = "\n".join(report_lines)
    st.text_area("브리핑 미리보기", report_text, height=300)
    st.download_button(
        label="⬇️ 브리핑 텍스트 다운로드",
        data=report_text.encode("utf-8"),
        file_name=f"주간브리핑_{datetime.now().strftime('%Y%m%d')}.txt",
        mime="text/plain",
    )


# ── 탭 4: 규제 사이트 링크 ─────────────────────────────────────────────────────
with tab_sources:
    st.caption("감열지 관련 규제를 직접 확인할 수 있는 공식 사이트 목록입니다.")

    SOURCES_INFO = [
        {
            "region": "🇪🇺 유럽",
            "sites": [
                {
                    "name": "ECHA — SVHC 후보물질 목록",
                    "desc": "BPA·BPS 등 고위험성물질(SVHC) 지정 현황. 연 2회 업데이트.",
                    "url": "https://echa.europa.eu/candidate-list-table",
                    "tag": "REACH / SVHC",
                },
                {
                    "name": "ECHA — REACH Annex XVII 제한물질",
                    "desc": "EU에서 사용·판매가 제한된 화학물질 목록. 감열지 BPA 금지(2020) 포함.",
                    "url": "https://echa.europa.eu/substances-restricted-under-reach",
                    "tag": "REACH 제한",
                },
                {
                    "name": "ECHA — 물질 검색",
                    "desc": "개별 화학물질(BPA, BPS 등)의 규제 현황, 분류, 위험성 정보 검색.",
                    "url": "https://echa.europa.eu/information-on-chemicals",
                    "tag": "물질 정보",
                },
                {
                    "name": "ECHA — 뉴스 & 보도자료",
                    "desc": "ECHA 최신 규제 동향 및 공식 발표.",
                    "url": "https://www.echa.europa.eu/en/press-releases",
                    "tag": "뉴스",
                },
                {
                    "name": "EFSA — 식품접촉재료 평가",
                    "desc": "감열지가 식품과 접촉 시 BPA 이행(migration) 위험성 평가 결과.",
                    "url": "https://www.efsa.europa.eu/en/topics/topic/food-contact-materials",
                    "tag": "식품접촉",
                },
                {
                    "name": "EUR-Lex — EU 관보 (Official Journal)",
                    "desc": "EU 규정 공식 발효 원문. 감열지 BPA 금지 규정(2016/2235) 등 검색 가능.",
                    "url": "https://eur-lex.europa.eu/homepage.html",
                    "tag": "법령 원문",
                },
                {
                    "name": "EUR-Lex — 감열지 BPA 금지 규정 (2016/2235)",
                    "desc": "EU의 감열지 BPA 사용 금지를 명시한 규정 원문 (2020년 1월 시행).",
                    "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R2235",
                    "tag": "법령 원문",
                },
            ],
        },
        {
            "region": "🇺🇸 미국",
            "sites": [
                {
                    "name": "EPA — TSCA 기존화학물질 위험성 평가",
                    "desc": "BPA·BPS 등 TSCA 대상 화학물질 위험성 평가 진행 현황.",
                    "url": "https://www.epa.gov/chemicals-under-tsca/risk-evaluations-existing-chemicals-under-tsca",
                    "tag": "TSCA",
                },
                {
                    "name": "EPA — BPA 정보 페이지",
                    "desc": "EPA의 BPA 공식 입장, 연구 현황, 규제 조치 정보.",
                    "url": "https://www.epa.gov/assessing-and-managing-chemicals-under-tsca/bisphenol-bpa",
                    "tag": "BPA 전용",
                },
                {
                    "name": "EPA — 보도자료",
                    "desc": "EPA 최신 화학물질 규제 관련 발표.",
                    "url": "https://www.epa.gov/newsreleases",
                    "tag": "뉴스",
                },
                {
                    "name": "FDA — 식품접촉물질 신고 프로그램",
                    "desc": "감열지 등 식품 접촉 재료의 FDA 승인 및 신고 현황.",
                    "url": "https://www.fda.gov/food/food-additives-petitions/food-contact-substance-fcs-notification-program",
                    "tag": "식품접촉",
                },
                {
                    "name": "FDA — 화학물질 안전 정보",
                    "desc": "BPA 포함 식품 관련 화학물질 FDA 공식 안전성 정보.",
                    "url": "https://www.fda.gov/food/chemicals",
                    "tag": "BPA / 화학물질",
                },
                {
                    "name": "Federal Register — 규제 입법 예고",
                    "desc": "미국 연방 규제 입법 예고 검색. 'bisphenol' 또는 'thermal paper'로 검색.",
                    "url": "https://www.federalregister.gov/documents/search?conditions%5Bterm%5D=bisphenol",
                    "tag": "입법 예고",
                },
            ],
        },
        {
            "region": "🏛 미국 주(州) 환경규제",
            "sites": [
                {
                    "name": "California Prop 65 — 유해물질 경고 목록",
                    "desc": "캘리포니아 주민 건강에 해로운 화학물질 목록. BPA·BPS 포함 여부 및 경고 기준 확인.",
                    "url": "https://www.p65warnings.ca.gov/chemicals",
                    "tag": "CA Prop 65",
                },
                {
                    "name": "OEHHA — Prop 65 공식 물질 목록",
                    "desc": "캘리포니아 환경건강위험평가청(OEHHA) 공식 유해물질 목록 원본.",
                    "url": "https://oehha.ca.gov/proposition-65/proposition-65-list",
                    "tag": "CA Prop 65",
                },
                {
                    "name": "CA DTSC — 안전소비재 규정 (Safer Consumer Products)",
                    "desc": "캘리포니아 독성물질관리부. 소비재 내 유해화학물질 규제. 감열지 포함 가능성 있음.",
                    "url": "https://www.dtsc.ca.gov/safer-products-and-workplaces/safer-consumer-products",
                    "tag": "CA DTSC",
                },
                {
                    "name": "CA DTSC — 우려 화학물질 목록",
                    "desc": "캘리포니아 규제 대상 우려 화학물질(Chemicals of Concern) 리스트.",
                    "url": "https://www.dtsc.ca.gov/safer-products-and-workplaces/chemicals-of-concern",
                    "tag": "CA DTSC",
                },
                {
                    "name": "Washington Ecology — 아동 유해 화학물질 규제",
                    "desc": "워싱턴 주 환경부. BPA 등 아동 건강 위해 화학물질 규제 현황.",
                    "url": "https://ecology.wa.gov/waste-toxics/reducing-toxic-threats/chemicals-of-high-concern-to-children",
                    "tag": "WA Ecology",
                },
                {
                    "name": "Washington Ecology — 규제 및 입법 현황",
                    "desc": "워싱턴 주 환경부 최신 규제 입법 현황 및 규칙 개정 동향.",
                    "url": "https://ecology.wa.gov/regulations-permits/laws-rules-rulemaking",
                    "tag": "WA Ecology",
                },
            ],
        },
        {
            "region": "📚 특허 · 기술 동향",
            "sites": [
                {
                    "name": "Google Patents — 감열지 특허 검색",
                    "desc": "BPA-free 현색제, 감열 코팅 관련 최신 특허 검색.",
                    "url": "https://patents.google.com/?q=thermal+paper+BPA-free+developer&after=priority:20200101",
                    "tag": "특허",
                },
                {
                    "name": "Espacenet — 유럽 특허청 특허 검색",
                    "desc": "유럽 특허청(EPO) 특허 데이터베이스. 감열지 관련 유럽 특허 검색.",
                    "url": "https://worldwide.espacenet.com/patent/search?q=thermal%20paper%20bisphenol",
                    "tag": "특허",
                },
            ],
        },
    ]

    for section in SOURCES_INFO:
        st.subheader(section["region"])
        for site in section["sites"]:
            col_info, col_btn = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"**{site['name']}** &nbsp; "
                    f"<span class='tag'>{site['tag']}</span>",
                    unsafe_allow_html=True,
                )
                st.caption(site["desc"])
            with col_btn:
                st.markdown(
                    f"<a href='{site['url']}' target='_blank'>"
                    f"<button style='width:100%;padding:6px 0;border-radius:6px;"
                    f"border:1px solid #ccc;background:#f0f2f6;cursor:pointer;'>🔗 바로가기</button>"
                    f"</a>",
                    unsafe_allow_html=True,
                )
        st.divider()
