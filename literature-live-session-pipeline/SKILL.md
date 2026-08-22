---
name: literature-live-session-pipeline
description: Orchestrate lawful literature collection through live Microsoft Edge sessions across ScienceDirect, CNKI, and Web of Science, then create an EndNote X9 library, import RIS metadata, and group records by section_paths from a manifest CSV. Use when browser login or bot verification blocks direct fetching, when the user wants separate browser sessions per source, or when a paper batch must be downloaded into a folder and mirrored into a grouped EndNote library.
---

# Literature Live Session Pipeline

Use this skill when the browser session is the source of truth and the batch needs both files and reference-management structure.

## Quick Start

1. Prepare the manifest CSV.
   Read [references/input-schema.md](references/input-schema.md).
   The core columns are `number`, `title`, `doi`, `source_hint`, `entry_url`, `candidate_urls`, and `section_paths`.
   If the source document is a Word file with EndNote `EN.CITE` fields, use [scripts/extract_manifest_from_endnote_docx.py](scripts/extract_manifest_from_endnote_docx.py) first.

2. Launch a source-specific Edge session.
   Use [scripts/launch_edge_live_session.ps1](scripts/launch_edge_live_session.ps1).
   Keep separate ports for `sciencedirect`, `cnki`, and `wos`.

3. Let the user finish the manual browser step.
   They must sign in lawfully, pass verification pages, open one representative record, and keep the window open.

4. Probe the current page before the full batch.
   Use [scripts/probe_live_session.py](scripts/probe_live_session.py).
   If the probe still reports a challenge page, stop and let the user finish the browser step manually.

5. Create the local EndNote library input.
   Use [scripts/build_ris_from_manifest.py](scripts/build_ris_from_manifest.py) to generate RIS.
   Use [scripts/create_endnote_library.py](scripts/create_endnote_library.py) if a fresh library is needed.

6. Import the RIS and group records in EndNote.
   Use [scripts/endnote_pipeline.py](scripts/endnote_pipeline.py).
   It can create the library, import RIS, and assign records to flat groups named from `section_paths`.

7. Fetch the PDFs.
   Route CNKI rows to [scripts/run_cnki_pdf_live_fetch.ps1](scripts/run_cnki_pdf_live_fetch.ps1). This route opens the exact-title detail page and clicks only the visible `PDF下载` control; it never selects CAJ.
   Route other publishers to [scripts/run_devtools_multi_source_fetch.ps1](scripts/run_devtools_multi_source_fetch.ps1), which wraps [scripts/devtools_multi_source_serial_fetch.py](scripts/devtools_multi_source_serial_fetch.py).

## Commands

Launch a ScienceDirect browser session:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.codex\skills\literature-live-session-pipeline\scripts\launch_edge_live_session.ps1" -Source sciencedirect
```

Launch a CNKI browser session:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.codex\skills\literature-live-session-pipeline\scripts\launch_edge_live_session.ps1" -Source cnki
```

Probe a live session:

```powershell
python "$HOME\.codex\skills\literature-live-session-pipeline\scripts\probe_live_session.py" --debug-port 9222 --url "https://example.com/article"
```

Build RIS from the manifest:

```powershell
python "$HOME\.codex\skills\literature-live-session-pipeline\scripts\build_ris_from_manifest.py" `
  --input-csv C:\path\to\manifest.csv `
  --ris-out C:\path\to\batch\manifest.ris `
  --json-out C:\path\to\batch\manifest.records.json
```

Extract a manifest from an EndNote-embedded DOCX:

```powershell
python "$HOME\.codex\skills\literature-live-session-pipeline\scripts\extract_manifest_from_endnote_docx.py" `
  --docx C:\path\to\manuscript.docx `
  --manifest-out C:\path\to\batch\manifest.csv `
  --report-json C:\path\to\batch\manifest.extract.json
```

Create or update the EndNote library:

```powershell
python "$HOME\.codex\skills\literature-live-session-pipeline\scripts\endnote_pipeline.py" `
  --manifest-csv C:\path\to\manifest.csv `
  --ris-path C:\path\to\batch\manifest.ris `
  --library-name "UHS_THMD_batch" `
  --library-root C:\path\to\batch `
  --report-json C:\path\to\batch\endnote_report.json
```

Run the download batch:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.codex\skills\literature-live-session-pipeline\scripts\run_devtools_multi_source_fetch.ps1" `
  -InputCsv C:\path\to\manifest.csv `
  -OutDir C:\path\to\batch\downloads `
  -DebugPort 9222 `
  -InterItemSleepSeconds 6
```

Run a CNKI PDF-only batch after the user has completed login or any visible verification:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.codex\skills\literature-live-session-pipeline\scripts\run_cnki_pdf_live_fetch.ps1" `
  -InputCsv C:\path\to\cnki-manifest.csv `
  -OutDir C:\path\to\batch\cnki-downloads `
  -DebugPort 9223 `
  -ReuseExistingPage `
  -InterItemSleepSeconds 7
```

## Operational Notes

- Treat `Web of Science` as a record router, not a guaranteed PDF host. Expect it to resolve DOI or publisher links first.
- For CNKI, use the dedicated PDF-only route: search result -> exact-title detail page -> exact visible text `PDF下载`. Do not use element IDs because CNKI can assign the same `id="cajDown"` to both CAJ and PDF anchors.
- CNKI keeps dormant CAPTCHA markup on normal pages. A prompt found only in raw HTML or body text is not proof of a real slider; require a verification URL/title or a rendered prompt that intersects the viewport.
- CNKI may write `_blank` downloads to the Windows `Downloads` folder even after a batch download directory is configured. The CNKI route watches both locations and copies, rather than removes, a valid system-download source.
- Treat a PDF permissions-encryption flag as metadata, not automatic failure. Accept it when the file opens without a password, has at least two readable pages, and matches the expected title.
- Keep separate Edge user-data directories by source. This is the default behavior of the launch script and is the recommended browser split.
- Use `section_paths` to name EndNote groups. Separate multiple groups with `|`.
- Prefer retrying only failed rows by trimming the manifest rather than re-running the entire batch immediately.

## Guardrails

- Stay inside the user's authorized browser session. Do not try to bypass paywalls, verification pages, or access controls.
- Stop if the page remains on a challenge, CAPTCHA, or institutional login screen.
- Do not execute or simulate a slider solution. The workflow only distinguishes a genuinely visible challenge from dormant hidden markup, then pauses for the user.
- Accept CNKI output only when its first bytes are `%PDF-`; reject CAJ and other payloads even if the filename ends in `.pdf`.
- Expect some `WOS` and `CNKI` rows to require manual correction of `entry_url` or `candidate_urls`.
- EndNote automation assumes `EndNote X9` on Windows and a visible desktop session.

## References

- Read [references/workflow.zh-CN.md](references/workflow.zh-CN.md) for the recommended Chinese workflow.
- Read [references/workflow.md](references/workflow.md) for the shorter English workflow.
- Read [references/input-schema.md](references/input-schema.md) for the manifest schema.
- Read [references/troubleshooting.md](references/troubleshooting.md) when the browser route or EndNote import fails.
