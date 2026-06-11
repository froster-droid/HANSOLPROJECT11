import os
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "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")
OPENAI_MODEL   = "gpt-4o-mini"

THERMAL_KEYWORDS = [

    # ── BPA (비스페놀A) ───────────────────────────────────────────────────
    # CAS 80-05-7 | 2,2-bis(4-hydroxyphenyl)propane
    "BPA", "Bisphenol A", "bisphenol A",
    "80-05-7",
    "2,2-bis(4-hydroxyphenyl)propane",
    "4,4'-isopropylidenediphenol",

    # ── BPS (비스페놀S) ───────────────────────────────────────────────────
    # CAS 80-09-1 | 4,4'-sulfonyldiphenol
    "BPS", "Bisphenol S", "bisphenol S",
    "80-09-1",
    "4,4'-sulfonyldiphenol",
    "4,4'-dihydroxydiphenyl sulfone",
    "bis(4-hydroxyphenyl) sulfone",

    # ── TGSH (비스페놀S계 대체 현색제) ───────────────────────────────────
    # CAS 41481-66-7 | Bis(3-allyl-4-hydroxyphenyl)sulfone
    "TGSH",
    "41481-66-7",
    "Bis(3-allyl-4-hydroxyphenyl)sulfone",
    "4,4'-sulfonylbis(2-allylphenol)",

    # ── D8 (비페놀설폰계 대체 현색제) ────────────────────────────────────
    # CAS 95235-30-6 | 4-Hydroxy-4'-isopropoxydiphenylsulfone
    "D-8", "D8 developer",
    "95235-30-6",
    "4-hydroxy-4'-isopropoxydiphenylsulfone",
    "4-[(4-isopropoxyphenyl)sulfonyl]phenol",

    # ── Pergafast 201 (비페놀 계열 비페놀계 대체 현색제) ─────────────────
    # CAS 232938-43-1 | 비페놀·페놀 프리 대체 현색제
    "Pergafast", "Pergafast 201", "PF-201",
    "232938-43-1",

    # ── 비스페놀 상위 포괄어 ──────────────────────────────────────────────
    "bisphenol", "Bisphenol",

    # ── 감열 염료 ─────────────────────────────────────────────────────────
    "leuco dye", "leuco base",
    "fluoran",
    "ODB-2",

    # ── 현색제 일반 ───────────────────────────────────────────────────────
    "colour developer", "color developer",
    "phenol developer",

    # ── 감열지 제품 유형 ──────────────────────────────────────────────────
    "thermal paper", "thermal receipt",
    "thermal label", "direct thermal",
    "receipt paper", "till receipt",
    "POS paper", "cash register receipt",
    "linerless label",

    # ── 식품접촉 ──────────────────────────────────────────────────────────
    "food contact material",    # "food contact" 단독 제거 → 노이즈 원인
    "migration limit", "migration testing",

    # ── 규제 체계 용어 (감열지 직접 연관 항목만 유지) ────────────────────
    "SVHC", "substance of very high concern",
    "safer consumer products",

    # ── PFAS (WA주 감열지 코팅 규제) ─────────────────────────────────────
    "PFAS", "per- and polyfluoroalkyl", "perfluoroalkyl",
    "PFOA", "PFOS",

    # ── CA 감열지 법안 / Phenol류 현색제 규제 ────────────────────────────
    "AB 1988",              # CA 2023년 영수증 Phenol 현색제 금지법 (2027년 시행)
    "phenol developer", "phenolic developer",
    "receipt paper ban",

    # ── 반덤핑 / 무역 구제 (미국 DOC, USITC) ─────────────────────────────
    "antidumping", "anti-dumping",
    "A-580-911",            # 미국 DOC 대한민국 감열지 반덤핑 케이스 번호 (2021년 발효)
    "countervailing duty",
    "dumping margin",
]

SOURCES = {
    "ECHA":             "유럽화학물질청",
    "EPA":              "미국환경보호청",
    "FDA":              "미국식품의약국",
    "EFSA":             "유럽식품안전청",
    "CA Prop 65":       "캘리포니아 Prop 65",
    "WA Ecology":       "워싱턴주 생태부",
    "Federal Register": "미국 연방관보",
    "DOC/USITC":        "미국 상무부/무역위",
}
