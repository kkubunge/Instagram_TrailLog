"""오션 브리즈(ocean) 카드뉴스 최대 10장 렌더러 (하늘빛 & 딥 오션 블루 트래블 매거진)."""

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
    draw_pill,
    fit_wrapped_text,
    get_footer_source_text,
    load_fitted_image,
    paste_rounded_image,
    project_gpx_points,
    wrap_text,
)

# 오션 브리즈 컬러 팔레트
C_SKY_BG = (238, 246, 255)
C_WHITE = (255, 255, 255)
C_BLUE_SOFT = (219, 236, 254)
C_BORDER = (191, 219, 254)
C_GRID = (224, 240, 254)
C_OCEAN_DARK = (12, 45, 72)
C_OCEAN = (2, 102, 168)
C_SKY_ACCENT = (14, 165, 233)
C_SKY_FILL = (14, 165, 233, 52)
C_INK = (15, 35, 58)
C_MUTED = (82, 109, 138)
C_LIGHT_TEXT = (224, 242, 254)


def _draw_ocean_footer(
    draw: ImageDraw.ImageDraw,
    fonts: FontSet,
    page_num: int,
    *,
    on_dark_bg: bool = False,
    left_text: str | None = None,
    total_pages: int = 10,
) -> None:
    """오션 브리즈 스타일 공통 하단 푸터를 그린다."""
    draw_footer(
        draw,
        fonts,
        page_num,
        line_color=(56, 122, 168) if on_dark_bg else C_BORDER,
        text_color=(186, 224, 248) if on_dark_bg else C_MUTED,
        accent_color=C_WHITE if on_dark_bg else C_OCEAN,
        total_pages=total_pages,
        left_text=left_text or "TrailLog  ·  출처: 한국관광공사 두루누비",
    )


def _render_cover(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    total_pages: int = 10,
) -> None:
    """1번 표지: 청량한 오션 블루 실사 풀블리드 배경(또는 오션 그라데이션) + 코스 타이틀."""
    cover_meta = (bundle.get("photos") or {}).get("cover") or {}
    cover_img = load_fitted_image(cover_meta.get("local_path"), (WIDTH, HEIGHT))

    if cover_img is not None:
        img = cover_img.copy()
        grad = build_vertical_gradient(
            (WIDTH, HEIGHT),
            [
                (0.0, (12, 45, 72, 220)),
                (0.26, (2, 102, 168, 145)),
                (0.40, (14, 165, 233, 18)),
                (0.82, (12, 45, 72, 15)),
                (0.92, (12, 45, 72, 195)),
                (1.0, (12, 45, 72, 240)),
            ],
        )
        img = Image.alpha_composite(img, grad)

        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.line((76, 106, WIDTH - 76, 106), fill=(255, 255, 255, 90), width=1)

        photo_title = str(cover_meta.get("title") or "").strip()
        if photo_title:
            cap_text = f"PHOTO · {photo_title}"
            f_cap = fonts.get("bold", 19)
            cap_w = min(int(odraw.textlength(cap_text, font=f_cap)) + 32, WIDTH - 152)
            odraw.rounded_rectangle(
                (76, 1190, 76 + cap_w, 1226),
                radius=18,
                fill=(12, 45, 72, 185),
                outline=(125, 211, 252, 110),
                width=1,
            )
            odraw.text((92, 1197), cap_text, font=f_cap, fill=(*C_LIGHT_TEXT, 255))

        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
    else:
        img = build_vertical_gradient(
            (WIDTH, HEIGHT),
            [
                (0.0, (12, 45, 72, 255)),
                (0.55, (3, 105, 161, 255)),
                (1.0, (56, 189, 248, 255)),
            ],
        )
        gpx_points = bundle.get("gpx", {}).get("points") or []
        bg_coords = project_gpx_points(gpx_points, (100, 560, WIDTH - 90, 1140), max_points=220)
        if len(bg_coords) >= 2:
            overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            odraw.line(bg_coords, fill=(255, 255, 255, 65), width=10, joint="curve")
            img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
        draw.line((76, 106, WIDTH - 76, 106), fill=(186, 230, 253), width=1)

    draw.text((76, 70), "TRAILLOG · OCEAN GUIDE", font=fonts.get("bold", 22), fill=C_LIGHT_TEXT)

    f_pill = fonts.get("bold", 26)
    pill_x = 76
    if bundle["sigun"]:
        pill_x = draw_pill(draw, pill_x, 128, bundle["sigun"], f_pill, C_SKY_ACCENT, C_WHITE) + 14
    draw_pill(draw, pill_x, 128, bundle["brd_label"], f_pill, C_OCEAN, C_WHITE)

    draw.text(
        (76, 204),
        bundle["route_name"] or "대한민국 두루누비 코스",
        font=fonts.get("medium", 30),
        fill=C_LIGHT_TEXT,
    )

    f_title = fonts.get("bold", 72)
    title_lines = wrap_text(draw, bundle["course_name"], f_title, WIDTH - 152, max_lines=2)
    sh_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sh_overlay)
    draw_lines(sh_draw, 78, 251, title_lines, f_title, (10, 28, 46, 160), line_gap=14)
    img = Image.alpha_composite(img, sh_overlay)
    draw = ImageDraw.Draw(img)
    next_y = draw_lines(draw, 76, 248, title_lines, f_title, C_WHITE, line_gap=14)

    draw.rounded_rectangle((76, next_y + 18, 216, next_y + 28), radius=5, fill=C_SKY_ACCENT)

    f_hook = fonts.get("medium", 34)
    hook_lines = wrap_text(draw, copy["hook_line"], f_hook, WIDTH - 152, max_lines=2)
    draw_lines(draw, 76, next_y + 52, hook_lines, f_hook, C_WHITE, line_gap=12)

    _draw_ocean_footer(
        draw,
        fonts,
        1,
        on_dark_bg=True,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_spots(
    bundle: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 2,
    total_pages: int = 10,
) -> None:
    """2번 카드: INDEX OF SPOTS 연하늘 스팟 카드(좌측 둥근 실사 썸네일 연동)."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*C_SKY_BG, 255))
    draw = ImageDraw.Draw(img)

    draw.text((76, 76), "01 · INDEX OF SPOTS", font=fonts.get("bold", 24), fill=C_OCEAN)
    draw.text((76, 118), "경로 따라 만나는 스팟", font=fonts.get("bold", 48), fill=C_INK)
    draw.text((76, 190), f"{bundle['course_name']} 주변 주요 스팟", font=fonts.get("medium", 28), fill=C_MUTED)

    spot_items = (bundle.get("photos") or {}).get("spot_items")
    if not spot_items:
        raw_spots = (bundle.get("spots") or bundle.get("summary_lines") or [bundle.get("contents_text") or "상세 정보 없음"])[:MAX_SPOT_PHOTOS]
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

        draw.rounded_rectangle(
            (76, curr_y, WIDTH - 76, curr_y + card_h),
            radius=22,
            fill=C_WHITE,
            outline=C_BORDER,
            width=2,
        )
        if thumb is not None:
            thumb_box = (94, curr_y + 16, 304, curr_y + 160)
            paste_rounded_image(img, thumb, thumb_box, radius=14, outline=C_BORDER, outline_width=1)
            draw = ImageDraw.Draw(img)

            draw.rounded_rectangle((104, curr_y + 26, 148, curr_y + 58), radius=9, fill=C_SKY_ACCENT)
            num_str = f"{idx:02d}"
            nw = draw.textlength(num_str, font=f_badge_sm)
            draw.text((104 + (44 - nw) / 2, curr_y + 30), num_str, font=f_badge_sm, fill=C_WHITE)

            label_lines = wrap_text(draw, str(photo_meta.get("title") or ""), f_spot_title, 654, max_lines=1)
            if label_lines:
                draw.text((326, curr_y + 20), label_lines[0], font=f_spot_title, fill=C_OCEAN)
            body_lines = wrap_text(draw, spot_text, f_body_thumb, 654, max_lines=3)
            draw_lines(draw, 326, curr_y + 52, body_lines, f_body_thumb, C_INK, line_gap=7)
        else:
            bx, by = 112, curr_y + (card_h - 60) // 2
            draw.rounded_rectangle((bx, by, bx + 60, by + 60), radius=18, fill=C_BLUE_SOFT)
            num_str = f"{idx:02d}"
            nw = draw.textlength(num_str, font=f_num)
            draw.text((bx + (60 - nw) / 2, by + 12), num_str, font=f_num, fill=C_OCEAN)

            lines = wrap_text(draw, spot_text, f_body, WIDTH - 290, max_lines=3)
            text_y = curr_y + max(24, (card_h - len(lines) * 38) // 2)
            draw_lines(draw, 200, text_y, lines, f_body, C_INK, line_gap=10)
        curr_y += card_h + gap

    _draw_ocean_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_highlights(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 3,
    total_pages: int = 10,
) -> None:
    """3번 카드: 딥 오션 EDITORIAL PICK 헤더 + 스카이 액센트 KEY 카드 + EDITOR'S NOTE."""
    img = Image.new("RGB", (WIDTH, HEIGHT), C_SKY_BG)
    draw = ImageDraw.Draw(img)

    f_quote = fonts.get("bold", 38)
    q_lines = wrap_text(draw, f'“{copy["hook_line"]}”', f_quote, WIDTH - 232, max_lines=2)
    q_bbox = f_quote.getbbox("가Ag")
    q_line_h = (q_bbox[3] - q_bbox[1]) + 10
    after_q = 138 + len(q_lines) * q_line_h
    tag_y = after_q + 18
    header_bottom = max(306, tag_y + 56)

    draw.rounded_rectangle(
        (76, 72, WIDTH - 76, header_bottom),
        radius=26,
        fill=C_OCEAN_DARK,
        outline=C_SKY_ACCENT,
        width=2,
    )
    draw.text((116, 102), "02 · EDITORIAL PICK", font=fonts.get("bold", 22), fill=(125, 211, 252))
    draw_lines(draw, 116, 138, q_lines, f_quote, C_WHITE, line_gap=10)

    tag_x = 116
    for tag in (copy.get("recommend_tags") or [])[:3]:
        next_x = draw_pill(
            draw,
            tag_x,
            tag_y,
            f"#{tag}",
            fonts.get("bold", 22),
            C_OCEAN,
            C_WHITE,
            pad_x=18,
            pad_y=9,
        )
        if next_x > WIDTH - 110:
            break
        tag_x = next_x + 12

    curr_y = header_bottom + 24
    for idx, pt in enumerate((copy.get("summary_points") or [])[:3], start=1):
        lines = wrap_text(draw, pt, fonts.get("medium", 28), WIDTH - 230, max_lines=2)
        card_h = 114 if len(lines) == 1 else 148
        draw.rounded_rectangle(
            (76, curr_y, WIDTH - 76, curr_y + card_h),
            radius=22,
            fill=C_WHITE,
            outline=C_BORDER,
            width=2,
        )
        draw.rounded_rectangle((92, curr_y + 20, 99, curr_y + card_h - 20), radius=4, fill=C_SKY_ACCENT)
        draw_pill(draw, 118, curr_y + 18, f"KEY {idx:02d}", fonts.get("bold", 22), C_BLUE_SOFT, C_OCEAN, pad_x=16, pad_y=5)
        draw_lines(draw, 118, curr_y + 62, lines, fonts.get("medium", 28), C_INK, line_gap=9)
        curr_y += card_h + 14

    story_top = curr_y + 6
    draw.rounded_rectangle((76, story_top, WIDTH - 76, 1216), radius=24, fill=C_WHITE, outline=C_BORDER, width=2)
    draw.text((112, story_top + 26), "EDITOR'S NOTE", font=fonts.get("bold", 22), fill=C_OCEAN)

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
    draw_lines(draw, 112, story_top + 64, story_lines, story_font, C_INK, line_gap=story_gap)

    _draw_ocean_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.save(out_path, format="PNG")


def _render_spot_photo(
    bundle: dict[str, Any],
    item: dict[str, Any],
    spot_idx: int,
    spot_total: int,
    page_num: int,
    total_pages: int,
    fonts: FontSet,
    out_path: Path,
) -> None:
    """스팟 갤러리 카드: 화이트 이중 액자 3:2 실사 사진과 하단 SPOT NOTE를 배치한다."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*C_SKY_BG, 255))
    draw = ImageDraw.Draw(img)

    photo_meta = item.get("photo") or {}
    photo_title = str(photo_meta.get("title") or f"주요 스팟 {spot_idx:02d}").strip()
    spot_text = str(item.get("text") or "").strip()

    draw.text(
        (76, 72),
        f"03 · SPOT GALLERY  ({spot_idx:02d} / {spot_total:02d})",
        font=fonts.get("bold", 22),
        fill=C_OCEAN,
    )
    f_title = fonts.get("bold", 46)
    if draw.textlength(photo_title, font=f_title) > WIDTH - 152:
        f_title = fonts.get("bold", 40)
    title_lines = wrap_text(draw, photo_title, f_title, WIDTH - 152, max_lines=1)
    draw.text((76, 112), title_lines[0] if title_lines else photo_title, font=f_title, fill=C_INK)

    sub_text = f"{bundle['course_name']}  ·  {bundle['sigun']}" if bundle.get("sigun") else bundle["course_name"]
    draw.text((76, 174), sub_text, font=fonts.get("medium", 24), fill=C_MUTED)

    # 화이트 액자풍 이중 프레임 + 중앙 3:2 실사 사진 (896 × 600px)
    draw.rounded_rectangle((76, 224, WIDTH - 76, 876), radius=26, fill=C_WHITE, outline=C_BORDER, width=2)
    photo_box = (92, 240, WIDTH - 92, 840)
    photo_img = load_fitted_image(
        photo_meta.get("local_path"),
        (photo_box[2] - photo_box[0], photo_box[3] - photo_box[1]),
    )
    if photo_img is not None:
        paste_rounded_image(img, photo_img, photo_box, radius=18)
        draw = ImageDraw.Draw(img)

    draw_pill(draw, 112, 260, f"SPOT {spot_idx:02d}", fonts.get("bold", 20), C_SKY_ACCENT, C_WHITE, pad_x=18, pad_y=8)

    plate_loc = bundle["sigun"] or "TRAILLOG"
    plate_str = f"PLATE {spot_idx + 1:02d} · {plate_loc}"
    f_plate = fonts.get("regular", 17)
    pw = draw.textlength(plate_str, font=f_plate)
    draw.text((WIDTH - 96 - pw, 847), plate_str, font=f_plate, fill=C_MUTED)

    # 하단 SPOT NOTE 카드
    draw.rounded_rectangle((76, 898, WIDTH - 76, 1214), radius=24, fill=C_WHITE, outline=C_BORDER, width=2)
    draw.rounded_rectangle((112, 928, 120, 962), radius=4, fill=C_SKY_ACCENT)
    draw.text((136, 932), "SPOT NOTE", font=fonts.get("bold", 22), fill=C_OCEAN)

    body_lines, body_font, body_gap = fit_wrapped_text(
        draw,
        spot_text,
        fonts,
        "medium",
        WIDTH - 224,
        152,
        start_size=31,
        min_size=23,
        line_gap=13,
    )
    draw_lines(draw, 112, 984, body_lines, body_font, C_INK, line_gap=body_gap)

    credit = "사진 제공: 한국관광공사 국문 관광정보"
    f_credit = fonts.get("regular", 19)
    cw = draw.textlength(credit, font=f_credit)
    draw.text((WIDTH - 112 - cw, 1168), credit, font=f_credit, fill=C_MUTED)

    _draw_ocean_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_route_map(
    bundle: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 9,
    total_pages: int = 10,
    section_no: str = "04",
) -> None:
    """스펙·GPX·고도 통합 카드: 거리·시간·난이도 3열 + 오션 GPX 지도 + 스카이 고도 다이어그램."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (*C_SKY_BG, 255))
    draw = ImageDraw.Draw(img)

    draw.text((76, 66), f"{section_no} · ROUTE & ELEVATION", font=fonts.get("bold", 22), fill=C_OCEAN)
    draw.text((76, 102), "코스 스펙 · 궤적 & 고도", font=fonts.get("bold", 46), fill=C_INK)

    # 상단 핵심 스펙 3열 흰색 카드
    spec_top, spec_bottom = 178, 282
    draw.rounded_rectangle((76, spec_top, WIDTH - 76, spec_bottom), radius=22, fill=C_WHITE, outline=C_BORDER, width=2)
    specs = [
        ("DISTANCE", bundle["distance_text"]),
        ("DURATION", bundle["duration_text"]),
        ("LEVEL", bundle["level_label"]),
    ]
    col_w = (WIDTH - 152) // 3
    f_spec_lbl = fonts.get("bold", 18)
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
        draw.text((cx - vw / 2, spec_top + 50), val, font=val_font, fill=C_OCEAN if i == 0 else C_OCEAN_DARK)

    # 중앙 GPX 지도 카드
    draw.rounded_rectangle((76, 304, WIDTH - 76, 816), radius=26, fill=C_WHITE, outline=C_BORDER, width=2)

    inner = (130, 362, WIDTH - 130, 740)
    for gx in range(inner[0], inner[2] + 1, 130):
        draw.line((gx, inner[1] - 14, gx, inner[3] + 14), fill=C_GRID, width=2)
    for gy in range(inner[1], inner[3] + 1, 100):
        draw.line((inner[0] - 14, gy, inner[2] + 14, gy), fill=C_GRID, width=2)

    gpx = bundle.get("gpx") or {}
    points = gpx.get("points") or []
    coords = project_gpx_points(points, inner, max_points=260)

    if len(coords) >= 2:
        overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        odraw.line(coords, fill=(14, 165, 233, 60), width=14, joint="curve")
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
        draw.line(coords, fill=C_OCEAN, width=7, joint="curve")
        sx, sy = coords[0]
        ex, ey = coords[-1]
        draw.ellipse((sx - 18, sy - 18, sx + 18, sy + 18), fill=C_SKY_ACCENT, outline=C_WHITE, width=4)
        draw.ellipse((ex - 18, ey - 18, ex + 18, ey + 18), fill=C_OCEAN_DARK, outline=C_WHITE, width=4)
        draw.text((sx - 7, sy - 12), "S", font=fonts.get("bold", 20), fill=C_WHITE)
        draw.text((ex - 6, ey - 12), "E", font=fonts.get("bold", 20), fill=C_WHITE)
    else:
        msg = "GPX 경로 데이터가 제공되지 않는 코스입니다."
        mw = draw.textlength(msg, font=fonts.get("medium", 28))
        draw.text(((WIDTH - mw) / 2, 535), msg, font=fonts.get("medium", 28), fill=C_MUTED)

    f_badge = fonts.get("bold", 21)
    cycle_str = f"{bundle['cycle_type']} · {bundle['distance_text']}"
    cw = int(draw.textlength(cycle_str, font=f_badge)) + 36
    draw_pill(draw, WIDTH - 104 - cw, 324, cycle_str, f_badge, C_BLUE_SOFT, C_OCEAN, pad_x=18, pad_y=8)

    f_legend = fonts.get("medium", 21)
    draw.ellipse((116, 772, 134, 790), fill=C_SKY_ACCENT)
    draw.text((144, 768), "출발(S)", font=f_legend, fill=C_INK)
    draw.ellipse((248, 772, 266, 790), fill=C_OCEAN_DARK)
    draw.text((276, 768), "도착(E)", font=f_legend, fill=C_INK)
    pt_info = f"GPX {gpx.get('point_count', 0):,} PTS"
    pw = draw.textlength(pt_info, font=f_legend)
    draw.text((WIDTH - 110 - pw, 768), pt_info, font=f_legend, fill=C_OCEAN)

    # 하단 고도 다이어그램 카드
    draw.rounded_rectangle((76, 838, WIDTH - 76, 1220), radius=26, fill=C_WHITE, outline=C_BORDER, width=2)
    draw.text((116, 864), "ELEVATION DIAGRAM", font=fonts.get("bold", 22), fill=C_OCEAN)

    eles = [p[2] for p in points if p[2] is not None]
    min_e, max_e, gain_e = gpx.get("min_ele"), gpx.get("max_ele"), gpx.get("elevation_gain")
    stat_str = (
        f"MIN {min_e}m · MAX {max_e}m · GAIN +{gain_e}m"
        if min_e is not None
        else "NO ELEVATION DATA"
    )
    sw = draw.textlength(stat_str, font=fonts.get("bold", 22))
    draw.text((WIDTH - 116 - sw, 864), stat_str, font=fonts.get("bold", 22), fill=C_SKY_ACCENT)

    img = draw_elevation_chart(
        img,
        eles,
        (146, 932, WIDTH - 120, 1164),
        fonts,
        grid_color=C_GRID,
        label_color=C_MUTED,
        line_color=C_SKY_ACCENT,
        fill_rgba=C_SKY_FILL,
    )
    draw = ImageDraw.Draw(img)
    _draw_ocean_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.convert("RGB").save(out_path, format="PNG")


def _render_info(
    bundle: dict[str, Any],
    fonts: FontSet,
    out_path: Path,
    *,
    page_num: int = 10,
    total_pages: int = 10,
    section_no: str = "05",
) -> None:
    """마지막 카드: FIELD CHECKLIST + 딥 오션 저장 CTA 배너."""
    img = Image.new("RGB", (WIDTH, HEIGHT), C_SKY_BG)
    draw = ImageDraw.Draw(img)

    draw.text((76, 76), f"{section_no} · FIELD CHECKLIST", font=fonts.get("bold", 24), fill=C_OCEAN)
    draw.text((76, 118), "출발 전 체크리스트", font=fonts.get("bold", 48), fill=C_INK)

    travel_lines = (bundle.get("traveler_lines") or [])[:7]
    if not travel_lines:
        travel_lines = ["시점 및 종점 대중교통 안내는 두루누비 공식 페이지를 참고해 주세요."]

    info_top, info_bottom = 224, 960
    draw.rounded_rectangle((76, info_top, WIDTH - 76, info_bottom), radius=26, fill=C_WHITE, outline=C_BORDER, width=2)

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
        draw.ellipse((116, iy + 9, 132, iy + 25), fill=C_SKY_ACCENT)
        after_y = draw_lines(draw, 154, iy, wrapped, f_item, C_INK, line_gap=10)
        if idx < len(drawn_items) - 1:
            draw.line((116, after_y + 8, WIDTH - 116, after_y + 8), fill=C_GRID, width=2)

    cta_top, cta_bottom = 996, 1212
    draw.rounded_rectangle(
        (76, cta_top, WIDTH - 76, cta_bottom),
        radius=26,
        fill=C_OCEAN_DARK,
        outline=C_SKY_ACCENT,
        width=2,
    )
    draw.text((118, cta_top + 44), "KEEP THIS GUIDE FOR LATER", font=fonts.get("bold", 21), fill=(125, 211, 252))
    draw.text((118, cta_top + 92), "이 코스가 마음에 들었다면 저장해 두세요", font=fonts.get("bold", 32), fill=C_WHITE)

    pill_x, pill_y = WIDTH - 270, cta_top + 84
    draw.rounded_rectangle((pill_x, pill_y, pill_x + 154, pill_y + 58), radius=29, fill=C_SKY_ACCENT)
    draw.text((pill_x + 26, pill_y + 14), "SAVE", font=fonts.get("bold", 25), fill=C_WHITE)
    draw_bookmark_icon(draw, pill_x + 112, pill_y + 16, w=18, h=26, fill=C_WHITE)

    _draw_ocean_footer(
        draw,
        fonts,
        page_num,
        left_text=get_footer_source_text(bundle),
        total_pages=total_pages,
    )
    img.save(out_path, format="PNG")


def render_ocean_slides(
    bundle: dict[str, Any], copy: dict[str, Any], fonts: FontSet, out_dir: Path
) -> list[Path]:
    """오션 브리즈(ocean) 스타일 최대 10장 슬라이드(표지>볼거리>핵심매력>사진>스펙·GPX>교통·저장)를 생성한다."""
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
            lambda p, tp=total_pages: _render_cover(bundle, copy, fonts, p, total_pages=tp),
        ),
        (
            "slide_02_spots.png",
            lambda p, tp=total_pages: _render_spots(bundle, fonts, p, page_num=2, total_pages=tp),
        ),
        (
            "slide_03_highlights.png",
            lambda p, tp=total_pages: _render_highlights(bundle, copy, fonts, p, page_num=3, total_pages=tp),
        ),
    ]
    for k, item in enumerate(photo_spots, start=1):
        pg = 3 + k
        specs.append(
            (
                f"slide_{pg:02d}_photo_{k:02d}.png",
                lambda p, it=item, si=k, st=spot_total, pn=pg, tp=total_pages: _render_spot_photo(
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
                lambda p, pn=route_pg, tp=total_pages, sec=route_sec: _render_route_map(
                    bundle, fonts, p, page_num=pn, total_pages=tp, section_no=sec
                ),
            ),
            (
                f"slide_{info_pg:02d}_info.png",
                lambda p, pn=info_pg, tp=total_pages, sec=info_sec: _render_info(
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
