---
name: sciencedirect-live-session-fetcher
description: Use when the user has lawful ScienceDirect or Elsevier access in Microsoft Edge, direct HTTP fetching is blocked by login or challenge pages, and they want serial PDF downloading through a live browser session that stays open.
---

# Sciencedirect Live Session Fetcher

Use this skill for the specific workflow where the browser session is the source of truth.

This skill is appropriate when:

- the target PDFs are on ScienceDirect or Elsevier pages
- the user can sign in lawfully through personal or institutional access
- direct requests are blocked by challenge pages, browser-only flows, or session gates
- the user can keep the authorized Edge window open during the run

Do not use this skill for unrelated publishers or to create access the user does not already have.

## Workflow

1. Prepare or confirm the input CSV.
   Required columns: `number`, `doi`.
   Optional columns: `title`, `note`, `year`, `journal`, `formatted`.
   If `note` contains candidate URLs, the fetcher prefers `doi.org` and `sciencedirect.com` links first.

2. Launch a dedicated Edge session with remote debugging.
   Use [scripts/launch_edge_clone_remote_debug.ps1](scripts/launch_edge_clone_remote_debug.ps1).
   This opens a separate Edge window with its own user-data directory and a DevTools port.

3. Let the user complete the manual part in that Edge window.
   They must:
   - sign in
   - pass any challenge page
   - open a representative article
   - click `View PDF`
   - keep the window open

4. If needed, probe the live session before a full batch.
   Use [scripts/attach_sciencedirect_remote_debug.py](scripts/attach_sciencedirect_remote_debug.py).
   Read [references/troubleshooting.md](references/troubleshooting.md) if the probe still shows a challenge page or missing PDF metadata.

5. Run the serial fetcher.
   Use [scripts/run_devtools_sciencedirect_fetch.ps1](scripts/run_devtools_sciencedirect_fetch.ps1), which wraps [scripts/devtools_sciencedirect_serial_fetch.py](scripts/devtools_sciencedirect_serial_fetch.py).
   Keep `InterItemSleepSeconds` at `5` to `8` unless the user explicitly wants a different pace.
   Python dependencies live in [scripts/requirements.txt](scripts/requirements.txt).

6. Review the run output and retry only failed rows.
   The fetcher writes:
   - `pdfs/`
   - `devtools_results.csv`
   - `devtools_missing.csv`
   - `downloaded_doi.txt`
   - `missing_doi.txt`
   - `summary.txt`

## Commands

Launch the Edge session:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\launch_edge_clone_remote_debug.ps1
```

Probe the live session:

```powershell
python C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\attach_sciencedirect_remote_debug.py --debugger-address 127.0.0.1:9222
```

Run the serial batch:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv C:\path\to\input.csv `
  -OutDir C:\path\to\out-dir `
  -InterItemSleepSeconds 6
```

## Guardrails

- Stay inside the user's authorized session. Do not try to bypass access controls.
- The Edge window with the live session must remain open during the run.
- If the session is still on a challenge page, stop and let the user finish it manually.
- Prefer retrying a small failed subset instead of rerunning the full list immediately.

## References

- Read [references/workflow.md](references/workflow.md) when you need the exact run order or parameter choices.
- Read [references/troubleshooting.md](references/troubleshooting.md) when the live session attaches but cannot expose PDF metadata or the viewer bytes.
