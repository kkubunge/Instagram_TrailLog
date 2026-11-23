"""두루누비 API 기반 인스타그램 카드뉴스 & 캡션 미리보기 생성 CLI."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import config
from caption_writer import generate_instagram_copy
from card_renderer import COMPARE_STYLES, STYLE_META, render_carousel_cards
from durunubi_api import DurunubiClient
from instagram_publisher import (
    InstagramCarouselPublisher,
    count_published_today_kst,
    load_published_history,
    minutes_since_last_publish,
)
from preview_builder import build_instagram_preview, build_style_compare_page
from theme_selector import select_theme_style
from tour_photo_api import TourPhotoClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("traillog")


def _sanitize_dirname(name: str) -> str:
    """폴더 이름에 사용할 수 없는 문자를 언더스코어로 치환한다."""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")[:50] or "course"


def _interleave_courses_by_route(
    courses: list[dict[str, object]],
    route_map: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    """노선(DMZ 평화의 길 · 해파랑길 · 남파랑길 · 서해랑길 등)별로 코스를 번갈아 정렬한다."""
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in courses:
        r_idx = str(item.get("routeIdx") or "").strip() or "_unknown"
        grouped.setdefault(r_idx, []).append(item)

    def _route_priority(r_idx: str) -> tuple[int, str]:
        name = str((route_map.get(r_idx) or {}).get("themeNm") or "")
        for order, kw in enumerate(("DMZ", "해파랑길", "남파랑길", "서해랑길")):
            if kw in name:
                return (order, r_idx)
        return (99, r_idx)

    ordered_keys = sorted(grouped.keys(), key=_route_priority)
    result: list[dict[str, object]] = []
    idx = 0
    while True:
        added = False
        for key in ordered_keys:
            bucket = grouped[key]
            if idx < len(bucket):
                result.append(bucket[idx])
                added = True
        if not added:
            break
        idx += 1
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """커맨드라인 인자를 파싱한다."""
    parser = argparse.ArgumentParser(
        description="한국관광공사 두루누비 API 기반 인스타그램 카드뉴스 미리보기 생성기"
    )
    parser.add_argument(
        "--brd",
        default="걷기",
        help="여행 구분 (걷기/도보/DNWW 또는 자전거/라이딩/DNBW, 기본값: 걷기)",
    )
    parser.add_argument("--keyword", default=None, help="코스명 검색 키워드 (예: 남파랑길, 해파랑길)")
    parser.add_argument(
        "--level",
        choices=("1", "2", "3"),
        default=None,
        help="코스 난이도 (1: 쉬움, 2: 보통, 3: 어려움)",
    )
    parser.add_argument(
        "--style",
        choices=("auto", "forest", "ocean", "all"),
        default="auto",
        help="카드뉴스 디자인 스타일 (auto: API 분석 자동 선택(숲·산→forest / 바다→ocean), forest: 포레스트, ocean: 오션 브리즈, all: 2종 전체 생성 및 비교)",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=1,
        help="조회된 코스 목록에서 시작할 순번 (1부터 시작, 기본값: 1)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="생성할 코스 카드뉴스 세트 개수 (기본값: 1)",
    )
    parser.add_argument(
        "--no-photos",
        action="store_true",
        help="한국관광공사 국문 관광정보(KorService2) 실사 사진 연동을 비활성화",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="카드뉴스 생성 후 @trailllog 인스타그램에 캐러셀로 자동 업로드",
    )
    parser.add_argument(
        "--dry-run-publish",
        action="store_true",
        help="실제 인스타그램 업로드 없이 JPEG 변환·계정·저장소 사전 검증만 수행",
    )
    parser.add_argument(
        "--skip-published",
        action="store_true",
        help="published_history.json에 이미 게시된 코스는 건너뛰고 미게시 코스부터 선택",
    )
    parser.add_argument(
        "--force-publish",
        action="store_true",
        help="이미 게시 이력이 있는 코스도 강제로 재게시",
    )
    parser.add_argument(
        "--cleanup-media",
        action="store_true",
        help="인스타그램 게시 완료 후 GitHub 미디어 브랜치의 업로드 이미지 정리",
    )
    parser.add_argument(
        "--round-robin",
        action="store_true",
        help="미게시 코스를 노선별(DMZ·해파랑길·남파랑길·서해랑길)로 번갈아 선택",
    )
    parser.add_argument(
        "--max-daily",
        type=int,
        default=0,
        help="하루(KST) 최대 게시 건수 제한 (0이면 제한 없음, --publish 시 적용)",
    )
    parser.add_argument(
        "--min-interval-minutes",
        type=int,
        default=0,
        help="직전 게시로부터 최소 경과 시간(분) 미달 시 자동 건너뜀 (0이면 제한 없음, --publish 시 적용)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """두루누비 코스를 수집해 선택한 스타일의 카드뉴스, 캡션, 미리보기 HTML을 생성한다."""
    args = parse_args(argv)
    brd_div = config.resolve_brd_div(args.brd)

    target_count = max(1, args.count)
    if args.publish and args.max_daily > 0:
        today_count = count_published_today_kst()
        if today_count >= args.max_daily:
            print(
                f"오늘(KST) 이미 {today_count}건 게시되어 일일 상한({args.max_daily}건)에 도달했습니다. 작업을 종료합니다."
            )
            return 0
        target_count = min(target_count, args.max_daily - today_count)
    if args.publish and args.min_interval_minutes > 0 and not args.force_publish:
        elapsed_min = minutes_since_last_publish()
        if elapsed_min is not None and elapsed_min < args.min_interval_minutes:
            print(
                f"최근 게시 후 {elapsed_min:.1f}분 경과해 최소 간격({args.min_interval_minutes}분) "
                "미달이므로 이번 회차를 건너뜁니다."
            )
            return 0

    client = DurunubiClient()
    routes = client.get_route_list(brd_div=brd_div, num_of_rows=100)
    route_map = {str(r.get("routeIdx", "")): r for r in routes if r.get("routeIdx")}

    start_idx = max(1, args.index)
    fetch_count = start_idx - 1 + target_count
    published_ids: set[str] = set()
    if args.skip_published:
        history = load_published_history()
        published_ids = {
            str(item.get("crs_idx") or "")
            for item in history.get("published", [])
            if isinstance(item, dict) and item.get("crs_idx")
        }

    collect_all_for_rr = bool(args.round_robin and not args.keyword)
    courses: list[dict[str, object]] = []
    if args.skip_published or collect_all_for_rr:
        page_no = 1
        while page_no <= 10 and (collect_all_for_rr or len(courses) < fetch_count):
            batch = client.get_course_list(
                crs_kor_nm=args.keyword,
                crs_level=args.level,
                brd_div=brd_div,
                num_of_rows=100,
                page_no=page_no,
            )
            if not batch:
                break
            for item in batch:
                if args.skip_published and str(item.get("crsIdx") or "").strip() in published_ids:
                    continue
                courses.append(item)
            if len(batch) < 100:
                break
            page_no += 1
    else:
        courses = client.get_course_list(
            crs_kor_nm=args.keyword,
            crs_level=args.level,
            brd_div=brd_div,
            num_of_rows=max(20, fetch_count),
            page_no=1,
        )

    if args.round_robin and courses:
        courses = _interleave_courses_by_route(courses, route_map)

    if not courses:
        print("조건에 해당하는 두루누비 코스를 찾지 못했습니다.")
        return 1

    targets = courses[start_idx - 1 : start_idx - 1 + target_count]
    if not targets:
        print(f"요청한 순번({start_idx})에 해당하는 코스가 없습니다. (조회 건수: {len(courses)}건)")
        return 1

    publisher: InstagramCarouselPublisher | None = None
    if args.publish or args.dry_run_publish:
        publisher = InstagramCarouselPublisher()

    for i, course in enumerate(targets, start=1):
        logger.info("[%d/%d] 코스 데이터 및 GPX 수집 중: %s", i, len(targets), course.get("crsKorNm"))
        bundle = client.get_course_bundle(course, route_map=route_map)

        auto_style, theme_info = select_theme_style(bundle)
        if args.style == "auto":
            styles_to_render = [auto_style]
            bundle["theme_selection"] = theme_info
        elif args.style == "all":
            styles_to_render = list(COMPARE_STYLES)
            bundle["theme_selection"] = {**theme_info, "mode": "all"}
        else:
            styles_to_render = [args.style]
            bundle["theme_selection"] = {
                **theme_info,
                "style": args.style,
                "mode": "manual",
                "auto_recommended": auto_style,
            }

        folder_name = f"{bundle['crs_idx']}_{_sanitize_dirname(bundle['course_name'])}"
        out_dir = config.OUTPUT_DIR / folder_name
        out_dir.mkdir(parents=True, exist_ok=True)

        photos_info: dict[str, object] = {
            "has_photos": False,
            "cover": None,
            "spot_items": [],
            "matched_spot_count": 0,
        }
        if not args.no_photos:
            try:
                logger.info("[%d/%d] KorService2 관광사진 수집 중...", i, len(targets))
                photos_info = TourPhotoClient().collect_course_photos(bundle, out_dir / "photos")
            except Exception as exc:
                logger.warning("관광사진 수집 생략(기존 레이아웃 폴백): %s", exc)
        bundle["photos"] = photos_info

        copy = generate_instagram_copy(bundle)

        caption_path = out_dir / "caption.txt"
        caption_path.write_text(copy["full_caption"], encoding="utf-8")

        export_bundle = {
            k: v for k, v in bundle.items() if k not in ("gpx", "raw_course", "raw_route")
        }
        export_bundle["gpx_summary"] = {
            k: v for k, v in bundle["gpx"].items() if k != "points"
        }
        export_bundle["copy"] = copy
        (out_dir / "course_data.json").write_text(
            json.dumps(export_bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        cover_cnt = 1 if photos_info.get("cover") else 0
        spot_cnt = int(photos_info.get("matched_spot_count") or 0)
        theme_sel = bundle["theme_selection"]
        applied_style = str(theme_sel["style"])
        applied_name = STYLE_META.get(applied_style, {}).get("name", applied_style)
        print(f"\n[{i}/{len(targets)}] 인스타그램 카드뉴스 생성 완료 (엔진: {copy['ai_model']})")
        print(f"- 코스명: {bundle['course_name']} ({bundle['sigun']} · {bundle['brd_label']})")
        if args.style == "auto":
            print(f"- 적용 컨셉: {applied_name} ({applied_style}, 자동 판별 — {theme_info['reason']})")
        elif args.style == "all":
            auto_name = STYLE_META.get(auto_style, {}).get("name", auto_style)
            print(f"- 적용 컨셉: 2종 비교 (자동 판별 추천: {auto_name}({auto_style}) — {theme_info['reason']})")
        else:
            print(f"- 적용 컨셉: {applied_name} ({applied_style}, 수동 지정 · 자동 추천: {auto_style})")
        print(f"- 연동 사진: 커버 {cover_cnt}장 + 스팟 {spot_cnt}장")
        print(f"- 출력 폴더: {out_dir}")
        print(f"- 캡션 파일: {caption_path}")

        if args.style == "all":
            style_results: dict[str, list[Path]] = {}
            for st in styles_to_render:
                st_dir = out_dir / st
                slide_paths = render_carousel_cards(bundle, copy, st_dir, style=st)
                build_instagram_preview(bundle, copy, slide_paths, st_dir)
                style_results[st] = slide_paths
                print(f"- [{st}] 슬라이드 {len(slide_paths)}장 생성: {st_dir}")
            compare_html = build_style_compare_page(bundle, copy, style_results, out_dir)
            print(f"- {len(style_results)}종 스타일 비교 HTML: {compare_html}")
            publish_style = auto_style
            publish_slides = style_results[auto_style]
        else:
            st = styles_to_render[0]
            slide_paths = render_carousel_cards(bundle, copy, out_dir, style=st)
            preview_html = build_instagram_preview(bundle, copy, slide_paths, out_dir)
            print(f"- 스타일: {st}")
            print(f"- 미리보기 HTML: {preview_html}")
            print(f"- 슬라이드 {len(slide_paths)}장: {', '.join(p.name for p in slide_paths)}")
            publish_style = st
            publish_slides = slide_paths

        if publisher is not None:
            pub_res = publisher.publish_slides(
                publish_slides,
                copy["full_caption"],
                course_key=folder_name,
                course_name=bundle["course_name"],
                style=publish_style,
                crs_idx=bundle["crs_idx"],
                dry_run=args.dry_run_publish and not args.publish,
                force=args.force_publish,
                cleanup_media=args.cleanup_media,
            )
            if pub_res.get("status") == "published":
                (out_dir / "publish_result.json").write_text(
                    json.dumps(pub_res, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"- 인스타그램 게시 완료: {pub_res.get('permalink') or pub_res.get('media_id')}")
            else:
                acc = pub_res.get("account") or {}
                quota = pub_res.get("quota") or {}
                print(
                    f"- 인스타그램 게시 사전 검증(dry-run) 통과: @{acc.get('username')} | "
                    f"{pub_res.get('slide_count')}장 ({pub_res.get('total_jpeg_kb')} KB) | "
                    f"남은 일일 한도 {quota.get('remaining')}/{quota.get('total')}"
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
