# ScienceDirect Live Session Fetcher

[中文说明](./README.zh-CN.md)

Reusable scripts and a Codex skill for serial PDF fetching through a live, already authorized browser session.

The strongest path in this repo is still ScienceDirect and Elsevier through a real Chromium DevTools session. On macOS, the recommended route is Google Chrome. The Chrome DevTools route also supports standard publisher PDF targets such as IEEE Xplore, but IEEE rows should start from the normal article detail page first and only then follow the authorized PDF iframe/link exposed by that session. The original Windows Edge route is still kept, and the repo also includes a mixed-publisher Firefox route for many mainstream publisher pages that expose a normal PDF link or `citation_pdf_url`.

This workflow is for cases where:

- the user has lawful access through personal or institutional sign-in
- direct HTTP download is blocked by a bot verification page, session gate, or browser-only flow
- the user can manually sign in, pass the bot verification page, and keep the browser window open

## Supported routes

- `macOS Chrome DevTools route`
  Recommended on this machine for ScienceDirect and Elsevier. The fetcher reuses a real Chrome session, reads article metadata, finds the short-lived signed PDF URL, and fetches the PDF inside the authorized page context. It also falls back to generic PDF metadata, links, iframe, embed, and object targets. For IEEE Xplore, it now normalizes `document`, `stamp`, and `stampPDF` URLs back to the article detail page before looking for the authorized PDF route.
- `Windows Edge DevTools route`
  Kept as a compatible route for Windows users. It uses the same Python fetcher through an Edge remote-debugging session.
- `Firefox mixed-publisher route`
  Intended for publisher pages that expose a normal PDF link or metadata such as `citation_pdf_url`, `.pdf`, `/pdf`, or `Download PDF`.
  This route has been exercised against publishers including MDPI, Springer Nature, Frontiers, AIP, ASCE, SSRN, and ICE / Géotechnique family pages, and is the intended fallback path for other mainstream publishers such as Wiley, Taylor & Francis, IEEE, ACM, ACS, Nature Portfolio, Oxford University Press, Cambridge University Press, and Sage when the page structure exposes a standard PDF target.

The scripts then attach to that live Chrome or Edge session through the DevTools remote debugging port, open one article at a time, extract ScienceDirect `pdfDownload` metadata or generic publisher PDF targets, and save the PDF from the authorized page context or in-browser PDF viewer.

## Legal boundary

Use this only with access you are authorized to use. The workflow does not bypass paywalls, CAPTCHA, institutional gates, or create access where none exists.

## What is included

- `scripts/launch_chrome_clone_remote_debug_macos.sh`
  Opens a separate macOS Chrome session with a dedicated user-data directory and a DevTools port. Supports direct per-process routing, extension disabling, and one-shot profiles.
- `scripts/launch_edge_clone_remote_debug.ps1`
  Opens a separate Edge session with a dedicated user-data directory and a DevTools port. Supports direct per-process routing, extension disabling, and one-shot profiles.
- `scripts/attach_sciencedirect_remote_debug.py`
  Optional probe to verify that the current Chrome or Edge session can see ScienceDirect article metadata.
- `scripts/devtools_sciencedirect_serial_fetch.py`
  The Chrome/Edge DevTools serial fetcher. Processes one row at a time, prefers ScienceDirect signed PDF URLs fetched in the live page context, and falls back to generic publisher PDF targets such as IEEE PDF iframes.
- `scripts/firefox_sciencedirect_serial_fetch.py`
  Visible Firefox serial fetcher for mixed publisher pages that expose a normal PDF link or publisher metadata.
- `scripts/run_devtools_sciencedirect_fetch.ps1`
  PowerShell wrapper around the Python fetcher.
- `scripts/run_devtools_sciencedirect_fetch_macos.sh`
  macOS shell wrapper around the same Python fetcher.
- `examples/input-template.csv`
  Minimal CSV template.
- `codex-skill/`
  A clean Codex skill copy of the same workflow for direct reuse under `~/.codex/skills`.

## Requirements

- macOS
- Google Chrome
- Python 3.10+
- Packages in `requirements.txt`

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Quick start

1. Launch the recommended clean Chrome session for ScienceDirect and Elsevier on macOS:

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

- For ScienceDirect and Elsevier on macOS, a clean one-shot Chrome session with `--direct-connection --disable-extensions --one-shot-profile` is the recommended setup.
- For off-campus IEEE access, sign in through the institutional route in the Chrome window first. The fetcher should then start from article pages, because direct `stamp.jsp` access can be treated like a personal-session PDF request and land on a misleading subscription page.
- On Windows, the original Edge setup remains available with `-DirectConnection -DisableExtensions -OneShotProfile`.
- Short-lived ScienceDirect `pdf.sciencedirectassets.com` URLs may return `403 Forbidden` if fetched outside the live authorized page context, even when the URL itself looks valid.
- If Chrome or Edge opens `extension://.../pdfjs/web/viewer.html?file=...`, a PDF-handling extension has intercepted the file. Restart the session with extensions disabled instead of reusing that viewer URL.
- A probe can still be useful even when it reports a challenge flag, as long as it also exposes `has_view_pdf=true`, `has_pdf_metadata=true`, or a real `pdf_url`. In that case, test one row before running the full batch.

## Documentation

- [Workflow](./docs/workflow.md)
- [Troubleshooting](./docs/troubleshooting.md)
