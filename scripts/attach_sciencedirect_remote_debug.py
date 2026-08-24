#!/usr/bin/env python3
"""Probe a live Chrome or Edge DevTools session for publisher PDF routes."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


PDF_RE = re.compile(
    r'"pdfDownload":\{"isPdfFullText":(?:true|false),"urlMetadata":\{"queryParams":\{"md5":"([^"]+)","pid":"([^"]+)"\},"pii":"([^"]+)","pdfExtension":"([^"]+)","path":"([^"]+)"\}\}'
)


def publisher_name(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    if "sciencedirect.com" in host or "elsevier.com" in host:
        return "elsevier"
    if host.endswith("onlinelibrary.wiley.com"):
        return "wiley"
    if host.endswith("cdnsciencepub.com"):
        return "cdn_science"
    if host.endswith("pubs.aip.org"):
        return "aip"
    if host.endswith("ieeexplore.ieee.org"):
        return "ieee"
    return "generic"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debugger-address", default="127.0.0.1:9222")
    parser.add_argument(
        "--browser",
        default="chrome",
        choices=("chrome", "edge"),
        help="Informational browser label for the result. Default: chrome.",
    )
    parser.add_argument(
        "--url",
        default="https://www.sciencedirect.com/science/article/pii/S0886779824005960?via%3Dihub",
    )
    parser.add_argument("--out-json", default="")
    parser.add_argument("--page-wait-seconds", type=int, default=3)
    return parser.parse_args()


class DevToolsClient:
    def __init__(self, debugger_address: str) -> None:
        if "://" in debugger_address:
            parsed = urlparse(debugger_address)
            self.base = f"{parsed.scheme}://{parsed.netloc}"
        else:
            self.base = f"http://{debugger_address}"

    def http_get(self, url: str, method: str = "GET") -> str:
        req = Request(url, method=method)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def open_page(self, url: str) -> dict:
        raw = self.http_get(f"{self.base}/json/new?{quote(url, safe=':/?&=%')}", method="PUT")
        return json.loads(raw)

    def close_page(self, page_id: str) -> None:
        try:
            self.http_get(f"{self.base}/json/close/{page_id}")
        except Exception:
            pass

    def call(self, ws_url: str, method: str, params: dict | None = None, msg_id: int = 1) -> dict:
        import websocket

        ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        try:
            ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == msg_id:
                    return msg
        finally:
            ws.close()

    def evaluate(self, ws_url: str, expression: str, *, msg_id: int = 1):
        msg = self.call(
            ws_url,
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
            msg_id=msg_id,
        )
        return msg.get("result", {}).get("result", {}).get("value")


def main() -> int:
    args = parse_args()
    devtools = DevToolsClient(args.debugger_address)
    page = None
    result = {
        "url": args.url,
        "browser": args.browser,
        "publisher": "",
        "attached": False,
        "current_url": "",
        "title": "",
        "has_view_pdf": False,
        "has_pdf_metadata": False,
        "pdf_url": "",
        "generic_pdf_urls": [],
        "bot_verification_page": False,
        "challenge_page": False,
    }

    try:
        page = devtools.open_page(args.url)
        result["attached"] = True
        time.sleep(args.page_wait_seconds)

        ws_url = page["webSocketDebuggerUrl"]
        html = devtools.evaluate(ws_url, "document.documentElement.outerHTML", msg_id=10) or ""
        current_url = devtools.evaluate(ws_url, "location.href", msg_id=11) or ""
        title = devtools.evaluate(ws_url, "document.title", msg_id=12) or ""

        result["current_url"] = current_url
        result["title"] = title
        result["publisher"] = publisher_name(current_url)
        result["has_view_pdf"] = "view pdf" in html.lower() or "download pdf" in html.lower()
        result["bot_verification_page"] = (
            "Please wait" in html
            or "tdm-reservation" in html
            or "id.elsevier.com" in current_url
            or "challenges.cloudflare.com" in html
            or "please wait" in title.lower()
            or "请稍候" in title
        )
        result["challenge_page"] = result["bot_verification_page"]

        match = PDF_RE.search(html)
        if match:
            md5, pid, pii, pdf_ext, path = match.groups()
            result["has_pdf_metadata"] = True
            result["pdf_url"] = f"https://www.sciencedirect.com/{path}/{pii}{pdf_ext}?md5={md5}&pid={pid}"

        generic_urls = devtools.evaluate(
            ws_url,
            """
(() => {
  const urls = [];
  const add = value => {
    if (!value) return;
    try { value = new URL(value, location.href).href; } catch (_) { return; }
    const lowered = value.toLowerCase();
    if (lowered.includes('.pdf') || lowered.includes('/pdf') || lowered.includes('getpdf.jsp')) {
      if (!urls.includes(value)) urls.push(value);
    }
  };
  document.querySelectorAll('meta').forEach(meta => {
    const key = (meta.name || meta.getAttribute('property') || '').toLowerCase();
    if (key.includes('citation_pdf_url')) add(meta.content);
  });
  document.querySelectorAll('a[href],iframe[src],embed[src],object[data]').forEach(el => {
    add(el.href || el.src || el.data);
  });
  return urls.slice(0, 20);
})()
            """.strip(),
            msg_id=13,
        ) or []
        result["generic_pdf_urls"] = generic_urls
        if not result["pdf_url"] and generic_urls:
            result["has_pdf_metadata"] = True
            result["pdf_url"] = generic_urls[0]

        if args.out_json:
            out_path = Path(args.out_json)
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        if page:
            devtools.close_page(page["id"])


if __name__ == "__main__":
    raise SystemExit(main())
