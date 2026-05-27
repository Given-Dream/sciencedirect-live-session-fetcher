# Workflow

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

For IEEE Xplore, sign in through the institutional route first when off campus. A healthy manual session may eventually show `stamp.jsp` with an embedded `stampPDF/getPDF.jsp` PDF iframe, but the batch fetcher should start from the normal `document/<arnumber>` article page and let that page expose the authorized PDF route.

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
  --inter-item-sleep-seconds 6
```

Recommended defaults:

- `--page-wait-seconds`: `8`
- `--inter-item-sleep-seconds`: `5` to `8`

Use longer sleeps if the site is sensitive to bursts.

For IEEE rows, prefer the IEEE article URL, for example `https://ieeexplore.ieee.org/document/<arnumber>`, in the CSV `note` column. If the input contains `stamp.jsp` or `stampPDF/getPDF.jsp`, the fetcher normalizes it back to the article page before PDF discovery.

## 5. Review output

- `downloaded` rows are complete
- `no_pdf_metadata` usually means the session does not yet have article/PDF access in that tab
- `generic_pdf_fetch_failed` usually means a generic publisher PDF link was found but could not be fetched in the current browser context
- `viewer_extract_failed` usually means the PDF viewer did not fully load or returned non-PDF content

## 6. Retry only failed rows

Create a smaller CSV from `devtools_missing.csv`, keep the Chrome session open, and rerun only those rows.
