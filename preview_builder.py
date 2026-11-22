"""생성된 카드뉴스와 캡션을 실제 인스타그램 모바일 피드 및 스타일 비교 형태로 미리 보는 HTML 생성기."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import config
from card_renderer import STYLE_META


def build_instagram_preview(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    slide_paths: list[Path],
    out_dir: Path,
) -> Path:
    """모바일 인스타그램 UI 목업 HTML 파일(instagram_preview.html)을 생성한다."""
    slide_names = [p.name for p in slide_paths]
    caption_escaped = html.escape(copy["full_caption"])
    sigun_escaped = html.escape(bundle["sigun"] or "대한민국")
    course_escaped = html.escape(bundle["course_name"])
    gpx_count = bundle.get("gpx", {}).get("point_count", 0)

    slides_json = json.dumps(slide_names, ensure_ascii=False)
    caption_js = json.dumps(copy["full_caption"], ensure_ascii=False)

    photos_meta = bundle.get("photos") or {}
    cover_cnt = 1 if photos_meta.get("cover") else 0
    spot_cnt = int(photos_meta.get("matched_spot_count") or 0)
    photo_summary = (
        f"커버 {cover_cnt}장 + 스팟 {spot_cnt}장 (KorService2)"
        if photos_meta.get("has_photos")
        else "미연동 (GPX/타이포 폴백)"
    )

    brand_handle = html.escape(config.BRAND_HANDLE)
    brand_avatar = html.escape(config.BRAND_AVATAR_TEXT)

    meta_rows = [
        ("코스 고유번호", bundle["crs_idx"]),
        ("소속 길 / 유형", f"{bundle['route_name']} ({bundle['brd_label']})"),
        ("지역", bundle["sigun"]),
        ("거리 / 소요시간", f"{bundle['distance_text']} / {bundle['duration_text']}"),
        ("난이도 / 순환형태", f"{bundle['level_label']} / {bundle['cycle_type']}"),
        ("GPX 좌표 / 고도", f"{gpx_count:,}개 (최저 {bundle['gpx'].get('min_ele')}m ~ 최고 {bundle['gpx'].get('max_ele')}m)"),
        ("연동 실사 사진", photo_summary),
        ("AI 생성 엔진", copy.get("ai_model", "unknown")),
    ]
    theme_sel = bundle.get("theme_selection") or {}
    if theme_sel:
        t_style = str(theme_sel.get("style") or "")
        t_name = STYLE_META.get(t_style, {}).get("name", t_style)
        t_mode = "자동" if theme_sel.get("mode") == "auto" else ("비교 전체" if theme_sel.get("mode") == "all" else "수동")
        t_reason = str(theme_sel.get("reason") or "").strip()
        theme_desc = f"{t_name} ({t_style} · {t_mode})" + (f" — {t_reason}" if t_reason else "")
        meta_rows.insert(0, ("적용 디자인 컨셉", theme_desc))
    meta_html = "".join(
        f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in meta_rows
    )

    page_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Instagram 미리보기 - {course_escaped}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px 16px 60px;
      background: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
      color: #0f172a;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 20px;
    }}
    .phone-frame {{
      width: 100%;
      max-width: 430px;
      background: #ffffff;
      border: 1px solid #dbdbdb;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 12px 32px rgba(15, 23, 42, 0.10);
    }}
    .ig-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      border-bottom: 1px solid #efefef;
    }}
    .ig-profile {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .ig-avatar {{
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: linear-gradient(135deg, #14342b, #d96b43);
      color: #fff;
      font-weight: 700;
      font-size: 13px;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .ig-user {{ font-size: 14px; font-weight: 700; line-height: 1.2; }}
    .ig-loc {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
    .carousel {{
      position: relative;
      width: 100%;
      aspect-ratio: 4 / 5;
      background: #0f2b23;
      overflow: hidden;
    }}
    .carousel img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .nav-btn {{
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      width: 32px;
      height: 32px;
      border-radius: 50%;
      border: none;
      background: rgba(15, 23, 42, 0.65);
      color: #fff;
      font-size: 18px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .nav-btn.prev {{ left: 10px; }}
    .nav-btn.next {{ right: 10px; }}
    .page-pill {{
      position: absolute;
      top: 12px;
      right: 12px;
      background: rgba(15, 23, 42, 0.72);
      color: #fff;
      font-size: 12px;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
    }}
    .ig-actions {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 14px 4px;
    }}
    .ig-actions-left {{
      display: flex;
      align-items: center;
      gap: 14px;
      font-size: 20px;
    }}
    .icon-btn {{
      background: none;
      border: none;
      cursor: pointer;
      font-size: 20px;
      padding: 2px;
    }}
    .dots {{
      display: flex;
      gap: 5px;
      align-items: center;
    }}
    .dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #cbd5e1;
      cursor: pointer;
    }}
    .dot.active {{ background: #0095f6; width: 7px; height: 7px; }}
    .ig-caption-wrap {{
      padding: 6px 14px 16px;
      font-size: 13.5px;
      line-height: 1.6;
    }}
    .ig-likes {{ font-weight: 700; margin-bottom: 6px; font-size: 13px; }}
    .ig-caption {{ white-space: pre-wrap; word-break: keep-all; color: #1e293b; }}
    .copy-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      background: #f8fafc;
      border-top: 1px solid #efefef;
    }}
    .copy-btn {{
      background: #14342b;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 8px 14px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }}
    .copy-btn:hover {{ background: #1e4b3f; }}
    .meta-panel {{
      width: 100%;
      max-width: 430px;
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 14px;
      padding: 12px 16px;
      font-size: 13px;
    }}
    .meta-panel summary {{
      cursor: pointer;
      font-weight: 700;
      color: #14342b;
    }}
    .meta-panel table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
    }}
    .meta-panel th, .meta-panel td {{
      text-align: left;
      padding: 6px 4px;
      border-bottom: 1px solid #e2e8f0;
      font-size: 12px;
      vertical-align: top;
    }}
    .meta-panel th {{ width: 34%; color: #475569; }}
  </style>
</head>
<body>
  <div class="phone-frame">
    <div class="ig-header">
      <div class="ig-profile">
        <div class="ig-avatar">{brand_avatar}</div>
        <div>
          <div class="ig-user">{brand_handle}</div>
          <div class="ig-loc">{sigun_escaped} · {course_escaped}</div>
        </div>
      </div>
      <span style="font-size:18px;color:#64748b;">•••</span>
    </div>

    <div class="carousel">
      <img id="slide-img" src="{slide_names[0]}" alt="카드뉴스 미리보기" />
      <div class="page-pill" id="page-pill">1 / {len(slide_names)}</div>
      <button class="nav-btn prev" id="prev-btn" aria-label="이전 슬라이드">‹</button>
      <button class="nav-btn next" id="next-btn" aria-label="다음 슬라이드">›</button>
    </div>

    <div class="ig-actions">
      <div class="ig-actions-left">
        <button class="icon-btn" id="like-btn" title="좋아요">🤍</button>
        <span title="댓글">💬</span>
        <span title="공유">✈️</span>
      </div>
      <div class="dots" id="dots"></div>
      <button class="icon-btn" id="save-btn" title="저장">🔖</button>
    </div>

    <div class="ig-caption-wrap">
      <div class="ig-likes" id="likes-text">좋아요 128개</div>
      <div class="ig-caption"><strong>{brand_handle}</strong> {caption_escaped}</div>
    </div>

    <div class="copy-bar">
      <span style="font-size:12px;color:#64748b;">인스타그램 업로드용 캡션</span>
      <button class="copy-btn" id="copy-btn">캡션+태그 복사</button>
    </div>
  </div>

  <details class="meta-panel">
    <summary>두루누비 API & GPX 원본 메타데이터 보기</summary>
    <table><tbody>{meta_html}</tbody></table>
  </details>

  <script>
    const slides = {slides_json};
    const fullCaption = {caption_js};
    let idx = 0;

    const imgEl = document.getElementById("slide-img");
    const pillEl = document.getElementById("page-pill");
    const dotsEl = document.getElementById("dots");

    function renderDots() {{
      dotsEl.innerHTML = "";
      slides.forEach((_, i) => {{
        const d = document.createElement("span");
        d.className = "dot" + (i === idx ? " active" : "");
        d.onclick = () => {{ idx = i; updateSlide(); }};
        dotsEl.appendChild(d);
      }});
    }}

    function updateSlide() {{
      imgEl.src = slides[idx];
      pillEl.textContent = (idx + 1) + " / " + slides.length;
      renderDots();
    }}

    document.getElementById("prev-btn").onclick = () => {{
      idx = (idx - 1 + slides.length) % slides.length;
      updateSlide();
    }};
    document.getElementById("next-btn").onclick = () => {{
      idx = (idx + 1) % slides.length;
      updateSlide();
    }};
    document.addEventListener("keydown", (e) => {{
      if (e.key === "ArrowLeft") document.getElementById("prev-btn").click();
      if (e.key === "ArrowRight") document.getElementById("next-btn").click();
    }});

    document.getElementById("like-btn").onclick = function () {{
      const liked = this.textContent === "❤️";
      this.textContent = liked ? "🤍" : "❤️";
      document.getElementById("likes-text").textContent = liked ? "좋아요 128개" : "좋아요 129개";
    }};

    document.getElementById("copy-btn").onclick = async function () {{
      try {{
        await navigator.clipboard.writeText(fullCaption);
        this.textContent = "복사 완료!";
        setTimeout(() => {{ this.textContent = "캡션+태그 복사"; }}, 1800);
      }} catch (err) {{
        alert("caption.txt 파일에서 복사해 주세요.");
      }}
    }};

    updateSlide();
  </script>
</body>
</html>
"""
    target = out_dir / "instagram_preview.html"
    target.write_text(page_html, encoding="utf-8")
    return target


def build_style_compare_page(
    bundle: dict[str, Any],
    copy: dict[str, Any],
    style_results: dict[str, list[Path]],
    out_dir: Path,
) -> Path:
    """선택된 스타일들을 한 화면에 나란히 비교하는 HTML을 생성한다."""
    course_escaped = html.escape(bundle["course_name"])
    sigun_escaped = html.escape(bundle["sigun"] or "대한민국")
    caption_escaped = html.escape(copy["full_caption"])
    style_count = len(style_results)
    container_max_width = "980px" if style_count == 2 else "1360px"

    cards_config: list[dict[str, Any]] = []
    cards_html = ""
    first_paths: list[Path] = next(iter(style_results.values()), [])

    def _slide_btn_label(idx: int, path: Path) -> str:
        name = path.stem
        if "cover" in name:
            return f"{idx + 1}. 표지"
        if "route_map" in name:
            return f"{idx + 1}. 스펙·GPX"
        if "spots" in name:
            return f"{idx + 1}. 볼거리"
        m = re.search(r"photo_(\d+)", name)
        if m:
            return f"{idx + 1}. 사진 {int(m.group(1))}"
        if "highlights" in name:
            return f"{idx + 1}. 핵심 매력"
        if "info" in name:
            return f"{idx + 1}. 교통·저장"
        return f"{idx + 1}번"

    sync_buttons_html = "\n      ".join(
        f'<button class="sync-btn{" active" if i == 0 else ""}" data-slide="{i}">{html.escape(_slide_btn_label(i, p))}</button>'
        for i, p in enumerate(first_paths)
    )
    for style_key, paths in style_results.items():
        meta = STYLE_META.get(style_key, {"name": style_key, "desc": ""})
        rel_slides = [f"{style_key}/{p.name}" for p in paths]
        cards_config.append({"key": style_key, "slides": rel_slides})
        cards_html += f"""
        <div class="compare-col" data-style="{html.escape(style_key)}">
          <div class="style-badge-bar">
            <div>
              <div class="style-name">{html.escape(meta['name'])} <span class="style-code">({html.escape(style_key)})</span></div>
              <div class="style-desc">{html.escape(meta['desc'])}</div>
            </div>
            <a class="open-link" href="{html.escape(style_key)}/instagram_preview.html" target="_blank">단독 보기 ↗</a>
          </div>
          <div class="phone-frame">
            <div class="ig-header">
              <div class="ig-profile">
                <div class="ig-avatar">{html.escape(config.BRAND_AVATAR_TEXT)}</div>
                <div>
                  <div class="ig-user">{html.escape(config.BRAND_HANDLE)}</div>
                  <div class="ig-loc">{sigun_escaped} · {course_escaped}</div>
                </div>
              </div>
              <span style="font-size:16px;color:#64748b;">•••</span>
            </div>
            <div class="carousel">
              <img class="slide-img" src="{html.escape(rel_slides[0])}" alt="{html.escape(meta['name'])}" />
              <div class="page-pill">1 / {len(rel_slides)}</div>
              <button class="nav-btn prev" aria-label="이전">‹</button>
              <button class="nav-btn next" aria-label="다음">›</button>
            </div>
            <div class="ig-actions">
              <span>🤍 💬 ✈️</span>
              <div class="dots"></div>
              <span>🔖</span>
            </div>
            <div class="ig-caption-preview">
              <strong>{html.escape(config.BRAND_HANDLE)}</strong> {html.escape(copy['hook_line'])} …
            </div>
          </div>
        </div>
        """

    config_json = json.dumps(cards_config, ensure_ascii=False)
    compare_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>스타일 비교 - {course_escaped}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 28px 24px 56px;
      background: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
      color: #0f172a;
    }}
    .top-bar {{
      max-width: {container_max_width};
      margin: 0 auto 24px;
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 16px;
      padding: 18px 22px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }}
    .top-title {{ font-size: 20px; font-weight: 800; }}
    .top-sub {{ font-size: 13px; color: #64748b; margin-top: 4px; }}
    .sync-controls {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
    }}
    .sync-btn {{
      border: 1px solid #cbd5e1;
      background: #f8fafc;
      color: #0f172a;
      padding: 8px 13px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }}
    .sync-btn.active {{
      background: #14342b;
      color: #ffffff;
      border-color: #14342b;
    }}
    .grid {{
      max-width: {container_max_width};
      margin: 0 auto;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 22px;
    }}
    .compare-col {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .style-badge-bar {{
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 12px;
      padding: 12px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .style-name {{ font-size: 15px; font-weight: 700; }}
    .style-code {{ font-size: 12px; color: #64748b; font-weight: 500; }}
    .style-desc {{ font-size: 12px; color: #475569; margin-top: 3px; }}
    .open-link {{
      font-size: 12px;
      font-weight: 600;
      color: #1d4ed8;
      text-decoration: none;
      white-space: nowrap;
    }}
    .phone-frame {{
      background: #ffffff;
      border: 1px solid #dbdbdb;
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }}
    .ig-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      border-bottom: 1px solid #efefef;
    }}
    .ig-profile {{ display: flex; align-items: center; gap: 8px; }}
    .ig-avatar {{
      width: 32px; height: 32px; border-radius: 50%;
      background: linear-gradient(135deg, #14342b, #d96b43);
      color: #fff; font-weight: 700; font-size: 12px;
      display: flex; align-items: center; justify-content: center;
    }}
    .ig-user {{ font-size: 13px; font-weight: 700; }}
    .ig-loc {{ font-size: 11px; color: #64748b; }}
    .carousel {{
      position: relative;
      width: 100%;
      aspect-ratio: 4 / 5;
      background: #0f172a;
    }}
    .carousel img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .nav-btn {{
      position: absolute; top: 50%; transform: translateY(-50%);
      width: 30px; height: 30px; border-radius: 50%; border: none;
      background: rgba(15, 23, 42, 0.65); color: #fff; font-size: 17px;
      cursor: pointer; display: flex; align-items: center; justify-content: center;
    }}
    .nav-btn.prev {{ left: 8px; }}
    .nav-btn.next {{ right: 8px; }}
    .page-pill {{
      position: absolute; top: 10px; right: 10px;
      background: rgba(15, 23, 42, 0.72); color: #fff;
      font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 999px;
    }}
    .ig-actions {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 12px 4px; font-size: 16px;
    }}
    .dots {{ display: flex; gap: 4px; }}
    .dot {{ width: 6px; height: 6px; border-radius: 50%; background: #cbd5e1; cursor: pointer; }}
    .dot.active {{ background: #0095f6; }}
    .ig-caption-preview {{
      padding: 4px 12px 14px;
      font-size: 12.5px;
      color: #334155;
      line-height: 1.5;
    }}
    .caption-box {{
      max-width: {container_max_width};
      margin: 22px auto 0;
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 14px;
      padding: 16px 20px;
      font-size: 13px;
      line-height: 1.65;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <div class="top-bar">
    <div>
      <div class="top-title">인스타그램 카드뉴스 {style_count}종 스타일 비교 — {course_escaped}</div>
      <div class="top-sub">상단 버튼으로 {style_count}가지 스타일의 같은 페이지를 동시에 비교하거나, 각 카드 좌우 화살표로 개별 확인하세요.</div>
    </div>
    <div class="sync-controls">
      <span style="font-size:12px;color:#64748b;">동시 이동:</span>
      {sync_buttons_html}
    </div>
  </div>

  <div class="grid">{cards_html}</div>

  <div class="caption-box"><strong>공통 캡션 미리보기:</strong><br /><br />{caption_escaped}</div>

  <script>
    const configs = {config_json};
    const controllers = [];

    configs.forEach((cfg) => {{
      const col = document.querySelector('.compare-col[data-style="' + cfg.key + '"]');
      const img = col.querySelector(".slide-img");
      const pill = col.querySelector(".page-pill");
      const dotsWrap = col.querySelector(".dots");
      let idx = 0;

      function update() {{
        img.src = cfg.slides[idx];
        pill.textContent = (idx + 1) + " / " + cfg.slides.length;
        dotsWrap.innerHTML = "";
        cfg.slides.forEach((_, i) => {{
          const d = document.createElement("span");
          d.className = "dot" + (i === idx ? " active" : "");
          d.onclick = () => {{ idx = i; update(); }};
          dotsWrap.appendChild(d);
        }});
      }}

      col.querySelector(".prev").onclick = () => {{
        idx = (idx - 1 + cfg.slides.length) % cfg.slides.length;
        update();
      }};
      col.querySelector(".next").onclick = () => {{
        idx = (idx + 1) % cfg.slides.length;
        update();
      }};
      update();
      controllers.push((targetIdx) => {{ idx = targetIdx; update(); }});
    }});

    let syncIdx = 0;
    const totalSlides = configs.length > 0 ? configs[0].slides.length : 0;

    function setSyncSlide(targetIdx) {{
      if (totalSlides <= 0) return;
      syncIdx = (targetIdx + totalSlides) % totalSlides;
      document.querySelectorAll(".sync-btn").forEach((b) => {{
        b.classList.toggle("active", Number(b.getAttribute("data-slide")) === syncIdx);
      }});
      controllers.forEach((fn) => fn(syncIdx));
    }}

    document.querySelectorAll(".sync-btn").forEach((btn) => {{
      btn.onclick = function () {{
        setSyncSlide(Number(this.getAttribute("data-slide")));
      }};
    }});

    document.addEventListener("keydown", (e) => {{
      if (e.key === "ArrowLeft") setSyncSlide(syncIdx - 1);
      if (e.key === "ArrowRight") setSyncSlide(syncIdx + 1);
    }});
  </script>
</body>
</html>
"""
    target = out_dir / "style_compare.html"
    target.write_text(compare_html, encoding="utf-8")
    return target
