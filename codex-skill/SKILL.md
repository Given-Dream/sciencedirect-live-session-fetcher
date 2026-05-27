---
name: sciencedirect-live-session-fetcher
description: Use when the user has lawful ScienceDirect/Elsevier or common publisher access in Chrome/Edge/Firefox, direct HTTP fetching is blocked by login or bot verification pages, and they want serial PDF downloading through a live browser session that stays open.
---

# Sciencedirect Live Session Fetcher

Use this skill for the workflow where the browser session is the source of truth.

This skill is appropriate when:

- the target PDFs are on ScienceDirect/Elsevier pages, IEEE Xplore PDF pages, or common DOI publisher pages that expose a PDF link
- the user can sign in lawfully through personal or institutional access
- direct requests are blocked by bot verification pages, browser-only flows, or session gates
- the user can keep the authorized Chrome, Edge, or Firefox window open during the run

Do not use this skill for unrelated publishers or to create access the user does not already have.

## Workflow

1. Prepare or confirm the input CSV.
   Required columns: `number`, `doi`.
   Optional columns: `title`, `note`, `year`, `journal`, `formatted`.
   If `note` contains candidate URLs, the fetcher prefers `doi.org` and `sciencedirect.com` links first.

2. Choose a browser route.
   On macOS, prefer the Chrome DevTools route for ScienceDirect, Elsevier, and IEEE Xplore batches. It reuses a real browser session, handles signed ScienceDirect PDF URLs, and also falls back to generic PDF metadata/link/iframe targets. For IEEE Xplore, start from the normal article detail page first; direct `stamp.jsp` access can be treated like a personal PDF request when the institutional route has not been established. The Windows Edge DevTools route is still available for Windows.
   Use the Firefox Selenium route for mixed batches across MDPI, Springer Nature, Frontiers, AIP, ASCE, SSRN, ICE / Géotechnique family pages, and similar DOI landing pages when the pages expose a normal PDF link or `citation_pdf_url`.
   Treat the same Firefox route as the intended fallback for other mainstream publisher pages such as Wiley, Taylor & Francis, IEEE, ACM, ACS, Nature Portfolio, Oxford University Press, Cambridge University Press, and Sage when the page structure exposes a standard PDF target.

3. Launch a dedicated Chrome session with remote debugging when using the macOS Chrome route.
   Use [scripts/launch_chrome_clone_remote_debug_macos.sh](scripts/launch_chrome_clone_remote_debug_macos.sh).
   This opens a separate Chrome window with its own user-data directory and a DevTools port.

4. Let the user complete the manual browser part.
   They must:
   - sign in lawfully when needed
   - pass any bot verification page manually
   - open a representative article
   - click `View PDF` or `Download PDF` once when the site requires it
   - keep the browser window open

5. If needed, probe the live Chrome or Edge session before a full batch.
   Use [scripts/attach_sciencedirect_remote_debug.py](scripts/attach_sciencedirect_remote_debug.py).
   Read [references/troubleshooting.md](references/troubleshooting.md) if the probe still shows a bot verification page or missing PDF metadata.

6. Run the serial fetcher.
   On macOS, use [scripts/run_devtools_sciencedirect_fetch_macos.sh](scripts/run_devtools_sciencedirect_fetch_macos.sh), which wraps [scripts/devtools_sciencedirect_serial_fetch.py](scripts/devtools_sciencedirect_serial_fetch.py). On Windows, use [scripts/run_devtools_sciencedirect_fetch.ps1](scripts/run_devtools_sciencedirect_fetch.ps1).
   Keep `inter-item-sleep-seconds` at `5` to `8` unless the user explicitly wants a different pace.
   Python dependencies live in [scripts/requirements.txt](scripts/requirements.txt).
   For ScienceDirect and Elsevier, the current stable path is: article page -> `pdfDownload` metadata -> signed `pdf.sciencedirectassets.com` URL -> fetch inside the live page context. This avoids short-lived signed URL failures that happen when an external HTTP client gets `403 Forbidden`. For IEEE Xplore, the Chrome DevTools route resolves DOI/search/stamp inputs to the article detail page, then follows the authorized PDF route exposed by that page.
   For mixed Firefox batches, use [scripts/firefox_sciencedirect_serial_fetch.py](scripts/firefox_sciencedirect_serial_fetch.py). It first tries ScienceDirect `pdfDownload` metadata, then generic publisher PDF metadata and visible PDF links.

7. Review the run output and retry only failed rows.
   The fetcher writes:
   - `pdfs/`
   - `devtools_results.csv`
   - `devtools_missing.csv`
   - `downloaded_doi.txt`
   - `missing_doi.txt`
   - `summary.txt`

## Commands

Launch the recommended macOS Chrome session:

```bash
bash ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile \
  --remote-debugging-port 9222 \
  --url "https://www.sciencedirect.com/"
```

Launch a one-shot Chrome session for a specific DOI:

```bash
bash ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile \
  --remote-debugging-port 9222 \
  --url "https://doi.org/10.1016/j.measurement.2025.118930"
```

Probe the live session:

```bash
python3 ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/attach_sciencedirect_remote_debug.py \
  --browser chrome \
  --debugger-address 127.0.0.1:9222
```

Run the serial batch:

```bash
bash ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/run_devtools_sciencedirect_fetch_macos.sh \
  --input-csv /path/to/input.csv \
  --out-dir /path/to/out-dir \
  --inter-item-sleep-seconds 6
```

Run a mixed-publisher Firefox batch:

```bash
python3 ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/firefox_sciencedirect_serial_fetch.py \
  --input-csv /path/to/input.csv \
  --out-dir /path/to/out-dir \
  --manual-ready-timeout 300 \
  --page-wait-seconds 10 \
  --inter-item-sleep-seconds 6
```

## Guardrails

- Stay inside the user's authorized session. Do not try to bypass access controls.
- The Chrome, Edge, or Firefox window with the live session must remain open during the run.
- `--one-shot-profile` creates a temporary dedicated Chrome user-data directory for this launched session only. It does not modify global browser profile state, and closing that Chrome window ends the effect.
- If the session is still on a bot verification page, stop and let the user finish it manually.
- If Chrome or Edge opens `extension://.../pdfjs/web/viewer.html?file=...`, the PDF is being handled by a browser extension. Prefer restarting the DevTools browser session with extensions disabled; the `file=` value is a short-lived ScienceDirect signed URL and may expire within minutes.
- A probe result can be mixed. If `has_view_pdf=true` and `has_pdf_metadata=true`, a single-row probe download is often worth trying even when the page still reports a challenge flag. Do not jump straight to the full batch until that probe succeeds.
- For non-ScienceDirect publishers, only use PDF URLs exposed in page metadata or visible links such as `citation_pdf_url`, `.pdf`, `/pdf`, `Download PDF`, or authorized delivery endpoints.
- For IEEE Xplore, prefer using an IEEE article URL such as `https://ieeexplore.ieee.org/document/<arnumber>` in the CSV `note` column. `stamp.jsp` and `stampPDF/getPDF.jsp` inputs are normalized back to the article page before PDF discovery.
- For off-campus IEEE access, let the user complete institutional sign-in inside the Chrome DevTools window before running the batch.
- Prefer retrying a small failed subset instead of rerunning the full list immediately.

## Lessons Learned

- For ScienceDirect and Elsevier on macOS, a clean one-shot Chrome session with `--direct-connection --disable-extensions --one-shot-profile` is the best default starting point.
- IEEE Xplore has been validated through the same Chrome DevTools route when the live session exposes `stampPDF/getPDF.jsp`.
- For Windows, the original Edge route with `-DirectConnection -DisableExtensions -OneShotProfile` remains available.
- Firefox can work well for mixed non-Elsevier publishers, but ScienceDirect is more sensitive to automated Firefox sessions and can fall back to `please wait` or signed-URL failures.
- The ScienceDirect `pdf.sciencedirectassets.com` links are short-lived signed URLs. If you extract them, use them immediately inside the authorized browser session or in the page context; do not treat them as durable links.
- Browser PDF extensions can silently replace the real PDF tab with `extension://...viewer.html?file=...`. When that happens, disable extensions and restart the session instead of retrying the same run repeatedly.

## References

- Read [references/workflow.md](references/workflow.md) when you need the exact run order or parameter choices.
- Read [references/workflow.zh-CN.md](references/workflow.zh-CN.md) when the user prefers Chinese operational guidance.
- Read [references/troubleshooting.md](references/troubleshooting.md) when the live session attaches but cannot expose PDF metadata or the viewer bytes.
