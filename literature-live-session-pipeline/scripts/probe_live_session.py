#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from literature_live_session_lib import DevToolsClient, choose_route, collect_page_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe a live browser session and suggest the next fetch route.")
    parser.add_argument("--debug-port", type=int, default=9222, help="Edge remote debugging port.")
    parser.add_argument("--url", required=True, help="Article, record, or landing page URL to inspect.")
    parser.add_argument("--page-wait-seconds", type=int, default=8, help="Wait after opening the page.")
    parser.add_argument("--out-json", default="", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    devtools = DevToolsClient(args.debug_port)
    page = None
    try:
        page = devtools.open_page(args.url)
        time.sleep(args.page_wait_seconds)
        snapshot = collect_page_snapshot(devtools, page["webSocketDebuggerUrl"])
        route = choose_route(snapshot)
        result = {
            "requested_url": args.url,
            "page_url": snapshot.get("href", ""),
            "title": snapshot.get("title", ""),
            "ready_state": snapshot.get("ready_state", ""),
            "detected_source": snapshot.get("detected_source", ""),
            "has_pdf_viewer": snapshot.get("has_pdf_viewer", False),
            "challenge_page": snapshot.get("challenge_page", False),
            "candidate_count": len(snapshot.get("candidate_urls", [])),
            "route": route,
            "body_preview": snapshot.get("body_text", "")[:800],
        }
        if args.out_json:
            Path(args.out_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        text = json.dumps(result, ensure_ascii=False, indent=2)
        try:
            print(text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
        return 0
    finally:
        if page:
            devtools.close_page(page["id"])


if __name__ == "__main__":
    raise SystemExit(main())
