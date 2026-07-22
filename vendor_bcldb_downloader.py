#!/usr/bin/env python3
"""
vendor_bcldb_downloader.py

Built-in Python only:
- no playwright
- no selenium
- no requests
- no pip installs

Run:
    python vendor_bcldb_downloader.py --config vendor_bcldb_raw_config.json
"""

import argparse
import datetime as dt
import json
import re
import sys
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


class DownloadError(Exception):
    pass


class Browser:
    def __init__(self, timeout=120):
        self.timeout = timeout
        self.cookie_jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
        }

    def open(self, url, data=None, headers=None):
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)

        req = Request(url, data=data, headers=req_headers)

        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return {
                    "url": resp.geturl(),
                    "status": getattr(resp, "status", 200),
                    "headers": resp.headers,
                    "content": resp.read(),
                }
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise DownloadError(f"HTTP {e.code} for {url}\n{body[:1000]}") from e
        except URLError as e:
            raise DownloadError(f"Network error for {url}: {e}") from e

    def get(self, url, referer=None):
        headers = {}
        if referer:
            headers["Referer"] = referer
        return self.open(url, headers=headers)

    def post(self, url, items, referer=None):
        parsed = urlparse(url)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": f"{parsed.scheme}://{parsed.netloc}",
        }
        if referer:
            headers["Referer"] = referer

        body = urlencode(items, doseq=True).encode("utf-8")
        return self.open(url, data=body, headers=headers)


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.links = []
        self.form = None
        self.link = None
        self.button = None
        self.select = None
        self.option = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = {k.lower(): (v or "") for k, v in attrs}

        if tag == "form":
            self.form = {
                "method": attrs.get("method", "get").lower(),
                "action": attrs.get("action", ""),
                "inputs": [],
                "buttons": [],
                "selects": [],
            }
            return

        if tag == "a":
            self.link = {"href": attrs.get("href", ""), "text": ""}
            return

        if not self.form:
            return

        if tag == "input":
            self.form["inputs"].append(attrs)
        elif tag == "button":
            self.button = dict(attrs)
            self.button["text"] = ""
        elif tag == "select":
            self.select = {
                "name": attrs.get("name", ""),
                "multiple": "multiple" in attrs,
                "options": [],
            }
        elif tag == "option" and self.select is not None:
            self.option = dict(attrs)
            self.option["text"] = ""

    def handle_data(self, data):
        if self.link is not None:
            self.link["text"] += data
        if self.button is not None:
            self.button["text"] += data
        if self.option is not None:
            self.option["text"] += data

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag == "a" and self.link is not None:
            self.link["text"] = clean(self.link["text"])
            self.links.append(self.link)
            self.link = None
            return

        if not self.form:
            return

        if tag == "option" and self.select is not None and self.option is not None:
            self.option["text"] = clean(self.option.get("text", ""))
            if not self.option.get("value"):
                self.option["value"] = self.option["text"]
            self.select["options"].append(self.option)
            self.option = None

        elif tag == "select" and self.select is not None:
            self.form["selects"].append(self.select)
            self.select = None

        elif tag == "button" and self.button is not None:
            self.button["text"] = clean(self.button.get("text", ""))
            self.form["buttons"].append(self.button)
            self.button = None

        elif tag == "form":
            self.forms.append(self.form)
            self.form = None


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def decode_response(resp):
    data = resp["content"]

    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass

    return data.decode("utf-8", errors="replace")


def debug_write(cfg, name, data):
    if not cfg.get("debug", False):
        return

    folder = Path(cfg.get("debug_dir", "debug_bcldb"))
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / name

    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")

    path.write_bytes(data)
    print(f"[debug] wrote {path}")


def is_weekday():
    return dt.date.today().weekday() < 5


def is_excel(resp):
    headers = resp["headers"]
    content_type = headers.get("Content-Type", "").lower()
    disposition = headers.get("Content-Disposition", "").lower()
    first_bytes = resp["content"][:8]

    return (
        "spreadsheet" in content_type
        or "excel" in content_type
        or (
            "attachment" in disposition
            and (".xlsx" in disposition or ".xls" in disposition)
        )
        or first_bytes.startswith(b"PK\x03\x04")
        or first_bytes.startswith(b"\xd0\xcf\x11\xe0")
    )


def looks_like_login(html):
    low = html.lower()

    return (
        "j_security_check" in low
        or "j_username" in low
        or "j_password" in low
    ) and ("login" in low or "password" in low)


def form_text(form):
    bits = [form.get("method", ""), form.get("action", "")]

    for item in form["inputs"]:
        bits.extend([
            item.get("name", ""),
            item.get("value", ""),
            item.get("type", ""),
        ])

    for button in form["buttons"]:
        bits.extend([
            button.get("name", ""),
            button.get("value", ""),
            button.get("text", ""),
        ])

    for select in form["selects"]:
        bits.append(select.get("name", ""))

        for option in select["options"]:
            bits.extend([
                option.get("value", ""),
                option.get("text", ""),
            ])

    return clean(" ".join(bits)).lower()


def parse_html(html):
    parser = PageParser()
    parser.feed(html)
    return parser


def choose_form(forms, cfg):
    if not forms:
        return None

    best = (0, forms[0])
    report_name = cfg["report_name"].lower()
    button_text = cfg.get("download_button_text", "Excel 2007").lower()

    for form in forms:
        text = form_text(form)
        score = 0

        for token, points in [
            ("productactivity", 20),
            ("product_activity", 20),
            ("download", 15),
            ("excel", 15),
            ("xlsx", 15),
            ("2007", 15),
            ("supplier", 10),
            ("agent", 10),
            (report_name, 10),
            (button_text, 20),
        ]:
            if token and token in text:
                score += points

        if score > best[0]:
            best = (score, form)

    return best[1]


def default_payload(form):
    payload = []

    for item in form["inputs"]:
        name = item.get("name", "")
        if not name:
            continue

        input_type = item.get("type", "text").lower()

        if input_type in ("submit", "button", "image", "reset", "file"):
            continue

        if input_type in ("checkbox", "radio") and "checked" not in item:
            continue

        payload.append((name, item.get("value", "")))

    for select in form["selects"]:
        name = select.get("name", "")
        if not name:
            continue

        selected = [
            o.get("value", "")
            for o in select["options"]
            if "selected" in o
        ]

        if not selected and select["options"]:
            selected = [select["options"][0].get("value", "")]

        for value in selected:
            payload.append((name, value))

    return payload


def set_param(payload, name, values):
    payload = [(k, v) for k, v in payload if k != name]

    if isinstance(values, list):
        payload.extend((name, str(v)) for v in values)
    else:
        payload.append((name, str(values)))

    return payload


def field_names(form):
    names = []

    for item in form["inputs"]:
        if item.get("name") and item["name"] not in names:
            names.append(item["name"])

    for select in form["selects"]:
        if select.get("name") and select["name"] not in names:
            names.append(select["name"])

    for button in form["buttons"]:
        if button.get("name") and button["name"] not in names:
            names.append(button["name"])

    return names


def fill_report_payload(form, cfg, excel_value):
    payload = default_payload(form)
    agents = [str(x) for x in cfg["agent_numbers"]]

    found_agent = False
    found_format = False
    found_report = False

    for name in field_names(form):
        low = name.lower()

        if "report" in low and "name" in low:
            payload = set_param(payload, name, cfg["report_name"])
            found_report = True

        if (
            ("supplier" in low or "agent" in low or "vendor" in low)
            and "name" not in low
            and "desc" not in low
            and "label" not in low
        ):
            payload = set_param(payload, name, agents)
            found_agent = True

        if any(x in low for x in ("format", "output", "export", "filetype", "file_type")):
            payload = set_param(payload, name, excel_value)
            found_format = True

    if not found_report:
        payload = set_param(payload, "reportName", cfg["report_name"])

    if not found_agent:
        for name in cfg.get("agent_field_names", []):
            payload = set_param(payload, name, agents)

    if not found_format:
        for name in cfg.get("format_field_names", []):
            payload = set_param(payload, name, excel_value)

    preferred = cfg.get("download_button_text", "Excel 2007").lower()

    for select in form["selects"]:
        if not select.get("name"):
            continue

        for option in select["options"]:
            text = f"{option.get('value', '')} {option.get('text', '')}".lower()

            if "excel" in text or "xlsx" in text or "2007" in text or preferred in text:
                payload = set_param(payload, select["name"], option.get("value", ""))
                break

    for item in form["inputs"] + form["buttons"]:
        input_type = item.get("type", "").lower()
        text = f"{item.get('name', '')} {item.get('value', '')} {item.get('text', '')}".lower()

        if (
            input_type in ("submit", "button", "image", "")
            and item.get("name")
            and (
                "excel" in text
                or "xlsx" in text
                or "2007" in text
                or preferred in text
            )
        ):
            payload = set_param(
                payload,
                item["name"],
                item.get("value") or item.get("text", ""),
            )
            break

    for name, value in cfg.get("form_field_overrides", {}).items():
        if isinstance(value, list):
            payload = set_param(payload, name, [str(x) for x in value])
        else:
            payload = set_param(payload, name, str(value))

    return payload


def submit_form(browser, page_url, form, payload):
    action = form.get("action") or page_url
    url = urljoin(page_url, action)
    method = form.get("method", "get").lower()

    if method == "post":
        return browser.post(url, payload, referer=page_url)

    parsed = urlparse(url)
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode(existing + payload, doseq=True)

    final_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        query,
        parsed.fragment,
    ))

    return browser.get(final_url, referer=page_url)


def try_form_download(browser, cfg, report_page):
    html = decode_response(report_page)
    parser = parse_html(html)

    forms_summary = [
        f"FORM {i + 1}: {form_text(f)[:2500]}"
        for i, f in enumerate(parser.forms)
    ]

    debug_write(cfg, "report_forms.txt", "\n\n".join(forms_summary))

    form = choose_form(parser.forms, cfg)

    if not form:
        return None

    excel_values = cfg.get(
        "excel_format_values_to_try",
        ["EXCEL2007", "Excel2007", "Excel 2007", "XLSX", "xlsx", "2007"],
    )

    for excel_value in excel_values:
        print(f"Trying report form with Excel value: {excel_value}")

        payload = fill_report_payload(form, cfg, excel_value)
        resp = submit_form(browser, report_page["url"], form, payload)

        debug_write(
            cfg,
            f"download_attempt_{safe_name(excel_value)}.bin",
            resp["content"],
        )

        if is_excel(resp):
            return resp

    return None


def try_link_download(browser, cfg, report_page):
    html = decode_response(report_page)
    parser = parse_html(html)

    for i, link in enumerate(parser.links, start=1):
        text = f"{link.get('text', '')} {link.get('href', '')}".lower()
        href = link.get("href", "")

        if not href or href.lower().startswith("javascript:"):
            continue

        if not any(x in text for x in ("download", "excel", "xlsx", "2007")):
            continue

        url = urljoin(report_page["url"], href)

        print(f"Trying download link {i}: {link.get('text', '')}")

        resp = browser.get(url, referer=report_page["url"])

        debug_write(cfg, f"link_attempt_{i}.bin", resp["content"])

        if is_excel(resp):
            return resp

    return None


def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_") or "value"


def make_output_path(cfg):
    today = dt.date.today()

    filename = cfg["filename_pattern"].format(
        mmddyyyy=today.strftime("%m%d%Y"),
        mm=today.strftime("%m"),
        dd=today.strftime("%d"),
        yyyy=today.strftime("%Y"),
    )

    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    return out_dir / filename


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="vendor_bcldb_raw_config.json")
    ap.add_argument("--force", action="store_true", help="Run even on weekends")

    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if cfg.get("skip_weekends", True) and not args.force and not is_weekday():
        print("Weekend detected. Skipping. Use --force to run anyway.")
        return 0

    browser = Browser(timeout=cfg.get("http_timeout_seconds", 120))

    print("Opening login page...")
    login_page = browser.get(cfg["login_page_url"])
    debug_write(cfg, "login_page.html", login_page["content"])

    print("Logging in...")
    login_payload = [
        ("j_username", cfg["username"]),
        ("j_password", cfg["password"]),
    ]

    login_resp = browser.post(
        cfg["login_submit_url"],
        login_payload,
        referer=cfg["login_page_url"],
    )

    debug_write(cfg, "login_response.html", login_resp["content"])

    print("Opening PAR/PO page...")
    sales_page = browser.get(
        cfg["sales_info_url"],
        referer=login_resp["url"],
    )

    debug_write(cfg, "sales_info.html", sales_page["content"])

    if looks_like_login(decode_response(sales_page)):
        raise DownloadError(
            "Login failed or returned to login page. "
            "Check username/password or debug_bcldb/sales_info.html."
        )

    print("Opening Product Activity Report page...")
    report_page = browser.get(
        cfg["report_page_url"],
        referer=cfg["sales_info_url"],
    )

    debug_write(cfg, "report_page.html", report_page["content"])

    if looks_like_login(decode_response(report_page)):
        raise DownloadError("Report page returned login page. Session was not accepted.")

    report_resp = try_form_download(browser, cfg, report_page)

    if report_resp is None:
        report_resp = try_link_download(browser, cfg, report_page)

    if report_resp is None or not is_excel(report_resp):
        raise DownloadError(
            "Could not automatically get the Excel file. "
            "Set debug=true in the JSON and rerun. "
            "Then check debug_bcldb/report_page.html and debug_bcldb/report_forms.txt "
            "for the exact form field names."
        )

    out_path = make_output_path(cfg)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    tmp_path.write_bytes(report_resp["content"])

    if out_path.exists():
        out_path.unlink()

    tmp_path.rename(out_path)

    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DownloadError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)