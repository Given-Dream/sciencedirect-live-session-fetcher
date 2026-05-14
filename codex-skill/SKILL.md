---
name: sciencedirect-live-session-fetcher
description: Use when the user has lawful ScienceDirect/Elsevier or common publisher access in Edge/Firefox, direct HTTP fetching is blocked by login or bot verification pages, and they want serial PDF downloading through a live browser session that stays open.
---

# Sciencedirect Live Session Fetcher

Use this skill for the workflow where the browser session is the source of truth.

This skill is appropriate when:

- the target PDFs are on ScienceDirect/Elsevier pages, or on common DOI publisher pages that expose a PDF link
- the user can sign in lawfully through personal or institutional access
- direct requests are blocked by bot verification pages, browser-only flows, or session gates
- the user can keep the authorized Edge or Firefox window open during the run

Do not use this skill for unrelated publishers or to create access the user does not already have.

## Workflow

1. Prepare or confirm the input CSV.
   Required columns: `number`, `doi`.
   Optional columns: `title`, `note`, `year`, `journal`, `formatted`.
   If `note` contains candidate URLs, the fetcher prefers `doi.org` and `sciencedirect.com` links first.

2. Choose a browser route.
   Prefer the Edge DevTools route for ScienceDirect and Elsevier batches. It reuses a real browser session and is the most reliable route for signed ScienceDirect PDF URLs.
   Use the Firefox Selenium route for mixed batches across MDPI, Springer Nature, Frontiers, AIP, ASCE, SSRN, ICE / Géotechnique family pages, and similar DOI landing pages when the pages expose a normal PDF link or `citation_pdf_url`.
   Treat the same Firefox route as the intended fallback for other mainstream publisher pages such as Wiley, Taylor & Francis, IEEE, ACM, ACS, Nature Portfolio, Oxford University Press, Cambridge University Press, and Sage when the page structure exposes a standard PDF target.

3. Launch a dedicated Edge session with remote debugging when using the Edge route.
   Use [scripts/launch_edge_clone_remote_debug.ps1](scripts/launch_edge_clone_remote_debug.ps1).
   This opens a separate Edge window with its own user-data directory and a DevTools port.

4. Let the user complete the manual browser part.
   They must:
   - sign in lawfully when needed
   - pass any bot verification page manually
   - open a representative article
   - click `View PDF` or `Download PDF` once when the site requires it
   - keep the browser window open

5. If needed, probe the live Edge session before a full batch.
   Use [scripts/attach_sciencedirect_remote_debug.py](scripts/attach_sciencedirect_remote_debug.py).
   Read [references/troubleshooting.md](references/troubleshooting.md) if the probe still shows a bot verification page or missing PDF metadata.

6. Run the serial fetcher.
   Use [scripts/run_devtools_sciencedirect_fetch.ps1](scripts/run_devtools_sciencedirect_fetch.ps1), which wraps [scripts/devtools_sciencedirect_serial_fetch.py](scripts/devtools_sciencedirect_serial_fetch.py).
   Keep `InterItemSleepSeconds` at `5` to `8` unless the user explicitly wants a different pace.
   Python dependencies live in [scripts/requirements.txt](scripts/requirements.txt).
   For ScienceDirect and Elsevier, the current stable path is: article page -> `pdfDownload` metadata -> signed `pdf.sciencedirectassets.com` URL -> fetch inside the live page context. This avoids short-lived signed URL failures that happen when an external HTTP client gets `403 Forbidden`.
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

Launch the Edge session:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\launch_edge_clone_remote_debug.ps1
```

Launch a direct Edge session with extensions disabled when ScienceDirect or PDF viewer extensions interfere:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\launch_edge_clone_remote_debug.ps1 `
  -DirectConnection `
  -DisableExtensions
```

Launch a one-shot Edge session that applies only to this temporary browser window and ends when the window is closed:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\launch_edge_clone_remote_debug.ps1 `
  -DirectConnection `
  -DisableExtensions `
  -OneShotProfile
```

Launch the recommended clean Elsevier session for a fresh run:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\launch_edge_clone_remote_debug.ps1 `
  -DirectConnection `
  -DisableExtensions `
  -OneShotProfile `
  -RemoteDebuggingPort 9222 `
  -Url "https://doi.org/10.1016/j.measurement.2025.118930"
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

Run a mixed-publisher Firefox batch:

```powershell
python C:\Users\SoungYu\.codex\skills\sciencedirect-live-session-fetcher\scripts\firefox_sciencedirect_serial_fetch.py `
  --input-csv C:\path\to\input.csv `
  --out-dir C:\path\to\out-dir `
  --manual-ready-timeout 300 `
  --page-wait-seconds 10 `
  --inter-item-sleep-seconds 6
```

## Guardrails

- Stay inside the user's authorized session. Do not try to bypass access controls.
- The Edge or Firefox window with the live session must remain open during the run.
- `-OneShotProfile` creates a temporary dedicated Edge user-data directory for this launched session only. It does not modify Windows proxy settings or global browser proxy settings, and closing that Edge window ends the effect.
- If the session is still on a bot verification page, stop and let the user finish it manually.
- If Edge opens `extension://.../pdfjs/web/viewer.html?file=...`, the PDF is being handled by a browser extension. Prefer restarting the DevTools Edge session with `-DisableExtensions`; the `file=` value is a short-lived ScienceDirect signed URL and may expire within minutes.
- A probe result can be mixed. If `has_view_pdf=true` and `has_pdf_metadata=true`, a single-row probe download is often worth trying even when the page still reports a challenge flag. Do not jump straight to the full batch until that probe succeeds.
- For non-ScienceDirect publishers, only use PDF URLs exposed in page metadata or visible links such as `citation_pdf_url`, `.pdf`, `/pdf`, `Download PDF`, or authorized delivery endpoints.
- Prefer retrying a small failed subset instead of rerunning the full list immediately.

## Lessons Learned

- For ScienceDirect and Elsevier, a clean one-shot Edge session with `-DirectConnection -DisableExtensions -OneShotProfile` is the best default starting point.
- Firefox can work well for mixed non-Elsevier publishers, but ScienceDirect is more sensitive to automated Firefox sessions and can fall back to `please wait` or signed-URL failures.
- The ScienceDirect `pdf.sciencedirectassets.com` links are short-lived signed URLs. If you extract them, use them immediately inside the authorized browser session or in the page context; do not treat them as durable links.
- Browser PDF extensions can silently replace the real PDF tab with `extension://...viewer.html?file=...`. When that happens, disable extensions and restart the session instead of retrying the same run repeatedly.

## References

- Read [references/workflow.md](references/workflow.md) when you need the exact run order or parameter choices.
- Read [references/workflow.zh-CN.md](references/workflow.zh-CN.md) when the user prefers Chinese operational guidance.
- Read [references/troubleshooting.md](references/troubleshooting.md) when the live session attaches but cannot expose PDF metadata or the viewer bytes.
