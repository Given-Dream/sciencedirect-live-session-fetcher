# Troubleshooting

## Browser side

- If the probe reports `challenge_page=true`, do not run the batch yet.
- If a `wos` row never resolves to a publisher or DOI link, add a better `entry_url` or `candidate_urls` value manually.
- If a normal CNKI result page is labelled a challenge solely because raw HTML contains `拖动下方拼图完成验证`, inspect visibility. CNKI can keep a dormant widget at extreme negative coordinates with zero opacity. A real challenge needs a verification URL/title or a rendered in-viewport prompt.
- If CNKI opens the wrong format, confirm that the selector matches exact visible text `PDF下载`. Do not select `#cajDown`: both CAJ and PDF links may share that ID.
- If the trusted PDF click produces no file, inspect both the batch browser-download directory and the user's `Downloads` folder. `_blank` flows may ignore the configured download path.
- If no file appears after the short click grace period, the CNKI downloader may navigate a temporary tab to the exact PDF-button href with the detail page as referrer. Do not substitute a guessed endpoint.
- If the result is `login_required` or `challenge_page`, complete the browser step manually and rerun only the failed subset. Do not automate login or slider solving.
- If a valid 74-page thesis is rejected only because `PdfReader.is_encrypted` is true, update the check: permissions encryption is acceptable when page count and text can be read without a password and the title matches.
- If PDF title extraction is garbled, do not silently accept. Record a visual first-page check, filename, English cover title/author if available, page count, and matching source/archive SHA-256 as the manual validation evidence.
- If a thesis DOI is truncated at the first period, allow periods in the DOI suffix. A suitable extraction core is `10\.\d{4,9}/[-._;()/:A-Z0-9]+` with case-insensitive matching.
- If a row loops between redirects, replace `doi` with a direct publisher or detail-page URL.

## EndNote side

- `endnote_pipeline.py` assumes a visible desktop session. Run it on the active Windows desktop, not in a locked session.
- `EndNote X9` is commonly a 32-bit desktop app. If `pywinauto` warns that 64-bit Python is automating a 32-bit target, prefer a 32-bit Python interpreter for the EndNote step.
- If EndNote is installed in a nonstandard location, pass `--endnote-exe`.
- If import fails because the duplicate-mode text does not match the current UI, pass the exact visible text through `--duplicate-mode`.
- If a record is missing during grouping, check that the `number` column is stable and that the generated RIS file contains the expected `LB  - RNxxxx` labels.
