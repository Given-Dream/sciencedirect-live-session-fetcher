#!/usr/bin/env python3
"""Serial publisher PDF fetch through a live Firefox Selenium session.

The script launches a visible Firefox window, so the user can complete lawful
institutional sign-in or verification in that same browser. It does not bypass
access controls; rows that do not expose PDF metadata or a visible PDF link are
reported as missing.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException


PDF_RE = re.compile(
    r'"pdfDownload":\{"isPdfFullText":(?:true|false),"urlMetadata":\{"queryParams":\{"md5":"([^"]+)","pid":"([^"]+)"\},"pii":"([^"]+)","pdfExtension":"([^"]+)","path":"([^"]+)"\}\}'
)
URL_RE = re.compile(r"https?://[^\s;,\)]+", flags=re.I)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serial publisher PDF fetch through visible Firefox")
    parser.add_argument("--input-csv", required=True, help="CSV with number, title, doi, note columns")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--page-wait-seconds", type=int, default=8, help="Wait after opening each page")
    parser.add_argument("--article-ready-timeout", type=int, default=75, help="Maximum seconds to wait for article PDF metadata")
    parser.add_argument("--inter-item-sleep-seconds", type=int, default=6, help="Pause between rows")
    parser.add_argument("--manual-ready-timeout", type=int, default=180, help="Seconds to wait for manual sign-in")
    parser.add_argument("--profile-dir", default="", help="Optional persistent Firefox profile directory to reuse login state")
    parser.add_argument("--use-current-page-first", action="store_true", help="Use the current browser page for the first row after manual setup")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N rows")
    return parser.parse_args()


def sanitize_name(text: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().replace(" ", "_")
    return (cleaned[:150] or fallback).rstrip(" ._")


def target_name(row: dict[str, str]) -> str:
    number = int(row["number"])
    label = sanitize_name(row.get("title", ""), "") or sanitize_name(row.get("doi", ""), f"reference_{number}")
    return f"{number:03d}-{label}.pdf"


def extract_urls(note: str) -> list[str]:
    urls = []
    for match in URL_RE.findall(note or ""):
        url = match.rstrip(".,);")
        if url not in urls:
            urls.append(url)
    return urls


def choose_article_url(row: dict[str, str]) -> str:
    doi = (row.get("doi") or "").strip()
    ssrn_match = re.match(r"10\.2139/ssrn\.(\d+)$", doi, flags=re.I)
    if ssrn_match:
        return f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={ssrn_match.group(1)}"
    urls = extract_urls(row.get("note", ""))
    for url in urls:
        lowered = url.lower()
        if "sciencedirect.com/" in lowered or "doi.org/" in lowered:
            return url
    if doi:
        return f"https://doi.org/{doi}"
    return urls[0] if urls else ""


def make_driver(download_dir: Path, profile_dir: Path | None = None) -> webdriver.Firefox:
    options = Options()
    if profile_dir:
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument("-profile")
        options.add_argument(str(profile_dir))
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.dir", str(download_dir))
    options.set_preference("browser.download.useDownloadDir", True)
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf,application/octet-stream")
    options.set_preference("browser.download.manager.showWhenStarting", False)
    options.set_preference("pdfjs.disabled", True)
    options.set_preference("browser.download.alwaysOpenPanel", False)
    driver = webdriver.Firefox(service=Service(), options=options)
    driver.set_page_load_timeout(45)
    driver.set_script_timeout(120)
    return driver


def latest_finished_pdf(download_dir: Path, before_files: set[Path], after: float) -> Path | None:
    deadline = time.time() + 90
    while time.time() < deadline:
        partials = list(download_dir.glob("*.part"))
        candidates = [
            p
            for p in download_dir.glob("*.pdf")
            if p not in before_files or p.stat().st_mtime >= after
        ]
        if candidates and not partials:
            return max(candidates, key=lambda p: p.stat().st_mtime)
        time.sleep(1)
    return None


def fetch_pdf_with_browser_cookies(driver: webdriver.Firefox, pdf_url: str) -> bytes | None:
    cookies = "; ".join(f"{cookie['name']}={cookie['value']}" for cookie in driver.get_cookies())
    try:
        user_agent = driver.execute_script("return navigator.userAgent") or "Mozilla/5.0"
    except WebDriverException:
        user_agent = "Mozilla/5.0"
    req = Request(
        pdf_url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/pdf,*/*",
            "Cookie": cookies,
            "Referer": driver.current_url,
        },
    )
    try:
        with urlopen(req, timeout=60) as resp:
            data = resp.read()
    except Exception:
        return None
    return data if data.startswith(b"%PDF-") else None


def fetch_pdf_in_page(driver: webdriver.Firefox, pdf_url: str) -> bytes | None:
    script = """
const url = arguments[0];
const done = arguments[arguments.length - 1];
fetch(url, {credentials: 'include'})
  .then(resp => resp.arrayBuffer())
  .then(buf => {
    const bytes = new Uint8Array(buf);
    const chunk = 0x8000;
    let binary = '';
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    done(btoa(binary));
  })
  .catch(err => done('ERR:' + String(err)));
    """
    try:
        value = driver.execute_async_script(script, pdf_url)
    except WebDriverException:
        return None
    if not value or (isinstance(value, str) and value.startswith("ERR:")):
        return None
    import base64

    try:
        data = base64.b64decode(value)
    except Exception:
        return None
    return data if data.startswith(b"%PDF-") else None


def normalize_pdf_url(current_url: str, value: str) -> str:
    value = (value or "").strip()
    if not value or value.startswith(("javascript:", "mailto:")):
        return ""
    return urljoin(current_url, value)


def score_pdf_url(url: str, text: str) -> int:
    lowered = (url + " " + text).lower()
    score = 0
    if "citation_pdf_url" in lowered:
        score += 50
    if ".pdf" in lowered:
        score += 40
    if "/pdf" in lowered or "pdf/" in lowered:
        score += 30
    if "download" in lowered:
        score += 20
    if "ssrn.com/delivery" in lowered or "download.ssrn.com" in lowered:
        score += 35
    if "pdf" in lowered:
        score += 10
    if any(noise in lowered for noise in ("privacy", "cookie", "terms", "cover-image")):
        score -= 40
    return score


def find_generic_pdf_url(driver: webdriver.Firefox) -> str:
    candidates = driver.execute_script(
        """
const out = [];
const push = (url, text, source) => {
  if (url) out.push({url: String(url), text: String(text || ''), source});
};
document.querySelectorAll('meta').forEach(meta => {
  const key = (meta.getAttribute('name') || meta.getAttribute('property') || '').toLowerCase();
  if (key.includes('citation_pdf_url') || key.includes('bepress_citation_pdf_url')) {
    push(meta.getAttribute('content'), key, 'meta');
  }
});
document.querySelectorAll('a[href], iframe[src], embed[src], object[data]').forEach(el => {
  const url = el.getAttribute('href') || el.getAttribute('src') || el.getAttribute('data');
  const text = (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
  push(url, text, el.tagName.toLowerCase());
});
return out;
        """
    )
    ranked = []
    current_url = driver.current_url
    for item in candidates or []:
        url = normalize_pdf_url(current_url, item.get("url", ""))
        text = item.get("text", "")
        score = score_pdf_url(url, text)
        if url and score >= 30:
            ranked.append((score, url))
    if not ranked:
        return ""
    ranked.sort(reverse=True)
    return ranked[0][1]


def download_pdf_url(driver: webdriver.Firefox, pdf_url: str, tmp_dir: Path, target_path: Path) -> tuple[bool, str]:
    pdf_bytes = fetch_pdf_in_page(driver, pdf_url)
    if pdf_bytes:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(pdf_bytes)
        return True, "in_page_fetch"

    before_files = set(tmp_dir.glob("*.pdf"))
    before = time.time()
    try:
        driver.get(pdf_url)
    except TimeoutException:
        pass
    downloaded = latest_finished_pdf(tmp_dir, before_files, before)
    if not downloaded:
        pdf_bytes = fetch_pdf_with_browser_cookies(driver, pdf_url)
        if pdf_bytes:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(pdf_bytes)
            return True, "browser_cookie_http_fallback"
        return False, "Firefox did not finish a PDF download"
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(downloaded), str(target_path))
    return True, "firefox_download"


def wait_for_article_html(driver: webdriver.Firefox, timeout_seconds: int) -> tuple[str, re.Match[str] | None]:
    deadline = time.time() + timeout_seconds
    last_html = ""
    last_match = None
    while time.time() < deadline:
        last_html = driver.page_source or ""
        last_match = PDF_RE.search(last_html)
        if last_match:
            return last_html, last_match
        title = (driver.title or "").lower()
        lower_html = last_html[:1200].lower()
        waiting_page = (
            "请稍候" in title
            or "please wait" in title
            or "tdm-policy" in lower_html
            or "tdm-reservation" in lower_html
        )
        if not waiting_page:
            generic_pdf = find_generic_pdf_url(driver)
            if generic_pdf:
                return last_html, None
        time.sleep(3)
    return last_html, last_match


def process_row(
    driver: webdriver.Firefox,
    row: dict[str, str],
    pdf_dir: Path,
    tmp_dir: Path,
    wait_seconds: int,
    article_ready_timeout: int,
    use_current_page: bool = False,
) -> dict[str, str]:
    article_url = choose_article_url(row)
    target_path = pdf_dir / target_name(row)
    if target_path.exists() and target_path.stat().st_size > 0:
        return {**row, "status": "downloaded", "pdf_path": str(target_path), "source_url": article_url, "note": "existing_file"}
    if not article_url:
        return {**row, "status": "no_candidate_urls", "pdf_path": "", "source_url": "", "note": row.get("note", "")}

    if not use_current_page:
        try:
            driver.get(article_url)
        except (TimeoutException, WebDriverException):
            pass
    time.sleep(wait_seconds)
    html, match = wait_for_article_html(driver, article_ready_timeout)
    if match:
        md5, pid, pii, pdf_ext, path = match.groups()
        pdf_url = f"https://www.sciencedirect.com/{path}/{pii}{pdf_ext}?md5={md5}&pid={pid}"
        ok, note = download_pdf_url(driver, pdf_url, tmp_dir, target_path)
        if ok:
            return {**row, "status": "downloaded", "pdf_path": str(target_path), "source_url": pdf_url, "note": "sciencedirect_" + note}
        return {**row, "status": "download_timeout", "pdf_path": "", "source_url": pdf_url, "note": note}

    pdf_url = find_generic_pdf_url(driver)
    if pdf_url:
        ok, note = download_pdf_url(driver, pdf_url, tmp_dir, target_path)
        if ok:
            return {**row, "status": "downloaded", "pdf_path": str(target_path), "source_url": pdf_url, "note": "generic_" + note}
        return {**row, "status": "download_timeout", "pdf_path": "", "source_url": pdf_url, "note": note}

    snippet = ((driver.title or "") + " | " + html[:400])[:500]
    return {**row, "status": "no_pdf_metadata", "pdf_path": "", "source_url": driver.current_url, "note": snippet}


def write_results(out_dir: Path, results: list[dict[str, str]], page_wait: int, sleep: int) -> None:
    fieldnames = ["number", "title", "doi", "year", "journal", "status", "pdf_path", "source_url", "note", "formatted"]
    for filename, rows in [
        ("firefox_results.csv", results),
        ("firefox_missing.csv", [r for r in results if r.get("status") != "downloaded"]),
    ]:
        with (out_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

    downloaded = [r.get("doi", "").strip() for r in results if r.get("status") == "downloaded" and r.get("doi", "").strip()]
    missing = [r.get("doi", "").strip() for r in results if r.get("status") != "downloaded" and r.get("doi", "").strip()]
    (out_dir / "downloaded_doi.txt").write_text("\n".join(downloaded) + ("\n" if downloaded else ""), encoding="utf-8")
    (out_dir / "missing_doi.txt").write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")
    (out_dir / "summary.txt").write_text(
        "\n".join(
            [
                f"total_rows: {len(results)}",
                f"downloaded: {sum(1 for row in results if row.get('status') == 'downloaded')}",
                f"missing: {sum(1 for row in results if row.get('status') != 'downloaded')}",
                f"output_dir: {out_dir}",
                f"browser: firefox",
                f"page_wait_seconds: {page_wait}",
                f"inter_item_sleep_seconds: {sleep}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    input_csv = Path(args.input_csv)
    out_dir = Path(args.out_dir)
    pdf_dir = out_dir / "pdfs"
    tmp_dir = out_dir / "_firefox_downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    with input_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if args.limit > 0:
        rows = rows[: args.limit]

    profile_dir = Path(args.profile_dir) if args.profile_dir else None
    driver = make_driver(tmp_dir, profile_dir)
    results: list[dict[str, str]] = []
    try:
        initial_url = choose_article_url(rows[0]) if rows else "https://www.sciencedirect.com/"
        try:
            driver.get(initial_url)
        except (TimeoutException, WebDriverException):
            pass
        print(f"Firefox opened. Complete lawful sign-in/verification if needed; waiting {args.manual_ready_timeout}s.")
        time.sleep(args.manual_ready_timeout)
        for index, row in enumerate(rows, start=1):
            print(f"[{index}/{len(rows)}] firefox serial fetch | {row.get('doi', '')}")
            result = process_row(
                driver,
                row,
                pdf_dir,
                tmp_dir,
                args.page_wait_seconds,
                args.article_ready_timeout,
                use_current_page=args.use_current_page_first and index == 1,
            )
            results.append(result)
            print(f"    -> {result['status']}")
            write_results(out_dir, results, args.page_wait_seconds, args.inter_item_sleep_seconds)
            if index < len(rows) and args.inter_item_sleep_seconds > 0:
                time.sleep(args.inter_item_sleep_seconds)
    finally:
        write_results(out_dir, results, args.page_wait_seconds, args.inter_item_sleep_seconds)
        driver.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
