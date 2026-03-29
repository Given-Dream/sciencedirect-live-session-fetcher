# Workflow

## 1. Prepare a dedicated Edge session

Use the launcher script to start Edge with:

- a dedicated `--user-data-dir`
- `--remote-debugging-port`
- a clean, isolated window

Default command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1
```

Useful overrides:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\launch_edge_clone_remote_debug.ps1 `
  -RemoteDebuggingPort 9333 `
  -CloneUserDataDir D:\edge-clones\sd-session\User Data `
  -Url "https://www.sciencedirect.com/"
```

## 2. Manual session preparation

In the opened Edge window:

1. complete account or institutional sign-in
2. pass any challenge page
3. open a representative article page
4. click `View PDF` at least once
5. keep that window open

The serial fetcher depends on the live browser session. If you close the window, the DevTools endpoint disappears and the run will fail.

## 3. Optional session probe

Use the probe when you want a quick yes/no check before a full batch:

```powershell
python .\scripts\attach_sciencedirect_remote_debug.py `
  --debugger-address 127.0.0.1:9222 `
  --url "https://www.sciencedirect.com/science/article/pii/S0886779824005960?via%3Dihub"
```

Healthy signs:

- `attached: true`
- `challenge_page: false`
- `has_pdf_metadata: true`

## 4. Run the batch fetch

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_devtools_sciencedirect_fetch.ps1 `
  -InputCsv .\examples\input-template.csv `
  -OutDir .\out\run-001 `
  -PageWaitSeconds 8 `
  -InterItemSleepSeconds 6
```

Recommended defaults:

- `PageWaitSeconds`: `8`
- `InterItemSleepSeconds`: `5` to `8`

Use longer sleeps if the site is sensitive to bursts.

## 5. Review output

- `downloaded` rows are complete
- `no_pdf_metadata` usually means the session does not yet have article/PDF access in that tab
- `viewer_extract_failed` usually means the PDF viewer did not fully load or returned non-PDF content

## 6. Retry only failed rows

Create a smaller CSV from `devtools_missing.csv`, keep the Edge session open, and rerun only those rows.
