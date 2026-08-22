#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


TYPE_MAP = {
    "J": "JOUR",
    "JOUR": "JOUR",
    "C": "CONF",
    "CONF": "CONF",
    "R": "RPRT",
    "RPRT": "RPRT",
    "M": "BOOK",
    "BOOK": "BOOK",
    "OL": "ELEC",
    "ELEC": "ELEC",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def split_authors(text: str) -> list[str]:
    text = normalize_space(text)
    if not text:
        return []
    parts = re.split(r"[;|]+", text)
    return [normalize_space(part) for part in parts if normalize_space(part)]


def split_section_paths(text: str) -> list[str]:
    parts = re.split(r"\|+", text or "")
    return [normalize_space(part) for part in parts if normalize_space(part)]


def normalize_author_for_ris(author: str) -> str:
    author = normalize_space(author)
    if not author:
        return author
    if "," in author:
        return author
    parts = author.split()
    if len(parts) == 1:
        return author + ","
    surname = parts[-1]
    given = " ".join(parts[:-1])
    return f"{surname}, {given}".strip()


def record_label(row: dict[str, str], index: int) -> str:
    value = normalize_space(row.get("number", ""))
    try:
        number = int(value)
    except Exception:
        number = index
    return f"RN{number:04d}"


def build_ris_entry(row: dict[str, str], index: int) -> tuple[str, dict[str, object]]:
    ris_type = TYPE_MAP.get(normalize_space(row.get("ris_type", "")).upper(), "JOUR")
    label = record_label(row, index)
    doi = normalize_space(row.get("doi", ""))
    url = normalize_space(row.get("entry_url", "")) or (f"https://doi.org/{doi}" if doi else "")
    pdf_path = normalize_space(row.get("pdf_path", ""))
    authors = split_authors(row.get("authors", ""))
    section_paths = split_section_paths(row.get("section_paths", ""))

    lines = [f"TY  - {ris_type}"]
    for author in authors:
        lines.append(f"AU  - {normalize_author_for_ris(author)}")
    if normalize_space(row.get("title", "")):
        lines.append(f"TI  - {normalize_space(row['title'])}")
    if normalize_space(row.get("journal", "")):
        lines.append(f"JO  - {normalize_space(row['journal'])}")
        lines.append(f"T2  - {normalize_space(row['journal'])}")
    if normalize_space(row.get("year", "")):
        lines.append(f"PY  - {normalize_space(row['year'])}")
        lines.append(f"Y1  - {normalize_space(row['year'])}")
    if normalize_space(row.get("volume", "")):
        lines.append(f"VL  - {normalize_space(row['volume'])}")
    if normalize_space(row.get("issue", "")):
        lines.append(f"IS  - {normalize_space(row['issue'])}")
    if normalize_space(row.get("pages", "")):
        pages = normalize_space(row["pages"])
        match = re.match(r"(.+?)-(.+)$", pages)
        if match:
            lines.append(f"SP  - {normalize_space(match.group(1))}")
            lines.append(f"EP  - {normalize_space(match.group(2))}")
        else:
            lines.append(f"SP  - {pages}")
    if doi:
        lines.append(f"DO  - {doi}")
    if url:
        lines.append(f"UR  - {url}")
    for section in section_paths:
        lines.append(f"KW  - {section}")
    lines.append(f"LB  - {label}")
    if normalize_space(row.get("source_hint", "")):
        lines.append(f"N1  - source_hint={normalize_space(row['source_hint'])}")
    if pdf_path:
        lines.append(f"L1  - {pdf_path}")
    lines.append("ER  -")

    meta = {
        "label": label,
        "section_paths": section_paths,
        "doi": doi,
        "title": normalize_space(row.get("title", "")),
    }
    return "\n".join(lines), meta


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a RIS file from a literature manifest CSV.")
    parser.add_argument("--input-csv", required=True, help="Manifest CSV.")
    parser.add_argument("--ris-out", required=True, help="Output RIS file path.")
    parser.add_argument("--json-out", required=True, help="Output JSON metadata path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_csv = Path(args.input_csv)
    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    entries: list[str] = []
    metadata: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        entry, meta = build_ris_entry(row, index)
        entries.append(entry)
        metadata.append(meta)

    Path(args.ris_out).write_text("\n\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")
    Path(args.json_out).write_text(
        json.dumps({"count": len(entries), "records": metadata}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} RIS records to {args.ris_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
