"""Gemini 연동 및 두루누비 데이터 기반 인스타그램 카피·캡션 생성기."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import config

logger = logging.getLogger(__name__)


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """모델 응답 문자열에서 JSON 객체를 파싱한다."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _build_prompt(bundle: dict[str, Any]) -> str:
    """카드뉴스 카피와 인스타그램 캡션 생성을 위한 Gemini 프롬프트를 작성한다."""
    spots_text = "\n".join(f"- {s}" for s in bundle["spots"][:6]) or "- 정보 없음"
    summary_text = "\n".join(f"- {s}" for s in bundle["summary_lines"][:5]) or "- 정보 없음"
    traveler_text = "\n".join(f"- {s}" for s in bundle["traveler_lines"][:5]) or "- 정보 없음"

    return (
        "당신은 국내 걷기·자전거 여행 인스타그램 매거진 'TrailLog(트레일로그)' 에디터입니다.\n"
        "아래 한국관광공사 두루누비 공식 데이터(사실)만 사용해 카드뉴스 문구와 인스타그램 캡션을 작성하세요.\n"
        "데이터에 없는 장소명, 시간, 거리, 요금을 지어내지 마세요.\n\n"
        f"[코스명] {bundle['course_name']}\n"
        f"[소속 길] {bundle['route_name']} ({bundle['route_linemsg']})\n"
        f"[지역/유형] {bundle['sigun']} / {bundle['brd_label']}\n"
        f"[스펙] 거리 {bundle['distance_text']} · 소요시간 {bundle['duration_text']} · 난이도 {bundle['level_label']} · {bundle['cycle_type']}\n"
        f"[코스 설명] {bundle['contents_text'][:900]}\n"
        f"[코스 요약]\n{summary_text}\n"
        f"[관광 포인트]\n{spots_text}\n"
        f"[교통/이용 안내]\n{traveler_text}\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요:\n"
        "{\n"
        '  "hook_line": "1번 표지 이미지에 들어갈 감성적인 한 줄 문구 (공백 포함 26자 이내)",\n'
        '  "summary_points": ["3번 카드 핵심 매력 1 (50자 이내)", "핵심 매력 2 (50자 이내)", "핵심 매력 3 (50자 이내)"],\n'
        '  "recommend_tags": ["추천 키워드1", "추천 키워드2", "추천 키워드3"],\n'
        '  "instagram_caption": "인스타그램 본문 (감성 도입 2줄 + 코스 스펙 요약 + 주요 볼거리 2~3줄 + 교통 한 줄 + 저장/공유 유도 문구. 해시태그와 출처는 제외)",\n'
        '  "hashtags": ["두루누비", "태그2", "... 총 12~14개, # 기호 없이 단어만"]\n'
        "}"
    )


def _call_gemini(prompt: str) -> dict[str, Any] | None:
    """설정된 Gemini 모델 우선순위대로 호출해 JSON 결과를 받아온다."""
    if not config.GEMINI_API_KEY:
        return None

    candidate_models = list(
        dict.fromkeys(
            [
                config.GEMINI_MODEL,
                "gemini-3.1-flash-lite",
                "gemini-3.5-flash-lite",
                "gemini-flash-lite-latest",
                "gemini-3.5-flash",
            ]
        )
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7},
    }

    with config.create_http_session() as session:
        for model in candidate_models:
            if not model:
                continue
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={config.GEMINI_API_KEY}"
            )
            try:
                resp = session.post(url, json=payload, timeout=15)
                if resp.status_code != 200:
                    logger.warning("Gemini 모델(%s) 오류 %s", model, resp.status_code)
                    continue
                data = resp.json()
                candidates = data.get("candidates") or []
                if not candidates:
                    continue
                parts = candidates[0].get("content", {}).get("parts") or []
                raw_text = "".join(part.get("text", "") for part in parts)
                parsed = _extract_json_block(raw_text)
                if parsed and parsed.get("hook_line") and parsed.get("instagram_caption"):
                    parsed["ai_model"] = model
                    return parsed
            except Exception as exc:
                logger.warning("Gemini 모델(%s) 호출 실패: %s", model, exc)

    return None


def _generate_fallback_copy(bundle: dict[str, Any]) -> dict[str, Any]:
    """Gemini 호출이 실패할 경우 두루누비 원문으로 카드뉴스 카피와 캡션을 구성한다."""
    course_name = bundle["course_name"]
    sigun = bundle["sigun"] or "국내"
    brd_label = bundle["brd_label"]
    hook = bundle["route_linemsg"] or f"{sigun}의 풍경을 따라 천천히 만나는 {brd_label}"
    if len(hook) > 28:
        hook = hook[:26].rstrip() + "…"

    summary_points = [s[:52] + ("…" if len(s) > 52 else "") for s in bundle["summary_lines"][:3]]
    if not summary_points:
        summary_points = [
            f"{sigun} 일대 {bundle['distance_text']} 구간을 따라 즐기는 {brd_label}",
            f"예상 소요시간 {bundle['duration_text']}, 난이도 '{bundle['level_label']}' 코스",
            f"{bundle['cycle_type']} 코스로 시점과 종점 풍경을 모두 감상할 수 있습니다.",
        ]

    spots_preview = "\n".join(f"• {s}" for s in bundle["spots"][:3])
    travel_preview = bundle["traveler_lines"][0] if bundle["traveler_lines"] else "대중교통 및 현장 안내를 참고해 주세요."

    caption_body = (
        f"이번 주말, {sigun}에서 '{course_name}' 한 바퀴 어떠신가요?\n"
        f"{hook}\n\n"
        f"📌 코스 한눈에 보기\n"
        f"• 거리/시간: {bundle['distance_text']} / 약 {bundle['duration_text']}\n"
        f"• 난이도/형태: {bundle['level_label']} ({bundle['cycle_type']})\n\n"
        + (f"✨ 주요 포인트\n{spots_preview}\n\n" if spots_preview else "")
        + f"🚌 출발·교통 팁\n{travel_preview}\n\n"
        "마음에 드셨다면 오른쪽 아래 저장 📌 눌러두고 다음 여행 때 꺼내보세요!"
    )

    sigun_tag = re.sub(r"\s+", "", sigun)
    route_tag = re.sub(r"\s+", "", bundle["route_name"])
    course_tag = re.sub(r"\s+", "", course_name)
    raw_tags = [
        "두루누비",
        "한국관광공사",
        route_tag,
        course_tag,
        f"{sigun_tag}여행",
        sigun_tag,
        "걷기여행" if bundle["brd_div"] == "DNWW" else "자전거여행",
        "트레킹" if bundle["brd_div"] == "DNWW" else "라이딩",
        "국내여행",
        "주말나들이",
        "걷기코스" if bundle["brd_div"] == "DNWW" else "자전거코스",
        "TrailLog",
        "트레일로그",
    ]
    hashtags = list(dict.fromkeys(t for t in raw_tags if t))[:14]

    return {
        "hook_line": hook,
        "summary_points": summary_points[:3],
        "recommend_tags": [brd_label, f"난이도 {bundle['level_label']}", bundle["cycle_type"]],
        "instagram_caption": caption_body,
        "hashtags": hashtags,
        "ai_model": "rule-based-fallback",
    }


def generate_instagram_copy(bundle: dict[str, Any]) -> dict[str, Any]:
    """카드뉴스 카피와 출처·해시태그가 포함된 최종 인스타그램 캡션을 생성한다."""
    prompt = _build_prompt(bundle)
    result = _call_gemini(prompt)
    if result is None:
        result = _generate_fallback_copy(bundle)

    raw_tags = result.get("hashtags") or []
    cleaned_tags: list[str] = []
    for tag in raw_tags:
        normalized = re.sub(r"[^0-9a-zA-Z가-힣_]", "", str(tag).lstrip("#").strip())
        if normalized and normalized not in cleaned_tags:
            cleaned_tags.append(normalized)
    if "두루누비" not in cleaned_tags:
        cleaned_tags.insert(0, "두루누비")
    hashtag_line = " ".join(f"#{t}" for t in cleaned_tags[:15])

    body = str(result.get("instagram_caption") or "").strip()
    source_line = (
        "📍 출처: 한국관광공사 두루누비 · 국문 관광정보 (공공데이터)"
        if (bundle.get("photos") or {}).get("has_photos")
        else "📍 출처: 한국관광공사 두루누비 정보 서비스 (공공데이터)"
    )
    full_caption = (
        f"{body}\n\n"
        "────────────────────\n"
        f"{source_line}\n\n"
        f"{hashtag_line}"
    )

    return {
        "hook_line": str(result.get("hook_line") or "").strip(),
        "summary_points": [str(x).strip() for x in (result.get("summary_points") or []) if str(x).strip()][:3],
        "recommend_tags": [str(x).strip() for x in (result.get("recommend_tags") or []) if str(x).strip()][:3],
        "caption_body": body,
        "hashtags": [f"#{t}" for t in cleaned_tags[:15]],
        "full_caption": full_caption,
        "ai_model": result.get("ai_model", "unknown"),
    }
