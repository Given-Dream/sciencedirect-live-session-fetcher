# Workflow

1. Prepare the manifest CSV.
2. Launch one Edge session per source with `launch_edge_live_session.ps1`.
3. Sign in manually and pass any verification page.
4. Probe one representative URL with `probe_live_session.py`.
5. Build RIS with `build_ris_from_manifest.py`.
6. Create or open the EndNote library with `endnote_pipeline.py`.
7. Run non-CNKI rows with `run_devtools_multi_source_fetch.ps1`.
8. Run CNKI rows with `run_cnki_pdf_live_fetch.ps1`: exact-title result -> detail page -> exact visible `PDF下载`. Never select CAJ and never use a duplicate element ID as the selector.
9. Stop for a real visible challenge or login page. Ignore only dormant verification markup that is hidden, transparent, or positioned outside the viewport.
10. Accept only `%PDF-` payloads. Validate at least two pages, password-free readability, NFKC-normalized title matching, and SHA-256. A readable PDF must not be rejected merely because its permissions flag says encrypted.
11. Retry only `cnki_pdf_missing.csv` rows and review `cnki_pdf_results.csv`, `cnki_pdf_summary.json`, and the EndNote report JSON.

Use separate output folders per batch. A typical batch folder contains:

- `manifest.csv`
- `manifest.ris`
- `manifest.records.json`
- `downloads/`
- `endnote_report.json`
- `endnote/<library-name>/`
