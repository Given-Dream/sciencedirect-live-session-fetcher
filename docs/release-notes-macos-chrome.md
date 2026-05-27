# macOS Chrome DevTools Release Notes

These notes summarize the current update for maintainers of `Given-Dream/sciencedirect-live-session-fetcher`.

## Summary

This update packages the macOS Google Chrome workflow that was developed from real ScienceDirect, Elsevier, and IEEE Xplore download sessions. The main improvement is a live Chrome DevTools route for macOS while keeping the original Windows Edge route and Firefox mixed-publisher route intact.

The fetcher is still designed for authorized sessions only: the user signs in manually, completes any institutional or challenge flow in the browser, and the scripts reuse that same live session to fetch PDFs that the page is already allowed to access.

## Main Changes

- New macOS Chrome launcher:
  `scripts/launch_chrome_clone_remote_debug_macos.sh`
- New macOS fetch wrapper:
  `scripts/run_devtools_sciencedirect_fetch_macos.sh`
- Updated DevTools probe:
  `scripts/attach_sciencedirect_remote_debug.py`
- Updated serial DevTools fetcher:
  `scripts/devtools_sciencedirect_serial_fetch.py`
- Mirrored macOS scripts and references under:
  `codex-skill/`
- Updated:
  `README.md`, `README.zh-CN.md`, `docs/workflow.md`, `docs/troubleshooting.md`

## macOS Quick Start

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Launch an isolated Chrome session:

```bash
bash ./scripts/launch_chrome_clone_remote_debug_macos.sh \
  --direct-connection \
  --disable-extensions \
  --one-shot-profile \
  --remote-debugging-port 9222 \
  --url "https://www.sciencedirect.com/"
```

In that Chrome window, sign in through the personal or institutional route, complete any manual verification, open a representative article/PDF once, and keep the window open.

Optional probe:

```bash
python3 ./scripts/attach_sciencedirect_remote_debug.py \
  --browser chrome \
  --debugger-address 127.0.0.1:9222
```

Run a small batch:

```bash
bash ./scripts/run_devtools_sciencedirect_fetch_macos.sh \
  --input-csv ./examples/input-template.csv \
  --out-dir ./out/run-001 \
  --page-wait-seconds 8 \
  --inter-item-sleep-seconds 6
```

## Input Guidance

The input CSV should contain at least:

- `number`
- `doi`

Recommended optional columns:

- `title`
- `journal`
- `year`
- `note`
- `formatted`

For IEEE Xplore, put the normal article detail URL in `note` when possible:

```text
https://ieeexplore.ieee.org/document/<arnumber>
```

The fetcher can normalize `stamp.jsp` and `stampPDF/getPDF.jsp` inputs back to the article detail page, but direct article URLs are more reliable.

## Output

Each DevTools run writes:

- `pdfs/`
- `devtools_results.csv`
- `devtools_missing.csv`
- `downloaded_doi.txt`
- `missing_doi.txt`
- `summary.txt`

Use `devtools_missing.csv` to create a smaller retry batch instead of rerunning the entire list.

## Tested Behavior From Real Sessions

- ScienceDirect/Elsevier works best from a fresh one-shot Chrome profile with direct connection and extensions disabled.
- ScienceDirect signed PDF URLs can expire quickly and may return `403 Forbidden` outside the authorized browser context.
- IEEE Xplore should be opened through the institutional article page first. Fetching the PDF from article context avoids some misleading "not included in subscription" flows caused by direct `stamp.jsp` navigation.
- IEEE and Elsevier can impose short-term limits after repeated downloads. Small batches with pauses are safer than long continuous runs.

## Known Limitations

- This project does not create access. If the live browser session cannot view the article/PDF, the script should record the failure instead of retrying indefinitely.
- CAPTCHA, bot challenge, institutional login, and subscription gates must be handled manually by the user in the browser.
- Publisher layout changes may require selector or heuristic updates.
- For IEEE batches, verify a few downloaded PDFs against their titles or DOIs, especially when starting from DOI landing pages or search pages.

## Suggested PR Description

```markdown
## Summary

- add macOS Google Chrome DevTools launch and fetch wrappers
- generalize the DevTools fetcher from Edge-only ScienceDirect to Chrome/Edge publisher PDF sessions
- preserve the ScienceDirect signed-PDF in-page fetch path
- add IEEE Xplore article-context PDF fetching and `stamp.jsp` normalization
- update English/Chinese docs, troubleshooting notes, and Codex skill references

## Notes

This workflow uses the user's existing authorized browser session. It does not bypass paywalls, CAPTCHA, login pages, or institutional access controls.

## Validation

- `python3 -m py_compile scripts/attach_sciencedirect_remote_debug.py scripts/devtools_sciencedirect_serial_fetch.py scripts/firefox_sciencedirect_serial_fetch.py codex-skill/scripts/attach_sciencedirect_remote_debug.py codex-skill/scripts/devtools_sciencedirect_serial_fetch.py codex-skill/scripts/firefox_sciencedirect_serial_fetch.py`
- `bash -n scripts/launch_chrome_clone_remote_debug_macos.sh scripts/run_devtools_sciencedirect_fetch_macos.sh codex-skill/scripts/launch_chrome_clone_remote_debug_macos.sh codex-skill/scripts/run_devtools_sciencedirect_fetch_macos.sh`
- `git diff --check`
```
