import argparse
from email import parser
import getpass
import hashlib
import html.parser
import http.cookiejar
import json
import logging
from multiprocessing import context
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
import zipfile


class FormParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.current_form = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag.lower() == "form":
            self.current_form = {
                "action": attrs.get("action", ""),
                "method": attrs.get("method", "GET").upper(),
                "inputs": []
            }
            self.forms.append(self.current_form)

        elif tag.lower() == "input" and self.current_form is not None:
            self.current_form["inputs"].append(attrs)

    def handle_endtag(self, tag):
        if tag.lower() == "form":
            self.current_form = None

class LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag.lower() == "a":
            self.current_href = attrs.get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href:
            self.current_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href:
            text = " ".join(part for part in self.current_text if part)
            self.links.append({
                "href": self.current_href,
                "text": text
            })
            self.current_href = None
            self.current_text = []

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("eliis_downloader.log")
        ]
    )


def make_opener():
    cookie_jar = http.cookiejar.CookieJar()

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar)
    )

    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    ]

    return opener


def read_url(opener, url, data=None):
    request = urllib.request.Request(url, data=data)

    with opener.open(request, timeout=60) as response:
        return response.read(), response.geturl()


def parse_forms(html_text):
    parser = FormParser()
    parser.feed(html_text)
    return parser.forms


def find_login_form(forms):
    for form in forms:
        for input_item in form["inputs"]:
            if input_item.get("type", "").lower() == "password":
                return form

    if forms:
        return forms[0]

    raise RuntimeError("No HTML form found on login page.")


def guess_username_field(inputs):
    candidates = ["user", "username", "userid", "userId", "login", "j_username"]

    for candidate in candidates:
        for item in inputs:
            name = item.get("name", "")
            if name.lower() == candidate.lower():
                return name

    for item in inputs:
        name = item.get("name", "")
        input_type = item.get("type", "").lower()

        if name and input_type in ["text", "email", ""]:
            if "user" in name.lower() or "login" in name.lower():
                return name

    raise RuntimeError("Could not auto-detect username field.")


def guess_password_field(inputs):
    for item in inputs:
        if item.get("type", "").lower() == "password":
            name = item.get("name", "")
            if name:
                return name

    for item in inputs:
        name = item.get("name", "")
        if "pass" in name.lower():
            return name

    raise RuntimeError("Could not auto-detect password field.")


def login(opener, config):
    login_url = config["login_url"]

    logging.info("Opening login page: %s", login_url)

    login_html_bytes, final_login_url = read_url(opener, login_url)
    login_html = login_html_bytes.decode("utf-8", errors="replace")

    forms = parse_forms(login_html)
    login_form = find_login_form(forms)

    action = login_form["action"] or final_login_url
    method = login_form["method"]

    post_url = urllib.parse.urljoin(final_login_url, action)

    username_field = config.get("username_field") or guess_username_field(login_form["inputs"])
    password_field = config.get("password_field") or guess_password_field(login_form["inputs"])

    username = "A19076B"
    password = "nikka11"

    payload = {}

    for item in login_form["inputs"]:
        name = item.get("name")
        value = item.get("value", "")

        if name:
            payload[name] = value

    payload[username_field] = username
    payload[password_field] = password

    encoded_payload = urllib.parse.urlencode(payload).encode("utf-8")

    logging.info("Submitting login form to: %s", post_url)

    if method == "POST":
        response_bytes, response_url = read_url(opener, post_url, data=encoded_payload)
    else:
        separator = "&" if "?" in post_url else "?"
        response_bytes, response_url = read_url(
            opener,
            post_url + separator + urllib.parse.urlencode(payload)
        )

    response_text = response_bytes.decode("utf-8", errors="replace")

    if "Login as a registered user" in response_text and "Password" in response_text:
        raise RuntimeError(
            "Login may have failed. Run --inspect-login and set username_field/password_field in config."
        )

    logging.info("Login request completed. Current URL: %s", response_url)


def safe_filename(name):
    name = Path(name).name
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name or "downloaded_file"


def render_template(value, context):
    if isinstance(value, str):
        return value.format(**context)

    if isinstance(value, dict):
        return {k: render_template(v, context) for k, v in value.items()}

    if isinstance(value, list):
        return [render_template(v, context) for v in value]

    return value


def unique_path(path):
    if not path.exists():
        return path

    counter = 1

    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1

def extract_zip_file(zip_path, extract_dir, overwrite=True):
    extract_dir = Path(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    base_path = extract_dir.resolve()

    logging.info("Extracting ZIP: %s", zip_path)
    logging.info("Extracting to: %s", extract_dir)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.infolist():
            target_path = (extract_dir / member.filename).resolve()

            if os.path.commonpath([str(base_path), str(target_path)]) != str(base_path):
                raise RuntimeError(f"Unsafe ZIP path detected: {member.filename}")

            if target_path.exists() and not overwrite and not member.is_dir():
                logging.info("Skipping existing extracted file: %s", target_path)
                continue

            zip_ref.extract(member, extract_dir)

    logging.info("Finished extracting: %s", zip_path)

def download_file(opener, download, download_dir, context):
    download = render_template(download, context)

    name = download["name"]
    url = download["url"]
    filename = safe_filename(download["filename"])

    if "download_dir" in download:
        output_dir = Path(download["download_dir"])
    else:
        output_dir = download_dir / context["date"]
        
    output_dir.mkdir(parents=True, exist_ok=True)

    overwrite = bool(download.get("overwrite", False))

    output_path = output_dir / filename

    if output_path.exists() and not overwrite:
        output_path = unique_path(output_path)

    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    logging.info("Downloading %s", name)
    logging.info("URL: %s", url)

    sha256 = hashlib.sha256()
    total_bytes = 0

    with opener.open(url, timeout=120) as response:
        with open(temp_path, "wb") as file:
            while True:
                chunk = response.read(1024 * 1024)

                if not chunk:
                    break

                file.write(chunk)
                sha256.update(chunk)
                total_bytes += len(chunk)

    temp_path.replace(output_path)

    #checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    #checksum_path.write_text(sha256.hexdigest(), encoding="utf-8")

    logging.info("Saved: %s", output_path)
    logging.info("Size: %.2f MB", total_bytes / 1024 / 1024)
    logging.info("SHA256: %s", sha256.hexdigest())

    if download.get("extract_zip"):
        extract_to = Path(download.get("extract_to", output_dir))
        extract_overwrite = bool(download.get("extract_overwrite", True))
        extract_zip_file(output_path, extract_to, overwrite=extract_overwrite)


def inspect_login(config):
    opener = make_opener()

    html_bytes, final_url = read_url(opener, config["login_url"])
    html_text = html_bytes.decode("utf-8", errors="replace")

    forms = parse_forms(html_text)

    print(f"Final login URL: {final_url}")
    print(f"Forms found: {len(forms)}")
    print()

    for form_index, form in enumerate(forms, start=1):
        print(f"Form {form_index}")
        print(f"  method: {form['method']}")
        print(f"  action: {form['action']}")
        print("  inputs:")

        for item in form["inputs"]:
            input_type = item.get("type", "")
            name = item.get("name", "")
            value = item.get("value", "")

            if "pass" in name.lower() or input_type.lower() == "password":
                value = "[hidden]"

            print(f"    type={input_type!r}, name={name!r}, value={value!r}")

        print()

def list_download_links(opener, page_url):
    logging.info("Opening downloads page: %s", page_url)

    html_bytes, final_url = read_url(opener, page_url)
    html_text = html_bytes.decode("utf-8", errors="replace")

    parser = LinkParser()
    parser.feed(html_text)

    print()
    print("Links found on downloads page:")
    print("=" * 80)

    found_any = False

    for index, link in enumerate(parser.links, start=1):
        href = link["href"]
        text = link["text"]

        absolute_url = urllib.parse.urljoin(final_url, href)

        # Show likely download links first, but still print everything useful.
        looks_useful = (
            ".zip" in absolute_url.lower()
            or "download" in absolute_url.lower()
            or "file" in absolute_url.lower()
            or "export" in absolute_url.lower()
            or "sales" in absolute_url.lower()
            or "inventory" in absolute_url.lower()
        )

        if looks_useful:
            found_any = True
            print(f"{index}. Text: {text}")
            print(f"   URL:  {absolute_url}")
            print()

    if not found_any:
        print("No obvious ZIP/download links found.")
        print()
        print("Showing all links instead:")
        print("=" * 80)

        for index, link in enumerate(parser.links, start=1):
            absolute_url = urllib.parse.urljoin(final_url, link["href"])
            print(f"{index}. Text: {link['text']}")
            print(f"   URL:  {absolute_url}")
            print()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="eliis_config.json")
    parser.add_argument("--inspect-login", action="store_true")
    parser.add_argument("--list-download-links", action="store_true")
    args = parser.parse_args()

    setup_logging()

    with open(args.config, "r", encoding="utf-8") as file:
        config = json.load(file)

    if args.inspect_login:
        inspect_login(config)
        return 0

    now = datetime.now()

    context = {
        "date": now.strftime("%Y-%m-%d"),
        "yyyymmdd": now.strftime("%Y%m%d"),
        "mmddyyyy": now.strftime("%m%d%Y"),
        "mm": now.strftime("%m"),
        "dd": now.strftime("%d"),
        "yyyy": now.strftime("%Y"),
        "datetime": now.strftime("%Y-%m-%d_%H-%M-%S")
    }

    opener = make_opener()
    login(opener, config)
    if args.list_download_links:
        downloads_page_url = config["downloads"][0]["url"]
        list_download_links(opener, downloads_page_url)
        return 0

    download_dir = Path(config.get("download_dir", "downloads"))

    download_dir.mkdir(parents=True, exist_ok=True)

    failures = 0

    for download in config.get("downloads", []):
        for attempt in range(1, 4):
            try:
                download_file(opener, download, download_dir, context)
                break
            except Exception as error:
                failures += 1
                logging.exception("Attempt %s failed for %s: %s", attempt, download.get("name"), error)

                if attempt < 3:
                    time.sleep(attempt * 5)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())