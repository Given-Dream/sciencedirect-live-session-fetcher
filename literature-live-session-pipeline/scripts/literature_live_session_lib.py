from __future__ import annotations

import base64
import csv
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import websocket
from websocket import WebSocketTimeoutException


PDF_RE = re.compile(
    r'"pdfDownload":\{"isPdfFullText":(?:true|false),"urlMetadata":\{"queryParams":\{"md5":"([^"]+)","pid":"([^"]+)"\},"pii":"([^"]+)","pdfExtension":"([^"]+)","path":"([^"]+)"\}\}'
)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", flags=re.I)
URL_RE = re.compile(r"https?://[^\s<>\"]+", flags=re.I)

PAGE_META_JS = r"""
(() => {
  const seen = new Set();
  const items = [];
  const push = (raw, reason) => {
    if (!raw) return;
    try {
      const text = String(raw).trim();
      if (!text) return;
      const value = new URL(text, location.href).href;
      if (seen.has(value)) return;
      seen.add(value);
      items.push({ url: value, reason });
    } catch (err) {
      return;
    }
  };

  for (const el of document.querySelectorAll("a[href]")) {
    push(el.getAttribute("href"), "anchor:" + (el.innerText || el.textContent || "").trim().slice(0, 80));
  }
  for (const el of document.querySelectorAll("iframe[src], embed[src]")) {
    push(el.getAttribute("src"), el.tagName.toLowerCase());
  }
  for (const el of document.querySelectorAll("object[data]")) {
    push(el.getAttribute("data"), "object");
  }
  for (const el of document.querySelectorAll("[data-url], [data-href], [data-downloadurl]")) {
    push(el.getAttribute("data-url"), "data-url");
    push(el.getAttribute("data-href"), "data-href");
    push(el.getAttribute("data-downloadurl"), "data-downloadurl");
  }
  for (const el of document.querySelectorAll("[onclick]")) {
    const raw = el.getAttribute("onclick") || "";
    const match = raw.match(/https?:\/\/[^\s'"]+/i);
    if (match) {
      push(match[0], "onclick");
    }
  }

  return {
    href: location.href,
    title: document.title || "",
    ready_state: document.readyState || "",
    body_text: (document.body ? document.body.innerText || "" : "").slice(0, 4000),
    has_pdf_viewer: Boolean(window.PDFViewerApplication),
    candidate_urls: items.slice(0, 250)
  };
})()
""".strip()

DOWNLOAD_KEYWORDS = (
    "download",
    "pdf",
    "fulltext",
    "full-text",
    "pdfft",
    "articlepdf",
    "caj",
    "readpdf",
    "pdfdown",
    "pdfdownload",
)
LOGIN_BLOCKLIST = ("login", "signin", "sign-in", "logout", "register")
PUBLISHER_HINTS = (
    "sciencedirect.com",
    "elsevier.com",
    "sciencedirectassets.com",
    "springer.com",
    "nature.com",
    "wiley.com",
    "tandfonline.com",
    "sagepub.com",
    "doi.org",
    "onlinelibrary.wiley.com",
)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def field_text(row: dict[str, Any], key: str) -> str:
    return normalize_space(str(row.get(key, "") or ""))


def split_multi_value(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[;\r\n]+", text)
    return [normalize_space(part) for part in parts if normalize_space(part)]


def extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for match in URL_RE.findall(text or ""):
        url = match.rstrip(".,);]>")
        if url not in found:
            found.append(url)
    return found


def sanitize_name(text: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().replace(" ", "_")
    cleaned = cleaned[:140]
    return cleaned or fallback


def detect_source(url: str, html: str = "", title: str = "") -> str:
    lowered = (url or "").lower()
    blob = f"{lowered}\n{title.lower()}\n{html[:2000].lower()}"
    if ".pdf" in lowered or "/pdf/" in lowered or "pdfviewer" in blob:
        return "pdf"
    if "sciencedirect.com" in lowered or "elsevier.com" in lowered:
        return "sciencedirect"
    if "cnki.net" in lowered or "cnki.com.cn" in lowered:
        return "cnki"
    if "webofscience.com" in lowered or "isiknowledge.com" in lowered or "clarivate" in lowered:
        return "wos"
    if "doi.org" in lowered:
        return "doi"
    return "generic"


def looks_like_pdf_url(url: str) -> bool:
    lowered = (url or "").lower()
    if lowered.endswith(".pdf"):
        return True
    return any(token in lowered for token in ("/pdf/", "articlepdf", "pdfft", "pdf="))


def looks_like_download_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(token in lowered for token in DOWNLOAD_KEYWORDS)


def is_doi_url(url: str) -> bool:
    return "doi.org/" in (url or "").lower()


def is_publisher_article_url(url: str) -> bool:
    lowered = (url or "").lower()
    if any(domain in lowered for domain in PUBLISHER_HINTS):
        return True
    return "/article/" in lowered or "/science/article/" in lowered


def same_origin(left: str, right: str) -> bool:
    try:
        a = urlparse(left)
        b = urlparse(right)
        return (a.scheme, a.netloc) == (b.scheme, b.netloc)
    except Exception:
        return False


def infer_pdf_url_from_sciencedirect(html: str) -> str:
    match = PDF_RE.search(html or "")
    if not match:
        return ""
    md5, pid, pii, pdf_ext, path = match.groups()
    return f"https://www.sciencedirect.com/{path}/{pii}{pdf_ext}?md5={md5}&pid={pid}"


def extract_first_doi(text: str) -> str:
    match = DOI_RE.search(text or "")
    return match.group(0).rstrip(").,;]") if match else ""


def challenge_flags(url: str, html: str, title: str, body_text: str = "") -> dict[str, bool]:
    lowered = f"{url}\n{title}\n{body_text[:3000]}\n{html[:3000]}".lower()
    blocked = (
        "please wait while" in lowered
        or "cf-chl" in lowered
        or "captcha" in lowered
        or "are you a robot?" in lowered
        or "please confirm you are a human" in lowered
        or "verify you are human" in lowered
        or "security verification" in lowered
        or "正在进行安全验证" in lowered
        or "验证您不是自动程序" in lowered
        or ("cloudflare" in lowered and ("ray id" in lowered or "security service" in lowered))
        or "id.elsevier.com" in lowered
    )
    return {
        "challenge_page": blocked,
        "bot_verification_page": blocked,
    }


def choose_start_urls(row: dict[str, Any]) -> list[dict[str, str]]:
    source_hint = field_text(row, "source_hint").lower() or "auto"
    starts: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: str, reason: str) -> None:
        if not url:
            return
        if url in seen:
            return
        seen.add(url)
        starts.append({"url": url, "reason": reason})

    entry_url = field_text(row, "entry_url")
    if entry_url:
        add(entry_url, "entry_url")

    for url in split_multi_value(field_text(row, "candidate_urls")):
        add(url, "candidate_urls")
    for url in extract_urls(field_text(row, "note")):
        add(url, "note")

    doi = field_text(row, "doi")
    if doi:
        doi_url = f"https://doi.org/{doi}"
        if source_hint == "doi":
            starts.insert(0, {"url": doi_url, "reason": "doi"})
        else:
            add(doi_url, "doi")

    def score(item: dict[str, str]) -> tuple[int, str]:
        url = item["url"].lower()
        primary = 0
        if source_hint in {"auto", ""}:
            primary = 0
        elif source_hint in url:
            primary = 100
        elif source_hint == "wos" and "webofscience.com" in url:
            primary = 100
        elif source_hint == "cnki" and "cnki" in url:
            primary = 100
        elif source_hint == "sciencedirect" and "sciencedirect.com" in url:
            primary = 100
        elif is_doi_url(url):
            primary = 30
        return (-primary, item["reason"])

    starts.sort(key=score)
    return starts


def make_target_name(row: dict[str, Any]) -> str:
    number = field_text(row, "number") or "0"
    try:
        label = f"{int(number):03d}"
    except Exception:
        label = sanitize_name(number, "000")
    name_basis = field_text(row, "doi") or field_text(row, "title") or number
    return f"{label}_{sanitize_name(name_basis, f'reference_{label}')}.pdf"


def write_utf8_no_bom(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(raw[3:])


def read_manifest_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class DevToolsClient:
    def __init__(self, debug_port: int) -> None:
        self.base = f"http://127.0.0.1:{debug_port}"

    def http_get(self, url: str, method: str = "GET") -> str:
        req = Request(url, method=method)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def open_page(self, url: str) -> dict[str, Any]:
        raw = self.http_get(f"{self.base}/json/new?{quote(url, safe=':/?&=%')}", method="PUT")
        return json.loads(raw)

    def close_page(self, page_id: str) -> None:
        try:
            self.http_get(f"{self.base}/json/close/{page_id}")
        except Exception:
            pass

    def call(self, ws_url: str, method: str, params: dict[str, Any] | None = None, msg_id: int = 1) -> dict[str, Any]:
        ws = websocket.create_connection(ws_url, timeout=180, suppress_origin=True)
        try:
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == msg_id:
                    return msg
        finally:
            ws.close()

    def evaluate_value(self, ws_url: str, expression: str, *, await_promise: bool = False, msg_id: int = 1) -> Any:
        msg = self.call(
            ws_url,
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
            msg_id=msg_id,
        )
        return msg.get("result", {}).get("result", {}).get("value")

    def evaluate_json(self, ws_url: str, expression: str, *, await_promise: bool = False, msg_id: int = 1) -> dict[str, Any]:
        value = self.evaluate_value(ws_url, expression, await_promise=await_promise, msg_id=msg_id)
        return value if isinstance(value, dict) else {}


def collect_page_snapshot(devtools: DevToolsClient, ws_url: str) -> dict[str, Any]:
    meta = devtools.evaluate_json(ws_url, PAGE_META_JS, msg_id=11) or {}
    html = devtools.evaluate_value(
        ws_url,
        "document.documentElement ? document.documentElement.outerHTML : ''",
        msg_id=12,
    ) or ""
    meta["html"] = html
    meta["detected_source"] = detect_source(str(meta.get("href", "")), html, str(meta.get("title", "")))
    meta.update(
        challenge_flags(
            str(meta.get("href", "")),
            html,
            str(meta.get("title", "")),
            str(meta.get("body_text", "")),
        )
    )
    meta.setdefault("candidate_urls", [])
    meta.setdefault("body_text", "")
    meta.setdefault("title", "")
    meta.setdefault("href", "")
    meta.setdefault("ready_state", "")
    meta.setdefault("has_pdf_viewer", False)
    return meta


def merge_candidate_urls(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in snapshot.get("candidate_urls", []):
        url = normalize_space(str(item.get("url", "")))
        reason = normalize_space(str(item.get("reason", ""))) or "dom"
        if url and url not in seen:
            seen.add(url)
            merged.append({"url": url, "reason": reason})
    for url in extract_urls(snapshot.get("html", "")):
        if url not in seen:
            seen.add(url)
            merged.append({"url": url, "reason": "html_regex"})
    return merged


def rank_candidate(current_url: str, source: str, candidate: dict[str, str]) -> dict[str, Any] | None:
    url = candidate["url"]
    lowered = url.lower()
    reason = candidate["reason"].lower()
    if not url or url == current_url:
        return None
    if any(token in lowered for token in LOGIN_BLOCKLIST):
        return None
    if lowered.startswith(("javascript:", "mailto:")):
        return None
    if "tdm/tdmrep-policy" in lowered:
        return None
    if source == "sciencedirect" and looks_like_pdf_url(url):
        if not any(domain in lowered for domain in ("sciencedirect.com", "elsevier.com", "sciencedirectassets.com")):
            return None

    score = 0
    kind = "next_url"
    if looks_like_pdf_url(url):
        score = 100
        kind = "pdf_url"
    elif same_origin(current_url, url) and looks_like_download_url(url):
        score = 96
        kind = "page_fetch"
    elif looks_like_download_url(url):
        score = 88
        kind = "next_url"
    elif is_doi_url(url):
        score = 82
        kind = "next_url"
    elif is_publisher_article_url(url):
        score = 78
        kind = "next_url"
    elif any(domain in lowered for domain in PUBLISHER_HINTS):
        score = 65

    if "full text" in reason or "全文" in reason or "download" in reason or "pdf" in reason:
        score += 10
    if source == "wos" and (is_doi_url(url) or is_publisher_article_url(url)):
        score += 15
    if source == "cnki" and same_origin(current_url, url) and looks_like_download_url(url):
        score += 15
    if source == "sciencedirect" and looks_like_pdf_url(url):
        score += 12

    if score < 60:
        return None
    return {
        "kind": kind,
        "url": url,
        "reason": candidate["reason"],
        "score": score,
    }


def choose_route(snapshot: dict[str, Any]) -> dict[str, Any]:
    source = snapshot["detected_source"]
    current_url = str(snapshot.get("href", ""))
    html = str(snapshot.get("html", ""))

    if snapshot.get("challenge_page"):
        return {
            "kind": "blocked",
            "url": current_url,
            "reason": "challenge_page",
            "source": source,
        }

    if snapshot.get("has_pdf_viewer") or looks_like_pdf_url(current_url):
        return {
            "kind": "pdf_url",
            "url": current_url,
            "reason": "viewer_or_pdf_url",
            "source": source,
        }

    if source == "sciencedirect":
        pdf_url = infer_pdf_url_from_sciencedirect(html)
        if pdf_url:
            return {
                "kind": "pdf_url",
                "url": pdf_url,
                "reason": "sciencedirect_pdf_metadata",
                "source": source,
            }

    ranked = []
    for candidate in merge_candidate_urls(snapshot):
        route = rank_candidate(current_url, source, candidate)
        if route is not None:
            ranked.append(route)
    ranked.sort(key=lambda item: item["score"], reverse=True)
    if ranked:
        best = ranked[0]
        best["source"] = source
        best["candidate_count"] = len(ranked)
        return best

    doi = extract_first_doi(f"{snapshot.get('body_text', '')}\n{html[:5000]}")
    if doi:
        doi_url = f"https://doi.org/{doi}"
        if doi_url != current_url:
            return {
                "kind": "next_url",
                "url": doi_url,
                "reason": "doi_from_page",
                "source": source,
            }

    return {
        "kind": "none",
        "url": current_url,
        "reason": "no_download_route_found",
        "source": source,
    }


def extract_pdf_bytes_from_viewer(devtools: DevToolsClient, ws_url: str) -> bytes | None:
    value = devtools.evaluate_value(
        ws_url,
        """
new Promise(resolve => {
  const tick = () => {
    const app = window.PDFViewerApplication;
    if (app && app.pdfDocument) {
      app.pdfDocument.getData().then(data => {
        const chunk = 0x8000;
        let binary = '';
        for (let i = 0; i < data.length; i += chunk) {
          binary += String.fromCharCode.apply(null, data.subarray(i, i + chunk));
        }
        resolve(btoa(binary));
      }).catch(err => resolve('ERR:' + String(err)));
    } else {
      setTimeout(tick, 1000);
    }
  };
  tick();
})
        """.strip(),
        await_promise=True,
        msg_id=21,
    )
    if not value or (isinstance(value, str) and value.startswith("ERR:")):
        return None
    return base64.b64decode(value)


def fetch_binary_from_page(devtools: DevToolsClient, ws_url: str, target_url: str) -> tuple[bytes | None, dict[str, str]]:
    payload = devtools.evaluate_value(
        ws_url,
        f"""
new Promise(resolve => {{
  fetch({json.dumps(target_url)}, {{ credentials: 'include' }})
    .then(async response => {{
      const buffer = await response.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      const chunk = 0x8000;
      let binary = '';
      for (let i = 0; i < bytes.length; i += chunk) {{
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
      }}
      resolve({{
        ok: response.ok,
        status: response.status,
        contentType: response.headers.get('content-type') || '',
        base64: btoa(binary),
      }});
    }})
    .catch(err => resolve({{ ok: false, status: 0, contentType: '', error: String(err), base64: '' }}));
}})
        """.strip(),
        await_promise=True,
        msg_id=22,
    )
    if not isinstance(payload, dict):
        return None, {"status": "no_payload", "content_type": ""}
    raw = payload.get("base64") or ""
    content_type = str(payload.get("contentType", "") or "")
    if not raw:
        return None, {
            "status": str(payload.get("status", 0)),
            "content_type": content_type,
            "error": str(payload.get("error", "")),
        }
    return base64.b64decode(raw), {
        "status": str(payload.get("status", 0)),
        "content_type": content_type,
    }


def open_pdf_and_extract(devtools: DevToolsClient, pdf_url: str, page_wait_seconds: int) -> bytes | None:
    pdf_page = None
    try:
        pdf_page = devtools.open_page(pdf_url)
        time.sleep(page_wait_seconds)
        ws_url = pdf_page["webSocketDebuggerUrl"]
        try:
            snapshot = collect_page_snapshot(devtools, ws_url)
        except Exception:
            snapshot = {}
        direct_url = str(snapshot.get("href", "") or pdf_url)
        if looks_like_pdf_url(direct_url):
            try:
                req = Request(direct_url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=60) as resp:
                    payload = resp.read()
                if payload.startswith(b"%PDF-"):
                    return payload
            except Exception:
                pass
        try:
            return extract_pdf_bytes_from_viewer(devtools, ws_url)
        except (WebSocketTimeoutException, Exception):
            return None
    finally:
        if pdf_page:
            devtools.close_page(pdf_page["id"])


def process_row(
    devtools: DevToolsClient,
    row: dict[str, Any],
    pdf_dir: Path,
    page_wait_seconds: int,
    max_hops: int,
) -> dict[str, str]:
    target_name = make_target_name(row)
    target_path = pdf_dir / target_name
    if target_path.exists() and target_path.stat().st_size > 0:
        return {
            **row,
            "status": "downloaded",
            "pdf_path": str(target_path),
            "source_url": "",
            "resolved_source": "",
            "route_trace_json": "[]",
            "note": "existing_file",
        }

    starts = choose_start_urls(row)
    if not starts:
        return {
            **row,
            "status": "no_candidate_urls",
            "pdf_path": "",
            "source_url": "",
            "resolved_source": "",
            "route_trace_json": "[]",
            "note": field_text(row, "note"),
        }

    last_result: dict[str, str] | None = None
    full_trace: list[dict[str, Any]] = []
    for start in starts:
        current_url = start["url"]
        visited: set[str] = set()
        for hop in range(1, max_hops + 1):
            if current_url in visited:
                last_result = {
                    **row,
                    "status": "loop_detected",
                    "pdf_path": "",
                    "source_url": current_url,
                    "resolved_source": "",
                    "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                    "note": "url_loop_detected",
                }
                break
            visited.add(current_url)

            page = None
            try:
                page = devtools.open_page(current_url)
                time.sleep(page_wait_seconds)
                snapshot = collect_page_snapshot(devtools, page["webSocketDebuggerUrl"])
                route = choose_route(snapshot)
                trace_item = {
                    "start_url": start["url"],
                    "start_reason": start["reason"],
                    "hop": hop,
                    "page_url": snapshot.get("href", ""),
                    "page_title": snapshot.get("title", ""),
                    "detected_source": snapshot.get("detected_source", ""),
                    "route_kind": route.get("kind", ""),
                    "route_url": route.get("url", ""),
                    "route_reason": route.get("reason", ""),
                    "challenge_page": snapshot.get("challenge_page", False),
                }
                full_trace.append(trace_item)

                if route["kind"] == "blocked":
                    last_result = {
                        **row,
                        "status": "challenge_page",
                        "pdf_path": "",
                        "source_url": snapshot.get("href", ""),
                        "resolved_source": snapshot.get("detected_source", ""),
                        "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                        "note": "complete manual verification in the live browser and retry",
                    }
                    break

                if route["kind"] == "page_fetch":
                    pdf_bytes, fetch_meta = fetch_binary_from_page(
                        devtools,
                        page["webSocketDebuggerUrl"],
                        route["url"],
                    )
                    if pdf_bytes and pdf_bytes.startswith(b"%PDF-"):
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        target_path.write_bytes(pdf_bytes)
                        return {
                            **row,
                            "status": "downloaded",
                            "pdf_path": str(target_path),
                            "source_url": route["url"],
                            "resolved_source": snapshot.get("detected_source", ""),
                            "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                            "note": f"page_fetch:{fetch_meta.get('content_type', '')}",
                        }
                    last_result = {
                        **row,
                        "status": "page_fetch_failed",
                        "pdf_path": "",
                        "source_url": route["url"],
                        "resolved_source": snapshot.get("detected_source", ""),
                        "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                        "note": f"status={fetch_meta.get('status', '')}; content_type={fetch_meta.get('content_type', '')}",
                    }
                    break

                if route["kind"] == "pdf_url":
                    pdf_bytes = None
                    if snapshot.get("has_pdf_viewer") and route["url"] == snapshot.get("href"):
                        pdf_bytes = extract_pdf_bytes_from_viewer(devtools, page["webSocketDebuggerUrl"])
                    if (
                        not pdf_bytes
                        and snapshot.get("detected_source") == "sciencedirect"
                    ):
                        pdf_bytes, fetch_meta = fetch_binary_from_page(
                            devtools,
                            page["webSocketDebuggerUrl"],
                            route["url"],
                        )
                        if pdf_bytes and pdf_bytes.startswith(b"%PDF-"):
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            target_path.write_bytes(pdf_bytes)
                            return {
                                **row,
                                "status": "downloaded",
                                "pdf_path": str(target_path),
                                "source_url": route["url"],
                                "resolved_source": snapshot.get("detected_source", ""),
                                "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                                "note": f"page_fetch_pdf_url:{fetch_meta.get('content_type', '')}",
                            }
                    if not pdf_bytes:
                        pdf_bytes = open_pdf_and_extract(devtools, route["url"], page_wait_seconds)
                    if pdf_bytes and pdf_bytes.startswith(b"%PDF-"):
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        target_path.write_bytes(pdf_bytes)
                        return {
                            **row,
                            "status": "downloaded",
                            "pdf_path": str(target_path),
                            "source_url": route["url"],
                            "resolved_source": snapshot.get("detected_source", ""),
                            "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                            "note": route["reason"],
                        }
                    last_result = {
                        **row,
                        "status": "viewer_extract_failed",
                        "pdf_path": "",
                        "source_url": route["url"],
                        "resolved_source": snapshot.get("detected_source", ""),
                        "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                        "note": route["reason"],
                    }
                    break

                if route["kind"] == "next_url":
                    current_url = route["url"]
                    continue

                last_result = {
                    **row,
                    "status": "no_download_route",
                    "pdf_path": "",
                    "source_url": snapshot.get("href", ""),
                    "resolved_source": snapshot.get("detected_source", ""),
                    "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
                    "note": route["reason"],
                }
                break
            finally:
                if page:
                    devtools.close_page(page["id"])

    return last_result or {
        **row,
        "status": "unknown_failure",
        "pdf_path": "",
        "source_url": "",
        "resolved_source": "",
        "route_trace_json": json.dumps(full_trace, ensure_ascii=False),
        "note": "no result generated",
    }
