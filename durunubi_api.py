"""한국관광공사 두루누비 정보 서비스(Ver 4.1) API 클라이언트 및 GPX 파서."""

from __future__ import annotations

import html
import logging
import math
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import unquote

import config

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"</?(?:[a-zA-Z][a-zA-Z0-9]*|!--)[^>]*>")
_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_SPACE_RE = re.compile(r"[ \t\r]+")


class DurunubiAPIError(RuntimeError):
    """두루누비 Open API 호출 중 오류가 발생했을 때 사용하는 예외."""


def clean_text(raw: Any) -> str:
    """API 응답의 HTML 태그·엔티티·탭 문자를 제거하고 깔끔한 줄바꿈 텍스트로 정리한다."""
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    text = _BR_RE.sub("\n", text)
    text = re.sub(r"</\s*p\s*>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_bullet_lines(raw: Any) -> list[str]:
    """`- ` 불릿 또는 줄바꿈으로 구분된 두루누비 텍스트를 항목 리스트로 분리한다."""
    cleaned = clean_text(raw)
    if not cleaned:
        return []
    items: list[str] = []
    for line in cleaned.splitlines():
        trimmed = re.sub(r"^[-•*·]+\s*", "", line).strip()
        if trimmed:
            items.append(trimmed)
    return items


def format_duration_minutes(minutes_raw: Any) -> str:
    """분 단위 소요시간 문자열을 한국어 시간/분 표현으로 변환한다."""
    try:
        total_min = int(float(str(minutes_raw).strip()))
    except (TypeError, ValueError):
        return "-"
    if total_min <= 0:
        return "-"
    hours, mins = divmod(total_min, 60)
    if hours and mins:
        return f"{hours}시간 {mins}분"
    if hours:
        return f"{hours}시간"
    return f"{mins}분"


def format_distance_km(dist_raw: Any) -> str:
    """코스 거리(km) 숫자를 보기 좋게 포맷한다."""
    try:
        dist = float(str(dist_raw).strip())
    except (TypeError, ValueError):
        return "-"
    if dist.is_integer():
        return f"{int(dist)}km"
    return f"{dist:.1f}km"


class DurunubiClient:
    """두루누비 routeList / courseList 조회 및 GPX 경로 파싱 클라이언트."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        mobile_app: str = config.MOBILE_APP_NAME,
        timeout: int = 20,
    ) -> None:
        raw_key = api_key or config.DURUNUBI_API_KEY
        if not raw_key:
            raise ValueError("DURUNUBI_API_KEY가 설정되어 있지 않습니다.")
        # 공공데이터포털 Encoding 키가 requests에서 이중 인코딩되지 않도록 디코딩
        self.service_key = unquote(raw_key)
        self.endpoint = (endpoint or config.DURUNUBI_ENDPOINT).rstrip("/")
        self.mobile_app = mobile_app
        self.timeout = timeout
        self.session = config.create_http_session()

    def _request(self, operation: str, **params: Any) -> dict[str, Any]:
        """공통 파라미터를 포함해 두루누비 GET 요청을 수행한다."""
        url = f"{self.endpoint}/{operation}"
        query: dict[str, Any] = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": self.mobile_app,
            "_type": "json",
        }
        for key, value in params.items():
            if value is not None and value != "":
                query[key] = value

        response = self.session.get(url, params=query, timeout=self.timeout)
        response.raise_for_status()
        text = response.text.strip()

        if text.startswith("<"):
            raise DurunubiAPIError(self._parse_xml_error(operation, text))

        data = response.json()
        resp = data.get("response", {})
        header = resp.get("header", {})
        result_code = str(header.get("resultCode", ""))
        result_msg = str(header.get("resultMsg", ""))
        if result_code != "0000":
            raise DurunubiAPIError(
                f"[{operation}] API 오류 (코드: {result_code}, 메시지: {result_msg})"
            )
        return resp.get("body", {})

    @staticmethod
    def _parse_xml_error(operation: str, xml_text: str) -> str:
        """공공데이터포털 XML 오류 응답에서 에러 코드와 메시지를 추출한다."""
        try:
            root = ET.fromstring(xml_text)
            auth_msg = root.findtext(".//returnAuthMsg") or ""
            reason_code = root.findtext(".//returnReasonCode") or ""
            err_msg = root.findtext(".//errMsg") or "XML 오류 응답"
            return (
                f"[{operation}] {err_msg} (코드: {reason_code}, 상세: {auth_msg})"
            )
        except ET.ParseError:
            return f"[{operation}] XML 오류 응답: {xml_text[:200]}"

    @staticmethod
    def _extract_items(body: dict[str, Any]) -> list[dict[str, Any]]:
        """응답 body의 items.item을 항상 리스트 형태로 정규화한다."""
        items = body.get("items")
        if not items or isinstance(items, str):
            return []
        item = items.get("item")
        if not item:
            return []
        if isinstance(item, dict):
            return [item]
        if isinstance(item, list):
            return [entry for entry in item if isinstance(entry, dict)]
        return []

    def get_route_list(
        self,
        theme_nm: str | None = None,
        brd_div: str | None = None,
        num_of_rows: int = 50,
        page_no: int = 1,
    ) -> list[dict[str, Any]]:
        """길 목록 정보(/routeList)를 조회한다."""
        body = self._request(
            "routeList",
            themeNm=theme_nm,
            brdDiv=brd_div,
            numOfRows=num_of_rows,
            pageNo=page_no,
        )
        return self._extract_items(body)

    def get_course_list(
        self,
        crs_kor_nm: str | None = None,
        route_idx: str | None = None,
        crs_level: str | None = None,
        brd_div: str | None = None,
        num_of_rows: int = 20,
        page_no: int = 1,
    ) -> list[dict[str, Any]]:
        """코스 목록 정보(/courseList)를 조회한다."""
        body = self._request(
            "courseList",
            crsKorNm=crs_kor_nm,
            routeIdx=route_idx,
            crsLevel=crs_level,
            brdDiv=brd_div,
            numOfRows=num_of_rows,
            pageNo=page_no,
        )
        return self._extract_items(body)

    def fetch_gpx_track(self, gpx_url: str) -> dict[str, Any]:
        """gpxpath URL에서 GPX XML을 내려받아 좌표 및 고도 통계를 파싱한다."""
        empty: dict[str, Any] = {
            "gpx_url": gpx_url,
            "points": [],
            "point_count": 0,
            "start_coord": None,
            "end_coord": None,
            "min_ele": None,
            "max_ele": None,
            "elevation_gain": None,
        }
        if not gpx_url:
            return empty
        try:
            resp = self.session.get(gpx_url, timeout=self.timeout)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:
            logger.warning("GPX 다운로드/파싱 실패 (%s): %s", gpx_url, exc)
            return empty

        points: list[tuple[float, float, float | None]] = []
        for elem in root.iter():
            if not (elem.tag.endswith("trkpt") or elem.tag.endswith("rtept")):
                continue
            try:
                lat = float(elem.attrib["lat"])
                lon = float(elem.attrib["lon"])
            except (KeyError, ValueError):
                continue
            if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                continue
            ele_val: float | None = None
            for child in elem:
                if child.tag.endswith("ele") and child.text:
                    try:
                        val = float(child.text.strip())
                        if math.isfinite(val):
                            ele_val = val
                    except ValueError:
                        pass
                    break
            points.append((lat, lon, ele_val))

        if not points:
            return empty

        eles = [p[2] for p in points if p[2] is not None]
        gain = 0.0
        if len(eles) >= 2:
            # GPX 미세 GPS 흔들림 보정을 위해 1m 이상 상승분만 합산하거나 소폭 누적
            for prev_e, curr_e in zip(eles, eles[1:]):
                diff = curr_e - prev_e
                if diff > 0:
                    gain += diff

        return {
            "gpx_url": gpx_url,
            "points": points,
            "point_count": len(points),
            "start_coord": (points[0][0], points[0][1]),
            "end_coord": (points[-1][0], points[-1][1]),
            "min_ele": round(min(eles), 1) if eles else None,
            "max_ele": round(max(eles), 1) if eles else None,
            "elevation_gain": round(gain) if eles else None,
        }

    def get_course_bundle(
        self,
        course_item: dict[str, Any],
        route_map: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """단일 코스 정보, 상위 길 정보, 정제 텍스트 및 GPX 데이터를 통합 번들로 구성한다."""
        route_idx = str(course_item.get("routeIdx", "")).strip()
        route_info = (route_map or {}).get(route_idx, {})
        brd_div = str(course_item.get("brdDiv") or route_info.get("brdDiv") or "DNWW")
        level_code = str(course_item.get("crsLevel") or "").strip()

        gpx_url = str(course_item.get("gpxpath") or "").strip()
        gpx_track = self.fetch_gpx_track(gpx_url) if gpx_url else self.fetch_gpx_track("")

        return {
            "crs_idx": str(course_item.get("crsIdx", "")).strip(),
            "route_idx": route_idx,
            "course_name": clean_text(course_item.get("crsKorNm")),
            "route_name": clean_text(route_info.get("themeNm")),
            "route_linemsg": clean_text(route_info.get("linemsg")),
            "sigun": clean_text(course_item.get("sigun")),
            "brd_div": brd_div,
            "brd_label": config.BRD_DIV_LABEL.get(brd_div, "트레킹"),
            "distance_km": str(course_item.get("crsDstnc") or "").strip(),
            "distance_text": format_distance_km(course_item.get("crsDstnc")),
            "duration_min": str(course_item.get("crsTotlRqrmHour") or "").strip(),
            "duration_text": format_duration_minutes(course_item.get("crsTotlRqrmHour")),
            "level_code": level_code,
            "level_label": config.LEVEL_LABEL.get(level_code, "보통"),
            "cycle_type": clean_text(course_item.get("crsCycle")) or "-",
            "contents_text": clean_text(course_item.get("crsContents")),
            "summary_lines": parse_bullet_lines(course_item.get("crsSummary")),
            "spots": parse_bullet_lines(course_item.get("crsTourInfo")),
            "traveler_lines": parse_bullet_lines(course_item.get("travelerinfo")),
            "gpx": gpx_track,
            "raw_course": course_item,
            "raw_route": route_info,
        }
