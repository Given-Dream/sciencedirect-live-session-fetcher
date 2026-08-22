from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import time
import unicodedata
from pathlib import Path
from typing import Any

from pypdf import PdfReader


from literature_live_session_lib import (
    DevToolsClient,
    choose_route,
    collect_page_snapshot,
    extract_pdf_bytes_from_viewer,
    fetch_binary_from_page,
    make_target_name,
    read_manifest_rows,
)


RESULT_FIELDS = [
    "number",
    "title",
    "doi",
    "source_hint",
    "entry_url",
    "candidate_urls",
    "section_paths",
    "status",
    "pdf_path",
    "source_url",
    "resolved_source",
    "route_trace_json",
    "pages",
    "encrypted",
    "title_match",
    "passwordless_readable",
    "sha256",
    "validation_method",
    "note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download CNKI PDFs by clicking exact-title result links in an authorized live Edge session."
    )
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--debug-port", type=int, default=9223)
    parser.add_argument("--page-wait-seconds", type=int, default=8)
    parser.add_argument("--download-timeout-seconds", type=int, default=90)
    parser.add_argument("--inter-item-sleep-seconds", type=int, default=7)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--system-download-dir",
        default=str(Path.home() / "Downloads"),
        help="Also monitor Edge's system download folder for target=_blank CNKI downloads.",
    )
    parser.add_argument(
        "--reuse-existing-page",
        action="store_true",
        help="Navigate one existing CNKI tab instead of creating a new tab per row.",
    )
    parser.add_argument(
        "--use-current-page-first",
        action="store_true",
        help="For the first row, use the currently displayed verified CNKI result page without navigating again.",
    )
    return parser.parse_args()


def list_pages(devtools: DevToolsClient) -> list[dict[str, Any]]:
    return json.loads(devtools.http_get(f"{devtools.base}/json/list"))


def visible_challenge(
    snapshot: dict[str, Any],
    devtools: DevToolsClient | None = None,
    ws_url: str = "",
) -> bool:
    """Detect a real verification page/overlay while ignoring dormant captcha DOM."""
    url = str(snapshot.get("href", "")).lower()
    title = str(snapshot.get("title", "")).lower()
    body = str(snapshot.get("body_text", "")).lower()

    # A dedicated verification URL is definitive even if its UI has not rendered yet.
    if "/verify/home" in url or "captchatype=" in url:
        return True

    title_markers = ("安全验证", "security verification", "verify you are human")
    body_markers = (
        "完成安全验证",
        "拖动下方拼图完成验证",
        "拖动滑块",
        "请完成验证",
        "verify you are human",
        "please confirm you are a human",
        "are you a robot?",
    )
    if any(marker in title for marker in title_markers) and any(
        marker in body for marker in body_markers
    ):
        return True

    if devtools is None or not ws_url:
        return False

    # CNKI keeps a Tencent captcha widget at y=-1000000 with opacity=0 on normal
    # result pages. Check direct prompt text, ancestor styles, and viewport
    # intersection so that dormant markup is never treated as a shown slider.
    expression = r"""
(() => {
  const markers = [
    '完成安全验证', '拖动下方拼图完成验证', '拖动滑块', '请完成验证',
    'verify you are human', 'please confirm you are a human', 'are you a robot?'
  ];
  const directText = el => [...el.childNodes]
    .filter(node => node.nodeType === Node.TEXT_NODE)
    .map(node => node.textContent || '')
    .join(' ')
    .trim()
    .toLowerCase();
  const renderedInViewport = el => {
    for (let node = el; node && node.nodeType === Node.ELEMENT_NODE; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden' ||
          style.visibility === 'collapse' || Number(style.opacity) <= 0.01) {
        return false;
      }
    }
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 &&
      rect.top < innerHeight && rect.left < innerWidth;
  };
  return [...document.querySelectorAll('body *')].some(el => {
    const text = directText(el);
    return markers.some(marker => text.includes(marker)) && renderedInViewport(el);
  });
})()
    """.strip()
    try:
        return bool(devtools.evaluate_value(ws_url, expression, msg_id=30))
    except Exception:
        return False


def choose_existing_cnki_page(devtools: DevToolsClient) -> dict[str, Any]:
    pages = [page for page in list_pages(devtools) if page.get("type") == "page"]
    candidates = [
        page
        for page in pages
        if "cnki.net" in str(page.get("url", "")).lower()
    ]
    if not candidates:
        raise RuntimeError("No existing CNKI page is available for reuse")
    candidates.sort(
        key=lambda page: (
            "verify/home" not in str(page.get("url", "")).lower(),
            "defaultresult" in str(page.get("url", "")).lower(),
            "kns.cnki.net" in str(page.get("url", "")).lower(),
        ),
        reverse=True,
    )
    return candidates[0]


def enable_downloads(devtools: DevToolsClient, ws_url: str, download_dir: Path) -> None:
    params = {
        "behavior": "allow",
        "downloadPath": str(download_dir.resolve()),
        "eventsEnabled": True,
    }
    try:
        devtools.call(ws_url, "Browser.setDownloadBehavior", params, msg_id=31)
    except Exception:
        devtools.call(ws_url, "Page.setDownloadBehavior", params, msg_id=32)


def click_exact_title_download(
    devtools: DevToolsClient,
    ws_url: str,
    title: str,
) -> dict[str, Any]:
    expression = f"""
(() => {{
  const target = {json.dumps(title, ensure_ascii=False)};
  const norm = value => String(value || '')
    .replace(/\\s+/g, '')
    .replace(/[：:，,。.;；·]/g, '')
    .toLowerCase();
  const targetNorm = norm(target);
  const titleAnchors = [...document.querySelectorAll('a[href]')]
    .filter(el => norm(el.innerText || el.textContent) === targetNorm);
  let row = titleAnchors.length ? titleAnchors[0].closest('tr') : null;
  if (!row) {{
    row = [...document.querySelectorAll('tr')]
      .find(el => norm(el.innerText || el.textContent).includes(targetNorm)) || null;
  }}
  if (!row) {{
    return {{status: 'title_not_found', target, body: (document.body?.innerText || '').slice(0, 1200)}};
  }}
  const clickable = [...row.querySelectorAll('a[href], button, [onclick]')];
  const download = clickable.find(el => /下载|pdf/i.test(el.innerText || el.textContent || el.getAttribute('title') || ''));
  if (!download) {{
    return {{
      status: 'download_control_not_found',
      target,
      row_text: (row.innerText || row.textContent || '').slice(0, 1200),
      controls: clickable.map(el => ({{text: (el.innerText || el.textContent || '').trim(), href: el.href || ''}})).slice(0, 30)
    }};
  }}
  download.scrollIntoView({{block: 'center', inline: 'center'}});
  const rect = download.getBoundingClientRect();
  const info = {{
    status: 'ready_for_trusted_click',
    target,
    text: (download.innerText || download.textContent || '').trim(),
    href: download.href || '',
    page_url: location.href,
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
    width: rect.width,
    height: rect.height
  }};
  return info;
}})()
    """.strip()
    value = devtools.evaluate_value(ws_url, expression, msg_id=33)
    if not isinstance(value, dict):
        return {"status": "click_script_no_result"}
    if value.get("status") != "ready_for_trusted_click":
        return value
    x = float(value.get("x", 0) or 0)
    y = float(value.get("y", 0) or 0)
    if x <= 0 or y <= 0 or float(value.get("width", 0) or 0) <= 0:
        return {**value, "status": "download_control_not_visible"}
    devtools.call(
        ws_url,
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1},
        msg_id=34,
    )
    devtools.call(
        ws_url,
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1},
        msg_id=35,
    )
    return {**value, "status": "clicked", "event": "trusted_mouse_click"}


def click_exact_title_link(
    devtools: DevToolsClient,
    ws_url: str,
    title: str,
) -> dict[str, Any]:
    """Enter the article detail page through its exact title link."""
    expression = f"""
(() => {{
  const target = {json.dumps(title, ensure_ascii=False)};
  const norm = value => String(value || '').normalize('NFKC')
    .replace(/[\s\p{P}\p{S}_]+/gu, '').toLowerCase();
  const targetNorm = norm(target);
  const candidates = [...document.querySelectorAll('a[href]')]
    .filter(el => norm(el.innerText || el.textContent) === targetNorm);
  const visible = candidates.find(el => {{
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' &&
      style.visibility !== 'hidden' && Number(style.opacity) > 0.01;
  }});
  if (!visible) return {{status: 'title_link_not_found', target}};
  visible.scrollIntoView({{block: 'center', inline: 'center'}});
  const rect = visible.getBoundingClientRect();
  return {{
    status: 'ready_for_trusted_click', target, href: visible.href || '',
    x: rect.left + rect.width / 2, y: rect.top + rect.height / 2,
    width: rect.width, height: rect.height
  }};
}})()
    """.strip()
    value = devtools.evaluate_value(ws_url, expression, msg_id=39)
    if not isinstance(value, dict):
        return {"status": "title_click_script_no_result"}
    if value.get("status") != "ready_for_trusted_click":
        return value
    x = float(value.get("x", 0) or 0)
    y = float(value.get("y", 0) or 0)
    devtools.call(
        ws_url,
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1},
        msg_id=40,
    )
    devtools.call(
        ws_url,
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1},
        msg_id=41,
    )
    return {**value, "status": "clicked", "event": "trusted_mouse_click"}


def click_pdf_download(
    devtools: DevToolsClient,
    ws_url: str,
) -> dict[str, Any]:
    """Click only the visible CNKI `PDF下载` control; never select CAJ."""
    expression = r"""
(() => {
  const norm = value => String(value || '').replace(/\s+/g, '').toLowerCase();
  const candidates = [...document.querySelectorAll('a[href], button, [onclick]')]
    .filter(el => norm(el.innerText || el.textContent) === 'pdf下载');
  const visible = candidates.find(el => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' &&
      style.visibility !== 'hidden' && Number(style.opacity) > 0.01;
  });
  if (!visible) {
    return {
      status: 'pdf_download_control_not_found',
      candidates: candidates.map(el => ({
        id: el.id || '', href: el.href || '',
        text: (el.innerText || el.textContent || '').trim()
      }))
    };
  }
  visible.scrollIntoView({block: 'center', inline: 'center'});
  const rect = visible.getBoundingClientRect();
  return {
    status: 'ready_for_trusted_click',
    id: visible.id || '',
    text: (visible.innerText || visible.textContent || '').trim(),
    href: visible.href || '',
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
    width: rect.width,
    height: rect.height
  };
})()
    """.strip()
    value = devtools.evaluate_value(ws_url, expression, msg_id=36)
    if not isinstance(value, dict):
        return {"status": "pdf_click_script_no_result"}
    if value.get("status") != "ready_for_trusted_click":
        return value
    x = float(value.get("x", 0) or 0)
    y = float(value.get("y", 0) or 0)
    devtools.call(
        ws_url,
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1},
        msg_id=37,
    )
    devtools.call(
        ws_url,
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1},
        msg_id=38,
    )
    return {**value, "status": "clicked", "event": "trusted_mouse_click"}


def wait_for_download(
    download_dir: Path,
    before: set[Path],
    timeout_seconds: int,
) -> Path | None:
    deadline = time.time() + timeout_seconds
    last_sizes: dict[Path, int] = {}
    stable_counts: dict[Path, int] = {}
    while time.time() < deadline:
        current = {path for path in download_dir.iterdir() if path.is_file()}
        new_files = [path for path in current - before if not path.name.endswith(".crdownload")]
        active = any(path.name.endswith(".crdownload") for path in current - before)
        for path in new_files:
            size = path.stat().st_size
            if size > 0 and last_sizes.get(path) == size:
                stable_counts[path] = stable_counts.get(path, 0) + 1
            else:
                stable_counts[path] = 0
            last_sizes[path] = size
            if stable_counts[path] >= 2 and not active:
                return path
        time.sleep(1)
    return None


def wait_for_article_detail(
    devtools: DevToolsClient,
    title: str,
    timeout_seconds: int = 25,
) -> dict[str, Any] | None:
    title_key = re.sub(r"[\W_]+", "", title, flags=re.UNICODE).lower()
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for page in list_pages(devtools):
            if page.get("type") != "page":
                continue
            url = str(page.get("url", "")).lower()
            page_title = re.sub(
                r"[\W_]+", "", str(page.get("title", "")), flags=re.UNICODE
            ).lower()
            if "/article/abstract" in url and title_key and title_key in page_title:
                return page
        time.sleep(0.5)
    return None


def wait_for_pdf_from_dirs(
    directories: list[Path],
    before: dict[Path, set[Path]],
    timeout_seconds: int,
) -> Path | None:
    """Return only a completed PDF; CAJ and other formats are ignored."""
    deadline = time.time() + timeout_seconds
    last_sizes: dict[Path, int] = {}
    stable_counts: dict[Path, int] = {}
    while time.time() < deadline:
        candidates: list[Path] = []
        for directory in directories:
            if not directory.exists():
                continue
            initial = before.get(directory, set())
            for path in directory.iterdir():
                if path.is_file() and path not in initial and not path.name.endswith(".crdownload"):
                    candidates.append(path)
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates:
            size = path.stat().st_size
            if size > 0 and last_sizes.get(path) == size:
                stable_counts[path] = stable_counts.get(path, 0) + 1
            else:
                stable_counts[path] = 0
            last_sizes[path] = size
            if stable_counts[path] >= 2 and path.read_bytes()[:5] == b"%PDF-":
                return path
        time.sleep(1)
    return None


def wait_for_pdf_or_login(
    devtools: DevToolsClient,
    directories: list[Path],
    before: dict[Path, set[Path]],
    page_urls_before: dict[str, str],
    timeout_seconds: int,
) -> tuple[Path | None, dict[str, str] | None]:
    """Prefer a completed PDF, but stop promptly when CNKI requires login."""
    deadline = time.time() + timeout_seconds
    login_seen_at: float | None = None
    login_page: dict[str, str] | None = None
    last_sizes: dict[Path, int] = {}
    stable_counts: dict[Path, int] = {}
    while time.time() < deadline:
        candidates: list[Path] = []
        for directory in directories:
            if not directory.exists():
                continue
            initial = before.get(directory, set())
            for path in directory.iterdir():
                if path.is_file() and path not in initial and not path.name.endswith(".crdownload"):
                    candidates.append(path)
        candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for path in candidates:
            size = path.stat().st_size
            if size > 0 and last_sizes.get(path) == size:
                stable_counts[path] = stable_counts.get(path, 0) + 1
            else:
                stable_counts[path] = 0
            last_sizes[path] = size
            if stable_counts[path] >= 2 and path.read_bytes()[:5] == b"%PDF-":
                return path, None

        for page in list_pages(devtools):
            if page.get("type") != "page":
                continue
            page_id = str(page.get("id", ""))
            page_url = str(page.get("url", ""))
            lowered = page_url.lower()
            was_login = "login.cnki.net" in page_urls_before.get(page_id, "").lower()
            if "login.cnki.net" in lowered and not was_login:
                login_page = {
                    "id": page_id,
                    "title": str(page.get("title", "")),
                    "url": page_url,
                }
                if login_seen_at is None:
                    login_seen_at = time.time()
        if login_seen_at is not None and time.time() - login_seen_at >= 8:
            return None, login_page
        time.sleep(1)
    return None, login_page


def save_pdf_payload(payload: bytes, target_path: Path) -> bool:
    if not payload.startswith(b"%PDF-"):
        return False
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(payload)
    return True


def normalized_title(value: str) -> str:
    return re.sub(
        r"[\W_]+",
        "",
        unicodedata.normalize("NFKC", value),
        flags=re.UNICODE,
    ).lower()


def validate_pdf(path: Path, expected_title: str) -> tuple[bool, dict[str, Any]]:
    details: dict[str, Any] = {"path": str(path), "size": path.stat().st_size}
    try:
        reader = PdfReader(str(path))
        details["pages"] = len(reader.pages)
        details["encrypted"] = bool(reader.is_encrypted)
        metadata_title = str((reader.metadata or {}).get("/Title", "") or "")
        details["metadata_title"] = metadata_title
        text_parts: list[str] = []
        readable_pages = 0
        for page in reader.pages[: min(3, len(reader.pages))]:
            try:
                text_parts.append(page.extract_text() or "")
                readable_pages += 1
            except Exception:
                continue
        text = "\n".join(text_parts)
        title_key = normalized_title(expected_title)
        searchable = normalized_title(metadata_title + "\n" + text)
        details["title_match"] = bool(title_key and title_key in searchable)
        details["passwordless_readable"] = readable_pages > 0
        details["text_preview"] = text[:300]
        details["valid"] = (
            len(reader.pages) >= 2
            and details["passwordless_readable"]
            and details["title_match"]
        )
        return bool(details["valid"]), details
    except Exception as exc:
        details.update({"valid": False, "error": f"{type(exc).__name__}: {exc}"})
        return False, details


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validation_columns(details: dict[str, Any], method: str = "automatic") -> dict[str, str]:
    return {
        "pages": str(details.get("pages", "")),
        "encrypted": str(details.get("encrypted", "")),
        "title_match": str(details.get("title_match", "")),
        "passwordless_readable": str(details.get("passwordless_readable", "")),
        "sha256": str(details.get("sha256", "")),
        "validation_method": method,
    }


def quarantine_file(path: Path, raw_download_dir: Path, label: str) -> Path:
    invalid_dir = raw_download_dir.parent / "invalid_downloads"
    invalid_dir.mkdir(parents=True, exist_ok=True)
    target = invalid_dir / f"{label}_{path.name}"
    counter = 1
    while target.exists():
        target = invalid_dir / f"{label}_{counter}_{path.name}"
        counter += 1
    shutil.move(str(path), str(target))
    return target


def recover_pdf_from_pages(
    devtools: DevToolsClient,
    page_ids_before: set[str],
    current_page_id: str,
    target_path: Path,
) -> tuple[bool, dict[str, Any]]:
    pages = [
        page
        for page in list_pages(devtools)
        if page.get("type") == "page"
        and (
            page.get("id") not in page_ids_before
            or page.get("id") == current_page_id
        )
    ]
    pages.sort(key=lambda page: page.get("id") != current_page_id, reverse=True)
    traces: list[dict[str, Any]] = []
    for page in pages:
        ws_url = page.get("webSocketDebuggerUrl", "")
        if not ws_url:
            continue
        try:
            snapshot = collect_page_snapshot(devtools, ws_url)
        except Exception as exc:
            traces.append({"page_url": page.get("url", ""), "error": str(exc)})
            continue
        challenge = visible_challenge(snapshot, devtools, ws_url)
        snapshot["challenge_page"] = challenge
        snapshot["bot_verification_page"] = challenge
        route = choose_route(snapshot)
        traces.append(
            {
                "page_url": snapshot.get("href", ""),
                "page_title": snapshot.get("title", ""),
                "challenge_page": challenge,
                "raw_challenge_flag": snapshot.get("challenge_page", False),
                "has_pdf_viewer": snapshot.get("has_pdf_viewer", False),
                "route": route,
            }
        )
        if challenge:
            continue
        payload: bytes | None = None
        if snapshot.get("has_pdf_viewer"):
            try:
                payload = extract_pdf_bytes_from_viewer(devtools, ws_url)
            except Exception:
                payload = None
        if not payload and route.get("kind") == "page_fetch":
            try:
                payload, _ = fetch_binary_from_page(devtools, ws_url, str(route.get("url", "")))
            except Exception:
                payload = None
        if payload and save_pdf_payload(payload, target_path):
            return True, {"pages": traces, "recovered_from": snapshot.get("href", "")}
    return False, {"pages": traces}


def process_row(
    devtools: DevToolsClient,
    row: dict[str, str],
    pdf_dir: Path,
    raw_download_dir: Path,
    system_download_dir: Path,
    page_wait_seconds: int,
    download_timeout_seconds: int,
    reuse_existing_page: bool,
    use_current_page_without_navigation: bool,
) -> dict[str, str]:
    target_path = pdf_dir / make_target_name(row)
    if target_path.exists():
        valid, validation = validate_pdf(target_path, row.get("title", ""))
        if valid:
            validation["sha256"] = sha256_file(target_path)
            return {
                **row,
                "status": "downloaded",
                "pdf_path": str(target_path),
                "source_url": "",
                "resolved_source": "cnki",
                "route_trace_json": json.dumps({"existing_validation": validation}, ensure_ascii=False),
                **validation_columns(validation, "existing_pdf_header_pages_title"),
                "note": "existing_valid_pdf",
            }
        quarantine_file(target_path, raw_download_dir, "rejected_existing")

    page = None
    close_page_when_done = False
    page_ids_before_entry: set[str] = set()
    trace: dict[str, Any] = {"search_url": row.get("entry_url", "")}
    try:
        if reuse_existing_page:
            page = choose_existing_cnki_page(devtools)
            if use_current_page_without_navigation:
                trace["page_mode"] = "reused_current_page_without_navigation"
            else:
                devtools.call(
                    page["webSocketDebuggerUrl"],
                    "Page.navigate",
                    {"url": row.get("entry_url", "")},
                    msg_id=29,
                )
                trace["page_mode"] = "reused_existing_cnki_page"
        else:
            page = devtools.open_page(row.get("entry_url", ""))
            close_page_when_done = True
            trace["page_mode"] = "new_page"
        time.sleep(page_wait_seconds)
        ws_url = page["webSocketDebuggerUrl"]
        snapshot = collect_page_snapshot(devtools, ws_url)
        challenge = visible_challenge(snapshot, devtools, ws_url)
        trace["search_snapshot"] = {
            "page_url": snapshot.get("href", ""),
            "page_title": snapshot.get("title", ""),
            "challenge_page": challenge,
            "raw_challenge_flag": snapshot.get("challenge_page", False),
            "body_preview": snapshot.get("body_text", "")[:800],
        }
        if challenge:
            return {
                **row,
                "status": "challenge_page",
                "pdf_path": "",
                "source_url": str(snapshot.get("href", "")),
                "resolved_source": "cnki",
                "route_trace_json": json.dumps(trace, ensure_ascii=False),
                "note": "complete manual verification in the live browser and retry",
            }

        enable_downloads(devtools, ws_url, raw_download_dir)
        page_ids_before_entry = {str(item.get("id", "")) for item in list_pages(devtools)}
        download_dirs = [raw_download_dir, system_download_dir]
        files_before = {
            directory: ({path for path in directory.iterdir() if path.is_file()} if directory.exists() else set())
            for directory in download_dirs
        }
        page_url = str(snapshot.get("href", ""))
        page_title = str(snapshot.get("title", ""))
        expected_key = normalized_title(row.get("title", ""))
        on_matching_detail = (
            "/article/abstract" in page_url.lower()
            and expected_key
            and expected_key in normalized_title(page_title)
        )
        if on_matching_detail:
            detail_page = page
            trace["detail_mode"] = "entry_url_is_matching_detail_page"
        else:
            title_click = click_exact_title_link(devtools, ws_url, row.get("title", ""))
            trace["title_click"] = title_click
            if title_click.get("status") != "clicked":
                return {
                    **row,
                    "status": str(title_click.get("status", "title_click_failed")),
                    "pdf_path": "",
                    "source_url": page_url,
                    "resolved_source": "cnki",
                    "route_trace_json": json.dumps(trace, ensure_ascii=False),
                    "note": "exact-title article link was not clicked",
                }
            detail_page = wait_for_article_detail(
                devtools, row.get("title", ""), timeout_seconds=8
            )
            if not detail_page:
                detail_url = str(title_click.get("href", ""))
                if not detail_url or "/article/abstract" not in detail_url.lower():
                    return {
                        **row,
                        "status": "detail_page_not_opened",
                        "pdf_path": "",
                        "source_url": detail_url,
                        "resolved_source": "cnki",
                        "route_trace_json": json.dumps(trace, ensure_ascii=False),
                        "note": "exact-title link clicked but no valid article-detail URL was available",
                    }
                devtools.call(
                    ws_url,
                    "Page.navigate",
                    {"url": detail_url},
                    msg_id=42,
                )
                time.sleep(page_wait_seconds)
                detail_page = page
                trace["detail_mode"] = "same_tab_navigation_to_exact_title_href"
            else:
                trace["detail_mode"] = "title_link_opened_detail_tab"
        detail_ws_url = str(detail_page.get("webSocketDebuggerUrl", ""))
        detail_snapshot = collect_page_snapshot(devtools, detail_ws_url)
        detail_challenge = visible_challenge(detail_snapshot, devtools, detail_ws_url)
        trace["detail_snapshot"] = {
            "page_url": detail_snapshot.get("href", ""),
            "page_title": detail_snapshot.get("title", ""),
            "challenge_page": detail_challenge,
        }
        if detail_challenge:
            return {
                **row,
                "status": "challenge_page",
                "pdf_path": "",
                "source_url": str(detail_snapshot.get("href", "")),
                "resolved_source": "cnki",
                "route_trace_json": json.dumps(trace, ensure_ascii=False),
                "note": "visible verification on article detail page",
            }
        enable_downloads(devtools, detail_ws_url, raw_download_dir)
        page_urls_before_pdf = {
            str(item.get("id", "")): str(item.get("url", ""))
            for item in list_pages(devtools)
            if item.get("type") == "page"
        }
        pdf_click = click_pdf_download(devtools, detail_ws_url)
        trace["pdf_click"] = pdf_click
        if pdf_click.get("status") != "clicked":
            return {
                **row,
                "status": str(pdf_click.get("status", "pdf_click_failed")),
                "pdf_path": "",
                "source_url": str(detail_snapshot.get("href", "")),
                "resolved_source": "cnki",
                "route_trace_json": json.dumps(trace, ensure_ascii=False),
                "note": "PDF download control was not clicked; CAJ was not used",
            }
        downloaded, login_page = wait_for_pdf_or_login(
            devtools,
            download_dirs,
            files_before,
            page_urls_before_pdf,
            min(download_timeout_seconds, 20),
        )
        if not downloaded and not login_page:
            # Some CNKI target=_blank controls are ignored by popup handling even
            # after a trusted click. Navigate a temporary tab to the exact same
            # PDF button href with the detail page as referrer. Page.navigate
            # reports isDownload=true when the browser accepts the request.
            fallback_page = None
            try:
                fallback_page = devtools.open_page("about:blank")
                fallback_ws = str(fallback_page.get("webSocketDebuggerUrl", ""))
                enable_downloads(devtools, fallback_ws, raw_download_dir)
                navigation = devtools.call(
                    fallback_ws,
                    "Page.navigate",
                    {
                        "url": str(pdf_click.get("href", "")),
                        "referrer": str(detail_snapshot.get("href", "")),
                    },
                    msg_id=43,
                )
                trace["pdf_link_navigation_fallback"] = navigation
                downloaded, login_page = wait_for_pdf_or_login(
                    devtools,
                    download_dirs,
                    files_before,
                    page_urls_before_pdf,
                    max(20, download_timeout_seconds - 20),
                )
            finally:
                if fallback_page:
                    try:
                        devtools.close_page(str(fallback_page.get("id", "")))
                    except Exception:
                        pass
        if login_page:
            trace["login_page"] = login_page
        if not downloaded:
            return {
                **row,
                "status": "login_required" if login_page else "pdf_download_timeout",
                "pdf_path": "",
                "source_url": str(pdf_click.get("href", "")),
                "resolved_source": "cnki",
                "route_trace_json": json.dumps(trace, ensure_ascii=False),
                "note": (
                    "clicked PDF download only; CNKI personal login is required"
                    if login_page
                    else "clicked PDF download only; no completed PDF detected"
                ),
            }
        valid, validation = validate_pdf(downloaded, row.get("title", ""))
        validation["sha256"] = sha256_file(downloaded)
        trace["downloaded_file"] = {"path": str(downloaded), "size": downloaded.stat().st_size}
        trace["downloaded_file_validation"] = validation
        if not valid:
            return {
                **row,
                "status": "downloaded_invalid_pdf",
                "pdf_path": "",
                "source_url": str(pdf_click.get("href", "")),
                "resolved_source": "cnki",
                "route_trace_json": json.dumps(trace, ensure_ascii=False),
                **validation_columns(validation, "automatic_pdf_header_pages_title"),
                "note": "PDF button produced a file that failed title/page validation",
            }
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if downloaded.parent.resolve() == system_download_dir.resolve():
            shutil.copy2(str(downloaded), str(target_path))
        elif downloaded.resolve() != target_path.resolve():
            shutil.move(str(downloaded), str(target_path))
        return {
            **row,
            "status": "downloaded",
            "pdf_path": str(target_path),
            "source_url": str(pdf_click.get("href", "")),
            "resolved_source": "cnki",
            "route_trace_json": json.dumps(trace, ensure_ascii=False),
            **validation_columns(validation, "automatic_pdf_header_pages_title"),
            "note": "entered_article_detail; clicked_PDF_download_only; verified_title_and_pages",
        }
    finally:
        if page_ids_before_entry:
            for opened in list_pages(devtools):
                opened_id = str(opened.get("id", ""))
                if opened.get("type") == "page" and opened_id not in page_ids_before_entry:
                    try:
                        devtools.close_page(opened_id)
                    except Exception:
                        pass
        if page and close_page_when_done:
            devtools.close_page(page["id"])


def write_reports(out_dir: Path, results: list[dict[str, str]], debug_port: int) -> None:
    results_csv = out_dir / "cnki_pdf_results.csv"
    missing_csv = out_dir / "cnki_pdf_missing.csv"
    with results_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, "") for key in RESULT_FIELDS})
    missing = [row for row in results if row.get("status") != "downloaded"]
    with missing_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for row in missing:
            writer.writerow({key: row.get(key, "") for key in RESULT_FIELDS})
    summary = {
        "total_rows": len(results),
        "downloaded": sum(row.get("status") == "downloaded" for row in results),
        "missing": len(missing),
        "status_counts": {
            status: sum(row.get("status") == status for row in results)
            for status in sorted({row.get("status", "") for row in results})
        },
        "debug_port": debug_port,
        "pdf_dir": str((out_dir / "pdfs").resolve()),
    }
    (out_dir / "cnki_pdf_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    pdf_dir = out_dir / "pdfs"
    raw_download_dir = out_dir / "browser_downloads"
    system_download_dir = Path(args.system_download_dir).expanduser()
    pdf_dir.mkdir(parents=True, exist_ok=True)
    raw_download_dir.mkdir(parents=True, exist_ok=True)

    rows = read_manifest_rows(Path(args.input_csv))
    if args.limit > 0:
        rows = rows[: args.limit]

    devtools = DevToolsClient(args.debug_port)
    results: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        print(f"[{index}/{len(rows)}] CNKI exact-title live click | {row.get('title', '')}")
        try:
            result = process_row(
                devtools,
                row,
                pdf_dir,
                raw_download_dir,
                system_download_dir,
                args.page_wait_seconds,
                args.download_timeout_seconds,
                args.reuse_existing_page,
                bool(
                    args.reuse_existing_page
                    and args.use_current_page_first
                    and index == 1
                ),
            )
        except Exception as exc:
            result = {
                **row,
                "status": "exception",
                "pdf_path": "",
                "source_url": "",
                "resolved_source": "cnki",
                "route_trace_json": "[]",
                "note": f"{type(exc).__name__}: {exc}",
            }
        results.append(result)
        print(f"    -> {result.get('status', '')}")
        write_reports(out_dir, results, args.debug_port)
        if result.get("status") in {"challenge_page", "login_required"}:
            print("Manual browser action required; stopping without bypass attempt.")
            break
        if index < len(rows) and args.inter_item_sleep_seconds > 0:
            time.sleep(args.inter_item_sleep_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
