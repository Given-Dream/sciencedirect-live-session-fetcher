import argparse
import json
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait


PDF_RE = re.compile(
    r'"pdfDownload":\{"isPdfFullText":(?:true|false),"urlMetadata":\{"queryParams":\{"md5":"([^"]+)","pid":"([^"]+)"\},"pii":"([^"]+)","pdfExtension":"([^"]+)","path":"([^"]+)"\}\}'
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debugger-address", default="127.0.0.1:9222")
    parser.add_argument(
        "--url",
        default="https://www.sciencedirect.com/science/article/pii/S0886779824005960?via%3Dihub",
    )
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    opts = Options()
    opts.add_experimental_option("debuggerAddress", args.debugger_address)
    driver = webdriver.Edge(options=opts)

    result = {
        "url": args.url,
        "attached": True,
        "current_url": "",
        "title": "",
        "has_view_pdf": False,
        "has_pdf_metadata": False,
        "pdf_url": "",
        "challenge_page": False,
    }

    try:
        driver.get(args.url)
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(3)
        html = driver.page_source

        result["current_url"] = driver.current_url
        result["title"] = driver.title
        result["has_view_pdf"] = "View PDF" in html
        result["challenge_page"] = (
            "Please wait" in html
            or "tdm-reservation" in html
            or "id.elsevier.com" in driver.current_url
        )

        match = PDF_RE.search(html)
        if match:
            md5, pid, pii, pdf_ext, path = match.groups()
            result["has_pdf_metadata"] = True
            result["pdf_url"] = (
                f"https://www.sciencedirect.com/{path}/{pii}{pdf_ext}?md5={md5}&pid={pid}"
            )

        if args.out_json:
            out_path = Path(args.out_json)
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
