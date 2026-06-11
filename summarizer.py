from typing import Dict, List

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL

try:
    _client = OpenAI(api_key=OPENAI_API_KEY)
    OPENAI_AVAILABLE = True
except Exception as e:
    print(f"[OpenAI 초기화 실패] {e}")
    _client = None
    OPENAI_AVAILABLE = False

_IMPORTANCE_LABELS = {
    "긴급": "🔴 긴급",
    "주목": "🟡 주목",
    "참고": "⚪ 참고",
}

_SYSTEM_PROMPT = """\
당신은 감열지(thermal paper) 산업의 규제 전문가입니다. 반드시 한국어로만 응답하세요.

[화학물질 약어 → 한글 규칙]
약어를 쓸 때는 반드시 괄호 안에 한글 풀네임을 병기하세요.
- BPA → BPA(비스페놀A)
- BPS → BPS(비스페놀S)
- BPF → BPF(비스페놀F)
- SVHC → SVHC(고위험성물질)
- REACH → REACH(유럽화학물질규정)
- TSCA → TSCA(미국독성물질관리법)
- FDA → FDA(미국식품의약국)
- EPA → EPA(미국환경보호청)
- ECHA → ECHA(유럽화학물질청)
- EFSA → EFSA(유럽식품안전청)
- migration → 이행(migration)
"""

_USER_PROMPT = """\
아래 규제 문서를 분석하세요.

[출처] {source}
[제목(영문)] {title}
[감지 키워드] {keywords}
[본문]
{text}

다음 형식을 정확히 지켜서 한 줄씩 답하세요:
제목번역: (위 영문 제목을 자연스러운 한국어로 번역)
요약: (3~5줄. 아래 항목 순서대로 작성 — ①이 규제가 다루는 물질 또는 제품 ②규제 내용 및 수준 ③감열지·POS라벨 업계에 미치는 영향. 화학물질 약어에는 반드시 한글 풀네임 병기)
중요도: (긴급 / 주목 / 참고 중 하나만 — 긴급=즉시 대응 필요 금지·제한, 주목=모니터링 필요, 참고=일반 정보)
시행일: (YYYY-MM-DD 형식. 없으면 미확인)
"""


def _parse_response(text: str) -> tuple[str, str, str, str]:
    title_kr, summary, importance, effective_date = "", "", "⚪ 참고", ""
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("제목번역:"):
            title_kr = line[5:].strip()
        elif line.startswith("요약:"):
            # 요약은 여러 줄일 수 있으므로 다음 키 전까지 수집
            parts = [line[3:].strip()]
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if any(next_line.startswith(k) for k in ("중요도:", "시행일:")):
                    i -= 1
                    break
                parts.append(next_line)
                i += 1
            summary = " ".join(p for p in parts if p)
        elif line.startswith("중요도:"):
            raw = line[4:].strip()
            for k, v in _IMPORTANCE_LABELS.items():
                if k in raw:
                    importance = v
                    break
        elif line.startswith("시행일:"):
            val = line[4:].strip()
            effective_date = "" if val == "미확인" else val
        i += 1
    return title_kr, summary, importance, effective_date


def summarize(data: Dict) -> Dict:
    if not OPENAI_AVAILABLE:
        return {**data, "summary_kr": "[OpenAI 연결 실패]", "importance": "⚪ 참고", "effective_date": ""}

    prompt = _USER_PROMPT.format(
        source=data.get("source", ""),
        title=data.get("title", ""),
        keywords=data.get("keywords_matched", ""),
        text=data.get("original_text", "")[:3000],
    )

    try:
        resp = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        result_text = resp.choices[0].message.content or ""
        title_kr, summary, importance, effective_date = _parse_response(result_text)
        return {**data, "title_kr": title_kr, "summary_kr": summary, "importance": importance, "effective_date": effective_date}

    except Exception as e:
        err_msg = str(e)
        print(f"  [OpenAI 오류] {err_msg[:120]}")
        if "429" in err_msg or "quota" in err_msg.lower():
            fallback = f"[할당량 초과] 키워드: {data.get('keywords_matched', '')}"
        elif "401" in err_msg or "Unauthorized" in err_msg:
            fallback = "[API 키 오류] config.py의 OPENAI_API_KEY를 확인하세요."
        else:
            fallback = f"[AI 요약 불가] 원문 확인 필요. 키워드: {data.get('keywords_matched', '')}"
        return {**data, "title_kr": "", "summary_kr": fallback, "importance": "⚪ 참고", "effective_date": ""}


def batch_summarize(items: List[Dict], progress_callback=None) -> List[Dict]:
    results = []
    for i, item in enumerate(items):
        if progress_callback:
            progress_callback(i + 1, len(items))
        results.append(summarize(item))
    return results
