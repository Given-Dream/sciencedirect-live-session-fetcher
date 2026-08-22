# Input Schema

Use a UTF-8 CSV manifest. The template is in [../assets/templates/literature-manifest-template.csv](../assets/templates/literature-manifest-template.csv).

## Core columns

- `number`: Integer-like record number. Used to create EndNote labels such as `RN0007`.
- `title`: Paper title.
- `doi`: DOI when known.
- `source_hint`: `sciencedirect`, `cnki`, `wos`, `doi`, or `auto`.
- `entry_url`: Primary page to open first. Use this when you already know the best article or record URL.
- `candidate_urls`: Extra URLs separated by `;`. Use this for publisher links, CNKI detail pages, or WOS record pages.
- `section_paths`: EndNote group names separated by `|`.

## Metadata columns used for RIS

- `authors`: Separate multiple authors with `;`.
- `journal`
- `year`
- `volume`
- `issue`
- `pages`
- `ris_type`: Optional RIS type override such as `JOUR`, `CONF`, `BOOK`, or `RPRT`.

## Optional operational columns

- `note`: Free text. URLs embedded here are also scanned by the fetcher.
- `pdf_path`: Optional existing local PDF path to include in RIS as `L1`.

## Recommended patterns

- For ScienceDirect: set `source_hint=sciencedirect` and provide either `entry_url` or `doi`.
- For CNKI: set `source_hint=cnki`; provide either the exact-title search-results URL or the article detail URL in `entry_url`. Keep the manifest title identical to the visible result title so the PDF-only route cannot select a neighbouring record.
- For Web of Science: set `source_hint=wos` and use the WOS record URL in `entry_url`. The fetcher then tries to route to DOI or publisher full text.

## CNKI metadata notes

- Preserve thesis DOIs such as `10.27272/d.cnki.gshdu.2025.003129` in full. If DOI text is parsed from a CNKI export, use a suffix pattern that permits periods, for example `DOI:\s*(10\.\d{4,9}/[-._;()/:A-Z0-9]+)` with case-insensitive matching, then strip only terminal sentence punctuation.
- Do not infer a citation or DOI from the download workflow. A row may legitimately have a blank DOI.
- For retry runs, write a new manifest containing only rows whose status in `cnki_pdf_missing.csv` is not `downloaded`.
