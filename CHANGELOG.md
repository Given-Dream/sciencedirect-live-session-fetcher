# Changelog

## Unreleased - macOS Chrome DevTools update

### Added

- Added `scripts/launch_chrome_clone_remote_debug_macos.sh` to launch an isolated Google Chrome session on macOS with a DevTools remote debugging port.
- Added `scripts/run_devtools_sciencedirect_fetch_macos.sh` as a macOS shell wrapper around the DevTools serial fetcher.
- Added the same macOS helper scripts to `codex-skill/scripts/` so the Codex skill can be installed and used directly.
- Added Chrome/Edge DevTools probing through `scripts/attach_sciencedirect_remote_debug.py` without requiring Selenium attachment.

### Changed

- Generalized `scripts/devtools_sciencedirect_serial_fetch.py` from an Edge-only ScienceDirect downloader into a Chromium DevTools publisher PDF fetcher.
- Kept the ScienceDirect/Elsevier path as the primary stable route: article page -> `pdfDownload` metadata -> short-lived `pdf.sciencedirectassets.com` PDF URL -> in-page fetch from the live authorized browser context.
- Added generic publisher PDF discovery from metadata, anchors, iframe, embed, and object elements.
- Improved IEEE Xplore handling by starting from the article detail page, normalizing `stamp.jsp` and `stampPDF/getPDF.jsp` inputs back to `document/<arnumber>`, and fetching authorized PDF endpoints from the article page context.
- Updated the README, Chinese README, workflow docs, troubleshooting docs, and Codex skill references for the macOS Chrome route.

### Compatibility

- The original Windows Edge launcher and PowerShell wrapper remain available.
- The Firefox mixed-publisher route remains available for publishers that expose standard PDF links or `citation_pdf_url` metadata.

### Operational Notes

- This workflow uses only the user's existing lawful personal or institutional access. It does not bypass paywalls, CAPTCHA, login pages, or institutional authorization gates.
- Publisher sites can rate-limit or temporarily block live sessions after repeated PDF access. Run small batches, keep sleeps between rows, and stop when challenge pages or access-limit symptoms appear.
- For IEEE Xplore, prefer `https://ieeexplore.ieee.org/document/<arnumber>` article URLs in the input `note` column. Direct `stamp.jsp` starts can be routed as a personal PDF request and may show misleading subscription errors even when institutional article access is available.
