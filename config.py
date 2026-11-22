"""TrailLog 두루누비 인스타그램 카드뉴스 프로젝트 전역 설정, 코드 매핑 및 폰트/SSL 헬퍼."""

from __future__ import annotations

import os
import ssl
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

OUTPUT_DIR = BASE_DIR / "output"

BRAND_NAME = "TrailLog"
BRAND_HANDLE = "trailllog"
BRAND_AVATAR_TEXT = "TL"
MOBILE_APP_NAME = "TrailLog"
PUBLISHED_HISTORY_FILE = BASE_DIR / "published_history.json"

DURUNUBI_API_KEY = os.getenv("DURUNUBI_API_KEY", "").strip()
DURUNUBI_ENDPOINT = os.getenv(
    "DURUNUBI_ENDPOINT", "https://apis.data.go.kr/B551011/Durunubi"
).rstrip("/")

# 국문 관광정보 API(KorService2) 설정 — 미설정 시 두루누비 인증키 자동 재사용
TOUR_API_KEY = os.getenv("TOUR_API_KEY", "").strip() or DURUNUBI_API_KEY
TOUR_API_ENDPOINT = os.getenv(
    "TOUR_API_ENDPOINT", "https://apis.data.go.kr/B551011/KorService2"
).rstrip("/")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()

# Instagram Graph API 및 GitHub 공개 이미지 호스팅 설정
IG_USER_ID = os.getenv("IG_USER_ID", "").strip()
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
IG_GRAPH_VERSION = os.getenv("IG_GRAPH_VERSION", "v24.0").strip()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "kkubunge/Instagram_TrailLog").strip()
GITHUB_MEDIA_BRANCH = os.getenv("GITHUB_MEDIA_BRANCH", "media-assets").strip()

# 두루누비 걷기/자전거 구분 코드 매핑
BRD_DIV_MAP: dict[str, str] = {
    "걷기": "DNWW",
    "도보": "DNWW",
    "걷기길": "DNWW",
    "DNWW": "DNWW",
    "자전거": "DNBW",
    "라이딩": "DNBW",
    "자전거길": "DNBW",
    "DNBW": "DNBW",
}

BRD_DIV_LABEL: dict[str, str] = {
    "DNWW": "걷기 여행",
    "DNBW": "자전거 여행",
}

LEVEL_LABEL: dict[str, str] = {
    "1": "쉬움",
    "2": "보통",
    "3": "어려움",
}

# 법정동 시도 코드(lDongRegnCd) 매핑
LDONG_REGN_MAP: dict[str, str] = {
    "서울": "11",
    "서울특별시": "11",
    "부산": "26",
    "부산광역시": "26",
    "대구": "27",
    "대구광역시": "27",
    "인천": "28",
    "인천광역시": "28",
    "광주": "29",
    "광주광역시": "29",
    "대전": "30",
    "대전광역시": "30",
    "울산": "31",
    "울산광역시": "31",
    "세종": "36110",
    "세종특별자치시": "36110",
    "경기": "41",
    "경기도": "41",
    "강원": "51",
    "강원특별자치도": "51",
    "강원도": "51",
    "충북": "43",
    "충청북도": "43",
    "충남": "44",
    "충청남도": "44",
    "전북": "52",
    "전북특별자치도": "52",
    "전라북도": "52",
    "전남": "46",
    "전라남도": "46",
    "경북": "47",
    "경상북도": "47",
    "경남": "48",
    "경상남도": "48",
    "제주": "50",
    "제주특별자치도": "50",
    "제주도": "50",
}


def resolve_ldong_regn(sigun: str | None) -> str | None:
    """시군구 문자열(예: '부산 남구')에서 KorService2용 법정동 시도 코드(lDongRegnCd)를 추출한다."""
    if not sigun:
        return None
    cleaned = str(sigun).strip()
    if not cleaned:
        return None
    first_token = cleaned.split()[0]
    if first_token in LDONG_REGN_MAP:
        return LDONG_REGN_MAP[first_token]
    for prefix, code in sorted(LDONG_REGN_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if cleaned.startswith(prefix):
            return code
    return None


def resolve_brd_div(value: str | None) -> str | None:
    """사용자 입력 걷기/자전거 명칭 또는 코드를 표준 brdDiv 코드로 변환한다."""
    if not value:
        return None
    cleaned = str(value).strip()
    upper = cleaned.upper()
    if upper in BRD_DIV_MAP:
        return BRD_DIV_MAP[upper]
    if cleaned in BRD_DIV_MAP:
        return BRD_DIV_MAP[cleaned]
    raise ValueError(
        f"지원하지 않는 구분입니다: '{value}'. 가능한 값: 걷기, 도보, 자전거, 라이딩, DNWW, DNBW"
    )


class _SystemSSLAdapter(HTTPAdapter):
    """Windows 등 OS 시스템 인증서 저장소를 사용하는 requests HTTPS 어댑터."""

    def init_poolmanager(self, *args: object, **kwargs: object) -> object:
        kwargs["ssl_context"] = ssl.create_default_context()
        return super().init_poolmanager(*args, **kwargs)

    def cert_verify(
        self, conn: object, url: str, verify: object, cert: object
    ) -> None:
        super().cert_verify(conn, url, verify, cert)
        if verify is True:
            conn.ca_certs = None  # type: ignore[attr-defined]


def create_http_session() -> requests.Session:
    """OS 시스템 인증서 저장소 기반 SSL 검증을 적용한 requests.Session을 반환한다."""
    session = requests.Session()
    session.mount("https://", _SystemSSLAdapter())
    return session


def get_font_paths() -> dict[str, str]:
    """Windows/Linux(GitHub Actions 포함) 환경에서 한글 카드뉴스 렌더링용 폰트 경로(bold/medium/regular)를 찾는다."""
    search_dirs = [
        BASE_DIR / "fonts",
        Path("C:/Windows/Fonts"),
        Path("/usr/share/fonts/opentype/noto"),
        Path("/usr/share/fonts/truetype/noto"),
        Path("/usr/share/fonts/truetype/nanum"),
        Path("/usr/share/fonts/opentype/pretendard"),
        Path("/usr/share/fonts"),
    ]
    candidates = {
        "bold": (
            "Pretendard-SemiBold.ttf",
            "Pretendard-Bold.ttf",
            "NotoSansKR-Bold.ttf",
            "NotoSansKR-Medium.ttf",
            "NotoSansCJK-Bold.ttc",
            "NanumSquareRoundB.ttf",
            "NanumGothicBold.ttf",
            "malgunbd.ttf",
        ),
        "medium": (
            "Pretendard-Medium.ttf",
            "NotoSansKR-Medium.ttf",
            "NotoSansCJK-Medium.ttc",
            "NotoSansCJK-Regular.ttc",
            "NanumSquareRoundR.ttf",
            "NanumGothic.ttf",
            "malgun.ttf",
        ),
        "regular": (
            "Pretendard-Regular.ttf",
            "NotoSansKR-Regular.ttf",
            "NotoSansCJK-Regular.ttc",
            "NanumSquareRoundR.ttf",
            "NanumGothic.ttf",
            "malgun.ttf",
        ),
    }

    resolved: dict[str, str] = {}
    for weight, names in candidates.items():
        found = ""
        for font_dir in search_dirs:
            if not font_dir.exists():
                continue
            for name in names:
                candidate = font_dir / name
                if candidate.exists():
                    found = str(candidate)
                    break
            if found:
                break
        if not found:
            # 하위 디렉터리 재귀 탐색 폴백 (Linux 배포판별 폰트 경로 차이 대응)
            for root_dir in (Path("/usr/share/fonts"), BASE_DIR / "fonts"):
                if not root_dir.exists():
                    continue
                for name in names:
                    match = next(root_dir.rglob(name), None)
                    if match and match.exists():
                        found = str(match)
                        break
                if found:
                    break
        if not found:
            raise FileNotFoundError(
                f"사용 가능한 한글 폰트를 찾지 못했습니다 ({weight}): {names}"
            )
        resolved[weight] = found
    return resolved
