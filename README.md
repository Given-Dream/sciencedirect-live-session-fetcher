# ScienceDirect Live Session Fetcher

Reusable scripts and a Codex skill for serial PDF fetching from ScienceDirect/Elsevier through a live, already authorized Microsoft Edge session.

This workflow is for cases where:

- the user has lawful access through personal or institutional sign-in
- direct HTTP download is blocked by a challenge page, session gate, or browser-only flow
- the user can manually sign in, pass the challenge, and keep the Edge window open

The scripts then attach to that live Edge session through the DevTools remote debugging port, open one article at a time, extract the `pdfDownload` metadata from the article page, and save the PDF from the in-browser PDF viewer.

## Legal boundary

Use this only with access you are authorized to use. The workflow does not bypass paywalls or create access where none exists.

## What is included

- `scripts/launch_edge_clone_remote_debug.ps1`
  Opens a separate Edge session with a dedicated user-data directory and a DevTools port.
- `scripts/attach_sciencedirect_remote_debug.py`
  Optional probe to verify that the current session can see ScienceDirect article metadata.
- `scripts/devtools_sciencedirect_serial_fetch.py`
  The serial fetcher. Processes one row at a time and sleeps between rows.
- `scripts/run_devtools_sciencedirect_fetch.ps1`
  PowerShell wrapper around the Python fetcher.
- `examples/input-template.csv`
  Minimal CSV template.
- `codex-skill/`
  A clean Codex skill copy of the same workflow for direct reuse under `~/.codex/skills`.

## Requirements

- Windows
- Microsoft Edge
- Python 3.10+
- Packages in `requirements.txt`

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

## Quick start

1. Launch the dedicated Edge session:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1
```

2. In the opened Edge window:

- sign in to ScienceDirect / institutional access
- pass any challenge page manually
- open one representative article and click `View PDF`
- keep the window open

3. Optional probe:

```powershell
python .\scripts\attach_sciencedirect_remote_debug.py --debugger-address 127.0.0.1:9222
```

4. Run the serial fetcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv .\examples\input-template.csv `
  -OutDir .\out\run-001 `
  -InterItemSleepSeconds 6
```

## Input format

The fetcher expects a UTF-8 CSV with these columns:

- `number`
- `doi`
- optional `title`
- optional `note`

If `note` contains candidate URLs, the fetcher prefers `doi.org` or `sciencedirect.com` URLs first.

## Output

Each run writes:

- `pdfs/`
- `devtools_results.csv`
- `devtools_missing.csv`
- `downloaded_doi.txt`
- `missing_doi.txt`
- `summary.txt`

## Documentation

- [Workflow](./docs/workflow.md)
- [Troubleshooting](./docs/troubleshooting.md)
