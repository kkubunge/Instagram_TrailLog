"""두루누비 API 코스 데이터 기반 자동 테마(forest / ocean) 판별기."""

from __future__ import annotations

import re
from typing import Any

# 바다/해안 컨셉(ocean) 키워드 및 가중치
_OCEAN_STRONG: tuple[str, ...] = (
    "쪽빛 바다",
    "해수욕장",
    "해안도로",
    "해안절경",
    "해안경관",
    "모래사장",
    "스카이워크",
    "해안길",
    "해안선",
    "바닷길",
    "바닷가",
    "동해안",
    "서해안",
    "남해안",
    "방파제",
    "선착장",
    "백사장",
    "해맞이",
    "해넘이",
    "바다",
    "해변",
    "갯벌",
    "등대",
    "어촌",
    "항구",
    "포구",
    "파도",
)

_OCEAN_NORMAL: tuple[str, ...] = (
    "남파랑길",
    "해파랑길",
    "서해랑길",
    "올레길",
    "여객선",
    "갯바위",
    "해식애",
    "연육교",
    "오륙도",
    "태종대",
    "해운대",
    "광안리",
    "마리나",
    "해안",
    "해상",
    "부두",
    "요트",
    "영도",
    "도서",
    "섬길",
)

# 숲/산 컨셉(forest) 키워드 및 가중치
_FOREST_STRONG: tuple[str, ...] = (
    "치유의 숲",
    "자연휴양림",
    "자작나무숲",
    "소나무숲",
    "국립공원",
    "도립공원",
    "군립공원",
    "휴양림",
    "수목원",
    "편백숲",
    "봉우리",
    "약수터",
    "숲길",
    "산길",
    "산림",
    "삼림",
    "등산",
    "계곡",
    "폭포",
    "능선",
    "정상",
    "고개",
    "산성",
    "단풍",
    "녹음",
    "임도",
    "오름",
    "산사",
    "고원",
)

_FOREST_NORMAL: tuple[str, ...] = (
    "생태공원",
    "야생화",
    "산책로",
    "둘레길",
    "자락길",
    "대나무",
    "울창",
    "솔밭",
    "솔숲",
    "들판",
    "평야",
    "농로",
    "호수",
    "강변",
    "하천",
    "습지",
    "사찰",
    "암자",
    "DMZ",
    "숲",
)

_OCEAN_KEYWORDS: list[tuple[str, int]] = sorted(
    [(kw, 3) for kw in _OCEAN_STRONG] + [(kw, 2) for kw in _OCEAN_NORMAL],
    key=lambda x: len(x[0]),
    reverse=True,
)
_FOREST_KEYWORDS: list[tuple[str, int]] = sorted(
    [(kw, 3) for kw in _FOREST_STRONG] + [(kw, 2) for kw in _FOREST_NORMAL],
    key=lambda x: len(x[0]),
    reverse=True,
)

# 행정구역·일반명사에 '산'이 들어간 오탐 제외 목록
_EXCLUDED_SAN_WORDS: set[str] = {
    "부산",
    "울산",
    "군산",
    "아산",
    "서산",
    "논산",
    "양산",
    "경산",
    "익산",
    "안산",
    "오산",
    "마산",
    "문산",
    "용산",
    "강산",
    "자산",
    "특산",
    "생산",
    "수산",
    "해산",
    "유산",
    "재산",
    "우산",
    "등산",
    "농산",
    "축산",
    "임산",
    "광산",
    "동산",
    "야산",
    "화산",
}

_SAN_NAME_RE = re.compile(r"(?<![가-힣])([가-힣]{1,5}산)")
_SAN_TRAILING_NON_MT_RE = re.compile(
    r"^(?:광역시|특별시|자치시|시|역|항|대교|박물관|구|군|동|읍|면|책|길|림|성|사)"
)
_COASTAL_ROUTE_HINTS: tuple[str, ...] = ("남파랑길", "해파랑길", "서해랑길")


def _score_keywords(
    text: str,
    keywords: list[tuple[str, int]],
    field_multiplier: float,
    matches_out: dict[str, float],
) -> float:
    """단일 텍스트 필드에서 비중복 스팬 기준으로 키워드 점수를 계산한다."""
    if not text:
        return 0.0

    occupied: list[tuple[int, int]] = []
    score = 0.0
    lowered = text.lower()

    for kw, weight in keywords:
        kw_lower = kw.lower()
        start = 0
        hit_count = 0
        while True:
            idx = lowered.find(kw_lower, start)
            if idx == -1:
                break
            end = idx + len(kw_lower)
            start = end
            if any(not (end <= s or idx >= e) for s, e in occupied):
                continue
            occupied.append((idx, end))
            hit_count += 1
            if hit_count <= 2:
                pts = weight * field_multiplier
                score += pts
                matches_out[kw] = matches_out.get(kw, 0.0) + pts
    return score


def _score_mountain_names(
    text: str,
    field_multiplier: float,
    matches_out: dict[str, float],
) -> float:
    """행정구역이나 일반명사가 아닌 산(山) 고유명사 등장 횟수에 보너스 점수를 부여한다."""
    if not text:
        return 0.0

    counts: dict[str, int] = {}
    for m in _SAN_NAME_RE.finditer(text):
        word = m.group(1)
        if word in _EXCLUDED_SAN_WORDS:
            continue
        trailing = text[m.end() :]
        if _SAN_TRAILING_NON_MT_RE.match(trailing):
            continue
        counts[word] = counts.get(word, 0) + 1

    score = 0.0
    for word, cnt in counts.items():
        pts = 2 * min(cnt, 2) * field_multiplier
        score += pts
        matches_out[word] = matches_out.get(word, 0.0) + pts
    return score


def select_theme_style(bundle: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """두루누비 코스 데이터 번들을 분석해 'forest' 또는 'ocean' 컨셉을 자동 결정한다."""
    core_text = "\n".join(
        str(bundle.get(k) or "").strip()
        for k in ("course_name", "route_name", "route_linemsg")
        if bundle.get(k)
    )
    mid_parts: list[str] = []
    for key in ("summary_lines", "spots"):
        vals = bundle.get(key) or []
        if isinstance(vals, list):
            mid_parts.extend(str(v).strip() for v in vals if str(v).strip())
        elif vals:
            mid_parts.append(str(vals).strip())
    mid_text = "\n".join(mid_parts)
    body_text = str(bundle.get("contents_text") or "").strip()

    fields: tuple[tuple[str, float], ...] = (
        (core_text, 2.0),
        (mid_text, 1.5),
        (body_text, 1.0),
    )

    forest_matches: dict[str, float] = {}
    ocean_matches: dict[str, float] = {}
    forest_score = 0.0
    ocean_score = 0.0

    for text, mult in fields:
        forest_score += _score_keywords(text, _FOREST_KEYWORDS, mult, forest_matches)
        forest_score += _score_mountain_names(text, mult, forest_matches)
        ocean_score += _score_keywords(text, _OCEAN_KEYWORDS, mult, ocean_matches)

    forest_top = [
        k for k, _ in sorted(forest_matches.items(), key=lambda x: (-x[1], x[0]))[:6]
    ]
    ocean_top = [
        k for k, _ in sorted(ocean_matches.items(), key=lambda x: (-x[1], x[0]))[:6]
    ]

    if ocean_score > forest_score:
        selected = "ocean"
        reason = f"바다/해안 우세 (바다 {ocean_score:.1f}점 vs 숲/산 {forest_score:.1f}점)"
    elif forest_score > ocean_score:
        selected = "forest"
        reason = f"숲/산 우세 (숲/산 {forest_score:.1f}점 vs 바다 {ocean_score:.1f}점)"
    else:
        gpx = bundle.get("gpx") or bundle.get("gpx_summary") or {}
        max_ele = gpx.get("max_ele")
        route_name = str(bundle.get("route_name") or "")
        course_name = str(bundle.get("course_name") or "")
        if isinstance(max_ele, (int, float)) and max_ele >= 250:
            selected = "forest"
            reason = f"점수 동률({forest_score:.1f}점) · 최고 고도 {max_ele}m 기준 숲/산 선택"
        elif any(h in route_name or h in course_name for h in _COASTAL_ROUTE_HINTS):
            selected = "ocean"
            reason = f"점수 동률({ocean_score:.1f}점) · 해안 트레일 노선명 기준 바다 선택"
        else:
            selected = "forest"
            reason = f"점수 동률({forest_score:.1f}점) · 기본 숲/산 선택"

    meta = {
        "style": selected,
        "mode": "auto",
        "forest_score": round(forest_score, 1),
        "ocean_score": round(ocean_score, 1),
        "forest_matches": forest_top,
        "ocean_matches": ocean_top,
        "reason": reason,
    }
    return selected, meta
