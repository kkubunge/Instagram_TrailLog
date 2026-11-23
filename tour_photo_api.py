"""한국관광공사 국문 관광정보 API(KorService2) 기반 코스·스팟 실사 사진 수집기."""

from __future__ import annotations

import io
import logging
import math
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image

import config

logger = logging.getLogger(__name__)

# 숙박(32)·쇼핑(38)·음식점(39) 등 오매칭을 막기 위해 코스/관광지 성격 타입만 허용
ALLOWED_CONTENT_TYPES: set[str] = {"12", "14", "25", "28"}
_TYPE_PRIORITY: dict[str, int] = {"12": 0, "28": 1, "14": 2, "25": 3}

_AREA_PREFIXES: tuple[str, ...] = (
    "서울 ",
    "부산 ",
    "대구 ",
    "인천 ",
    "광주 ",
    "대전 ",
    "울산 ",
    "제주 ",
    "강원 ",
    "경기 ",
    "경북 ",
    "경남 ",
    "전북 ",
    "전남 ",
    "충북 ",
    "충남 ",
)
_TRIM_SUFFIXES: tuple[str, ...] = ("해맞이공원", "스카이워크", "전망대", "해수욕장")

_QUOTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"'([^'\n]{2,30})'"),
    re.compile(r"‘([^’\n]{2,30})’"),
    re.compile(r'"([^"\n]{2,30})"'),
    re.compile(r"“([^”\n]{2,30})”"),
)
_CLAUSE_TAIL_RE = re.compile(
    r"(?:하는|있는|조성한|꾸며진|자랑하는|갖춘|딴|가진|위치한|대표하는|상징하는|유명한|형성된|만나는|펼쳐지는|이어지는|자리한|인접한|된)\s+([가-힣A-Za-z0-9\s·\-]{2,20})$"
)
_PLACE_SUFFIX_RE = re.compile(
    r"(?:^|\s)([가-힣]{2,12}(?:대교|공원|해변|해수욕장|전망대|휴양림|수목원|저수지|폭포|계곡|산성|사찰|박물관|마을|섬|산|길|항|포구))(?=$|[\s.,!?])"
)
_GENERIC_TAIL_WORDS: set[str] = {
    "자연휴양림",
    "해수욕장",
    "해맞이공원",
    "스카이워크",
    "전망대",
    "생태공원",
    "박물관",
    "기념공원",
}


def _extract_unquoted_terms(source_text: str) -> list[str]:
    """따옴표가 없거나 긴 문장형 스팟 설명에서 핵심 지명 후보를 추출한다."""
    first_line = str(source_text or "").splitlines()[0].strip()
    if not first_line:
        return []
    head_sentence = re.split(r"\.\s+", first_line, maxsplit=1)[0].strip().rstrip(".,!?")
    if not head_sentence:
        return []

    found: list[str] = []

    def _push(val: str) -> None:
        cleaned = val.strip(" \t.,!?\"'‘’“”")
        if 2 <= len(cleaned) <= 24 and cleaned not in found:
            found.append(cleaned)

    # 1) 관형절 어미 뒤 지명 추출 (예: '상징하는 오륙도', '자랑하는 잠곡저수지')
    m_tail = _CLAUSE_TAIL_RE.search(head_sentence)
    if m_tail:
        _push(m_tail.group(1))

    # 2) 쉼표 뒤 명사구 (예: '..., 고대산 역고드름')
    if "," in head_sentence:
        after_comma = head_sentence.rsplit(",", 1)[-1].strip().rstrip(".,!?")
        compact_len = len(re.sub(r"\s+", "", after_comma))
        if 2 <= compact_len <= 18 and not re.search(r"(?:다|요|음|함|됨|임)$", after_comma):
            _push(after_comma)

    # 3) 고유명사+장소 접미사 패턴 (예: '7.42km의 광안대교')
    for m_place in _PLACE_SUFFIX_RE.finditer(head_sentence):
        _push(m_place.group(1))

    # 2어절 이상 긴 후보(10자 초과)는 마지막 핵심 어절도 보조 후보로 추가
    expanded: list[str] = []
    for item in found:
        if item not in expanded:
            expanded.append(item)
        parts = item.split()
        if len(parts) >= 2 and len(item) > 10:
            last_word = parts[-1]
            if len(last_word) >= 2 and last_word not in _GENERIC_TAIL_WORDS and last_word not in expanded:
                expanded.append(last_word)
    return expanded


def extract_spot_keywords(spot_text: str) -> list[str]:
    """스팟 안내 문구에서 관광정보 검색용 핵심 지명 키워드 후보를 추출한다."""
    text = str(spot_text or "").strip()
    if not text:
        return []

    raw_terms: list[str] = []
    for pattern in _QUOTE_PATTERNS:
        for match in pattern.findall(text):
            cleaned = match.strip()
            if cleaned and cleaned not in raw_terms:
                raw_terms.append(cleaned)

    if raw_terms:
        expanded_quotes: list[str] = []
        for term in raw_terms:
            expanded_quotes.append(term)
            if len(term) > 14:
                for extra in _extract_unquoted_terms(term):
                    if extra not in expanded_quotes:
                        expanded_quotes.append(extra)
        raw_terms = expanded_quotes
        for extra in _extract_unquoted_terms(text):
            if extra not in raw_terms:
                raw_terms.append(extra)
    else:
        for extra in _extract_unquoted_terms(text):
            if extra not in raw_terms:
                raw_terms.append(extra)
        if len(text) <= 24 and text not in raw_terms:
            raw_terms.append(text)

    candidates: list[str] = []

    def _add(term: str) -> None:
        val = term.strip()
        if val and val not in candidates:
            candidates.append(val)

    for term in raw_terms:
        _add(term)

        # 두루누비 약칭을 관광정보 공식 명칭으로 보정
        if term in ("유엔공원", "UN공원"):
            _add("유엔기념공원")
        elif "UN공원" in term:
            _add(term.replace("UN공원", "유엔기념공원"))
        elif "유엔공원" in term:
            _add(term.replace("유엔공원", "유엔기념공원"))

        # "부산 차이나타운"처럼 지역 접두어 뒤 핵심어가 3글자 이상이면 단독어 추가
        for prefix in _AREA_PREFIXES:
            if term.startswith(prefix):
                rest = term[len(prefix) :].strip()
                if len(rest) >= 3:
                    _add(rest)
                break

        # "오륙도해맞이공원"처럼 긴 시설 접미어가 붙은 경우 앞 핵심 지명 추가
        for suffix in _TRIM_SUFFIXES:
            if term.endswith(suffix) and len(term) > len(suffix):
                head = term[: -len(suffix)].strip()
                if len(head) >= 2:
                    _add(head)
                break

    return candidates


class TourPhotoClient:
    """KorService2/searchKeyword2로 두루누비 코스 및 스팟 실사 사진을 조회·저장하는 클라이언트."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        mobile_app: str = config.MOBILE_APP_NAME,
        timeout: int = 15,
    ) -> None:
        raw_key = api_key or config.TOUR_API_KEY
        if not raw_key:
            raise ValueError("TOUR_API_KEY 또는 DURUNUBI_API_KEY가 설정되어 있지 않습니다.")
        # 공공데이터포털 Encoding 키가 requests에서 이중 인코딩되지 않도록 디코딩
        self.service_key = unquote(raw_key)
        self.endpoint = (endpoint or config.TOUR_API_ENDPOINT).rstrip("/")
        self.mobile_app = mobile_app
        self.timeout = timeout
        self.session = config.create_http_session()

    def search_keyword(
        self,
        keyword: str,
        ldong_regn_cd: str | None = None,
        num_of_rows: int = 6,
    ) -> list[dict[str, Any]]:
        """KorService2 키워드 검색(/searchKeyword2)으로 관광정보 목록을 조회한다."""
        if not keyword:
            return []
        url = f"{self.endpoint}/searchKeyword2"
        query: dict[str, Any] = {
            "serviceKey": self.service_key,
            "MobileOS": "ETC",
            "MobileApp": self.mobile_app,
            "_type": "json",
            "arrange": "Q",
            "keyword": keyword,
            "numOfRows": num_of_rows,
            "pageNo": 1,
        }
        if ldong_regn_cd:
            query["lDongRegnCd"] = ldong_regn_cd

        try:
            resp = self.session.get(url, params=query, timeout=self.timeout)
            resp.raise_for_status()
            text = resp.text.strip()
            if text.startswith("<"):
                logger.warning("KorService2 XML 오류 응답 (%s): %s", keyword, text[:160])
                return []
            data = resp.json()
            header = data.get("response", {}).get("header", {})
            if str(header.get("resultCode", "")) != "0000":
                logger.warning(
                    "KorService2 API 오류 (%s): %s - %s",
                    keyword,
                    header.get("resultCode"),
                    header.get("resultMsg"),
                )
                return []
            body = data.get("response", {}).get("body", {})
            items = body.get("items")
            if not items or isinstance(items, str):
                return []
            item = items.get("item")
            if isinstance(item, dict):
                return [item]
            if isinstance(item, list):
                return [entry for entry in item if isinstance(entry, dict)]
            return []
        except Exception as exc:
            logger.warning("KorService2 검색 실패 (%s): %s", keyword, exc)
            return []

    @staticmethod
    def _parse_lat_lon(item: dict[str, Any]) -> tuple[float | None, float | None]:
        """KorService2 응답 항목에서 유효한 위경도(lat, lon)를 추출한다."""
        try:
            lat = float(item.get("mapy"))  # type: ignore[arg-type]
            lon = float(item.get("mapx"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None, None
        if not (32.0 <= lat <= 39.5 and 124.0 <= lon <= 132.5):
            return None, None
        return lat, lon

    @staticmethod
    def _min_distance_to_gpx_km(
        lat: float,
        lon: float,
        gpx_points: list[tuple[float, float, float | None]] | None,
    ) -> float | None:
        """스팟 좌표에서 GPX 경로까지 최소 직선 거리(km)를 계산한다."""
        if not gpx_points:
            return None
        step = max(1, len(gpx_points) // 250)
        sampled = gpx_points[::step]
        if sampled[-1] != gpx_points[-1]:
            sampled.append(gpx_points[-1])
        cos_lat = math.cos(math.radians(lat)) or 1.0
        min_d = min(
            math.hypot((p[0] - lat) * 111.0, (p[1] - lon) * 111.0 * cos_lat)
            for p in sampled
        )
        return round(min_d, 2)

    @classmethod
    def _pick_best_item(
        cls,
        items: list[dict[str, Any]],
        used_ids: set[str],
        gpx_points: list[tuple[float, float, float | None]] | None = None,
    ) -> tuple[dict[str, Any], float | None, float | None, float | None] | None:
        """허용 타입(12/14/25/28), 이미지 보유 여부, 중복 제외 및 GPX 근접도 기준으로 최적 항목을 고른다."""
        candidates: list[tuple[dict[str, Any], float | None, float | None, float | None]] = []
        for item in items:
            cid = str(item.get("contentid") or "").strip()
            ctype = str(item.get("contenttypeid") or "").strip()
            img_url = str(item.get("firstimage") or "").strip()
            if not cid or not img_url:
                continue
            if cid in used_ids:
                continue
            if ctype not in ALLOWED_CONTENT_TYPES:
                continue
            lat, lon = cls._parse_lat_lon(item)
            dist = (
                cls._min_distance_to_gpx_km(lat, lon, gpx_points)
                if (lat is not None and lon is not None and gpx_points)
                else None
            )
            candidates.append((item, lat, lon, dist))

        if not candidates:
            return None

        if gpx_points:
            candidates.sort(
                key=lambda x: (
                    0 if (x[3] is not None and x[3] <= 5.0) else 1,
                    _TYPE_PRIORITY.get(str(x[0].get("contenttypeid")), 99),
                    x[3] if x[3] is not None else 999.0,
                )
            )
        else:
            candidates.sort(
                key=lambda x: _TYPE_PRIORITY.get(str(x[0].get("contenttypeid")), 99)
            )
        return candidates[0]

    def _download_image(self, url: str, target_base: Path) -> Path | None:
        """이미지 URL을 내려받아 유효한 PNG/JPG 파일로 저장한다."""
        if not url:
            return None
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            raw_bytes = resp.content
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img.verify()

            ctype_header = (resp.headers.get("Content-Type") or "").lower()
            ext = Path(urlparse(url).path).suffix.lower()
            if "png" in ctype_header or ext == ".png":
                suffix = ".png"
            else:
                suffix = ".jpg"

            target_path = target_base.with_suffix(suffix)
            target_path.write_bytes(raw_bytes)
            return target_path
        except Exception as exc:
            logger.warning("관광사진 다운로드/검증 실패 (%s): %s", url, exc)
            return None

    def _find_and_download(
        self,
        keywords: list[str],
        ldong_regn_cd: str | None,
        used_ids: set[str],
        target_base: Path,
        gpx_points: list[tuple[float, float, float | None]] | None = None,
    ) -> dict[str, Any] | None:
        """키워드 후보를 순차 검색해 중복 없는 최적 관광사진 1장을 내려받는다."""
        for kw in keywords:
            items = self.search_keyword(kw, ldong_regn_cd=ldong_regn_cd, num_of_rows=6)
            chosen = self._pick_best_item(items, used_ids, gpx_points=gpx_points)
            if not chosen:
                continue
            picked, lat, lon, dist_km = chosen
            img_url = str(picked.get("firstimage") or "").strip()
            local_path = self._download_image(img_url, target_base)
            if not local_path:
                continue

            cid = str(picked.get("contentid") or "").strip()
            used_ids.add(cid)
            meta: dict[str, Any] = {
                "title": str(picked.get("title") or kw).strip(),
                "content_id": cid,
                "content_type_id": str(picked.get("contenttypeid") or "").strip(),
                "keyword": kw,
                "url": img_url,
                "local_path": str(local_path),
            }
            if lat is not None and lon is not None:
                meta["lat"] = lat
                meta["lon"] = lon
                if dist_km is not None:
                    meta["dist_to_gpx_km"] = dist_km
            return meta
        return None

    def collect_course_photos(
        self, bundle: dict[str, Any], photos_dir: Path
    ) -> dict[str, Any]:
        """코스 번들의 대표 커버 사진과 스팟별 실사 사진을 수집해 로컬에 저장한다."""
        photos_dir.mkdir(parents=True, exist_ok=True)
        regn_cd = config.resolve_ldong_regn(bundle.get("sigun"))
        gpx_points = (bundle.get("gpx") or {}).get("points") or None
        used_ids: set[str] = set()

        # 1) 코스/길명 기반 커버 사진 탐색
        cover_keywords = list(
            dict.fromkeys(
                k.strip()
                for k in (bundle.get("route_name"), bundle.get("course_name"))
                if k and str(k).strip()
            )
        )
        cover_photo = self._find_and_download(
            cover_keywords, regn_cd, used_ids, photos_dir / "cover", gpx_points=gpx_points
        )

        # 2) 스팟별 사진 탐색 (원본 순서 유지)
        spots: list[str] = list(bundle.get("spots") or [])
        all_spot_entries: list[dict[str, Any]] = []
        for idx, spot_text in enumerate(spots, start=1):
            kws = extract_spot_keywords(spot_text)
            photo_meta = None
            if kws:
                photo_meta = self._find_and_download(
                    kws,
                    regn_cd,
                    used_ids,
                    photos_dir / f"spot_{idx:02d}",
                    gpx_points=gpx_points,
                )
            all_spot_entries.append({"text": spot_text, "photo": photo_meta})

        # 3) 커버 폴백: 대표 코스 사진을 못 찾았으면 첫 번째 스팟 사진을 커버로 복사 활용
        if cover_photo is None:
            first_with_photo = next(
                (entry["photo"] for entry in all_spot_entries if entry["photo"]),
                None,
            )
            if first_with_photo:
                src = Path(first_with_photo["local_path"])
                if src.exists():
                    dst = (photos_dir / "cover").with_suffix(src.suffix)
                    shutil.copy2(src, dst)
                    cover_photo = {**first_with_photo, "local_path": str(dst)}

        # 4) 3번 슬라이드용 최대 5개 선별: 원래 순서를 유지하되 사진 있는 스팟 우선 배치
        photo_indices = [i for i, e in enumerate(all_spot_entries) if e["photo"] is not None]
        no_photo_indices = [i for i, e in enumerate(all_spot_entries) if e["photo"] is None]
        chosen_indices = photo_indices[:5]
        if len(chosen_indices) < 5:
            chosen_indices.extend(no_photo_indices[: 5 - len(chosen_indices)])
        chosen_indices.sort()

        spot_items = [all_spot_entries[i] for i in chosen_indices]
        matched_spot_count = sum(1 for item in spot_items if item["photo"] is not None)
        has_photos = bool(cover_photo or matched_spot_count > 0)

        return {
            "has_photos": has_photos,
            "cover": cover_photo,
            "spot_items": spot_items,
            "matched_spot_count": matched_spot_count,
        }
