# ScienceDirect Live Session Fetcher

[中文说明](./README.zh-CN.md)

Reusable scripts and a Codex skill for serial PDF fetching through a live, already authorized browser session.

This repo started with a Windows Edge DevTools workflow for ScienceDirect and Elsevier. That original path is still kept as the main baseline of the project. The shared Chromium fetcher now also has explicit live-session adapters for Wiley and AGU/Wiley, Canadian Science Publishing, AIP Publishing, and IEEE Xplore, plus a Firefox mixed-publisher route for sites that expose a normal PDF link or `citation_pdf_url`.

This workflow is for cases where:

- the user has lawful access through personal or institutional sign-in
- direct HTTP download is blocked by a bot verification page, session gate, or browser-only flow
- the user can manually sign in, pass the bot verification page, and keep the browser window open

## Supported routes

- `Windows Edge DevTools route`
  The original core route of this repo. Best for ScienceDirect and Elsevier on Windows. The fetcher reuses a real Edge session, reads article metadata, finds the short-lived signed PDF URL, and fetches the PDF inside the authorized page context.
- `macOS Chrome DevTools route`
  An added route built on the same DevTools workflow for macOS users. It works especially well for ScienceDirect and Elsevier and shares the explicit Wiley/AGU, Canadian Science Publishing, AIP, and IEEE adapters used by the Windows route. It also falls back to generic publisher PDF metadata, links, iframe, embed, and object targets.
- `Firefox mixed-publisher route`
  Intended for publisher pages that expose a normal PDF link or metadata such as `citation_pdf_url`, `.pdf`, `/pdf`, or `Download PDF`.
  This route has been exercised against publishers including MDPI, Springer Nature, Frontiers, AIP, ASCE, SSRN, and ICE / Geotechnique family pages, and is the intended fallback path for other mainstream publishers such as Wiley, Taylor & Francis, IEEE, ACM, ACS, Nature Portfolio, Oxford University Press, Cambridge University Press, and Sage when the page structure exposes a standard PDF target.

The scripts attach to a live Chrome or Edge session through the DevTools remote debugging port, open one article at a time, discover the publisher's authorized PDF route, and save the PDF from the page context, credentialed DevTools resource loader, navigation response, browser download event, or internal PDF viewer. Every saved file must have a `%PDF-` signature, and publisher-specific candidates must match the current DOI or IEEE article number.

## Legal boundary

Use this only with access you are authorized to use. The workflow does not bypass paywalls, CAPTCHA, institutional gates, or create access where none exists.

## What is included

- `scripts/launch_edge_clone_remote_debug.ps1`
  Opens a separate Edge session with a dedicated user-data directory and a DevTools port. Supports direct per-process routing, extension disabling, and one-shot profiles.
- `scripts/run_devtools_sciencedirect_fetch.ps1`
  PowerShell wrapper around the Python fetcher for the original Windows Edge route.
- `scripts/launch_chrome_clone_remote_debug_macos.sh`
  Opens a separate macOS Chrome session with a dedicated user-data directory and a DevTools port. Supports direct per-process routing, extension disabling, and one-shot profiles.
- `scripts/run_devtools_sciencedirect_fetch_macos.sh`
  macOS shell wrapper around the same Python fetcher.
- `scripts/attach_sciencedirect_remote_debug.py`
  Optional probe to verify that the current Chrome or Edge session can see article metadata and publisher PDF signals.
- `scripts/devtools_sciencedirect_serial_fetch.py`
  The shared Chrome/Edge DevTools serial fetcher. It keeps the stable ScienceDirect signed-PDF path and adds explicit Wiley/AGU, Canadian Science Publishing, AIP, and IEEE routes with DOI/article identity filtering.
- `scripts/firefox_sciencedirect_serial_fetch.py`
  Visible Firefox serial fetcher for mixed publisher pages that expose a normal PDF link or publisher metadata.
- `examples/input-template.csv`
  Minimal CSV template.
- `codex-skill/`
  A clean Codex skill copy of the same workflow for direct reuse under `~/.codex/skills`.

## Requirements

- Python 3.10+
- Packages in `requirements.txt`
- Windows + Microsoft Edge for the original DevTools route
- macOS + Google Chrome for the added macOS route

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

## Quick start

### Windows Edge quick start

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
python .\scripts\attach_sciencedirect_remote_debug.py `
  --browser edge `
  --debugger-address 127.0.0.1:9222
```

4. Run the Edge serial fetcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv .\examples\input-template.csv `
  -OutDir .\out\run-001 `
  -InterItemSleepSeconds 6
```

### macOS Chrome quick start

1. Launch the recommended clean Chrome session for ScienceDirect and Elsevier:

```bash
bash ./scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile \
  --remote-debugging-port 9222 \
  --url "https://doi.org/10.1016/j.measurement.2025.118930"
```

2. In the opened browser window:

- sign in to ScienceDirect / institutional access
- pass any bot verification page manually
- open one representative article and click `View PDF`
- keep the window open

3. Optional probe:

```bash
python3 ./scripts/attach_sciencedirect_remote_debug.py \
  --browser chrome \
  --debugger-address 127.0.0.1:9222
```

4. Run the Chrome DevTools serial fetcher:

```bash
bash ./scripts/run_devtools_sciencedirect_fetch_macos.sh \
  --input-csv ./examples/input-template.csv \
  --out-dir ./out/run-001 \
  --inter-item-sleep-seconds 6
```

5. For mixed publishers, use the Firefox route:

```bash
python3 ./scripts/firefox_sciencedirect_serial_fetch.py \
  --input-csv ./examples/input-template.csv \
  --out-dir ./out/firefox-run-001 \
  --manual-ready-timeout 300 \
  --page-wait-seconds 10 \
  --inter-item-sleep-seconds 6
```

## Input format

The fetchers expect a UTF-8 CSV with these columns:

- `number`
- `doi`
- optional `title`
- optional `note`

If `note` contains candidate URLs, the DevTools fetcher prefers `doi.org` or `sciencedirect.com` URLs first, then falls back to the first URL in `note`. For IEEE, prefer the IEEE article URL such as `https://ieeexplore.ieee.org/document/<arnumber>` in `note`; `stamp.jsp` and `stampPDF/getPDF.jsp` URLs are normalized back to the article detail page before PDF discovery.

## Output

Each run writes:

- `pdfs/`
- `devtools_results.csv`
- `devtools_missing.csv`
- `downloaded_doi.txt`
- `missing_doi.txt`
- `summary.txt`

## Notes from real runs

- For ScienceDirect and Elsevier on Windows, a clean one-shot Edge session with `-DirectConnection -DisableExtensions -OneShotProfile` has been a reliable default.
- The macOS Chrome route keeps the same DevTools core and is the recommended added route for macOS users.
- For off-campus IEEE access, sign in through the institutional route in the Chrome or Edge window first. The fetcher should then start from article pages, because direct `stamp.jsp` access can be treated like a personal-session PDF request and land on a misleading subscription page.
- Short-lived ScienceDirect `pdf.sciencedirectassets.com` URLs may return `403 Forbidden` if fetched outside the live authorized page context, even when the URL itself looks valid.
- If Chrome or Edge opens `extension://.../pdfjs/web/viewer.html?file=...`, a PDF-handling extension has intercepted the file. Restart the session with extensions disabled instead of reusing that viewer URL.
- A probe can still be useful even when it reports a challenge flag, as long as it also exposes `has_view_pdf=true`, `has_pdf_metadata=true`, or a real `pdf_url`. In that case, test one row before running the full batch.

## Documentation

- [Workflow](./docs/workflow.md)
- [Troubleshooting](./docs/troubleshooting.md)

## Multi-source literature skill

The repository also includes the installable [literature-live-session-pipeline](./literature-live-session-pipeline/) skill. It preserves the original publisher routes while adding a CNKI PDF-only live-session workflow: exact-title result, article detail page, and exact visible `PDF下载` control. The CNKI route ignores dormant hidden CAPTCHA markup, stops for real visible verification, rejects CAJ payloads, and validates readable PDFs even when CNKI sets a permissions-encryption flag.

Browser profiles, login sessions, downloaded papers, and runtime output are intentionally excluded from Git.
