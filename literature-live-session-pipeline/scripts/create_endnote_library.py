#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_DIR / "assets" / "endnote-x9-blank"
DEFAULT_OUTPUT_ROOT = Path.home() / "Documents" / "EndNote Libraries"


def sanitize_topic(topic: str) -> str:
    cleaned = topic.strip()
    for ch in '<>:"/\\|?*':
        cleaned = cleaned.replace(ch, "_")
    cleaned = cleaned.rstrip(" .")
    return cleaned or "endnote_library"


def unique_name(root: Path, base_name: str) -> str:
    target_dir = root / base_name
    target_enl = target_dir / f"{base_name}.enl"
    if not target_dir.exists() and not target_enl.exists():
        return base_name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{stamp}"


def copy_template(dest_dir: Path, library_name: str) -> tuple[Path, Path]:
    template_enl = TEMPLATE_ROOT / "blank.enl"
    template_data = TEMPLATE_ROOT / "blank.Data"
    if not template_enl.exists() or not template_data.exists():
        raise FileNotFoundError(f"EndNote blank template not found under {TEMPLATE_ROOT}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_enl = dest_dir / f"{library_name}.enl"
    dest_data = dest_dir / f"{library_name}.Data"

    shutil.copy2(template_enl, dest_enl)
    shutil.copytree(template_data, dest_data)
    return dest_enl, dest_data


def create_library(topic: str, root: Path) -> tuple[Path, Path]:
    base_name = sanitize_topic(topic)
    library_name = unique_name(root, base_name)
    dest_dir = root / library_name
    return copy_template(dest_dir, library_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a new EndNote X9 library from the bundled blank template.")
    parser.add_argument("--topic", required=True, help="Topic name used as the EndNote library name.")
    parser.add_argument(
        "--root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=f"Root directory for new libraries. Defaults to {DEFAULT_OUTPUT_ROOT}",
    )
    parser.add_argument("--out-json", default="", help="Optional JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    enl_path, data_path = create_library(args.topic, root)
    payload = {
        "topic": args.topic,
        "library": str(enl_path),
        "data": str(data_path),
    }
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
