#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from literature_live_session_lib import DevToolsClient, process_row, read_manifest_rows, write_utf8_no_bom


FIELDNAMES = [
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
    "note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serial multi-source literature fetch through a live Edge DevTools session.")
    parser.add_argument("--input-csv", required=True, help="Manifest CSV.")
    parser.add_argument("--out-dir", required=True, help="Output directory.")
    parser.add_argument("--debug-port", type=int, default=9222, help="Edge remote debugging port.")
    parser.add_argument("--page-wait-seconds", type=int, default=8, help="Wait after opening each page.")
    parser.add_argument("--inter-item-sleep-seconds", type=int, default=5, help="Pause between rows.")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N rows.")
    parser.add_argument("--max-hops", type=int, default=4, help="Maximum HTML-to-HTML routing hops.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_csv = Path(args.input_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = out_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)

    rows = read_manifest_rows(input_csv)
    if args.limit > 0:
        rows = rows[: args.limit]

    devtools = DevToolsClient(args.debug_port)
    results: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        label = row.get("doi", "") or row.get("title", "") or row.get("number", "")
        print(f"[{index}/{len(rows)}] live-session fetch | {label}")
        result = process_row(devtools, row, pdf_dir, args.page_wait_seconds, args.max_hops)
        results.append(result)
        print(f"    -> {result['status']}")
        if index < len(rows) and args.inter_item_sleep_seconds > 0:
            print(f"    -> sleeping {args.inter_item_sleep_seconds}s before next row")
            time.sleep(args.inter_item_sleep_seconds)

    results_csv = out_dir / "live_session_results.csv"
    missing_csv = out_dir / "live_session_missing.csv"
    downloaded_txt = out_dir / "downloaded_doi.txt"
    missing_txt = out_dir / "missing_doi.txt"
    summary_txt = out_dir / "summary.txt"

    with results_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})

    missing_rows = [row for row in results if row.get("status") != "downloaded"]
    with missing_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in missing_rows:
            writer.writerow({key: row.get(key, "") for key in FIELDNAMES})

    downloaded_dois = [row.get("doi", "").strip() for row in results if row.get("status") == "downloaded" and row.get("doi", "").strip()]
    missing_dois = [row.get("doi", "").strip() for row in missing_rows if row.get("doi", "").strip()]
    write_utf8_no_bom(downloaded_txt, "\n".join(downloaded_dois) + ("\n" if downloaded_dois else ""))
    write_utf8_no_bom(missing_txt, "\n".join(missing_dois) + ("\n" if missing_dois else ""))

    summary_lines = [
        f"total_rows: {len(results)}",
        f"downloaded: {sum(1 for row in results if row.get('status') == 'downloaded')}",
        f"missing: {sum(1 for row in results if row.get('status') != 'downloaded')}",
        f"output_dir: {out_dir}",
        f"debug_port: {args.debug_port}",
        f"page_wait_seconds: {args.page_wait_seconds}",
        f"inter_item_sleep_seconds: {args.inter_item_sleep_seconds}",
        f"max_hops: {args.max_hops}",
    ]
    write_utf8_no_bom(summary_txt, "\n".join(summary_lines) + "\n")
    print("\n".join(summary_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
