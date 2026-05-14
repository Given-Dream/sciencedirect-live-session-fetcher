#!/usr/bin/env python3
"""Serial ScienceDirect PDF fetch through an already logged-in Edge DevTools session.

Workflow:
1. Reuse an existing Edge window launched with --remote-debugging-port.
2. Open one article tab at a time from DOI or candidate URL.
3. Read article HTML through DevTools Runtime.evaluate.
4. Extract ScienceDirect pdfDownload metadata.
5. Open the pdfft page in a new tab.
6. Extract the PDF bytes directly from the in-browser PDF.js viewer.
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
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

import websocket


PDF_RE = re.compile(
    r'"pdfDownload":\{"isPdfFullText":(?:true|false),"urlMetadata":\{"queryParams":\{"md5":"([^"]+)","pid":"([^"]+)"\},"pii":"([^"]+)","pdfExtension":"([^"]+)","path":"([^"]+)"\}\}'
)
URL_RE = re.compile(r"https?://[^\s;,\)]+", flags=re.I)
SIGNED_PDF_RE = re.compile(r"https://pdf\.sciencedirectassets\.com/[^\s\"'<>]+", flags=re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serial ScienceDirect fetch through DevTools")
    parser.add_argument("--input-csv", required=True, help="CSV with number, doi, note columns")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--debug-port", type=int, default=9222, help="Edge remote debugging port")
    parser.add_argument("--page-wait-seconds", type=int, default=8, help="Wait after opening each tab")
    parser.add_argument("--inter-item-sleep-seconds", type=int, default=5, help="Pause between rows")
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
    for url in urls:
        lowered = url.lower()
        if "doi.org/" in lowered or "sciencedirect.com/" in lowered:
            return url
    if doi:
        return f"https://doi.org/{doi}"
    return urls[0] if urls else ""


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


def current_signed_pdf_tabs(devtools: DevToolsClient) -> list[str]:
    urls = []
    for page in devtools.list_pages():
        url = page.get("url", "")
        file_url = extract_file_param_from_viewer_url(url)
        candidate = file_url or url
        if "pdf.sciencedirectassets.com" in candidate and candidate not in urls:
            urls.append(candidate)
    return urls


def choose_signed_pdf_url(devtools: DevToolsClient, pii: str) -> str:
    for url in current_signed_pdf_tabs(devtools):
        if pii and pii in url:
            return url
    signed = current_signed_pdf_tabs(devtools)
    return signed[0] if signed else ""


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
        match = PDF_RE.search(article_html)
        if not match:
            title = devtools.evaluate(article_page["webSocketDebuggerUrl"], "document.title", msg_id=11) or ""
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
