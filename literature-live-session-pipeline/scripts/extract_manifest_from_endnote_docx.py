#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", flags=re.I)
HEADING_RE = re.compile(r"^([1-9]\d*(?:\.\d+)*)\s+(.+?)\s*$")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def heading_level(text: str) -> int | None:
    match = HEADING_RE.match(normalize_space(text))
    if not match:
        return None
    return match.group(1).count(".") + 1


def extract_first_doi(*chunks: str) -> str:
    for chunk in chunks:
        match = DOI_RE.search(chunk or "")
        if match:
            return match.group(0).rstrip(").,;]")
    return ""


def field_text(node: ET.Element | None, path: str) -> str:
    if node is None:
        return ""
    value = node.findtext(path, default="")
    return normalize_space(value)


def all_texts(node: ET.Element, path: str) -> list[str]:
    values: list[str] = []
    for item in node.findall(path):
        text = normalize_space(item.text or "")
        if text:
            values.append(text)
    return values


def detect_source_hint(url: str, doi: str) -> str:
    lowered = (url or "").lower()
    if "sciencedirect.com" in lowered or "elsevier.com" in lowered:
        return "sciencedirect"
    if "cnki.net" in lowered or "cnki.com.cn" in lowered:
        return "cnki"
    if "webofscience.com" in lowered or "clarivate" in lowered or "isiknowledge.com" in lowered:
        return "wos"
    if doi:
        return "doi"
    return "auto"


def map_ris_type(ref_type_name: str, work_type: str) -> str:
    lowered_ref = (ref_type_name or "").lower()
    lowered_work = (work_type or "").lower()
    if "journal" in lowered_ref or "article" in lowered_work:
        return "JOUR"
    if "conference" in lowered_ref:
        return "CONF"
    if "report" in lowered_ref:
        return "RPRT"
    if "thesis" in lowered_work or "dissertation" in lowered_work:
        return "BOOK"
    if "book" in lowered_ref:
        return "BOOK"
    return "JOUR"


def parse_endnote_instruction(instr: str) -> list[ET.Element]:
    raw = html.unescape(instr or "")
    if "ADDIN EN.CITE" not in raw or "<EndNote>" not in raw:
        return []
    start = raw.find("<EndNote>")
    payload = raw[start:].strip()
    payload = re.sub(r"&(?!#?\w+;)", "&amp;", payload)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    return root.findall(".//record")


def paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for text_node in paragraph.findall(".//w:t", NS):
        if text_node.text:
            parts.append(text_node.text)
    return normalize_space("".join(parts))


def paragraph_instructions(paragraph: ET.Element) -> list[str]:
    values: list[str] = []
    for node in paragraph.findall(".//w:instrText", NS):
        if node.text:
            values.append(node.text)
    for node in paragraph.findall(".//w:fldSimple", NS):
        instr = node.attrib.get(f"{{{W_NS}}}instr", "")
        if instr:
            values.append(instr)
    return values


def update_stack(stack: list[str], level: int, heading: str) -> list[str]:
    new_stack = stack[: max(level - 1, 0)]
    new_stack.append(heading)
    return new_stack


def build_record(record: ET.Element) -> dict[str, str]:
    titles = record.find("titles")
    periodical = record.find("periodical")
    urls = all_texts(record, "./urls/related-urls/url")
    electronic_resource = field_text(record, "./electronic-resource-num")
    accession_num = field_text(record, "./accession-num")
    doi = extract_first_doi(electronic_resource, accession_num, *urls)
    entry_url = urls[0] if urls else (f"https://doi.org/{doi}" if doi else "")
    candidate_urls = ";".join(urls[1:]) if len(urls) > 1 else ""
    ref_type_name = record.find("./ref-type").get("name", "") if record.find("./ref-type") is not None else ""
    work_type = field_text(record, "./work-type")

    return {
        "original_recnum": field_text(record, "./rec-number"),
        "title": field_text(titles, "./title"),
        "journal": field_text(titles, "./secondary-title") or field_text(periodical, "./full-title"),
        "authors": ";".join(all_texts(record, "./contributors/authors/author")),
        "year": field_text(record, "./dates/year"),
        "volume": field_text(record, "./volume"),
        "issue": field_text(record, "./number"),
        "pages": field_text(record, "./pages"),
        "doi": doi,
        "entry_url": entry_url,
        "candidate_urls": candidate_urls,
        "source_hint": detect_source_hint(entry_url, doi),
        "ris_type": map_ris_type(ref_type_name, work_type),
        "work_type": work_type,
        "ref_type_name": ref_type_name,
    }


def parse_docx(docx_path: Path) -> tuple[list[dict[str, str]], dict[str, object]]:
    with zipfile.ZipFile(docx_path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    heading_stack: list[str] = []
    records: OrderedDict[str, dict[str, object]] = OrderedDict()
    empty_endnote_fields = 0
    paragraph_count = 0

    for paragraph in root.findall(".//w:p", NS):
        paragraph_count += 1
        text = paragraph_text(paragraph)
        level = heading_level(text)
        if level is not None:
            heading_stack = update_stack(heading_stack, level, text)

        section_groups = heading_stack[:] if heading_stack else ["Unsectioned"]
        for instr in paragraph_instructions(paragraph):
            if "ADDIN EN.CITE" not in instr:
                continue
            recs = parse_endnote_instruction(instr)
            if not recs:
                empty_endnote_fields += 1
                continue
            for rec in recs:
                parsed = build_record(rec)
                recnum = parsed["original_recnum"] or f"unnamed_{len(records)+1}"
                row = records.get(recnum)
                if row is None:
                    row = {
                        **parsed,
                        "first_seen_paragraph": paragraph_count,
                        "display_sections": [],
                        "section_group_set": set(),
                        "cite_count": 0,
                    }
                    records[recnum] = row
                row["cite_count"] = int(row["cite_count"]) + 1
                display_sections = row["display_sections"]
                section_group_set = row["section_group_set"]
                current_leaf = section_groups[-1]
                if current_leaf not in display_sections:
                    display_sections.append(current_leaf)
                for group in section_groups:
                    section_group_set.add(group)

    rows: list[dict[str, str]] = []
    for index, (_, row) in enumerate(records.items(), start=1):
        section_paths = [group for group in row["display_sections"] if group]
        ancestor_groups = [group for group in row["section_group_set"] if group and group not in section_paths]
        merged_groups = ancestor_groups + section_paths
        ordered_groups: list[str] = []
        seen_groups: set[str] = set()
        for group in merged_groups:
            if group not in seen_groups:
                ordered_groups.append(group)
                seen_groups.add(group)

        note_parts = [
            f"original_recnum={row['original_recnum']}",
            f"cite_count={row['cite_count']}",
            f"work_type={row['work_type']}",
            f"ref_type_name={row['ref_type_name']}",
        ]
        rows.append(
            {
                "number": str(index),
                "title": str(row["title"]),
                "doi": str(row["doi"]),
                "source_hint": str(row["source_hint"]),
                "entry_url": str(row["entry_url"]),
                "candidate_urls": str(row["candidate_urls"]),
                "section_paths": "|".join(ordered_groups),
                "authors": str(row["authors"]),
                "journal": str(row["journal"]),
                "year": str(row["year"]),
                "volume": str(row["volume"]),
                "issue": str(row["issue"]),
                "pages": str(row["pages"]),
                "ris_type": str(row["ris_type"]),
                "note": "; ".join(part for part in note_parts if part and not part.endswith("=")),
                "pdf_path": "",
                "original_recnum": str(row["original_recnum"]),
                "cite_count": str(row["cite_count"]),
                "first_seen_paragraph": str(row["first_seen_paragraph"]),
            }
        )

    report = {
        "docx_path": str(docx_path),
        "paragraph_count": paragraph_count,
        "record_count": len(rows),
        "empty_endnote_fields": empty_endnote_fields,
        "records": rows,
    }
    return rows, report


def write_manifest(rows: list[dict[str, str]], manifest_out: Path) -> None:
    fieldnames = [
        "number",
        "title",
        "doi",
        "source_hint",
        "entry_url",
        "candidate_urls",
        "section_paths",
        "authors",
        "journal",
        "year",
        "volume",
        "issue",
        "pages",
        "ris_type",
        "note",
        "pdf_path",
        "original_recnum",
        "cite_count",
        "first_seen_paragraph",
    ]
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    with manifest_out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract a literature manifest from EndNote-embedded citations in a DOCX file.")
    parser.add_argument("--docx", required=True, help="Input DOCX with EndNote EN.CITE fields.")
    parser.add_argument("--manifest-out", required=True, help="Output manifest CSV.")
    parser.add_argument("--report-json", required=True, help="Output JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    docx_path = Path(args.docx)
    manifest_out = Path(args.manifest_out)
    report_json = Path(args.report_json)

    rows, report = parse_docx(docx_path)
    write_manifest(rows, manifest_out)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"records": len(rows), "manifest": str(manifest_out), "report": str(report_json)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
