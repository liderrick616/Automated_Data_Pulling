#1 in donwload for tuesday
import os
import re
import json
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
import html
from datetime import datetime

# =========================================================
# Config & Paths
# =========================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "BCGR_raw.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

USERNAME = config["username"]
PASSWORD = config["password"]

# Target directory for Outstanding RPO
DOWNLOAD_DIR = r"C:\Users\DLI\Beam Suntory Inc\Canadian S&OP Collaboration Hub - Documents\Daily Reports\Daily Inventory - All Boards\1. BC\BCLDB Inventory Analysis\CW Outstanding RPO"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Generate filename: Outstanding RPO yyyy-mm-dd.csv
current_date = datetime.now().strftime("%Y-%m-%d")
final_filename = f"Outstanding RPO {current_date}.csv"

# =========================================================
# Custom Variables for Outstanding RPO Inquiry
# =========================================================

TOOL_ID = "44"
FILTER_PAGE_URL = f"https://www.containerworld.com/CWFS/WEB_CAS/CAS_REPORT_INV_ORPOR_FILTER?p_online_tool_id={TOOL_ID}"
REPORT_INTERNAL_NAME = "dl_os_orders"

# =========================================================
# Session / Cookies Setup
# =========================================================

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
opener.addheaders = [
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
]

# =========================================================
# Open Home Page & Login
# =========================================================

HOME_URL = "https://www.containerworld.com/CWFS/WEB_PUBLIC/PUB_HOME"
print("Opening home page...")
home_html = opener.open(HOME_URL).read().decode("utf-8", errors="ignore")

cache_match = re.search(r'name="no_cache_id"\s+value="([^"]+)"', home_html, re.IGNORECASE)
if not cache_match:
    raise Exception("Could not locate no_cache_id.")

no_cache_id = cache_match.group(1)

login_url = "https://www.containerworld.com/CWFS/WEB_CAS/CAS_CUST_USER_LOGON"
payload = {
    "no_cache_id": no_cache_id,
    "username1": "",
    "username2": USERNAME,
    "userpassword1": "",
    "userpassword2": PASSWORD,
    "resolution": "",
    "attempts": "0",
    "log_browser_type": "Netscape",
    "log_browser_version": "5.0",
    "log_os": "Win32",
    "log_resolution": "1920 x 1080",
    "log_colour_depth": "24",
    "log_java_enabled": "false",
    "remember_me": "yes",
    "is_client_mobile": "N"
}

query_string = urllib.parse.urlencode(payload)
login_request = urllib.request.Request(
    f"{login_url}?{query_string}",
    method="GET",
    headers={"X-Requested-With": "XMLHttpRequest", "Referer": HOME_URL, "Accept": "*/*"}
)

print("Submitting login...")
login_html = opener.open(login_request).read().decode("utf-8", errors="ignore")

if "error" in login_html.lower() or "invalid" in login_html.lower():
    print("WARNING: Login may have failed.")
else:
    print("Login request accepted.")

# =========================================================
# Initialize Oracle Session Context
# =========================================================

print("Synchronizing backend Oracle session context...")
opener.open(FILTER_PAGE_URL)

# Force cookies to map to the root directory so they are transmitted
for c in cookie_jar:
    c.path = "/"

# =========================================================
# Construct the Secure Pipe-Delimited Oracle Frame Request
# =========================================================

print("Constructing pipeline payload...")

# Payload perfectly matches Javascript architecture with pipe delimiters
dl_url_string = (
    f"https://www.containerworld.com/reports/rwservlet?{REPORT_INTERNAL_NAME}|"
    "desformat=delimiteddata|delimited_hdr=yes|delimiter=,|p_resolution=1024|"
    f"p_online_tool_id={TOOL_ID}"
)

safe_dl_url = urllib.parse.quote(dl_url_string, safe=':/=?,')
frame_url = f"https://www.containerworld.com/CWFS/WEB_CAS/CAS_SHOW_DOWNLOAD_FRAME?report_url={safe_dl_url}"

# =========================================================
# Execute Frame, Generate Security Token, and Download File
# =========================================================

print("Triggering Oracle Security Verification Frame...")
frame_request = urllib.request.Request(frame_url, method="GET")
frame_request.add_header("Referer", FILTER_PAGE_URL)

try:
    frame_response = opener.open(frame_request)
    content_type = frame_response.headers.get("Content-Type", "").lower()

    if "text/html" in content_type:
        frame_html = frame_response.read().decode('utf-8', errors='ignore')
        
        match = re.search(r'(/reports/rwservlet[^"\']+)', frame_html)
        
        if match and "REP-" not in frame_html:
            final_url = html.unescape(match.group(1))
            final_url = "https://www.containerworld.com" + final_url
            final_url = final_url.replace(" ", "%20")
                
            print(f"Extracted Authorized Final URL: {final_url[:80]}...")
            download_request = urllib.request.Request(final_url, method="GET")
            download_request.add_header("Referer", frame_url)
            download_response = opener.open(download_request)
        else:
            err_match = re.search(r'<pre>(.*?)</pre>', frame_html, re.IGNORECASE | re.DOTALL)
            if err_match:
                print("Oracle Error:", err_match.group(1).strip())
            raise Exception("Download failed. Server returned an HTML error page.")
    else:
        print("Server pushed file directly via stream.")
        download_response = frame_response

    # Verify we aren't saving an Oracle HTML error screen as a CSV
    final_content_type = download_response.headers.get("Content-Type", "").lower()
    if "text/html" in final_content_type:
        error_html = download_response.read().decode('utf-8', errors='ignore')
        err_match = re.search(r'<pre>(.*?)</pre>', error_html, re.IGNORECASE | re.DOTALL)
        if err_match:
            print("Oracle Error:", err_match.group(1).strip())
        raise Exception("Final download failed. Server returned HTML instead of CSV.")

    output_path = os.path.join(DOWNLOAD_DIR, final_filename)
    print(f"Writing payload to disk: {output_path}")

    with open(output_path, "wb") as f:
        f.write(download_response.read())

    print(f"Execution fully completed. File saved as {final_filename}.")

except urllib.error.HTTPError as e:
    print(f"\n--- HTTP ERROR {e.code} ---")
    print(e.read().decode('utf-8', errors='ignore')[:1500])
    raise Exception(f"Download failed with HTTP {e.code}")
