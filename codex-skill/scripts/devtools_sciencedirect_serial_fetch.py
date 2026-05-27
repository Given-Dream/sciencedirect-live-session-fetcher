#!/usr/bin/env python3
"""Serial publisher PDF fetch through an already logged-in Chromium DevTools session.

Workflow:
1. Reuse an existing Chrome or Edge window launched with --remote-debugging-port.
2. Open one article tab at a time from DOI or candidate URL.
3. Read article HTML through DevTools Runtime.evaluate.
4. Extract ScienceDirect pdfDownload metadata or generic PDF iframe/link targets.
5. Open the PDF route in a new tab when needed.
6. Extract the PDF bytes from the authorized page context or PDF viewer.
7. Save the PDF, close the temporary tabs, sleep a few seconds, then continue.

This stays inside the user's live browser session and avoids direct bulk HTTP bursts.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import Request, urlopen


PDF_RE = re.compile(
    r'"pdfDownload":\{"isPdfFullText":(?:true|false),"urlMetadata":\{"queryParams":\{"md5":"([^"]+)","pid":"([^"]+)"\},"pii":"([^"]+)","pdfExtension":"([^"]+)","path":"([^"]+)"\}\}'
)
URL_RE = re.compile(r"https?://[^\s;,\)]+", flags=re.I)
SIGNED_PDF_RE = re.compile(r"https://pdf\.sciencedirectassets\.com/[^\s\"'<>]+", flags=re.I)
IEEE_AR_NUMBER_RE = re.compile(r"/document/(\d+)|[?&]arnumber=(\d+)", flags=re.I)
IEEE_DOCUMENT_RE = re.compile(r"(?:https?://ieeexplore\.ieee\.org)?/document/(\d+)", flags=re.I)
IEEE_ARTICLE_NUMBER_FIELD_RE = re.compile(
    r'"(?:articleNumber|arnumber|articleId|documentId)"\s*:\s*"?(\d{4,})"?',
    flags=re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serial publisher PDF fetch through DevTools")
    parser.add_argument("--input-csv", required=True, help="CSV with number, doi, note columns")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--debug-port", type=int, default=9222, help="Chrome or Edge remote debugging port")
    parser.add_argument("--page-wait-seconds", type=int, default=8, help="Wait after opening each tab")
    parser.add_argument("--inter-item-sleep-seconds", type=int, default=8, help="Pause between rows")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N rows")
    return parser.parse_args()


def sanitize_name(text: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().replace(" ", "_")
    cleaned = cleaned[:140]
    return cleaned or fallback


def make_target_name(number: str, title: str, doi: str) -> str:
    label = sanitize_name(title, "") or sanitize_name(doi, f"reference_{number}")
    return f"{int(number):03d}-{label}.pdf"


def extract_urls(note: str) -> list[str]:
    urls = []
    for match in URL_RE.findall(note or ""):
        url = match.rstrip(".,);")
        if url not in urls:
            urls.append(url)
    return urls


def choose_article_url(row: dict[str, str]) -> str:
    doi = (row.get("doi") or "").strip()
    urls = extract_urls(row.get("note", ""))
    if doi.lower().startswith("10.1109/"):
        for url in urls:
            lowered = url.lower()
            if "ieeexplore.ieee.org" not in lowered:
                continue
            arnumber = extract_ieee_arnumber(url)
            if arnumber:
                return ieee_document_url(arnumber)
        for url in urls:
            if "doi.org/" in url.lower():
                return url
        if doi:
            return f"https://doi.org/{doi}"
        for url in urls:
            if "ieeexplore.ieee.org" in url.lower():
                return url
        return f"https://doi.org/{doi}"
    for url in urls:
        lowered = url.lower()
        if "doi.org/" in lowered or "sciencedirect.com/" in lowered:
            return url
    if urls:
        return urls[0]
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def extract_ieee_arnumber(text: str) -> str:
    match = IEEE_AR_NUMBER_RE.search(text or "")
    if not match:
        return ""
    return next((value for value in match.groups() if value), "")


def is_ieee_url(url: str) -> bool:
    return "ieeexplore.ieee.org" in (urlparse(url).netloc or "").lower()


def is_ieee_document_url(url: str) -> bool:
    return is_ieee_url(url) and "/document/" in urlparse(url).path.lower()


def is_ieee_search_url(url: str) -> bool:
    return is_ieee_url(url) and "/search/" in urlparse(url).path.lower()


def is_ieee_stamp_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return is_ieee_url(url) and ("/stamp/" in path or "/stamppdf/" in path)


def ieee_document_url(arnumber: str) -> str:
    return f"https://ieeexplore.ieee.org/document/{arnumber}" if arnumber else ""


def ieee_stamp_url(arnumber: str) -> str:
    return f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}" if arnumber else ""


def ieee_stamp_pdf_url(arnumber: str, article_url: str = "") -> str:
    if not arnumber:
        return ""
    url = f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={arnumber}"
    if article_url:
        ref = base64.b64encode(article_url.encode("utf-8")).decode("ascii")
        url += f"&ref={ref}"
    return url


def normalize_match_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def title_match_score(title: str, haystack: str) -> int:
    words = [word for word in normalize_match_text(title).split() if len(word) >= 4]
    if not words:
        return 0
    haystack_norm = set(normalize_match_text(haystack).split())
    if not haystack_norm:
        return 0
    hits = sum(1 for word in words if word in haystack_norm)
    return int(60 * hits / max(len(words), 1))


def find_ieee_arnumber_near_doi(text: str, doi: str) -> str:
    if not text or not doi:
        return ""
    lowered = text.lower()
    needle = doi.lower()
    index = lowered.find(needle)
    if index < 0:
        return ""
    window = text[max(0, index - 2500) : index + 2500]
    candidates = []
    for pattern in (IEEE_DOCUMENT_RE, IEEE_ARTICLE_NUMBER_FIELD_RE):
        for match in pattern.finditer(window):
            arnumber = next((value for value in match.groups() if value), "")
            if arnumber and arnumber not in candidates:
                candidates.append(arnumber)
    return candidates[0] if len(candidates) == 1 else ""


def write_utf8_no_bom(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        path.write_bytes(raw[3:])


class DevToolsClient:
    def __init__(self, debug_port: int) -> None:
        self.base = f"http://127.0.0.1:{debug_port}"

    def http_get(self, url: str, method: str = "GET") -> str:
        req = Request(url, method=method)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def open_page(self, url: str) -> dict:
        raw = self.http_get(f"{self.base}/json/new?{quote(url, safe=':/?&=%')}", method="PUT")
        return json.loads(raw)

    def list_pages(self) -> list[dict]:
        return json.loads(self.http_get(f"{self.base}/json"))

    def close_page(self, page_id: str) -> None:
        try:
            self.http_get(f"{self.base}/json/close/{page_id}")
        except Exception:
            pass

    def call(self, ws_url: str, method: str, params: dict | None = None, msg_id: int = 1) -> dict:
        import websocket

        ws = websocket.create_connection(ws_url, timeout=180, suppress_origin=True)
        try:
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == msg_id:
                    return msg
        finally:
            ws.close()

    def evaluate(self, ws_url: str, expression: str, *, await_promise: bool = False, msg_id: int = 1):
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
        if "error" in msg:
            return None
        return msg.get("result", {}).get("result", {}).get("value")


def extract_pdf_bytes_from_viewer(devtools: DevToolsClient, ws_url: str) -> bytes | None:
    value = devtools.evaluate(
        ws_url,
        """
new Promise(resolve => {
  const deadline = Date.now() + 15000;
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
    } else if (Date.now() > deadline) {
      resolve('ERR:timeout_waiting_for_pdf_viewer');
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


def extract_file_param_from_viewer_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"chrome-extension", "extension"}:
        return ""
    values = parse_qs(parsed.query).get("file") or []
    return values[0] if values else ""


def extract_signed_pdf_url_from_text(text: str) -> str:
    if not text:
        return ""
    decoded = html.unescape(text)
    match = SIGNED_PDF_RE.search(decoded)
    return match.group(0) if match else ""


def current_signed_pdf_tabs(devtools: DevToolsClient, pii: str = "") -> list[str]:
    urls = []
    for page in devtools.list_pages():
        url = page.get("url", "")
        file_url = extract_file_param_from_viewer_url(url)
        candidate = file_url or url
        if pii and pii not in candidate:
            continue
        if "pdf.sciencedirectassets.com" in candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def choose_signed_pdf_url(devtools: DevToolsClient, pii: str) -> str:
    for url in current_signed_pdf_tabs(devtools, pii):
        if pii and pii in url:
            return url
    return ""


def fetch_pdf_bytes_from_signed_url(url: str) -> bytes | None:
    if not url:
        return None
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception:
        return None
    return data if data.startswith(b"%PDF-") else None


def fetch_pdf_bytes_in_page(devtools: DevToolsClient, ws_url: str, pdf_url: str, *, msg_id: int = 31) -> bytes | None:
    value = devtools.evaluate(
        ws_url,
        f"""
new Promise(resolve => {{
  fetch({json.dumps(pdf_url)}, {{ credentials: 'include' }})
    .then(resp => resp.arrayBuffer())
    .then(buf => {{
      const data = new Uint8Array(buf);
      const chunk = 0x8000;
      let binary = '';
      for (let i = 0; i < data.length; i += chunk) {{
        binary += String.fromCharCode.apply(null, data.subarray(i, i + chunk));
      }}
      resolve(btoa(binary));
    }})
    .catch(err => resolve('ERR:' + String(err)));
}})
        """.strip(),
        await_promise=True,
        msg_id=msg_id,
    )
    if not value or (isinstance(value, str) and value.startswith("ERR:")):
        return None
    try:
        data = base64.b64decode(value)
    except Exception:
        return None
    return data if data.startswith(b"%PDF-") else None


def normalize_pdf_url(current_url: str, value: str) -> str:
    value = (value or "").strip()
    if not value or value.startswith(("javascript:", "mailto:")):
        return ""
    return urljoin(current_url, html.unescape(value))


def score_pdf_url(url: str, text: str, source: str = "") -> int:
    lowered = " ".join((url, text, source)).lower()
    score = 0
    if "ieeexplore.ieee.org/stamppdf/getpdf.jsp" in lowered:
        score += 90
    if "ieeexplore.ieee.org/stamp/stamp.jsp" in lowered:
        score += 65
    if "ieeexplore.ieee.org/document/" in lowered:
        score += 55
    if "citation_pdf_url" in lowered:
        score += 50
    if ".pdf" in lowered:
        score += 40
    if "/pdf" in lowered or "pdf/" in lowered:
        score += 30
    if "download" in lowered:
        score += 20
    if "pdf" in lowered:
        score += 10
    if any(noise in lowered for noise in ("privacy", "cookie", "terms", "cover-image")):
        score -= 40
    return score


def find_generic_pdf_url(devtools: DevToolsClient, ws_url: str, current_url: str, *, msg_id: int = 41) -> str:
    candidates = devtools.evaluate(
        ws_url,
        """
(() => {
  const out = [];
  const push = (url, text, source) => {
    if (url) out.push({url: String(url), text: String(text || ''), source});
  };
  document.querySelectorAll('meta').forEach(meta => {
    const key = (meta.getAttribute('name') || meta.getAttribute('property') || '').toLowerCase();
    if (key.includes('citation_pdf_url') || key.includes('bepress_citation_pdf_url')) {
      push(meta.getAttribute('content'), key, 'meta');
    }
  });
  document.querySelectorAll('a[href], iframe[src], embed[src], object[data]').forEach(el => {
    const url = el.getAttribute('href') || el.getAttribute('src') || el.getAttribute('data');
    const text = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    push(url, text, el.tagName.toLowerCase());
  });
  return out;
})()
        """.strip(),
        msg_id=msg_id,
    )
    ranked = []
    for item in candidates or []:
        url = normalize_pdf_url(current_url, item.get("url", ""))
        if not url:
            continue
        arnumber = extract_ieee_arnumber(url)
        if arnumber and "ieeexplore.ieee.org" in url.lower():
            if not is_ieee_document_url(current_url):
                continue
            article_number = extract_ieee_arnumber(current_url)
            if article_number and arnumber != article_number:
                continue
            if is_ieee_document_url(url):
                url = ieee_stamp_url(arnumber)
        score = score_pdf_url(url, item.get("text", ""), item.get("source", ""))
        if score >= 30:
            ranked.append((score, url))
    if not ranked:
        arnumber = extract_ieee_arnumber(current_url)
        if not arnumber and not is_ieee_search_url(current_url):
            text = devtools.evaluate(
                ws_url,
                "document.documentElement.innerText || document.documentElement.outerHTML",
                msg_id=msg_id + 100,
            ) or ""
            arnumber = extract_ieee_arnumber(text)
        if arnumber and is_ieee_document_url(current_url):
            return ieee_stamp_url(arnumber)
        return ""
    ranked.sort(reverse=True)
    return ranked[0][1]


def current_generic_pdf_tabs(devtools: DevToolsClient, article_url: str, pii: str = "") -> list[str]:
    urls = []
    article_host = urlparse(article_url).netloc.lower()
    article_number = extract_ieee_arnumber(article_url)
    for page in devtools.list_pages():
        url = page.get("url", "")
        file_url = extract_file_param_from_viewer_url(url)
        candidate = file_url or url
        lowered = candidate.lower()
        if candidate in urls:
            continue
        if pii and candidate.startswith("https://pdf.sciencedirectassets.com/") and pii in candidate:
            urls.append(candidate)
            continue
        if article_number and article_number in candidate and "ieeexplore.ieee.org/stamppdf/getpdf.jsp" in lowered:
            urls.append(candidate)
            continue
        if article_host and article_host in urlparse(candidate).netloc.lower() and score_pdf_url(candidate, "") >= 60:
            urls.append(candidate)
    return urls


def resolve_ieee_article_url(
    devtools: DevToolsClient,
    ws_url: str,
    current_url: str,
    row: dict[str, str],
    *,
    msg_id: int = 200,
) -> tuple[str, str]:
    """Resolve IEEE search/DOI landing pages to the real article detail URL.

    IEEE access behaves more like a normal web app than a static PDF endpoint.
    Starting from the document detail page keeps the institutional session path
    intact and avoids treating the browser like a direct stamp.jsp downloader.
    """
    doi = (row.get("doi") or "").strip()
    title = (row.get("title") or "").strip()

    if is_ieee_document_url(current_url):
        return current_url, "ieee_document_page"
    if is_ieee_stamp_url(current_url):
        arnumber = extract_ieee_arnumber(current_url)
        if arnumber:
            return ieee_document_url(arnumber), "ieee_stamp_normalized_to_document"

    page_data = devtools.evaluate(
        ws_url,
        """
(() => {
  const links = [...document.querySelectorAll('a[href]')].map(a => ({
    href: a.href,
    text: (a.innerText || a.getAttribute('aria-label') || a.getAttribute('title') || '').trim(),
    context: (
      a.closest('xpl-results-item, .List-results-items, .result-item, li, article, section, div')?.innerText
      || a.parentElement?.innerText
      || ''
    ).trim()
  }));
  const text = document.documentElement.innerText || '';
  const html = document.documentElement.outerHTML || '';
  return { links, text, html };
})()
        """.strip(),
        msg_id=msg_id,
    ) or {}
    links = page_data.get("links") or []
    body_text = page_data.get("text") or ""
    body_html = page_data.get("html") or ""

    arnumber = find_ieee_arnumber_near_doi(body_html + "\n" + body_text, doi)
    if arnumber:
        return ieee_document_url(arnumber), "ieee_article_number_near_doi"

    ranked: list[tuple[int, str]] = []
    for item in links:
        href = normalize_pdf_url(current_url, item.get("href", ""))
        arnumber = extract_ieee_arnumber(href)
        if not arnumber or not is_ieee_url(href):
            continue
        nearby_text = " ".join((item.get("text", ""), item.get("context", ""), href))
        doi_hit = bool(doi and doi.lower() in nearby_text.lower())
        title_score = title_match_score(title, nearby_text)
        if is_ieee_document_url(href) and (doi_hit or title_score >= 35):
            score = (80 if doi_hit else 0) + title_score
            ranked.append((score, ieee_document_url(arnumber)))

    if ranked:
        ranked.sort(reverse=True)
        return ranked[0][1], "ieee_article_link_from_landing_page"

    return current_url, "ieee_article_url_unresolved"


def save_pdf_bytes(target_path: Path, pdf_bytes: bytes) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(pdf_bytes)


def download_generic_pdf_url(
    devtools: DevToolsClient,
    article_ws_url: str,
    article_url: str,
    pdf_url: str,
    target_path: Path,
    page_wait_seconds: int,
    pii: str = "",
) -> tuple[bool, str, str]:
    candidates = [pdf_url, *current_generic_pdf_tabs(devtools, article_url, pii)]
    seen = set()
    pdf_page = None

    try:
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            pdf_bytes = fetch_pdf_bytes_in_page(devtools, article_ws_url, candidate, msg_id=50 + len(seen))
            if pdf_bytes:
                save_pdf_bytes(target_path, pdf_bytes)
                return True, candidate, "generic_in_page_fetch"

        pdf_page = devtools.open_page(pdf_url)
        time.sleep(page_wait_seconds)
        pdf_ws_url = pdf_page["webSocketDebuggerUrl"]
        viewer_url = devtools.evaluate(pdf_ws_url, "location.href", msg_id=70) or ""
        viewer_html = devtools.evaluate(pdf_ws_url, "document.documentElement.outerHTML", msg_id=71) or ""
        nested_url = (
            extract_file_param_from_viewer_url(viewer_url)
            or extract_signed_pdf_url_from_text(viewer_url)
            or extract_signed_pdf_url_from_text(viewer_html)
            or find_generic_pdf_url(devtools, pdf_ws_url, viewer_url or pdf_url, msg_id=72)
        )
        for candidate in [nested_url, viewer_url, pdf_url, *current_generic_pdf_tabs(devtools, article_url, pii)]:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            for ws_url, label in ((article_ws_url, "generic_article_context_fetch"), (pdf_ws_url, "generic_pdf_context_fetch")):
                pdf_bytes = fetch_pdf_bytes_in_page(devtools, ws_url, candidate, msg_id=80 + len(seen))
                if pdf_bytes:
                    save_pdf_bytes(target_path, pdf_bytes)
                    return True, candidate, label
            pdf_bytes = fetch_pdf_bytes_from_signed_url(candidate)
            if pdf_bytes:
                save_pdf_bytes(target_path, pdf_bytes)
                return True, candidate, "generic_http_fetch"

        pdf_bytes = extract_pdf_bytes_from_viewer(devtools, pdf_ws_url)
        if pdf_bytes:
            save_pdf_bytes(target_path, pdf_bytes)
            return True, pdf_url, "generic_pdfjs_extract"
        return False, pdf_url, "generic_pdf_fetch_failed"
    finally:
        if pdf_page:
            devtools.close_page(pdf_page["id"])


def download_ieee_pdf_from_article_context(
    devtools: DevToolsClient,
    article_ws_url: str,
    article_url: str,
    target_path: Path,
) -> tuple[bool, str, str]:
    arnumber = extract_ieee_arnumber(article_url)
    if not arnumber:
        return False, article_url, "ieee_no_article_number"
    pdf_url = ieee_stamp_pdf_url(arnumber, article_url)
    pdf_bytes = fetch_pdf_bytes_in_page(devtools, article_ws_url, pdf_url, msg_id=210)
    if pdf_bytes:
        save_pdf_bytes(target_path, pdf_bytes)
        return True, pdf_url, "ieee_article_context_fetch"
    return False, pdf_url, "ieee_article_context_fetch_failed"


def process_row(
    devtools: DevToolsClient,
    row: dict[str, str],
    pdf_dir: Path,
    page_wait_seconds: int,
) -> dict[str, str]:
    article_url = choose_article_url(row)
    target_name = make_target_name(row["number"], row.get("title", ""), row.get("doi", ""))
    target_path = pdf_dir / target_name
    if target_path.exists() and target_path.stat().st_size > 0:
        return {
            **row,
            "status": "downloaded",
            "pdf_path": str(target_path),
            "source_url": article_url,
            "note": "existing_file",
        }

    if not article_url:
        return {**row, "status": "no_candidate_urls", "pdf_path": "", "source_url": "", "note": row.get("note", "")}

    article_page = None
    pdf_page = None
    try:
        article_page = devtools.open_page(article_url)
        time.sleep(page_wait_seconds)
        article_html = devtools.evaluate(
            article_page["webSocketDebuggerUrl"],
            "document.documentElement.outerHTML",
            msg_id=10,
        ) or ""
        title = devtools.evaluate(article_page["webSocketDebuggerUrl"], "document.title", msg_id=11) or ""
        current_url = devtools.evaluate(article_page["webSocketDebuggerUrl"], "location.href", msg_id=12) or article_url
        if (
            (row.get("doi") or "").strip().lower().startswith("10.1109/")
            and not is_ieee_document_url(current_url)
        ):
            resolved_url, resolve_note = resolve_ieee_article_url(
                devtools,
                article_page["webSocketDebuggerUrl"],
                current_url,
                row,
                msg_id=110,
            )
            if resolved_url != current_url and is_ieee_document_url(resolved_url):
                devtools.close_page(article_page["id"])
                article_page = devtools.open_page(resolved_url)
                time.sleep(page_wait_seconds)
                article_html = devtools.evaluate(
                    article_page["webSocketDebuggerUrl"],
                    "document.documentElement.outerHTML",
                    msg_id=120,
                ) or ""
                title = devtools.evaluate(article_page["webSocketDebuggerUrl"], "document.title", msg_id=121) or ""
                current_url = (
                    devtools.evaluate(article_page["webSocketDebuggerUrl"], "location.href", msg_id=122)
                    or resolved_url
                )
            elif not is_ieee_document_url(current_url):
                return {
                    **row,
                    "status": "ieee_article_url_unresolved",
                    "pdf_path": "",
                    "source_url": current_url,
                    "note": resolve_note,
                }
        lowered_probe = (title + " " + current_url + " " + article_html[:2000]).lower()
        if (
            "请稍候" in title
            or "please wait" in lowered_probe
            or "tdm-reservation" in lowered_probe
            or "challenges.cloudflare.com" in lowered_probe
        ):
            return {
                **row,
                "status": "challenge_page",
                "pdf_path": "",
                "source_url": current_url,
                "note": (title or article_html[:500])[:500],
            }
        if (
            "this content is not included in your subscription" in lowered_probe
            or "reason=notincluded" in current_url.lower()
        ):
            return {
                **row,
                "status": "access_not_in_subscription",
                "pdf_path": "",
                "source_url": current_url,
                "note": (title or article_html[:500])[:500],
            }
        if (row.get("doi") or "").strip().lower().startswith("10.1109/") and is_ieee_document_url(current_url):
            ok, source_url, note = download_ieee_pdf_from_article_context(
                devtools,
                article_page["webSocketDebuggerUrl"],
                current_url,
                target_path,
            )
            if ok:
                return {
                    **row,
                    "status": "downloaded",
                    "pdf_path": str(target_path),
                    "source_url": source_url,
                    "note": note,
                }
            # Continue into generic discovery for older or unusual IEEE layouts.
        match = PDF_RE.search(article_html)
        if not match:
            generic_pdf_url = find_generic_pdf_url(
                devtools,
                article_page["webSocketDebuggerUrl"],
                current_url,
                msg_id=13,
            )
            if not generic_pdf_url:
                live_candidates = current_generic_pdf_tabs(devtools, current_url)
                generic_pdf_url = live_candidates[0] if live_candidates else ""
            if generic_pdf_url:
                ok, source_url, note = download_generic_pdf_url(
                    devtools,
                    article_page["webSocketDebuggerUrl"],
                    current_url,
                    generic_pdf_url,
                    target_path,
                    page_wait_seconds,
                )
                if ok:
                    return {
                        **row,
                        "status": "downloaded",
                        "pdf_path": str(target_path),
                        "source_url": source_url,
                        "note": note,
                    }
                return {
                    **row,
                    "status": "generic_pdf_fetch_failed",
                    "pdf_path": "",
                    "source_url": source_url,
                    "note": note,
                }
            snippet = (article_html[:500] or title)[:500]
            return {
                **row,
                "status": "no_pdf_metadata",
                "pdf_path": "",
                "source_url": article_url,
                "note": snippet,
            }

        md5, pid, pii, pdf_ext, path = match.groups()
        pdf_url = f"https://www.sciencedirect.com/{path}/{pii}{pdf_ext}?md5={md5}&pid={pid}"
        pdf_page = devtools.open_page(pdf_url)
        time.sleep(page_wait_seconds)
        viewer_url = devtools.evaluate(pdf_page["webSocketDebuggerUrl"], "location.href", msg_id=20) or ""
        viewer_html = devtools.evaluate(pdf_page["webSocketDebuggerUrl"], "document.documentElement.outerHTML", msg_id=22) or ""
        signed_pdf_url = extract_file_param_from_viewer_url(viewer_url)
        if not signed_pdf_url:
            signed_pdf_url = extract_signed_pdf_url_from_text(viewer_url) or extract_signed_pdf_url_from_text(viewer_html)
        if signed_pdf_url:
            pdf_url = signed_pdf_url
        else:
            signed_pdf_url = choose_signed_pdf_url(devtools, pii)
            if signed_pdf_url:
                pdf_url = signed_pdf_url
        pdf_bytes = fetch_pdf_bytes_in_page(devtools, article_page["webSocketDebuggerUrl"], pdf_url, msg_id=30)
        if not pdf_bytes:
            pdf_bytes = fetch_pdf_bytes_in_page(devtools, pdf_page["webSocketDebuggerUrl"], pdf_url, msg_id=31)
        if pdf_bytes and pdf_bytes.startswith(b"%PDF-"):
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(pdf_bytes)
            return {
                **row,
                "status": "downloaded",
                "pdf_path": str(target_path),
                "source_url": pdf_url,
                "note": "in_page_fetch",
            }
        pdf_bytes = fetch_pdf_bytes_from_signed_url(pdf_url)
        if pdf_bytes and pdf_bytes.startswith(b"%PDF-"):
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(pdf_bytes)
            return {
                **row,
                "status": "downloaded",
                "pdf_path": str(target_path),
                "source_url": pdf_url,
                "note": "signed_url_http_fetch",
            }
        pdf_bytes = extract_pdf_bytes_from_viewer(devtools, pdf_page["webSocketDebuggerUrl"])
        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
            return {
                **row,
                "status": "viewer_extract_failed",
                "pdf_path": "",
                "source_url": pdf_url,
                "note": "PDF.js extraction failed or returned non-PDF content",
            }

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(pdf_bytes)
        return {
            **row,
            "status": "downloaded",
            "pdf_path": str(target_path),
            "source_url": pdf_url,
            "note": "devtools_pdfjs_extract",
        }
    finally:
        if article_page:
            devtools.close_page(article_page["id"])
        if pdf_page:
            devtools.close_page(pdf_page["id"])


def main() -> int:
    args = parse_args()
    input_csv = Path(args.input_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = out_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    devtools = DevToolsClient(args.debug_port)
    results = []
    for index, row in enumerate(rows, start=1):
        doi = row.get("doi", "")
        print(f"[{index}/{len(rows)}] devtools serial fetch | {doi}")
        result = process_row(devtools, row, pdf_dir, args.page_wait_seconds)
        results.append(result)
        print(f"    -> {result['status']}")
        if index < len(rows) and args.inter_item_sleep_seconds > 0:
            print(f"    -> sleeping {args.inter_item_sleep_seconds}s before next row")
            time.sleep(args.inter_item_sleep_seconds)

    fieldnames = ["number", "title", "doi", "year", "journal", "status", "pdf_path", "source_url", "note", "formatted"]
    results_csv = out_dir / "devtools_results.csv"
    missing_csv = out_dir / "devtools_missing.csv"
    downloaded_doi_txt = out_dir / "downloaded_doi.txt"
    missing_doi_txt = out_dir / "missing_doi.txt"
    summary_txt = out_dir / "summary.txt"

    with results_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    missing_rows = [row for row in results if row.get("status") != "downloaded"]
    with missing_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in missing_rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    downloaded_dois = [row.get("doi", "").strip() for row in results if row.get("status") == "downloaded" and row.get("doi", "").strip()]
    missing_dois = [row.get("doi", "").strip() for row in missing_rows if row.get("doi", "").strip()]
    write_utf8_no_bom(downloaded_doi_txt, "\n".join(downloaded_dois) + ("\n" if downloaded_dois else ""))
    write_utf8_no_bom(missing_doi_txt, "\n".join(missing_dois) + ("\n" if missing_dois else ""))

    summary_lines = [
        f"total_rows: {len(results)}",
        f"downloaded: {sum(1 for row in results if row.get('status') == 'downloaded')}",
        f"missing: {sum(1 for row in results if row.get('status') != 'downloaded')}",
        f"output_dir: {out_dir}",
        f"debug_port: {args.debug_port}",
        f"page_wait_seconds: {args.page_wait_seconds}",
        f"inter_item_sleep_seconds: {args.inter_item_sleep_seconds}",
    ]
    write_utf8_no_bom(summary_txt, "\n".join(summary_lines) + "\n")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
