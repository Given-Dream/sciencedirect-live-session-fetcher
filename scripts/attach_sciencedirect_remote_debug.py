#!/usr/bin/env python3
"""Probe a live Chrome or Edge DevTools session for ScienceDirect PDF metadata."""

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
        "attached": False,
        "current_url": "",
        "title": "",
        "has_view_pdf": False,
        "has_pdf_metadata": False,
        "pdf_url": "",
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
        result["has_view_pdf"] = "View PDF" in html
        result["bot_verification_page"] = (
            "Please wait" in html
            or "tdm-reservation" in html
            or "id.elsevier.com" in current_url
        )
        result["challenge_page"] = result["bot_verification_page"]

        match = PDF_RE.search(html)
        if match:
            md5, pid, pii, pdf_ext, path = match.groups()
            result["has_pdf_metadata"] = True
            result["pdf_url"] = f"https://www.sciencedirect.com/{path}/{pii}{pdf_ext}?md5={md5}&pid={pid}"

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
