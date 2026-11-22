"""GitHub 공개 이미지 호스팅 및 Instagram Graph API 캐러셀 자동 업로드 모듈."""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image

import card_common
import config

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
MAX_IG_CAPTION_LEN = 2200


class InstagramPublishError(RuntimeError):
    """인스타그램 게시 또는 공개 이미지 호스팅 중 오류 발생 시 사용하는 예외."""


def load_published_history(history_path: Path | None = None) -> dict[str, Any]:
    """게시 이력 JSON 파일을 읽어 딕셔너리로 반환한다."""
    target = history_path or config.PUBLISHED_HISTORY_FILE
    if not target.exists():
        return {"published": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("published"), list):
            return data
    except Exception as exc:
        logger.warning("게시 이력 파일 파싱 실패(%s): %s", target, exc)
    return {"published": []}


def save_published_history(
    history: dict[str, Any], history_path: Path | None = None
) -> None:
    """게시 이력 JSON 파일을 저장한다."""
    target = history_path or config.PUBLISHED_HISTORY_FILE
    target.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_course_published(crs_idx: str, history_path: Path | None = None) -> bool:
    """해당 코스 고유번호(crs_idx)가 이미 게시되었는지 확인한다."""
    if not crs_idx:
        return False
    history = load_published_history(history_path)
    return any(
        str(item.get("crs_idx") or "") == crs_idx
        for item in history.get("published", [])
        if isinstance(item, dict)
    )


def record_published_course(
    entry: dict[str, Any], history_path: Path | None = None
) -> None:
    """새로 게시된 코스 이력을 published_history.json에 추가한다."""
    history = load_published_history(history_path)
    items = [x for x in history.get("published", []) if isinstance(x, dict)]
    items.append(entry)
    history["published"] = items
    save_published_history(history, history_path)


def convert_slide_to_jpeg_bytes(image_path: Path, quality: int = 92) -> bytes:
    """Meta Graph API 요구 형식에 맞게 슬라이드 이미지를 RGB JPEG 바이트로 변환한다."""
    with Image.open(image_path) as im:
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            rgba = im.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            rgb = bg
        else:
            rgb = im.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()


def _sanitize_slug(text: str) -> str:
    """원격 경로에 안전하게 사용할 수 있는 경로 세그먼트를 생성한다."""
    cleaned = re.sub(r"[^0-9A-Za-z가-힣_\-]+", "_", str(text or "")).strip("_")
    return cleaned[:60] or "course"


def _trim_caption(caption: str) -> str:
    """인스타그램 최대 캡션 길이(2,200자)를 초과하면 안전하게 자른다."""
    text = str(caption or "").strip()
    if len(text) <= MAX_IG_CAPTION_LEN:
        return text
    return text[: MAX_IG_CAPTION_LEN - 1].rstrip() + "…"


class GitHubMediaHost:
    """Meta Graph API가 이미지를 가져갈 수 있도록 GitHub 공개 브랜치에 JPEG를 호스팅한다."""

    def __init__(
        self,
        token: str | None = None,
        repo: str | None = None,
        branch: str | None = None,
        timeout: int = 20,
    ) -> None:
        self.token = (token or config.GITHUB_TOKEN).strip()
        self.repo = (repo or config.GITHUB_REPO).strip().strip("/")
        self.branch = (branch or config.GITHUB_MEDIA_BRANCH).strip()
        self.timeout = timeout
        if not self.token:
            raise InstagramPublishError("GITHUB_TOKEN이 설정되어 있지 않습니다.")
        if not self.repo or "/" not in self.repo:
            raise InstagramPublishError(
                f"GITHUB_REPO 형식이 올바르지 않습니다: '{self.repo}'"
            )
        self.api_base = f"https://api.github.com/repos/{self.repo}"
        self.session = config.create_http_session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._public_session = config.create_http_session()

    def _encode_path(self, remote_path: str) -> str:
        """슬래시 구분자를 유지하면서 경로 세그먼트만 URL 인코딩한다."""
        parts = [p for p in remote_path.strip("/").split("/") if p]
        return "/".join(quote(p, safe="") for p in parts)

    def verify_repo(self) -> dict[str, Any]:
        """대상 GitHub 저장소 존재 여부 및 Public 공개 상태를 확인한다."""
        resp = self.session.get(self.api_base, timeout=self.timeout)
        if resp.status_code != 200:
            raise InstagramPublishError(
                f"GitHub 저장소 조회 실패 ({self.repo}): HTTP {resp.status_code} {resp.text[:160]}"
            )
        data = resp.json()
        if data.get("private"):
            raise InstagramPublishError(
                f"저장소 '{self.repo}'가 Private 상태입니다. Meta API가 이미지 URL을 가져가려면 Public 저장소여야 합니다."
            )
        return {
            "full_name": data.get("full_name"),
            "private": bool(data.get("private")),
            "default_branch": data.get("default_branch") or "main",
            "media_branch": self.branch,
        }

    def ensure_branch(self) -> str:
        """미디어 호스팅 브랜치가 존재하지 않으면 기본 브랜치에서 자동 생성한다."""
        ref_url = f"{self.api_base}/git/ref/heads/{quote(self.branch, safe='')}"
        resp = self.session.get(ref_url, timeout=self.timeout)
        if resp.status_code == 200:
            return resp.json()["object"]["sha"]

        if resp.status_code != 404:
            raise InstagramPublishError(
                f"미디어 브랜치({self.branch}) 확인 실패: HTTP {resp.status_code} {resp.text[:160]}"
            )

        repo_info = self.verify_repo()
        default_branch = repo_info["default_branch"]
        base_ref_url = f"{self.api_base}/git/ref/heads/{quote(default_branch, safe='')}"
        base_resp = self.session.get(base_ref_url, timeout=self.timeout)
        if base_resp.status_code != 200:
            raise InstagramPublishError(
                f"기본 브랜치({default_branch}) 커밋 SHA 조회 실패: HTTP {base_resp.status_code} {base_resp.text[:160]}"
            )
        base_sha = base_resp.json()["object"]["sha"]

        create_url = f"{self.api_base}/git/refs"
        create_resp = self.session.post(
            create_url,
            json={"ref": f"refs/heads/{self.branch}", "sha": base_sha},
            timeout=self.timeout,
        )
        if create_resp.status_code not in (200, 201):
            raise InstagramPublishError(
                f"미디어 브랜치({self.branch}) 생성 실패: HTTP {create_resp.status_code} {create_resp.text[:160]}"
            )
        logger.info("GitHub 미디어 호스팅 브랜치 생성 완료: %s", self.branch)
        return base_sha

    def _get_file_sha(self, encoded_path: str) -> str | None:
        """특정 브랜치 경로에 기존 파일이 있을 경우 blob SHA를 반환한다."""
        url = f"{self.api_base}/contents/{encoded_path}"
        resp = self.session.get(url, params={"ref": self.branch}, timeout=self.timeout)
        if resp.status_code == 200 and isinstance(resp.json(), dict):
            return resp.json().get("sha")
        return None

    def upload_jpeg_bytes(
        self, remote_path: str, jpeg_bytes: bytes, message: str
    ) -> str:
        """JPEG 바이트를 GitHub 미디어 브랜치에 업로드하고 검증된 공개 raw URL을 반환한다."""
        encoded_path = self._encode_path(remote_path)
        api_url = f"{self.api_base}/contents/{encoded_path}"

        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(jpeg_bytes).decode("ascii"),
            "branch": self.branch,
        }
        existing_sha = self._get_file_sha(encoded_path)
        if existing_sha:
            payload["sha"] = existing_sha

        resp = self.session.put(api_url, json=payload, timeout=self.timeout)
        if resp.status_code not in (200, 201):
            raise InstagramPublishError(
                f"GitHub 이미지 업로드 실패 ({remote_path}): HTTP {resp.status_code} {resp.text[:200]}"
            )

        raw_url = (
            f"https://raw.githubusercontent.com/{self.repo}/"
            f"{quote(self.branch, safe='')}/{encoded_path}"
        )

        # CDN 전파 지연을 고려해 비인증 공개 URL 접근 가능 여부를 사전 검증
        last_status = 0
        for attempt in range(3):
            if attempt > 0:
                time.sleep(1.5)
            pub_resp = self._public_session.get(raw_url, timeout=self.timeout)
            last_status = pub_resp.status_code
            ctype = (pub_resp.headers.get("Content-Type") or "").lower()
            if last_status == 200 and len(pub_resp.content) > 0 and (
                "image" in ctype or "octet-stream" in ctype
            ):
                return raw_url

        raise InstagramPublishError(
            f"업로드한 공개 이미지 URL 접근 검증 실패 ({raw_url}): HTTP {last_status}"
        )

    def delete_files(self, remote_paths: list[str]) -> int:
        """업로드된 미디어 파일들을 GitHub 미디어 브랜치에서 삭제한다."""
        deleted = 0
        for remote_path in remote_paths:
            encoded_path = self._encode_path(remote_path)
            sha = self._get_file_sha(encoded_path)
            if not sha:
                continue
            api_url = f"{self.api_base}/contents/{encoded_path}"
            resp = self.session.delete(
                api_url,
                json={
                    "message": f"Cleanup media asset: {remote_path}",
                    "sha": sha,
                    "branch": self.branch,
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                deleted += 1
            else:
                logger.warning("미디어 정리 실패(%s): HTTP %s", remote_path, resp.status_code)
        return deleted


class InstagramCarouselPublisher:
    """Meta Instagram Graph API 기반 캐러셀 자동 게시 클라이언트."""

    def __init__(
        self,
        ig_user_id: str | None = None,
        access_token: str | None = None,
        graph_version: str | None = None,
        media_host: GitHubMediaHost | None = None,
        timeout: int = 30,
    ) -> None:
        self.ig_user_id = (ig_user_id or config.IG_USER_ID).strip()
        self.access_token = (access_token or config.IG_ACCESS_TOKEN).strip()
        self.graph_version = (graph_version or config.IG_GRAPH_VERSION or "v24.0").strip()
        if not self.ig_user_id:
            raise InstagramPublishError("IG_USER_ID가 설정되어 있지 않습니다.")
        if not self.access_token:
            raise InstagramPublishError("IG_ACCESS_TOKEN이 설정되어 있지 않습니다.")
        self.base_url = f"https://graph.facebook.com/{self.graph_version}"
        self.timeout = timeout
        self.session = config.create_http_session()
        self._media_host = media_host

    def _get_media_host(self) -> GitHubMediaHost:
        if self._media_host is None:
            self._media_host = GitHubMediaHost()
        return self._media_host

    @staticmethod
    def _raise_for_graph_error(resp_data: Any, context: str) -> None:
        """Meta Graph API 응답 내 error 객체를 파싱해 상세 예외를 발생시킨다."""
        if isinstance(resp_data, dict) and "error" in resp_data:
            err = resp_data["error"] or {}
            msg = err.get("message") or str(err)
            code = err.get("code")
            subcode = err.get("error_subcode")
            raise InstagramPublishError(
                f"[{context}] Meta Graph API 오류 (code={code}, subcode={subcode}): {msg}"
            )

    def _graph_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {**params, "access_token": self.access_token}
        resp = self.session.get(
            f"{self.base_url}/{path.lstrip('/')}", params=query, timeout=self.timeout
        )
        data = resp.json()
        self._raise_for_graph_error(data, f"GET {path}")
        if resp.status_code >= 400:
            raise InstagramPublishError(f"[GET {path}] HTTP {resp.status_code}")
        return data

    def _graph_post(self, path: str, data_params: dict[str, Any]) -> dict[str, Any]:
        payload = {**data_params, "access_token": self.access_token}
        resp = self.session.post(
            f"{self.base_url}/{path.lstrip('/')}", data=payload, timeout=self.timeout
        )
        data = resp.json()
        self._raise_for_graph_error(data, f"POST {path}")
        if resp.status_code >= 400:
            raise InstagramPublishError(f"[POST {path}] HTTP {resp.status_code}")
        return data

    def verify_credentials(self) -> dict[str, Any]:
        """인스타그램 계정 정보와 24시간 일일 게시 한도(quota)를 조회한다."""
        account = self._graph_get(
            self.ig_user_id,
            {"fields": "id,username,name,media_count"},
        )
        limit_resp = self._graph_get(
            f"{self.ig_user_id}/content_publishing_limit",
            {"fields": "config,quota_usage"},
        )
        entries = limit_resp.get("data") or []
        quota_info = entries[0] if entries else {}
        quota_usage = int(quota_info.get("quota_usage") or 0)
        quota_total = int((quota_info.get("config") or {}).get("quota_total") or 100)
        return {
            "account": {
                "id": account.get("id"),
                "username": account.get("username"),
                "name": account.get("name"),
                "media_count": account.get("media_count"),
            },
            "quota": {
                "usage": quota_usage,
                "total": quota_total,
                "remaining": max(0, quota_total - quota_usage),
            },
        }

    def _create_media_container(self, params: dict[str, Any]) -> str:
        """개별 또는 캐러셀 미디어 컨테이너를 생성하고 creation_id를 반환한다."""
        data = self._graph_post(f"{self.ig_user_id}/media", params)
        cid = str(data.get("id") or "").strip()
        if not cid:
            raise InstagramPublishError(f"미디어 컨테이너 ID를 받지 못했습니다: {data}")
        return cid

    def _wait_container_finished(
        self, creation_id: str, timeout_sec: int = 90, interval_sec: int = 3
    ) -> None:
        """Meta 서버에서 이미지 수집·인코딩이 완료(FINISHED)될 때까지 폴링한다."""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            data = self._graph_get(
                creation_id,
                {"fields": "status_code,status"},
            )
            status_code = str(data.get("status_code") or "").upper()
            if status_code == "FINISHED":
                return
            if status_code in ("ERROR", "EXPIRED"):
                raise InstagramPublishError(
                    f"컨테이너({creation_id}) 처리 실패: {status_code} ({data.get('status')})"
                )
            time.sleep(interval_sec)
        raise InstagramPublishError(
            f"컨테이너({creation_id}) 처리 시간 초과 ({timeout_sec}초)"
        )

    def publish_slides(
        self,
        slide_paths: list[Path],
        caption: str,
        *,
        course_key: str,
        course_name: str = "",
        style: str = "",
        crs_idx: str = "",
        dry_run: bool = False,
        force: bool = False,
        cleanup_media: bool = False,
    ) -> dict[str, Any]:
        """슬라이드 이미지들과 캡션을 검증·호스팅하고 @trailllog 계정에 캐러셀로 게시한다."""
        ordered_slides = sorted(
            [Path(p) for p in slide_paths if Path(p).exists()],
            key=lambda p: p.name,
        )
        if not ordered_slides:
            raise InstagramPublishError("업로드할 슬라이드 이미지(slide_*.png)가 없습니다.")
        if len(ordered_slides) > card_common.MAX_SLIDES:
            raise InstagramPublishError(
                f"인스타그램 캐러셀은 최대 {card_common.MAX_SLIDES}장까지 지원합니다. (현재 {len(ordered_slides)}장)"
            )

        if crs_idx and not force and is_course_published(crs_idx):
            raise InstagramPublishError(
                f"이미 게시된 코스입니다 ({crs_idx} · {course_name}). 재게시하려면 --force-publish 옵션을 사용하세요."
            )

        final_caption = _trim_caption(caption)
        jpeg_items: list[tuple[Path, bytes, tuple[int, int]]] = []
        total_bytes = 0
        for p in ordered_slides:
            with Image.open(p) as im:
                size = im.size
            jpg = convert_slide_to_jpeg_bytes(p)
            total_bytes += len(jpg)
            jpeg_items.append((p, jpg, size))

        creds = self.verify_credentials()
        media_host = self._get_media_host()
        repo_info = media_host.verify_repo()

        if dry_run:
            return {
                "status": "dry_run",
                "account": creds["account"],
                "quota": creds["quota"],
                "repo": repo_info,
                "slide_count": len(jpeg_items),
                "total_jpeg_kb": round(total_bytes / 1024, 1),
                "caption_length": len(final_caption),
                "crs_idx": crs_idx,
                "course_name": course_name,
                "style": style,
            }

        if creds["quota"]["remaining"] <= 0:
            raise InstagramPublishError("인스타그램 일일 게시 한도(quota)를 모두 소진했습니다.")

        media_host.ensure_branch()
        slug = _sanitize_slug(course_key)
        ts_tag = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
        remote_paths: list[str] = []
        image_urls: list[str] = []

        for slide_path, jpg_bytes, _ in jpeg_items:
            remote_path = f"media/{slug}_{ts_tag}/{slide_path.stem}.jpg"
            url = media_host.upload_jpeg_bytes(
                remote_path,
                jpg_bytes,
                message=f"Upload carousel slide {slide_path.stem} for {course_name or slug}",
            )
            remote_paths.append(remote_path)
            image_urls.append(url)

        if len(image_urls) == 1:
            root_creation_id = self._create_media_container(
                {"image_url": image_urls[0], "caption": final_caption}
            )
            self._wait_container_finished(root_creation_id)
        else:
            child_ids: list[str] = []
            for img_url in image_urls:
                child_id = self._create_media_container(
                    {"image_url": img_url, "is_carousel_item": "true"}
                )
                self._wait_container_finished(child_id)
                child_ids.append(child_id)

            root_creation_id = self._create_media_container(
                {
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_ids),
                    "caption": final_caption,
                }
            )
            self._wait_container_finished(root_creation_id)

        pub_data = self._graph_post(
            f"{self.ig_user_id}/media_publish",
            {"creation_id": root_creation_id},
        )
        media_id = str(pub_data.get("id") or "").strip()
        if not media_id:
            raise InstagramPublishError(f"게시 후 media_id를 받지 못했습니다: {pub_data}")

        permalink = ""
        timestamp = ""
        try:
            meta = self._graph_get(media_id, {"fields": "id,permalink,timestamp"})
            permalink = str(meta.get("permalink") or "")
            timestamp = str(meta.get("timestamp") or "")
        except Exception as exc:
            logger.warning("게시물 퍼머링크 조회 실패(게시는 완료됨): %s", exc)

        published_at = timestamp or datetime.now(KST).isoformat()
        record_entry = {
            "crs_idx": crs_idx,
            "course_name": course_name,
            "style": style,
            "media_id": media_id,
            "permalink": permalink,
            "slide_count": len(jpeg_items),
            "published_at": published_at,
        }
        record_published_course(record_entry)

        cleaned_count = 0
        if cleanup_media and remote_paths:
            try:
                cleaned_count = media_host.delete_files(remote_paths)
            except Exception as exc:
                logger.warning("임시 호스팅 이미지 정리 실패(게시 완료): %s", exc)

        return {
            "status": "published",
            **record_entry,
            "account": creds["account"],
            "image_urls": image_urls,
            "cleaned_media_count": cleaned_count,
        }

    def publish_directory(
        self,
        out_dir: Path,
        *,
        dry_run: bool = False,
        force: bool = False,
        cleanup_media: bool = False,
    ) -> dict[str, Any]:
        """생성된 output/<코스> 폴더에서 슬라이드와 캡션을 읽어 게시한다."""
        target_dir = Path(out_dir)
        if not target_dir.exists():
            raise InstagramPublishError(f"출력 폴더를 찾을 수 없습니다: {target_dir}")

        course_data_path = target_dir / "course_data.json"
        course_data: dict[str, Any] = {}
        if course_data_path.exists():
            course_data = json.loads(course_data_path.read_text(encoding="utf-8"))

        theme_sel = course_data.get("theme_selection") or {}
        style = str(theme_sel.get("style") or "")
        crs_idx = str(course_data.get("crs_idx") or "")
        course_name = str(course_data.get("course_name") or target_dir.name)

        slides = sorted(target_dir.glob("slide_*.png"))
        if not slides and style and (target_dir / style).exists():
            slides = sorted((target_dir / style).glob("slide_*.png"))
        if not slides:
            raise InstagramPublishError(
                f"슬라이드 파일(slide_*.png)을 찾지 못했습니다: {target_dir}"
            )

        caption_path = target_dir / "caption.txt"
        if caption_path.exists():
            caption = caption_path.read_text(encoding="utf-8").strip()
        else:
            caption = str((course_data.get("copy") or {}).get("full_caption") or "").strip()
        if not caption:
            raise InstagramPublishError(f"캡션이 비어 있습니다: {target_dir}")

        result = self.publish_slides(
            slides,
            caption,
            course_key=target_dir.name,
            course_name=course_name,
            style=style,
            crs_idx=crs_idx,
            dry_run=dry_run,
            force=force,
            cleanup_media=cleanup_media,
        )
        if result.get("status") == "published":
            (target_dir / "publish_result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="TrailLog 인스타그램 캐러셀 자동 업로드 및 연결 점검 CLI"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Instagram 계정/일일 한도 및 GitHub 공개 저장소 연결 상태만 확인",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="게시할 output/<코스> 폴더 경로",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 업로드 없이 JPEG 변환 및 사전 검증만 수행",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 published_history.json에 기록된 코스도 강제 재게시",
    )
    parser.add_argument(
        "--cleanup-media",
        action="store_true",
        help="게시 완료 후 GitHub 미디어 브랜치에 올린 이미지 파일 정리",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    args = _parse_args(argv)
    publisher = InstagramCarouselPublisher()

    if args.check:
        creds = publisher.verify_credentials()
        repo = publisher._get_media_host().verify_repo()
        acc = creds["account"]
        quota = creds["quota"]
        print("인스타그램 & GitHub 연결 점검 통과")
        print(f"- IG 계정: @{acc['username']} (ID: {acc['id']}, 게시물: {acc['media_count']}개)")
        print(f"- 일일 게시 한도: {quota['usage']} / {quota['total']} (잔여 {quota['remaining']}건)")
        print(f"- GitHub 저장소: {repo['full_name']} (Public={not repo['private']}, 기본 브랜치: {repo['default_branch']}, 미디어 브랜치: {repo['media_branch']})")
        return 0

    if args.dir:
        result = publisher.publish_directory(
            args.dir,
            dry_run=args.dry_run,
            force=args.force,
            cleanup_media=args.cleanup_media,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("--check 또는 --dir <폴더경로>를 지정해 주세요. (--help로 옵션 확인)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
