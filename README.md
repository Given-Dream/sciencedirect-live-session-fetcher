# ScienceDirect Live Session Fetcher

[中文说明](./README.zh-CN.md)

Reusable scripts and a Codex skill for serial PDF fetching through a live, already authorized browser session.

The strongest path in this repo is still ScienceDirect and Elsevier through a real Edge DevTools session. The repo also includes a mixed-publisher Firefox route for many mainstream publisher pages that expose a normal PDF link or `citation_pdf_url`.

This workflow is for cases where:

- the user has lawful access through personal or institutional sign-in
- direct HTTP download is blocked by a bot verification page, session gate, or browser-only flow
- the user can manually sign in, pass the bot verification page, and keep the browser window open

## Supported routes

- `Edge DevTools route`
  Best for ScienceDirect and Elsevier. The fetcher reuses a real Edge session, reads article metadata, finds the short-lived signed PDF URL, and fetches the PDF inside the authorized page context.
- `Firefox mixed-publisher route`
  Intended for publisher pages that expose a normal PDF link or metadata such as `citation_pdf_url`, `.pdf`, `/pdf`, or `Download PDF`.
  This route has been exercised against publishers including MDPI, Springer Nature, Frontiers, AIP, ASCE, SSRN, and ICE / Géotechnique family pages, and is the intended fallback path for other mainstream publishers such as Wiley, Taylor & Francis, IEEE, ACM, ACS, Nature Portfolio, Oxford University Press, Cambridge University Press, and Sage when the page structure exposes a standard PDF target.

The scripts then attach to that live Edge session through the DevTools remote debugging port, open one article at a time, extract the `pdfDownload` metadata from the article page, and save the PDF from the in-browser PDF viewer.

## Legal boundary

Use this only with access you are authorized to use. The workflow does not bypass paywalls, CAPTCHA, institutional gates, or create access where none exists.

## What is included

- `scripts/launch_edge_clone_remote_debug.ps1`
  Opens a separate Edge session with a dedicated user-data directory and a DevTools port. Supports direct per-process routing, extension disabling, and one-shot profiles.
- `scripts/attach_sciencedirect_remote_debug.py`
  Optional probe to verify that the current session can see ScienceDirect article metadata.
- `scripts/devtools_sciencedirect_serial_fetch.py`
  The ScienceDirect and Elsevier serial fetcher. Processes one row at a time, prefers signed PDF URLs fetched in the live page context, and sleeps between rows.
- `scripts/firefox_sciencedirect_serial_fetch.py`
  Visible Firefox serial fetcher for mixed publisher pages that expose a normal PDF link or publisher metadata.
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

1. Launch the recommended clean Edge session for ScienceDirect and Elsevier:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1 `
  -DirectConnection `
  -DisableExtensions `
  -OneShotProfile `
  -RemoteDebuggingPort 9222 `
  -Url "https://doi.org/10.1016/j.measurement.2025.118930"
```

2. In the opened browser window:

- sign in to ScienceDirect / institutional access
- pass any bot verification page manually
- open one representative article and click `View PDF`
- keep the window open

3. Optional probe:

```powershell
python .\scripts\attach_sciencedirect_remote_debug.py --debugger-address 127.0.0.1:9222
```

4. Run the Edge serial fetcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv .\examples\input-template.csv `
  -OutDir .\out\run-001 `
  -InterItemSleepSeconds 6
```

## Input format

The fetchers expect a UTF-8 CSV with these columns:

- `number`
- `doi`
- optional `title`
- optional `note`

If `note` contains candidate URLs, the fetchers prefer `doi.org` or `sciencedirect.com` URLs first. The mixed Firefox route can also use publisher landing-page URLs from `note`.

## Output

Each run writes:

- `pdfs/`
- `devtools_results.csv`
- `devtools_missing.csv`
- `downloaded_doi.txt`
- `missing_doi.txt`
- `summary.txt`

## Notes from real runs

- For ScienceDirect and Elsevier, a clean one-shot Edge session with `-DirectConnection -DisableExtensions -OneShotProfile` has been the most reliable setup.
- Short-lived ScienceDirect `pdf.sciencedirectassets.com` URLs may return `403 Forbidden` if fetched outside the live authorized page context, even when the URL itself looks valid.
- If Edge opens `extension://.../pdfjs/web/viewer.html?file=...`, a PDF-handling extension has intercepted the file. Restart the session with extensions disabled instead of reusing that viewer URL.
- A probe can still be useful even when it reports a challenge flag, as long as it also exposes `has_view_pdf=true`, `has_pdf_metadata=true`, or a real `pdf_url`. In that case, test one row before running the full batch.

## Documentation

- [Workflow](./docs/workflow.md)
- [Troubleshooting](./docs/troubleshooting.md)
