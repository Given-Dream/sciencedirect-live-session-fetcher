#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import time
from pathlib import Path

import win32clipboard
from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys
from pywinauto.win32defines import WM_COMMAND

from create_endnote_library import create_library


CREATE_GROUP_COMMAND_ID = 33231
RENAME_GROUP_COMMAND_ID = 33232
GROUP_MENU_INDEX = 4
ADD_TO_GROUP_SUBMENU_INDEX = 10
OPEN_LIBRARY_COMMAND_ID = 57601
IMPORT_FILE_COMMAND_ID = 32777
GROUP_INLINE_EDITOR_CONTROL_ID = 6000

ENDNOTE_DIALOG_PREFIXES = (
    "EndNote",
    "EndNote X9",
)
ENDNOTE_EXTRA_DIALOG_TITLES = {
    "\u9009\u62e9\u4e00\u4e2a\u6587\u732e\u5e93:",
}


def normalize_space(text: str) -> str:
    return " ".join((text or "").split())


def resolve_endnote_exe(explicit: str) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            Path(r"D:\soft\endnote\Program Files (x86)\EndNote X9\EndNote.exe"),
            Path(r"C:\Program Files (x86)\EndNote X9\EndNote.exe"),
            Path(r"C:\Program Files\EndNote X9\EndNote.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("EndNote.exe was not found. Pass --endnote-exe explicitly.")


def set_clipboard_text(text: str) -> None:
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


def dismiss_endnote_dialogs() -> list[str]:
    seen: list[str] = []
    for _ in range(8):
        closed_any = False
        for dlg in Desktop(backend="win32").windows(class_name="#32770"):
            if not dlg.is_visible():
                continue
            title = dlg.window_text()
            if title == "EndNote X9 Select Matching Reference":
                try:
                    dlg.type_keys("{ESC}")
                    time.sleep(0.5)
                    seen.append(title)
                    closed_any = True
                except Exception:
                    pass
                continue
            if not title.startswith(ENDNOTE_DIALOG_PREFIXES) and title not in ENDNOTE_EXTRA_DIALOG_TITLES:
                continue
            try:
                cancel_buttons = [c for c in dlg.children() if c.class_name() == "Button" and c.control_id() == 2]
                buttons = [c for c in dlg.children() if c.class_name() == "Button"]
                if cancel_buttons:
                    cancel_buttons[0].click()
                elif buttons:
                    buttons[0].click()
                else:
                    dlg.type_keys("{ESC}")
                time.sleep(0.5)
                seen.append(title)
                closed_any = True
            except Exception:
                pass
        if not closed_any:
            break
    return seen


def start_or_attach_endnote(endnote_exe: Path, library_path: Path) -> tuple[Application, object, bool]:
    for raw in Desktop(backend="win32").windows():
        title = raw.window_text()
        if "EndNote X9" in title and raw.class_name() == "EndNote X9 Frame" and raw.is_visible():
            app = Application(backend="win32").connect(handle=raw.handle)
            return app, app.window(handle=raw.handle), True

    subprocess.Popen([str(endnote_exe), str(library_path)])
    deadline = time.time() + 30
    while time.time() < deadline:
        dismiss_endnote_dialogs()
        for win in Desktop(backend="win32").windows():
            title = win.window_text()
            if "EndNote X9" in title and win.class_name() == "EndNote X9 Frame":
                app = Application(backend="win32").connect(handle=win.handle)
                return app, app.window(handle=win.handle), False
        time.sleep(1)
    raise RuntimeError("EndNote main window did not appear in time.")


def wait_for_window(title_candidates: list[str], timeout_s: float = 10.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for title in title_candidates:
            try:
                dlg = Desktop(backend="win32").window(title=title)
                if dlg.exists(timeout=0.5):
                    return dlg
            except Exception:
                pass
        time.sleep(0.5)
    raise RuntimeError(f"Did not find any dialog in: {title_candidates}")


def dialog_control_ids(dlg) -> set[int]:
    ids: set[int] = set()
    for child in dlg.children():
        try:
            ids.add(int(child.control_id()))
        except Exception:
            pass
    return ids


def wait_for_dialog_by_ids(required_ids: set[int], timeout_s: float = 10.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for dlg in Desktop(backend="win32").windows(class_name="#32770"):
            if not dlg.is_visible():
                continue
            ids = dialog_control_ids(dlg)
            if required_ids.issubset(ids):
                return dlg
        time.sleep(0.5)
    raise RuntimeError(f"Did not find any visible dialog with control ids: {sorted(required_ids)}")


def child_by_class_and_id(parent, class_name: str, control_id: int):
    for child in parent.children():
        try:
            if child.class_name() == class_name and child.control_id() == control_id:
                return child
        except Exception:
            continue
    raise RuntimeError(f"Control not found: class={class_name}, id={control_id}")


def ensure_main_actionable(win) -> None:
    for _ in range(10):
        dismiss_endnote_dialogs()
        if win.is_enabled():
            return
        time.sleep(0.5)
    raise RuntimeError("EndNote main window is still disabled after dismissing dialogs.")


def select_any(combo, candidates: list[str]) -> None:
    texts = []
    try:
        texts = combo.item_texts()
    except Exception:
        texts = []
    for candidate in candidates:
        try:
            if candidate in texts:
                combo.select(candidate)
                return
        except Exception:
            pass
    if texts:
        combo.select(texts[0])


def import_ris(win, ris_path: Path, duplicate_mode: str) -> None:
    ensure_main_actionable(win)
    win.set_focus()
    opened = False
    try:
        win.menu_select("\u6587\u4ef6(&F)->\u5bfc\u5165->\u6587\u4ef6...")
        opened = True
    except Exception:
        pass
    if not opened:
        win.send_message(WM_COMMAND, IMPORT_FILE_COMMAND_ID, 0)
    time.sleep(1)

    dlg = wait_for_dialog_by_ids({1124, 1125, 1127, 1097, 1100})
    combos = dlg.children(class_name="ComboBox")
    if len(combos) < 3:
        raise RuntimeError("Import dialog did not expose expected combo boxes.")
    import_combo, dup_combo, trans_combo = combos[:3]

    select_any(import_combo, ["Reference Manager (RIS)"])
    select_any(dup_combo, [duplicate_mode, "\u5168\u90e8\u5bfc\u5165", "Import All"])
    select_any(trans_combo, ["Unicode (UTF-8)", "UTF-8"])

    child_by_class_and_id(dlg, "Button", 1097).click()
    time.sleep(1)
    open_dlg = wait_for_dialog_by_ids({1148, 1})
    open_edit = child_by_class_and_id(open_dlg, "Edit", 1148)
    try:
        open_edit.set_edit_text(str(ris_path))
    except Exception:
        open_edit.click_input()
        open_edit.type_keys("^a{BACKSPACE}", with_spaces=True)
        open_edit.type_keys(str(ris_path), with_spaces=True)
    try:
        child_by_class_and_id(open_dlg, "Button", 1).click()
    except Exception:
        open_edit.type_keys("{ENTER}")
    time.sleep(1)

    import_path = None
    try:
        import_path = child_by_class_and_id(dlg, "RichEdit20W", 1100)
        if not normalize_space(import_path.window_text()):
            import_path.set_edit_text(str(ris_path))
    except Exception:
        pass

    import_button = child_by_class_and_id(dlg, "Button", 1)
    if not import_button.is_enabled() and import_path is not None:
        try:
            import_path.click_input()
            import_path.type_keys("^a{BACKSPACE}", with_spaces=True)
            import_path.type_keys(str(ris_path), with_spaces=True)
            time.sleep(0.5)
        except Exception:
            pass

    import_button = child_by_class_and_id(dlg, "Button", 1)
    if not import_button.is_enabled():
        raise RuntimeError(f"Import dialog did not accept RIS path: {ris_path}")
    import_button.click()
    time.sleep(8)
    dismiss_endnote_dialogs()


def open_library(win, library_path: Path) -> None:
    del win
    os.startfile(str(library_path))
    time.sleep(5)
    dismiss_endnote_dialogs()


def feed_library_dialog(library_path: Path) -> bool:
    for title in ["\u9009\u62e9\u4e00\u4e2a\u6587\u732e\u5e93:", "\u6253\u5f00"]:
        try:
            dlg = Desktop(backend="win32").window(title=title)
            if not dlg.exists(timeout=1) or not dlg.is_visible():
                continue
            edit = dlg.child_window(control_id=1148, class_name="Edit")
            edit.set_edit_text(str(library_path))
            edit.type_keys("{ENTER}")
            time.sleep(5)
            dismiss_endnote_dialogs()
            return True
        except Exception:
            continue
    return False


def get_add_to_group_entries(win) -> list[dict]:
    ensure_main_actionable(win)
    menu = win.menu_items()[GROUP_MENU_INDEX]["menu_items"]["menu_items"][ADD_TO_GROUP_SUBMENU_INDEX]["menu_items"]["menu_items"]
    entries = []
    for item in menu:
        text = item.get("text") or ""
        item_id = item.get("item_id") or 0
        if item_id >= 40302 and text.startswith("   "):
            entries.append(item)
    return entries


def group_id_map(win) -> dict[str, int]:
    return {item["text"].strip(): item["item_id"] for item in get_add_to_group_entries(win)}


def endnote_doc_window(win):
    mdi_clients = [c for c in win.children() if c.class_name() == "MDIClient"]
    if not mdi_clients:
        raise RuntimeError("EndNote MDI client not found.")
    docs = mdi_clients[0].children()
    if not docs:
        raise RuntimeError("EndNote library document window not found.")
    return docs[0]


def wait_for_group_inline_editor(win, timeout_s: float = 5.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        dismiss_endnote_dialogs()
        try:
            doc = endnote_doc_window(win)
            editors = [
                c
                for c in doc.children()
                if c.class_name() == "RICHEDIT50W" and c.control_id() == GROUP_INLINE_EDITOR_CONTROL_ID
            ]
            if editors:
                return editors[0]
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError("EndNote did not expose the inline group editor after creating a group.")


def create_group(win, name: str) -> int:
    before_ids = {item["item_id"] for item in get_add_to_group_entries(win)}
    win.set_focus()
    win.send_message(WM_COMMAND, CREATE_GROUP_COMMAND_ID, 0)
    editor = wait_for_group_inline_editor(win)
    try:
        editor.set_window_text(name)
    except Exception:
        set_clipboard_text(name)
        send_keys("^a{BACKSPACE}^v")
    time.sleep(0.3)
    send_keys("{ENTER}")
    time.sleep(1.0)
    dismiss_endnote_dialogs()

    for _ in range(10):
        after = get_add_to_group_entries(win)
        new_ids = sorted({item["item_id"] for item in after} - before_ids)
        if new_ids:
            return new_ids[0]
        time.sleep(0.4)
    raise RuntimeError(f"Failed to detect the new group after creating: {name}")


def parse_manifest_groups(manifest_csv: Path) -> tuple[list[dict[str, object]], list[str]]:
    with manifest_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assignments: list[dict[str, object]] = []
    groups: list[str] = []
    seen_groups: set[str] = set()
    for index, row in enumerate(rows, start=1):
        value = normalize_space(row.get("number", ""))
        try:
            number = int(value)
        except Exception:
            number = index
        label = f"RN{number:04d}"
        row_groups = [normalize_space(part) for part in (row.get("section_paths", "") or "").split("|") if normalize_space(part)]
        assignments.append({"label": label, "groups": row_groups, "title": normalize_space(row.get("title", ""))})
        for group in row_groups:
            if group not in seen_groups:
                seen_groups.add(group)
                groups.append(group)
    return assignments, groups


def set_search_controls(win):
    ensure_main_actionable(win)
    children = win.children()
    mode = [c for c in children if c.control_id() == 3235][0]
    field = [c for c in children if c.control_id() == 257][0]
    comp = [c for c in children if c.control_id() == 258][0]
    edit = [c for c in children if c.control_id() == 259][0]
    button = [c for c in children if c.control_id() == 3158][0]
    listview = [c for c in children if c.class_name() == "SysListView32" and c.control_id() == 1024][0]
    select_any(mode, ["Search Whole Library", "\u641c\u7d22\u6574\u4e2a\u6587\u732e\u5e93"])
    select_any(field, ["Label"])
    select_any(comp, ["Is", "\u662f"])
    return edit, button, listview


def search_record(win, edit, button, listview, label: str) -> bool:
    ensure_main_actionable(win)
    edit.set_edit_text(label)
    button.click()
    time.sleep(0.7)
    dismiss_endnote_dialogs()
    count = listview.item_count()
    if count <= 0:
        return False
    listview.set_focus()
    win.type_keys("^a")
    time.sleep(0.2)
    return True


def add_selected_to_group(win, group_command_id: int) -> None:
    ensure_main_actionable(win)
    win.send_message(WM_COMMAND, group_command_id, 0)
    time.sleep(0.2)
    dismiss_endnote_dialogs()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create/import/group a literature EndNote library from a manifest.")
    parser.add_argument("--manifest-csv", required=True, help="Manifest CSV with section_paths.")
    parser.add_argument("--ris-path", required=True, help="RIS file generated from the manifest.")
    parser.add_argument("--library-path", default="", help="Existing .enl library path. Leave empty to create a new one.")
    parser.add_argument("--library-name", default="", help="Library name when creating a new library.")
    parser.add_argument("--library-root", default="", help="Root folder when creating a new library.")
    parser.add_argument("--endnote-exe", default="", help="Optional EndNote.exe path.")
    parser.add_argument("--duplicate-mode", default="\u5168\u90e8\u5bfc\u5165", help="EndNote duplicate handling text shown in the import dialog.")
    parser.add_argument("--report-json", required=True, help="Output report JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_csv = Path(args.manifest_csv)
    ris_path = Path(args.ris_path)
    report_path = Path(args.report_json)

    if args.library_path:
        library_path = Path(args.library_path)
    else:
        if not args.library_name:
            raise ValueError("Provide --library-path or --library-name.")
        root = Path(args.library_root) if args.library_root else report_path.parent / "endnote"
        library_path, _ = create_library(args.library_name, root)

    endnote_exe = resolve_endnote_exe(args.endnote_exe)
    assignments, needed_groups = parse_manifest_groups(manifest_csv)
    app, win, attached_existing = start_or_attach_endnote(endnote_exe, library_path)
    if attached_existing:
        open_library(win, library_path)
    elif not feed_library_dialog(library_path):
        open_library(win, library_path)
    ensure_main_actionable(win)
    import_ris(win, ris_path, args.duplicate_mode)

    existing = group_id_map(win)
    created: dict[str, int] = {}
    for group in needed_groups:
        if group in existing:
            created[group] = existing[group]
        else:
            created[group] = create_group(win, group)

    edit, button, listview = set_search_controls(win)
    missing_labels: list[str] = []
    assignments_done: list[dict[str, str]] = []
    for item in assignments:
        label = str(item["label"])
        groups = list(item["groups"])
        if not groups:
            continue
        if not search_record(win, edit, button, listview, label):
            missing_labels.append(label)
            continue
        for group in groups:
            add_selected_to_group(win, created[group])
            assignments_done.append({"label": label, "group": group})

    payload = {
        "library_path": str(library_path),
        "endnote_exe": str(endnote_exe),
        "created_groups": created,
        "missing_labels": missing_labels,
        "assignment_count": len(assignments_done),
        "assignments_preview": assignments_done[:50],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
