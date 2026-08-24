---
name: sciencedirect-live-session-fetcher
description: Download scholarly PDFs serially through a lawful live Chrome, Edge, or Firefox session when direct HTTP is blocked by login, institutional authentication, bot checks, attachment handling, or an internal PDF viewer. Use for ScienceDirect/Elsevier, Wiley Online Library and AGU/Wiley, Canadian Science Publishing, AIP Publishing, IEEE Xplore, and other publisher pages that expose an authorized PDF route.
---

# Publisher Live Session Fetcher

Use this skill for the workflow where the browser session is the source of truth.

Do not use this skill for unrelated publishers or to create access the user does not already have.

## Workflow

1. Prepare or confirm the input CSV.
   Required columns: `number`, `doi`.
   Optional columns: `title`, `note`, `year`, `journal`, `formatted`.
   If `note` contains candidate URLs, retain them. The fetcher opens the DOI/article page first and uses PDF-like note URLs as authorized delivery candidates, which is especially useful for AIP and IEEE.

2. Choose a browser route.
   Prefer the Chromium DevTools route on macOS and Windows for ScienceDirect, Elsevier, Wiley/AGU, Canadian Science Publishing, AIP, and IEEE. It captures authenticated network resources, attachment downloads, and Chromium's internal PDF viewer targets. For IEEE Xplore, start from the normal article detail page so the institutional route can establish itself before `stamp.jsp` or `stampPDF/getPDF.jsp` is used.
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

   The Chromium route uses this cascade for non-Elsevier publishers:
   1. same-origin fetch inside the authorized article page
   2. `Network.loadNetworkResource` with the live profile's credentials, without exporting cookies
   3. navigation-time response capture and browser download events
   4. same-origin extraction from Edge/Chrome's underlying PDF iframe target
   5. PDF.js viewer extraction as a final fallback

   Publisher adapters:
   - Wiley and AGU/Wiley: prefer the resolved journal subdomain and try `/doi/pdfdirect/<doi>` before `/doi/pdf/<doi>`
   - Canadian Science Publishing: try `/doi/pdf/<doi>?download=true`, then the non-query route
   - AIP: inspect metadata, visible links, raw page HTML, and PDF-like URLs supplied in `note`; try the official `article-pdf` route and its `download=true` variant
   - IEEE Xplore: resolve the DOI to `document/<arnumber>`, then try the authorized `stamp.jsp` and `stampPDF/getPDF.jsp` chain

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
  --download-wait-seconds 45 \
  --inter-item-sleep-seconds 6
```

Run the Windows Edge batch:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\skills\sciencedirect-live-session-fetcher\scripts\run_devtools_sciencedirect_fetch.ps1" `
  -InputCsv "D:\path\input.csv" `
  -OutDir "D:\path\publisher-pdfs" `
  -DownloadWaitSeconds 45 `
  -InterItemSleepSeconds 6
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
- Treat `network_resource_non_pdf:200` as an authenticated endpoint returning HTML, not as a valid PDF. Keep the row missing and report the route instead of saving the HTML with a `.pdf` extension.
- Do not export or replay browser cookies. Use page-context fetch, CDP resource loading, response capture, or the PDF target's own context.
- For IEEE Xplore, prefer using an IEEE article URL such as `https://ieeexplore.ieee.org/document/<arnumber>` in the CSV `note` column. `stamp.jsp` and `stampPDF/getPDF.jsp` inputs are normalized back to the article page before PDF discovery.
- For off-campus IEEE access, let the user complete institutional sign-in inside the Chrome DevTools window before running the batch.
- For Wiley, AIP, CSP, or IEEE challenge pages, let the user complete the publisher or institutional flow in the same dedicated browser. Never automate CAPTCHA solving.
- Omit `--direct-connection` when institutional access depends on a configured proxy or campus VPN route.
- Prefer retrying a small failed subset instead of rerunning the full list immediately.

## Lessons Learned

- For ScienceDirect and Elsevier on macOS, a clean one-shot Chrome session with `--direct-connection --disable-extensions --one-shot-profile` is the best default starting point.
- IEEE Xplore has been validated through the same Chrome DevTools route when the live session exposes `stampPDF/getPDF.jsp`.
- Wiley and AGU/Wiley have been validated through resolved journal subdomains. Do not force all `10.1002` DOIs through the generic `onlinelibrary.wiley.com` host.
- Edge's built-in PDF viewer exposes the real publisher PDF as a child target. Fetch from that child target's own origin when article-context JavaScript is blocked by CORS.
- Canadian Science Publishing and AIP may return an HTML article/authentication page with HTTP 200 from a PDF-looking URL. Validate the `%PDF-` signature before saving.
- For Windows, the original Edge route with `-DirectConnection -DisableExtensions -OneShotProfile` remains available.
- Firefox can work well for mixed non-Elsevier publishers, but ScienceDirect is more sensitive to automated Firefox sessions and can fall back to `please wait` or signed-URL failures.
- The ScienceDirect `pdf.sciencedirectassets.com` links are short-lived signed URLs. If you extract them, use them immediately inside the authorized browser session or in the page context; do not treat them as durable links.
- Browser PDF extensions can silently replace the real PDF tab with `extension://...viewer.html?file=...`. When that happens, disable extensions and restart the session instead of retrying the same run repeatedly.

## References

- Read [references/workflow.md](references/workflow.md) when you need the exact run order or parameter choices.
- Read [references/workflow.zh-CN.md](references/workflow.zh-CN.md) when the user prefers Chinese operational guidance.
- Read [references/troubleshooting.md](references/troubleshooting.md) when the live session attaches but cannot expose PDF metadata or the viewer bytes.
