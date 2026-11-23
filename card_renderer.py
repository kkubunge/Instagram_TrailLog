"""인스타그램 카드뉴스 스타일 레지스트리 및 기본 포레스트(forest) 스타일 렌더러."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw

from card_common import (
    HEIGHT,
    MAX_SPOT_PHOTOS,
    WIDTH,
    FontSet,
    build_vertical_gradient,
    draw_bookmark_icon,
    draw_elevation_chart,
    draw_footer,
    draw_lines,
    draw_map_spot_markers,
    draw_pill,
    extract_map_spots,
    fit_wrapped_text,
    get_footer_source_text,
    load_fitted_image,
    paste_rounded_image,
    project_gpx_and_spots,
    project_gpx_points,
    wrap_text,
)
from style_ocean import render_ocean_slides

# 포레스트 매거진 컬러 팔레트
C_FOREST_DARK = (16, 44, 36)
C_FOREST = (22, 58, 48)
C_FOREST_LIGHT = (36, 84, 70)
C_MINT_BG = (232, 242, 238)
C_IVORY = (246, 243, 236)
C_WHITE = (255, 255, 255)
C_BORDER = (226, 221, 210)
C_GRID = (236, 240, 238)
C_TERRACOTTA = (217, 107, 67)
C_TERRACOTTA_BG = (252, 237, 231)
C_SLATE = (24, 36, 48)
C_MUTED = (100, 116, 139)
C_LIGHT_TEXT = (226, 236, 232)
C_GREEN_LINE = (21, 128, 61)
C_GREEN_FILL = (21, 128, 61, 48)

STYLE_META: dict[str, dict[str, str]] = {
    "forest": {
        "name": "아웃도어 포레스트",
        "desc": "숲·산 코스에 맞춘 딥 그린 & 아이보리 트레킹 매거진 스타일 (최대 10장)",
    },
    "ocean": {
        "name": "오션 브리즈",
        "desc": "바다·해안 코스에 맞춘 하늘빛 & 딥 오션 블루 트래블 매거진 스타일 (최대 10장)",
    },
}

COMPARE_STYLES: tuple[str, ...] = ("forest", "ocean")


def _draw_forest_footer(
    draw: ImageDraw.ImageDraw,
    fonts: FontSet,
    page_num: int,
    on_dark_bg: bool = False,
    left_text: str | None = None,
    total_pages: int = 10,
) -> None:
    """포레스트 스타일 공통 하단 푸터를 그린다."""
    draw_footer(
        draw,
        fonts,
        page_num,
        line_color=(50, 92, 78) if on_dark_bg else C_BORDER,
        text_color=(180, 206, 196) if on_dark_bg else C_MUTED,
        accent_color=C_WHITE if on_dark_bg else C_FOREST,
        total_pages=total_pages,
        left_text=left_text or "TrailLog  ·  출처: 한국관광공사 두루누비",
    )


def _draw_forest_cover_with_photo(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    fonts: FontSet,
    cover_img: Image.Image,
    cover_meta: dict[str, Any],
    out_path: Path,
    *,
    total_pages: int = 10,
) -> None:
    """실사 풀블리드 배경과 타이포그래피 중심의 포레스트 1번 표지 카드를 그린다."""
    img = cover_img.copy()
    grad = build_vertical_gradient(
        (WIDTH, HEIGHT),
        [
            (0.0, (14, 40, 32, 225)),
            (0.26, (14, 40, 32, 165)),
            (0.40, (14, 40, 32, 18)),
            (0.82, (14, 40, 32, 15)),
            (0.92, (14, 40, 32, 195)),
            (1.0, (14, 40, 32, 240)),
        ],
    )
    img = Image.alpha_composite(img, grad)

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    # 좌하단 사진 캡션 필 (푸터 바로 위 배치)
    photo_title = str(cover_meta.get("title") or "").strip()
    if photo_title:
        cap_text = f"PHOTO · {photo_title}"
        f_cap = fonts.get("bold", 19)
        cap_w = int(odraw.textlength(cap_text, font=f_cap)) + 32
        cap_w = min(cap_w, WIDTH - 152)
        odraw.rounded_rectangle(
            (76, 1190, 76 + cap_w, 1226),
            radius=18,
            fill=(14, 40, 32, 175),
            outline=(255, 255, 255, 70),
            width=1,
        )
        odraw.text((92, 1197), cap_text, font=f_cap, fill=(*C_LIGHT_TEXT, 255))

    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # 좌상단 텍스트 영역
    draw.text((76, 72), "TRAILLOG · FOREST GUIDE", font=fonts.get("bold", 22), fill=(186, 222, 208))

    f_pill = fonts.get("bold", 26)
    pill_x = 76
    if bundle["sigun"]:
        pill_x = draw_pill(draw, pill_x, 124, bundle["sigun"], f_pill, C_TERRACOTTA, C_WHITE) + 14
    draw_pill(draw, pill_x, 124, bundle["brd_label"], f_pill, C_FOREST_LIGHT, C_WHITE)

    draw.text((76, 204), bundle["route_name"] or "대한민국 두루누비 코스", font=fonts.get("medium", 30), fill=(210, 236, 224))

    f_title = fonts.get("bold", 72)
    title_lines = wrap_text(draw, bundle["course_name"], f_title, WIDTH - 152, max_lines=2)
    sh_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sh_overlay)
    draw_lines(sh_draw, 78, 251, title_lines, f_title, (10, 24, 18, 160), line_gap=14)
    img = Image.alpha_composite(img, sh_overlay)
    draw = ImageDraw.Draw(img)
    next_y = draw_lines(draw, 76, 248, title_lines, f_title, C_WHITE, line_gap=14)

    draw.rounded_rectangle((76, next_y + 18, 216, next_y + 28), radius=5, fill=C_TERRACOTTA)

    f_hook = fonts.get("medium", 34)
    hook_lines = wrap_text(draw, copy["hook_line"], f_hook, WIDTH - 152, max_lines=2)
    draw_lines(draw, 76, next_y + 52, hook_lines, f_hook, C_WHITE, line_gap=12)

    _draw_forest_footer(
        draw,
        fonts,
        1,
        on_dark_bg=True,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_forest_1_cover(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    total_pages: int = 10,
) -> None:
    """1번 표지 카드: 실사 배경(보유 시) 또는 그라데이션 + GPX 실루엣 + 코스 타이틀."""
    cover_meta = (bundle.get("photos") or {}).get("cover") or {}
    cover_img = load_fitted_image(cover_meta.get("local_path"), (WIDTH, HEIGHT))
    if cover_img is not None:
        _draw_forest_cover_with_photo(
            bundle, copy, fonts, cover_img, cover_meta, out_path, total_pages=total_pages
        )
        return

    img = Image.new("RGBA", (WIDTH, HEIGHT), C_FOREST_DARK)
    draw = ImageDraw.Draw(img)

    for row in range(HEIGHT):
        ratio = row / HEIGHT
        r = int(14 + ratio * 16)
        g = int(40 + ratio * 28)
        b = int(32 + ratio * 22)
        draw.line((0, row, WIDTH, row), fill=(r, g, b, 255))

    gpx_points = bundle.get("gpx", {}).get("points") or []
    bg_coords = project_gpx_points(gpx_points, (100, 560, WIDTH - 90, 1140), max_points=220)
    if len(bg_coords) >= 2:
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.line(bg_coords, fill=(255, 255, 255, 34), width=14, joint="curve")
        odraw.line(bg_coords, fill=(217, 107, 67, 75), width=4, joint="curve")
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

    draw.text((76, 78), "TRAILLOG · FOREST GUIDE", font=fonts.get("bold", 24), fill=(176, 212, 198))

    f_pill = fonts.get("bold", 26)
    pill_x = 76
    if bundle["sigun"]:
        pill_x = draw_pill(draw, pill_x, 148, bundle["sigun"], f_pill, C_TERRACOTTA, C_WHITE) + 14
    draw_pill(draw, pill_x, 148, bundle["brd_label"], f_pill, C_FOREST_LIGHT, C_WHITE)

    draw.text((76, 280), bundle["route_name"] or "대한민국 두루누비 코스", font=fonts.get("medium", 34), fill=(195, 224, 212))

    f_title = fonts.get("bold", 78)
    title_lines = wrap_text(draw, bundle["course_name"], f_title, WIDTH - 152, max_lines=3)
    next_y = draw_lines(draw, 76, 345, title_lines, f_title, C_WHITE, line_gap=18)

    draw.rounded_rectangle((76, next_y + 24, 216, next_y + 34), radius=5, fill=C_TERRACOTTA)

    f_hook = fonts.get("medium", 38)
    hook_lines = wrap_text(draw, copy["hook_line"], f_hook, WIDTH - 152, max_lines=3)
    draw_lines(draw, 76, next_y + 66, hook_lines, f_hook, C_LIGHT_TEXT, line_gap=14)

    _draw_forest_footer(
        draw,
        fonts,
        1,
        on_dark_bg=True,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_forest_2_route_map(
    bundle: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 9,
    total_pages: int = 10,
    section_no: str = "04",
) -> None:
    """스펙·GPX·고도 통합 카드: 코스 핵심 스펙 3열 + 실제 GPX 경로 지도 + 고도(Elevation) 프로파일 그래프."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), C_IVORY)
    draw = ImageDraw.Draw(img)

    draw.text((76, 66), f"{section_no} · COURSE SPEC & GPX", font=fonts.get("bold", 22), fill=C_TERRACOTTA)
    draw.text((76, 102), "코스 스펙 · 경로 & 고도", font=fonts.get("bold", 46), fill=C_SLATE)

    # 상단 핵심 스펙 3열 카드
    spec_top, spec_bottom = 178, 282
    draw.rounded_rectangle((76, spec_top, WIDTH - 76, spec_bottom), radius=22, fill=C_WHITE, outline=C_BORDER, width=2)
    specs = [
        ("총 거리", bundle["distance_text"]),
        ("소요시간", bundle["duration_text"]),
        ("난이도", bundle["level_label"]),
    ]
    col_w = (WIDTH - 152) // 3
    f_spec_lbl = fonts.get("medium", 20)
    f_spec_val = fonts.get("bold", 36)
    for i, (lbl, val) in enumerate(specs):
        cx = 76 + col_w * i + col_w // 2
        if i > 0:
            div_x = 76 + col_w * i
            draw.line((div_x, spec_top + 22, div_x, spec_bottom - 22), fill=C_BORDER, width=2)
        lw = draw.textlength(lbl, font=f_spec_lbl)
        val_font = f_spec_val if draw.textlength(val, font=f_spec_val) <= col_w - 28 else fonts.get("bold", 28)
        vw = draw.textlength(val, font=val_font)
        draw.text((cx - lw / 2, spec_top + 20), lbl, font=f_spec_lbl, fill=C_MUTED)
        draw.text((cx - vw / 2, spec_top + 50), val, font=val_font, fill=C_TERRACOTTA if i == 0 else C_FOREST_DARK)

    # 중앙 GPX 경로 지도 카드
    draw.rounded_rectangle((76, 304, WIDTH - 76, 816), radius=26, fill=C_WHITE, outline=C_BORDER, width=2)

    inner_map = (130, 362, WIDTH - 130, 740)
    for gx in range(inner_map[0], inner_map[2] + 1, 130):
        draw.line((gx, inner_map[1] - 14, gx, inner_map[3] + 14), fill=C_GRID, width=2)
    for gy in range(inner_map[1], inner_map[3] + 1, 100):
        draw.line((inner_map[0] - 14, gy, inner_map[2] + 14, gy), fill=C_GRID, width=2)

    gpx = bundle.get("gpx") or {}
    points = gpx.get("points") or []
    map_spots = extract_map_spots(bundle, points)
    coords, projected_spots = project_gpx_and_spots(points, map_spots, inner_map, max_points=260)

    f_badge = fonts.get("bold", 21)
    cycle_str = f"{bundle['cycle_type']} · {bundle['distance_text']}"
    cw = int(draw.textlength(cycle_str, font=f_badge)) + 36
    badge_x0 = WIDTH - 104 - cw

    if len(coords) >= 2:
        draw.line(coords, fill=(21, 128, 61, 60), width=14, joint="curve")
        draw.line(coords, fill=C_FOREST, width=7, joint="curve")
        sx, sy = coords[0]
        ex, ey = coords[-1]
        draw.ellipse((sx - 18, sy - 18, sx + 18, sy + 18), fill=C_GREEN_LINE, outline=C_WHITE, width=4)
        draw.ellipse((ex - 18, ey - 18, ex + 18, ey + 18), fill=C_TERRACOTTA, outline=C_WHITE, width=4)
        draw.text((sx - 7, sy - 12), "S", font=fonts.get("bold", 20), fill=C_WHITE)
        draw.text((ex - 6, ey - 12), "E", font=fonts.get("bold", 20), fill=C_WHITE)
        draw_map_spot_markers(
            draw,
            fonts,
            projected_spots,
            gpx_coords=coords,
            start_end_coords=(coords[0], coords[-1]),
            bounds=(96, 350, WIDTH - 96, 756),
            avoid_boxes=[(badge_x0 - 8, 316, WIDTH - 96, 368)],
            accent_color=C_TERRACOTTA,
            text_color=C_SLATE,
            chip_bg=C_WHITE,
            chip_border=C_TERRACOTTA,
        )
    else:
        msg = "GPX 경로 데이터가 제공되지 않는 코스입니다."
        mw = draw.textlength(msg, font=fonts.get("medium", 28))
        draw.text(((WIDTH - mw) / 2, 535), msg, font=fonts.get("medium", 28), fill=C_MUTED)

    draw_pill(draw, badge_x0, 324, cycle_str, f_badge, C_MINT_BG, C_FOREST, pad_x=18, pad_y=8)

    f_legend = fonts.get("medium", 21)
    draw.ellipse((116, 772, 134, 790), fill=C_GREEN_LINE)
    draw.text((144, 768), "START 출발", font=f_legend, fill=C_SLATE)
    draw.ellipse((288, 772, 306, 790), fill=C_TERRACOTTA)
    draw.text((316, 768), "FINISH 도착", font=f_legend, fill=C_SLATE)
    if projected_spots:
        draw.ellipse((466, 771, 486, 791), fill=C_WHITE, outline=C_TERRACOTTA, width=3)
        draw.text((495, 768), f"스팟(1~{len(projected_spots)})", font=f_legend, fill=C_SLATE)
    pt_info = f"실측 GPX 좌표 {gpx.get('point_count', 0):,}개 반영"
    pw = draw.textlength(pt_info, font=f_legend)
    draw.text((WIDTH - 110 - pw, 768), pt_info, font=f_legend, fill=C_MUTED)

    # 하단 고도 변화 카드
    draw.rounded_rectangle((76, 838, WIDTH - 76, 1220), radius=26, fill=C_WHITE, outline=C_BORDER, width=2)
    draw.text((116, 864), "고도 변화 (ELEVATION PROFILE)", font=fonts.get("bold", 23), fill=C_FOREST)

    eles = [p[2] for p in points if p[2] is not None]
    min_e, max_e, gain_e = gpx.get("min_ele"), gpx.get("max_ele"), gpx.get("elevation_gain")
    stat_str = (
        f"최저 {min_e}m   ·   최고 {max_e}m   ·   누적상승 +{gain_e}m"
        if min_e is not None
        else "고도 정보 미제공"
    )
    sw = draw.textlength(stat_str, font=fonts.get("bold", 23))
    draw.text((WIDTH - 116 - sw, 864), stat_str, font=fonts.get("bold", 23), fill=C_TERRACOTTA)

    img = draw_elevation_chart(
        img,
        eles,
        (146, 932, WIDTH - 120, 1164),
        fonts,
        grid_color=C_GRID,
        label_color=C_MUTED,
        line_color=C_GREEN_LINE,
        fill_rgba=C_GREEN_FILL,
        spot_markers=projected_spots,
        marker_color=C_TERRACOTTA,
    )
    draw = ImageDraw.Draw(img)
    _draw_forest_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_forest_3_spots(
    bundle: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 2,
    total_pages: int = 10,
) -> None:
    """2번 카드: 주요 관광 포인트 및 경유 스팟 최대 5개 카드(실사 썸네일 연동) 배치."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*C_IVORY, 255))
    draw = ImageDraw.Draw(img)

    draw.text((76, 76), "01 · COURSE HIGHLIGHTS", font=fonts.get("bold", 24), fill=C_TERRACOTTA)
    draw.text((76, 118), "코스 따라 만나는 볼거리", font=fonts.get("bold", 50), fill=C_SLATE)
    draw.text((76, 190), f"{bundle['course_name']} 주변 주요 스팟", font=fonts.get("medium", 28), fill=C_MUTED)

    spot_items = (bundle.get("photos") or {}).get("spot_items")
    if not spot_items:
        raw_spots = (bundle.get("spots") or bundle.get("summary_lines") or [bundle.get("contents_text") or "상세 스팟 정보가 없습니다."])[:MAX_SPOT_PHOTOS]
        spot_items = [{"text": s, "photo": None} for s in raw_spots]

    top_y, avail_h, gap = 266, 930, 20
    card_h = min(176, (avail_h - gap * max(0, len(spot_items) - 1)) // max(1, len(spot_items)))
    f_num = fonts.get("bold", 30)
    f_badge_sm = fonts.get("bold", 20)
    f_spot_title = fonts.get("bold", 21)
    f_body = fonts.get("medium", 27)
    f_body_thumb = fonts.get("medium", 24)
    curr_y = top_y

    for idx, item in enumerate(spot_items, start=1):
        spot_text = str(item.get("text") or "")
        photo_meta = item.get("photo") or {}
        thumb = load_fitted_image(photo_meta.get("local_path"), (210, 144))

        draw.rounded_rectangle((76, curr_y, WIDTH - 76, curr_y + card_h), radius=22, fill=C_WHITE, outline=C_BORDER, width=2)
        if thumb is not None:
            thumb_box = (94, curr_y + 16, 304, curr_y + 160)
            paste_rounded_image(img, thumb, thumb_box, radius=14, outline=C_BORDER, outline_width=1)
            draw = ImageDraw.Draw(img)
            # 썸네일 좌상단 테라코타 번호 배지
            draw.rounded_rectangle((104, curr_y + 26, 148, curr_y + 58), radius=9, fill=C_TERRACOTTA)
            num_str = f"{idx:02d}"
            nw = draw.textlength(num_str, font=f_badge_sm)
            draw.text((104 + (44 - nw) / 2, curr_y + 30), num_str, font=f_badge_sm, fill=C_WHITE)

            label_lines = wrap_text(draw, str(photo_meta.get("title") or ""), f_spot_title, 654, max_lines=1)
            label = label_lines[0] if label_lines else ""
            if label:
                draw.text((326, curr_y + 20), label, font=f_spot_title, fill=C_TERRACOTTA)
            body_lines = wrap_text(draw, spot_text, f_body_thumb, 654, max_lines=3)
            draw_lines(draw, 326, curr_y + 52, body_lines, f_body_thumb, C_SLATE, line_gap=7)
        else:
            bx, by = 112, curr_y + (card_h - 60) // 2
            draw.rounded_rectangle((bx, by, bx + 60, by + 60), radius=18, fill=C_TERRACOTTA_BG)
            num_str = f"{idx:02d}"
            nw = draw.textlength(num_str, font=f_num)
            draw.text((bx + (60 - nw) / 2, by + 12), num_str, font=f_num, fill=C_TERRACOTTA)

            lines = wrap_text(draw, spot_text, f_body, WIDTH - 290, max_lines=3)
            text_y = curr_y + max(24, (card_h - len(lines) * 38) // 2)
            draw_lines(draw, 200, text_y, lines, f_body, C_SLATE, line_gap=10)
        curr_y += card_h + gap

    _draw_forest_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_forest_spot_photo(
    bundle: dict[str, Any],
    item: dict[str, Any],
    spot_idx: int,
    spot_total: int,
    page_num: int,
    total_pages: int,
    fonts: FontSet,
    out_path: Path,
) -> None:
    """스팟 갤러리 카드: 3:2 비율 대형 실사 사진과 하단 스팟 가이드 설명을 배치한다."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*C_IVORY, 255))
    draw = ImageDraw.Draw(img)

    photo_meta = item.get("photo") or {}
    photo_title = str(photo_meta.get("title") or f"주요 스팟 {spot_idx:02d}").strip()
    spot_text = str(item.get("text") or "").strip()

    draw.text(
        (76, 72),
        f"03 · SPOT GALLERY  ({spot_idx:02d} / {spot_total:02d})",
        font=fonts.get("bold", 22),
        fill=C_TERRACOTTA,
    )
    f_title = fonts.get("bold", 46)
    if draw.textlength(photo_title, font=f_title) > WIDTH - 152:
        f_title = fonts.get("bold", 40)
    title_lines = wrap_text(draw, photo_title, f_title, WIDTH - 152, max_lines=1)
    draw.text((76, 112), title_lines[0] if title_lines else photo_title, font=f_title, fill=C_SLATE)

    sub_text = f"{bundle['course_name']}  ·  {bundle['sigun']}" if bundle.get("sigun") else bundle["course_name"]
    draw.text((76, 174), sub_text, font=fonts.get("medium", 24), fill=C_MUTED)

    # 중앙 대형 3:2 실사 사진 프레임 (928 × 620px)
    photo_box = (76, 228, WIDTH - 76, 848)
    photo_img = load_fitted_image(
        photo_meta.get("local_path"),
        (photo_box[2] - photo_box[0], photo_box[3] - photo_box[1]),
    )
    if photo_img is not None:
        paste_rounded_image(img, photo_img, photo_box, radius=26, outline=C_BORDER, outline_width=2)
        draw = ImageDraw.Draw(img)
    else:
        draw.rounded_rectangle(photo_box, radius=26, fill=C_WHITE, outline=C_BORDER, width=2)

    draw_pill(draw, 102, 254, f"SPOT {spot_idx:02d}", fonts.get("bold", 21), C_TERRACOTTA, C_WHITE, pad_x=18, pad_y=8)

    # 하단 스팟 가이드 카드
    draw.rounded_rectangle((76, 880, WIDTH - 76, 1214), radius=26, fill=C_WHITE, outline=C_BORDER, width=2)
    draw.rounded_rectangle((112, 918, 120, 954), radius=4, fill=C_TERRACOTTA)
    draw.text((136, 922), "SPOT GUIDE", font=fonts.get("bold", 22), fill=C_TERRACOTTA)

    body_lines, body_font, body_gap = fit_wrapped_text(
        draw,
        spot_text,
        fonts,
        "medium",
        WIDTH - 224,
        168,
        start_size=32,
        min_size=24,
        line_gap=14,
    )
    draw_lines(draw, 112, 976, body_lines, body_font, C_SLATE, line_gap=body_gap)

    credit = "사진 제공: 한국관광공사 국문 관광정보"
    f_credit = fonts.get("regular", 19)
    cw = draw.textlength(credit, font=f_credit)
    draw.text((WIDTH - 112 - cw, 1164), credit, font=f_credit, fill=C_MUTED)

    _draw_forest_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_forest_4_highlights(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 3,
    total_pages: int = 10,
) -> None:
    """3번 카드: 매거진 인용 헤더 & 핵심 매력 포인트 & 잘림 없는 코스 스토리."""
    img = Image.new("RGB", (WIDTH, HEIGHT), C_IVORY)
    draw = ImageDraw.Draw(img)

    f_quote = fonts.get("bold", 38)
    q_lines = wrap_text(draw, f'“{copy["hook_line"]}”', f_quote, WIDTH - 232, max_lines=2)
    q_bbox = f_quote.getbbox("가Ag")
    q_line_h = (q_bbox[3] - q_bbox[1]) + 10
    after_q = 138 + len(q_lines) * q_line_h
    tag_y = after_q + 18
    header_bottom = max(306, tag_y + 56)

    draw.rounded_rectangle((76, 72, WIDTH - 76, header_bottom), radius=28, fill=C_FOREST)
    draw.text((116, 102), "02 · EDITORIAL PICK", font=fonts.get("bold", 22), fill=(176, 212, 198))
    draw_lines(draw, 116, 138, q_lines, f_quote, C_WHITE, line_gap=10)

    tag_x = 116
    for tag in (copy.get("recommend_tags") or [])[:3]:
        next_x = draw_pill(draw, tag_x, tag_y, f"#{tag}", fonts.get("bold", 22), C_FOREST_LIGHT, C_WHITE, pad_x=18, pad_y=9)
        if next_x > WIDTH - 110:
            break
        tag_x = next_x + 12

    curr_y = header_bottom + 24
    for idx, pt in enumerate((copy.get("summary_points") or [])[:3], start=1):
        lines = wrap_text(draw, pt, fonts.get("medium", 28), WIDTH - 224, max_lines=2)
        card_h = 114 if len(lines) == 1 else 148
        draw.rounded_rectangle((76, curr_y, WIDTH - 76, curr_y + card_h), radius=22, fill=C_WHITE, outline=C_BORDER, width=2)
        draw_pill(draw, 112, curr_y + 18, f"POINT {idx}", fonts.get("bold", 22), C_MINT_BG, C_FOREST, pad_x=16, pad_y=5)
        draw_lines(draw, 112, curr_y + 62, lines, fonts.get("medium", 28), C_SLATE, line_gap=9)
        curr_y += card_h + 14

    story_top = curr_y + 6
    draw.rounded_rectangle((76, story_top, WIDTH - 76, 1216), radius=24, fill=C_WHITE, outline=C_BORDER, width=2)
    draw.text((112, story_top + 26), "COURSE STORY", font=fonts.get("bold", 22), fill=C_TERRACOTTA)
    story_raw = bundle.get("contents_text") or " ".join(bundle.get("summary_lines") or [])
    avail_story_h = 1216 - (story_top + 64) - 24
    story_lines, story_font, story_gap = fit_wrapped_text(
        draw,
        story_raw,
        fonts,
        "regular",
        WIDTH - 224,
        avail_story_h,
        start_size=26,
        min_size=19,
        line_gap=10,
    )
    draw_lines(draw, 112, story_top + 64, story_lines, story_font, C_SLATE, line_gap=story_gap)

    _draw_forest_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.save(out_path, format="PNG")


def _render_forest_5_info(
    bundle: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 10,
    total_pages: int = 10,
    section_no: str = "05",
) -> None:
    """마지막 카드: 출발 전 교통·이용 팁 및 저장 유도 배너."""
    img = Image.new("RGB", (WIDTH, HEIGHT), C_IVORY)
    draw = ImageDraw.Draw(img)

    draw.text((76, 76), f"{section_no} · TRAVELER INFO", font=fonts.get("bold", 24), fill=C_TERRACOTTA)
    draw.text((76, 118), "출발 전 체크! 교통 & 팁", font=fonts.get("bold", 50), fill=C_SLATE)

    travel_lines = (bundle.get("traveler_lines") or [])[:7]
    if not travel_lines:
        travel_lines = ["시점 및 종점 대중교통 안내는 두루누비 공식 페이지를 참고해 주세요."]

    info_top, info_bottom = 224, 960
    draw.rounded_rectangle((76, info_top, WIDTH - 76, info_bottom), radius=28, fill=C_WHITE, outline=C_BORDER, width=2)

    f_item = fonts.get("medium", 26)
    curr_y = info_top + 40
    drawn_items: list[tuple[int, list[str]]] = []
    for item_text in travel_lines:
        wrapped = wrap_text(draw, item_text, f_item, WIDTH - 260, max_lines=3)
        needed_h = len(wrapped) * 36 + 26
        if curr_y + needed_h > info_bottom - 20:
            break
        drawn_items.append((curr_y, wrapped))
        curr_y += needed_h

    for idx, (iy, wrapped) in enumerate(drawn_items):
        draw.ellipse((116, iy + 9, 132, iy + 25), fill=C_TERRACOTTA)
        after_y = draw_lines(draw, 154, iy, wrapped, f_item, C_SLATE, line_gap=10)
        if idx < len(drawn_items) - 1:
            draw.line((116, after_y + 8, WIDTH - 116, after_y + 8), fill=C_GRID, width=2)

    cta_top, cta_bottom = 996, 1212
    draw.rounded_rectangle((76, cta_top, WIDTH - 76, cta_bottom), radius=28, fill=C_FOREST_DARK)
    draw.text((118, cta_top + 44), "다음 주말 여행 코스로 찜해두고 싶다면?", font=fonts.get("medium", 27), fill=(186, 220, 206))
    draw.text((118, cta_top + 98), "오른쪽 아래 [저장] 눌러두고 꺼내 보세요!", font=fonts.get("bold", 36), fill=C_WHITE)

    pill_x, pill_y = WIDTH - 274, cta_top + 92
    draw.rounded_rectangle((pill_x, pill_y, pill_x + 158, pill_y + 58), radius=29, fill=C_TERRACOTTA)
    draw.text((pill_x + 28, pill_y + 14), "SAVE", font=fonts.get("bold", 25), fill=C_WHITE)
    draw_bookmark_icon(draw, pill_x + 114, pill_y + 16, w=18, h=26, fill=C_WHITE)

    _draw_forest_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.save(out_path, format="PNG")


def render_forest_slides(
    bundle: dict[str, Any], copy: dict[str, Any], fonts: FontSet, out_dir: Path
) -> list[Path]:
    """아웃도어 포레스트(forest) 스타일 최대 10장 슬라이드(표지>볼거리>핵심매력>사진>스펙·GPX>교통·저장)를 생성한다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("slide_*.png"):
        old.unlink()

    photo_spots = [
        it
        for it in ((bundle.get("photos") or {}).get("spot_items") or [])
        if (it.get("photo") or {}).get("local_path")
    ][:MAX_SPOT_PHOTOS]
    spot_total = len(photo_spots)
    total_pages = 5 + spot_total

    specs: list[tuple[str, Callable[[Path], None]]] = [
        (
            "slide_01_cover.png",
            lambda p, tp=total_pages: _render_forest_1_cover(bundle, copy, fonts, p, total_pages=tp),
        ),
        (
            "slide_02_spots.png",
            lambda p, tp=total_pages: _render_forest_3_spots(bundle, fonts, p, page_num=2, total_pages=tp),
        ),
        (
            "slide_03_highlights.png",
            lambda p, tp=total_pages: _render_forest_4_highlights(bundle, copy, fonts, p, page_num=3, total_pages=tp),
        ),
    ]
    for k, item in enumerate(photo_spots, start=1):
        pg = 3 + k
        specs.append(
            (
                f"slide_{pg:02d}_photo_{k:02d}.png",
                lambda p, it=item, si=k, st=spot_total, pn=pg, tp=total_pages: _render_forest_spot_photo(
                    bundle, it, si, st, pn, tp, fonts, p
                ),
            )
        )

    route_pg = 4 + spot_total
    info_pg = 5 + spot_total
    route_sec = "04" if spot_total > 0 else "03"
    info_sec = "05" if spot_total > 0 else "04"
    specs.extend(
        [
            (
                f"slide_{route_pg:02d}_route_map.png",
                lambda p, pn=route_pg, tp=total_pages, sec=route_sec: _render_forest_2_route_map(
                    bundle, fonts, p, page_num=pn, total_pages=tp, section_no=sec
                ),
            ),
            (
                f"slide_{info_pg:02d}_info.png",
                lambda p, pn=info_pg, tp=total_pages, sec=info_sec: _render_forest_5_info(
                    bundle, fonts, p, page_num=pn, total_pages=tp, section_no=sec
                ),
            ),
        ]
    )

    paths: list[Path] = []
    for filename, fn in specs:
        target = out_dir / filename
        fn(target)
        paths.append(target)
    return paths


STYLE_REGISTRY: dict[
    str, Callable[[dict[str, Any], dict[str, Any], FontSet, Path], list[Path]]
] = {
    "forest": render_forest_slides,
    "ocean": render_ocean_slides,
}


def render_carousel_cards(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    out_dir: Path,
    style: str = "forest",
) -> list[Path]:
    """지정된 스타일(forest/ocean)로 인스타그램 캐러셀 카드 슬라이드를 생성한다."""
    if style not in STYLE_REGISTRY:
        raise ValueError(
            f"지원하지 않는 스타일입니다: '{style}'. 가능한 값: {', '.join(STYLE_REGISTRY.keys())}"
        )
    fonts = FontSet()
    return STYLE_REGISTRY[style](bundle, copy, fonts, out_dir)
