"""인스타그램 카드뉴스 스타일들이 공유하는 공통 레이아웃·텍스트·GPX 렌더링 유틸리티."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

import config

WIDTH = 1080
HEIGHT = 1350
MAX_SPOT_PHOTOS = 5
MAX_SLIDES = 10


class FontSet:
    """크기별 한글 폰트 객체를 캐시해 제공하는 헬퍼."""

    def __init__(self) -> None:
        self.paths = config.get_font_paths()
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def get(self, weight: str, size: int) -> ImageFont.FreeTypeFont:
        key = (weight, size)
        if key not in self._cache:
            path = self.paths.get(weight, self.paths["regular"])
            self._cache[key] = ImageFont.truetype(path, size)
        return self._cache[key]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int | None = None,
) -> list[str]:
    """픽셀 폭 기준으로 한국어/영문 혼합 텍스트를 줄바꿈하고 넘치면 말줄임 처리한다."""
    if not text:
        return []

    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    lines: list[str] = []

    for para in paragraphs:
        current = ""
        for ch in para:
            candidate = current + ch
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
                continue
            if current:
                split_idx = current.rfind(" ")
                if split_idx >= max(1, len(current) // 2):
                    lines.append(current[:split_idx].rstrip())
                    current = current[split_idx + 1 :] + ch
                else:
                    lines.append(current.rstrip())
                    current = ch
            else:
                lines.append(ch)
                current = ""
        if current:
            lines.append(current.rstrip())

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_width:
            last = last[:-1]
        lines[-1] = (last.rstrip() + "…") if last else "…"

    return lines


def draw_lines(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, ...],
    line_gap: int = 12,
) -> int:
    """여러 줄 텍스트를 순서대로 그리고 다음 y 좌표를 반환한다."""
    bbox = font.getbbox("가Ag")
    line_h = (bbox[3] - bbox[1]) + line_gap
    curr_y = y
    for line in lines:
        draw.text((x, curr_y), line, font=font, fill=fill)
        curr_y += line_h
    return curr_y


def fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    fonts: FontSet,
    weight: str,
    max_width: int,
    max_height: int,
    *,
    start_size: int = 26,
    min_size: int = 19,
    line_gap: int = 10,
) -> tuple[list[str], ImageFont.FreeTypeFont, int]:
    """주어진 높이 안에 본문이 잘리지 않고 모두 들어가도록 폰트 크기와 줄간격을 자동 조절한다."""
    font = fonts.get(weight, start_size)
    gap = line_gap
    for size in range(start_size, min_size - 1, -1):
        font = fonts.get(weight, size)
        gap = max(6, round(line_gap * (size / start_size)))
        lines = wrap_text(draw, text, font, max_width, max_lines=None)
        if not lines:
            return [], font, gap
        bbox = font.getbbox("가Ag")
        line_h = (bbox[3] - bbox[1]) + gap
        total_h = len(lines) * line_h - gap
        if total_h <= max_height:
            return lines, font, gap

    # 최소 폰트 크기에서도 높이를 초과하는 극단적 장문만 허용 줄 수로 제한
    bbox = font.getbbox("가Ag")
    line_h = (bbox[3] - bbox[1]) + gap
    max_lines = max(1, (max_height + gap) // max(1, line_h))
    return wrap_text(draw, text, font, max_width, max_lines=max_lines), font, gap


def draw_pill(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.FreeTypeFont,
    bg_fill: tuple[int, ...],
    text_fill: tuple[int, ...],
    pad_x: int = 22,
    pad_y: int = 11,
    outline: tuple[int, ...] | None = None,
    outline_width: int = 0,
) -> int:
    """텍스트 폭에 맞춘 둥근 필(pill) 배지를 그리고 오른쪽 끝 x 좌표를 반환한다."""
    tw = int(draw.textlength(text, font=font))
    bbox = font.getbbox(text)
    th = bbox[3] - bbox[1]
    w = tw + pad_x * 2
    h = th + pad_y * 2
    draw.rounded_rectangle(
        (x, y, x + w, y + h),
        radius=h // 2,
        fill=bg_fill,
        outline=outline,
        width=outline_width,
    )
    draw.text((x + pad_x, y + pad_y - bbox[1] // 2), text, font=font, fill=text_fill)
    return x + w


def draw_bookmark_icon(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int = 18,
    h: int = 26,
    fill: tuple[int, ...] = (255, 255, 255),
) -> None:
    """이모지 깨짐 방지를 위해 벡터 북마크 아이콘을 직접 그린다."""
    draw.polygon(
        [(x, y), (x + w, y), (x + w, y + h), (x + w // 2, y + int(h * 0.69)), (x, y + h)],
        fill=fill,
    )


def draw_footer(
    draw: ImageDraw.ImageDraw,
    fonts: FontSet,
    page_num: int,
    *,
    line_color: tuple[int, ...],
    text_color: tuple[int, ...],
    accent_color: tuple[int, ...],
    total_pages: int = 10,
    left_text: str = f"{config.BRAND_NAME}  ·  출처: 한국관광공사 두루누비",
) -> None:
    """카드 하단에 브랜드, 공공데이터 출처, 페이지 번호를 그린다."""
    draw.line((76, HEIGHT - 96, WIDTH - 76, HEIGHT - 96), fill=line_color, width=2)
    f_small = fonts.get("medium", 22)
    f_page = fonts.get("bold", 24)
    draw.text((76, HEIGHT - 72), left_text, font=f_small, fill=text_color)
    page_str = f"{page_num} / {total_pages}"
    pw = draw.textlength(page_str, font=f_page)
    draw.text((WIDTH - 76 - pw, HEIGHT - 74), page_str, font=f_page, fill=accent_color)


def project_gpx_points(
    points: list[tuple[float, float, float | None]],
    box: tuple[int, int, int, int],
    max_points: int = 240,
) -> list[tuple[float, float]]:
    """GPX 위경도 좌표를 위도 보정(cos)과 종횡비를 유지해 지정 박스 내부 좌표로 변환한다."""
    if len(points) < 2:
        return []

    step = max(1, len(points) // max_points)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])

    lats = [p[0] for p in sampled]
    lons = [p[1] for p in sampled]
    mid_lat = (min(lats) + max(lats)) / 2.0
    cos_lat = math.cos(math.radians(mid_lat)) or 1.0

    xs = [lon * cos_lat for lon in lons]
    ys = [-lat for lat in lats]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)

    left, top, right, bottom = box
    box_w = max(1, right - left)
    box_h = max(1, bottom - top)
    scale = min(box_w / span_x, box_h / span_y)

    offset_x = left + (box_w - span_x * scale) / 2.0
    offset_y = top + (box_h - span_y * scale) / 2.0

    return [
        (offset_x + (x - min_x) * scale, offset_y + (y - min_y) * scale)
        for x, y in zip(xs, ys)
    ]


def sample_elevations(eles: list[float], max_buckets: int = 120) -> list[float]:
    """구간별 봉우리/계곡이 누락되지 않도록 고도 리스트를 샘플링한다."""
    if len(eles) <= 2:
        return list(eles)
    buckets = min(max_buckets, len(eles))
    sampled: list[float] = []
    for b in range(buckets):
        s_idx = int(b * len(eles) / buckets)
        e_idx = max(s_idx + 1, int((b + 1) * len(eles) / buckets))
        seg = eles[s_idx:e_idx]
        sampled.append(max(seg) if b % 2 == 0 else min(seg))
    return sampled


def draw_elevation_chart(
    img: Image.Image,
    eles: list[float],
    chart_box: tuple[int, int, int, int],
    fonts: FontSet,
    *,
    grid_color: tuple[int, ...],
    label_color: tuple[int, ...],
    line_color: tuple[int, ...],
    fill_rgba: tuple[int, int, int, int],
) -> Image.Image:
    """지정된 영역에 고도 영역 차트와 축 눈금을 그린다."""
    draw = ImageDraw.Draw(img)
    chart_left, chart_top, chart_right, chart_bottom = chart_box

    if len(eles) < 2:
        msg = "이 코스는 고도(ele) 측정 데이터를 포함하고 있지 않습니다."
        mw = draw.textlength(msg, font=fonts.get("medium", 25))
        draw.text(
            ((WIDTH - mw) / 2, (chart_top + chart_bottom) // 2 - 14),
            msg,
            font=fonts.get("medium", 25),
            fill=label_color,
        )
        return img

    e_sampled = sample_elevations(eles, max_buckets=120)
    e_min = float(min(eles))
    e_max = float(max(eles))
    e_span = max(e_max - e_min, 5.0)

    for frac in (0.0, 0.5, 1.0):
        gy = int(chart_bottom - frac * (chart_bottom - chart_top))
        draw.line((chart_left, gy, chart_right, gy), fill=grid_color, width=2)
        label_e = f"{int(round(e_min + frac * e_span))}m"
        draw.text((chart_left - 54, gy - 12), label_e, font=fonts.get("regular", 18), fill=label_color)

    pts_chart: list[tuple[float, float]] = []
    n = len(e_sampled)
    for i, val in enumerate(e_sampled):
        px = chart_left + (i / (n - 1)) * (chart_right - chart_left)
        py = chart_bottom - ((val - e_min) / e_span) * (chart_bottom - chart_top)
        pts_chart.append((px, py))

    poly = [(chart_left, chart_bottom), *pts_chart, (chart_right, chart_bottom)]
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.polygon(poly, fill=fill_rgba)
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(img)
    draw.line(pts_chart, fill=line_color, width=5, joint="curve")

    draw.text((chart_left, chart_bottom + 14), "출발점", font=fonts.get("regular", 20), fill=label_color)
    end_lbl = "도착점"
    ew = draw.textlength(end_lbl, font=fonts.get("regular", 20))
    draw.text((chart_right - ew, chart_bottom + 14), end_lbl, font=fonts.get("regular", 20), fill=label_color)
    return img


def load_fitted_image(path: str | Path | None, size: tuple[int, int]) -> Image.Image | None:
    """로컬 이미지 파일을 열어 지정 크기에 맞게 중앙 크롭(LANCZOS)한 RGBA 이미지를 반환한다."""
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    try:
        with Image.open(target) as im:
            rgba = im.convert("RGBA")
            return ImageOps.fit(
                rgba,
                size,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
    except Exception:
        return None


def paste_rounded_image(
    canvas: Image.Image,
    photo: Image.Image,
    box: tuple[int, int, int, int],
    radius: int = 16,
    outline: tuple[int, ...] | None = None,
    outline_width: int = 0,
) -> None:
    """지정 영역에 안티앨리어싱된 둥근 모서리 사진을 합성하고 선택적으로 테두리를 그린다."""
    w = box[2] - box[0]
    h = box[3] - box[1]
    if w <= 0 or h <= 0:
        return

    fitted = ImageOps.fit(
        photo.convert("RGBA"),
        (w, h),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    mask_hi = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(mask_hi).rounded_rectangle(
        (0, 0, w * 2 - 1, h * 2 - 1),
        radius=radius * 2,
        fill=255,
    )
    mask = mask_hi.resize((w, h), Image.Resampling.LANCZOS)
    canvas.paste(fitted, (box[0], box[1]), mask)

    if outline and outline_width > 0:
        ImageDraw.Draw(canvas).rounded_rectangle(
            box,
            radius=radius,
            outline=outline,
            width=outline_width,
        )


def build_vertical_gradient(
    size: tuple[int, int],
    stops: list[tuple[float, tuple[int, int, int, int]]],
) -> Image.Image:
    """정규화 높이(0.0~1.0)별 RGBA 정지점을 선형 보간해 수직 그라데이션 오버레이를 만든다."""
    w, h = size
    grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if not stops or w <= 0 or h <= 0:
        return grad

    ordered = sorted(stops, key=lambda x: x[0])
    gdraw = ImageDraw.Draw(grad)
    span_h = max(1, h - 1)

    for y in range(h):
        ratio = y / span_h
        if ratio <= ordered[0][0]:
            color = ordered[0][1]
        elif ratio >= ordered[-1][0]:
            color = ordered[-1][1]
        else:
            color = ordered[-1][1]
            for (r0, c0), (r1, c1) in zip(ordered, ordered[1:]):
                if r0 <= ratio <= r1:
                    t = (ratio - r0) / max(1e-6, r1 - r0)
                    color = tuple(round(c0[i] + (c1[i] - c0[i]) * t) for i in range(4))  # type: ignore[assignment]
                    break
        gdraw.line((0, y, w, y), fill=color)
    return grad


def get_footer_source_text(bundle: dict[str, Any]) -> str:
    """사진 연동 여부에 따라 카드 하단 공식 데이터 출처 문구를 반환한다."""
    if (bundle.get("photos") or {}).get("has_photos"):
        return f"{config.BRAND_NAME}  ·  출처: 한국관광공사 두루누비 · 국문 관광정보"
    return f"{config.BRAND_NAME}  ·  출처: 한국관광공사 두루누비"
