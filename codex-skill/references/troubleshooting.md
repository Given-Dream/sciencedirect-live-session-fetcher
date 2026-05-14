# Troubleshooting

## `no_pdf_metadata`

Common causes:

- the page is still on a bot verification or sign-in screen
- the article page did not fully load
- the session can see the article landing page but not the PDF metadata

What to do:

1. keep the same Edge window open
2. manually open the target article in that window
3. click `View PDF`
4. rerun only the failed rows

## `viewer_extract_failed`

Common causes:

- the in-browser PDF viewer did not finish loading
- the tab opened a non-PDF error page
- the session expired between the article page and the PDF viewer page

What to do:

- increase `PageWaitSeconds`
- keep `InterItemSleepSeconds` at `5+`
- manually test one failed DOI in the same session
- if the page already exposed a signed `pdf.sciencedirectassets.com` URL, prefer rerunning with the current Edge DevTools path instead of relying only on the in-viewer extractor

## `viewer_extract_failed` with a valid ScienceDirect signed URL

Common causes:

- the signed PDF URL is valid only inside the current authorized browser context
- a direct HTTP fetch outside the page context gets `403 Forbidden`
- the browser extension PDF viewer changed the page shape before PDF.js finished loading

What to do:

1. keep the same Edge window open
2. disable PDF-handling extensions in the next fresh session
3. retry one row first
4. use the current DevTools fetcher, which now prefers in-page fetch for ScienceDirect signed URLs before falling back to viewer extraction

## The browser keeps showing bot verification pages

Likely causes:

- the session is not fully authorized yet
- the current network path is triggering a bot verification page
- the browser profile is too clean and needs a complete sign-in flow

What to do:

- finish the bot verification in the same Edge window
- open a real article and its PDF manually first
- avoid opening too many articles quickly

## Probe says challenge page, but also shows PDF metadata

This can happen on ScienceDirect.

What to do:

1. trust the positive signals first: `has_view_pdf=true`, `has_pdf_metadata=true`, or a populated `pdf_url`
2. run a one-row probe download before the full batch
3. only continue to the full batch after that probe row is saved successfully

## The fetcher cannot attach to the session

Check:

- Edge was launched with `--remote-debugging-port`
- the port matches your command, for example `9222`
- the Edge window is still open

If needed, start a fresh session with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1
```

## Existing main Edge windows interfere

If you reuse a live profile, close all Edge windows first. The recommended path is to use the dedicated launcher and isolated user-data directory instead.

## Edge opens `extension://.../pdfjs/web/viewer.html?file=...`

Common causes:

- Adobe or another PDF-handling extension intercepted the PDF
- the extension wrapped the real short-lived ScienceDirect URL in its own viewer page

What to do:

1. start a fresh Edge session with `-DisableExtensions`
2. prefer `-OneShotProfile` for a clean run
3. do not reuse an old `file=` link after a few minutes; ScienceDirect signed URLs expire quickly

## Article rows with only DOI and no candidate URLs

This is supported. The fetcher will open `https://doi.org/<doi>` first.

## Network-specific access problems

This workflow does not solve access or routing problems by itself. If your institution requires a specific network path, VPN split tunneling, or campus egress route, fix that first and then rerun the workflow.

## Recommended default for ScienceDirect after repeated failures

Use a fresh one-shot Edge session:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1 `
  -DirectConnection `
  -DisableExtensions `
  -OneShotProfile `
  -RemoteDebuggingPort 9222 `
  -Url "https://doi.org/<doi>"
```
