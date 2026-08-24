# Publisher Live-Session Workflow

## 1. Prepare a dedicated Chrome session on macOS

Use the launcher script to start Chrome with:

- a dedicated `--user-data-dir`
- `--remote-debugging-port`
- a clean, isolated window

Recommended command:

```bash
bash ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile \
  --remote-debugging-port 9222 \
  --url "https://www.sciencedirect.com/"
```

Windows users can still use the original Edge launcher:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1
```

## 2. Manual session preparation

In the opened Chrome window:

1. complete account or institutional sign-in
2. pass any bot verification page
3. open a representative article page
4. click `View PDF`, `Download PDF`, or open the PDF viewer once
5. keep that window open

Prepare the publisher needed by the batch:

- Wiley/AGU: open the resolved journal subdomain and one `PDF` link
- Canadian Science Publishing: pass the challenge page, if shown
- AIP: open the article and its PDF action once
- IEEE Xplore: sign in through the institutional route first when off campus; start from `document/<arnumber>` and let it expose `stamp.jsp` / `stampPDF/getPDF.jsp`

The serial fetcher depends on the live browser session. If you close the window, the DevTools endpoint disappears and the run will fail.

## 3. Optional session probe

Use the probe when you want a quick yes/no check before a full batch:

```bash
python3 ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/attach_sciencedirect_remote_debug.py \
  --browser chrome \
  --debugger-address 127.0.0.1:9222 \
  --url "https://www.sciencedirect.com/science/article/pii/S0886779824005960?via%3Dihub"
```

Healthy signs:

- `attached: true`
- `bot_verification_page: false`
- `has_pdf_metadata: true`

For Windows Edge, add `--browser edge`.

## 4. Run the batch fetch

```bash
bash ~/.codex/skills/sciencedirect-live-session-fetcher/scripts/run_devtools_sciencedirect_fetch_macos.sh \
  --input-csv ./examples/input-template.csv \
  --out-dir ./out/run-001 \
  --page-wait-seconds 8 \
  --download-wait-seconds 45 \
  --inter-item-sleep-seconds 6
```

Recommended defaults:

- `--page-wait-seconds`: `8`
- `--download-wait-seconds`: `45`; increase to `60` for slow PDF viewers or large files
- `--inter-item-sleep-seconds`: `5` to `8`

Use longer sleeps if the site is sensitive to bursts.

For IEEE rows, prefer the IEEE article URL, for example `https://ieeexplore.ieee.org/document/<arnumber>`, in the CSV `note` column. If the input contains `stamp.jsp` or `stampPDF/getPDF.jsp`, the fetcher normalizes it back to the article page before PDF discovery.

## 5. Review output

- `downloaded` rows are complete
- `no_pdf_metadata` usually means the session does not yet have article/PDF access in that tab
- `generic_pdf_fetch_failed` usually means a generic publisher PDF link was found but could not be fetched in the current browser context
- `network_resource_non_pdf:200` in `note` means the official PDF-looking route returned HTML, commonly an authentication, abstract, or challenge page
- `viewer_extract_failed` usually means the PDF viewer did not fully load or returned non-PDF content

The Chromium route validates `%PDF-` before saving and supports, in order: page-context fetch, credentialed CDP resource load, navigation/download capture, Edge/Chrome PDF child-target extraction, and PDF.js extraction.

## 6. Retry only failed rows

Create a smaller CSV from `devtools_missing.csv`, keep the Chrome session open, and rerun only those rows.
