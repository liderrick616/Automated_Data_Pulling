
#!/usr/bin/env python3
# AlbertaGR.py
#
# Downloads the LiquorConnect "Receipts End of Day" report as CSV.
# Uses only Python standard-library modules. No Playwright, Selenium, or requests.

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import html
from html.parser import HTMLParser
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import urllib.error

SCRIPT_VERSION = "AlbertaGR report-login debug v2026-05-13-1514"
MFA_REENTER_PASSWORD = "Start#1229"
MFA_SUBMIT_EVENT_TARGET = "ctl00$PlaceHolderMain$signInControl$SubmitEmailConfirmation"

class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: List[Dict[str, Any]] = []
        self.current_form: Optional[Dict[str, Any]] = None
        self.all_controls: List[Dict[str, str]] = []
        self.labels: List[Dict[str, str]] = []
        self._label_attrs: Optional[Dict[str, str]] = None
        self._label_text: List[str] = []

    @staticmethod
    def _attrs(attrs: List[Tuple[str, Optional[str]]]) -> Dict[str, str]:
        return {k.lower(): (v if v is not None else "") for k, v in attrs}

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        attrs_d = self._attrs(attrs)

        if tag_l == "form":
            self.current_form = {"tag": "form", "attrs": attrs_d, "controls": []}
            self.forms.append(self.current_form)
            return

        if tag_l in ("input", "button", "select", "textarea"):
            control = {"tag": tag_l, **attrs_d}
            self.all_controls.append(control)
            if self.current_form is not None:
                self.current_form["controls"].append(control)

        if tag_l == "label":
            self._label_attrs = attrs_d
            self._label_text = []

    def handle_data(self, data: str) -> None:
        if self._label_attrs is not None:
            self._label_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l == "form":
            self.current_form = None
        elif tag_l == "label" and self._label_attrs is not None:
            self.labels.append({
                "attrs": self._label_attrs,
                "text": " ".join(" ".join(self._label_text).split())
            })
            self._label_attrs = None
            self._label_text = []


class WebClient:
    def __init__(self, user_agent: str, timeout: int, verbose: bool) -> None:
        self.timeout = timeout
        self.verbose = verbose
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPRedirectHandler()
        )
        self.user_agent = user_agent

    def log(self, message: str) -> None:
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")

    def open(
        self,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        referer: Optional[str] = None,
    ) -> Tuple[str, int, Dict[str, str], bytes]:
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/csv,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
        if headers:
            request_headers.update(headers)
        if referer:
            request_headers["Referer"] = referer

        req = urllib.request.Request(url, data=data, headers=request_headers)
        method = "POST" if data is not None else "GET"
        self.log(f"{method} {url}")

        try:
            resp = self.opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            resp = e

        raw = resp.read()
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        if resp_headers.get("content-encoding", "").lower() == "gzip":
            raw = gzip.decompress(raw)

        return resp.geturl(), int(getattr(resp, "code", 0) or 0), resp_headers, raw


def read_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    # Optional environment overrides so the password does not have to be edited into the JSON.
    cfg["username"] = os.environ.get("ALBERTAGR_USERNAME", cfg.get("username", ""))
    cfg["password"] = os.environ.get("ALBERTAGR_PASSWORD", cfg.get("password", ""))
    return cfg


def decode_response(headers: Dict[str, str], raw: bytes) -> str:
    content_type = headers.get("content-type", "")
    m = re.search(r"charset=([A-Za-z0-9_\-]+)", content_type, flags=re.I)
    encodings = [m.group(1)] if m else []
    encodings += ["utf-8", "cp1252", "latin-1"]

    for enc in encodings:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_html(text: str) -> FormParser:
    parser = FormParser()
    parser.feed(text)
    return parser


def normalize_label(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def form_action(form: Dict[str, Any], page_url: str) -> str:
    action = form.get("attrs", {}).get("action", "")
    return urllib.parse.urljoin(page_url, html.unescape(action or page_url))


def build_fields_from_form(form: Dict[str, Any]) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for c in form.get("controls", []):
        tag = c.get("tag", "").lower()
        name = c.get("name", "")
        if not name:
            continue

        if tag == "input":
            typ = c.get("type", "text").lower()
            if typ in ("submit", "button", "image", "reset", "file"):
                continue
            if typ in ("checkbox", "radio") and "checked" not in c:
                continue
            fields[name] = c.get("value", "")
        elif tag in ("textarea", "select"):
            fields[name] = c.get("value", "")

    return fields


def post_form(
    client: WebClient,
    form: Dict[str, Any],
    page_url: str,
    fields: Dict[str, str],
    referer: Optional[str] = None,
) -> Tuple[str, int, Dict[str, str], bytes]:
    target = form_action(form, page_url)
    payload = urllib.parse.urlencode(fields).encode("utf-8")
    return client.open(
        target,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        referer=referer or page_url,
    )


def dump_debug(debug_dir: Optional[Path], name: str, content: bytes | str) -> None:
    if debug_dir is None:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    encoding = None if isinstance(content, bytes) else "utf-8"
    with (debug_dir / name).open(mode, encoding=encoding) as f:
        f.write(content)


def control_text(c: Dict[str, str]) -> str:
    return " ".join([
        c.get("name", ""),
        c.get("id", ""),
        c.get("value", ""),
        c.get("title", ""),
        c.get("alt", ""),
        c.get("aria-label", ""),
    ])


def find_password_form(parser: FormParser) -> Dict[str, Any]:
    for form in parser.forms:
        for c in form.get("controls", []):
            if c.get("tag") == "input" and c.get("type", "").lower() == "password":
                return form
    if parser.forms:
        return parser.forms[0]
    raise RuntimeError("Could not find a login form on the login page.")


def find_login_fields(form: Dict[str, Any], cfg: Dict[str, Any]) -> Tuple[str, str, Optional[Dict[str, str]]]:
    controls = form.get("controls", [])

    username_field = cfg.get("login_username_field") or ""
    password_field = cfg.get("login_password_field") or ""

    if not password_field:
        for c in controls:
            if c.get("tag") == "input" and c.get("type", "").lower() == "password" and c.get("name"):
                password_field = c["name"]
                break

    if not username_field:
        preferred = []
        fallback = []
        for c in controls:
            if c.get("tag") != "input" or not c.get("name"):
                continue
            typ = c.get("type", "text").lower()
            if typ not in ("text", "email", "tel", ""):
                continue
            joined = normalize_label(control_text(c))
            if any(token in joined for token in ("username", "userid", "login", "email", "account", "user")):
                preferred.append(c["name"])
            else:
                fallback.append(c["name"])
        username_field = (preferred or fallback or [""])[0]

    if not username_field or not password_field:
        raise RuntimeError("Could not identify the username/password fields on the login page.")

    submit_control = None
    for c in controls:
        typ = c.get("type", "").lower()
        tag = c.get("tag", "")
        if (tag == "input" and typ in ("submit", "button", "image")) or tag == "button":
            txt = normalize_label(control_text(c))
            if any(token in txt for token in ("signin", "login", "logon", "submit")):
                submit_control = c
                break
    if submit_control is None:
        for c in controls:
            typ = c.get("type", "").lower()
            if c.get("tag") == "input" and typ in ("submit", "button", "image") and c.get("name"):
                submit_control = c
                break

    return username_field, password_field, submit_control




def redact_text(value: str) -> str:
    # Hide common secret-bearing query/header values while preserving useful diagnostics.
    value = re.sub(r"(?i)(password=)[^&\s]+", r"\1***", value)
    value = re.sub(r"(?i)(pwd=)[^&\s]+", r"\1***", value)
    return value


def redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    redacted: Dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in {"set-cookie", "cookie", "authorization", "proxy-authorization"}:
            redacted[k] = "***redacted***"
        else:
            redacted[k] = redact_text(str(v))
    return redacted


def cookie_snapshot(client: Optional[WebClient]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    if client is None:
        return out

    for c in client.cookie_jar:
        out.append({
            "name": c.name,
            "domain": c.domain,
            "path": c.path,
            "secure": bool(c.secure),
            "expires": c.expires,
            "value_length": len(c.value or ""),
        })

    return out


def dump_http_meta(
    debug_dir: Optional[Path],
    stem: str,
    url: str,
    status: int,
    headers: Dict[str, str],
    raw: bytes,
    client: Optional[WebClient] = None,
) -> None:
    if debug_dir is None:
        return

    meta = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "url": redact_text(url),
        "status": status,
        "content_type": headers.get("content-type", ""),
        "content_length_header": headers.get("content-length", ""),
        "body_bytes": len(raw),
        "headers": redact_headers(headers),
        "cookies": cookie_snapshot(client),
    }

    dump_debug(debug_dir, f"{stem}_meta.json", json.dumps(meta, indent=2))


def dump_forms_summary(debug_dir: Optional[Path], stem: str, page_html: str) -> None:
    if debug_dir is None:
        return

    parser = parse_html(page_html)
    lines: List[str] = []
    lines.append(f"forms: {len(parser.forms)}")

    for idx, form in enumerate(parser.forms, start=1):
        attrs = form.get("attrs", {})
        lines.append("")
        lines.append(f"FORM {idx}: method={attrs.get('method', '')} action={attrs.get('action', '')}")

        for c in form.get("controls", []):
            tag = c.get("tag", "")
            ctype = c.get("type", "")
            name = c.get("name", "")
            cid = c.get("id", "")
            value = c.get("value", "")

            if "pass" in name.lower() or "pass" in cid.lower() or ctype.lower() == "password":
                value = "***redacted***"
            elif len(value) > 100:
                value = value[:100] + "..."

            lines.append(f"  {tag} type={ctype} name={name} id={cid} value={value}")

    dump_debug(debug_dir, f"{stem}_forms.txt", "`n".join(lines))

def extract_login_event_target(page_html: str) -> Optional[str]:
    # LiquorConnect's Login button is an ASP.NET LinkButton:
    # WebForm_DoPostBackWithOptions(new WebForm_PostBackOptions("ctl00$...$Login", ...))
    unescaped = html.unescape(page_html)
    targets: List[str] = []
    for m in re.finditer(r"WebForm_PostBackOptions\(\s*['\"]([^'\"]+)['\"]", unescaped, flags=re.I):
        targets.append(m.group(1))
    for target in targets:
        if "login" in normalize_label(target):
            return target
    return targets[0] if targets else None


def extract_ajax_postback_context(page_html: str, event_target: str) -> Tuple[str, str]:
    script_manager = "ctl00$ScriptManager"
    update_panel = "ctl00$PlaceHolderMain$LoginUpdatePanel"

    m = re.search(
        r"PageRequestManager\._initialize\(\s*['\"]([^'\"]+)['\"].*?\[([^\]]*)\]",
        page_html,
        flags=re.I | re.S,
    )
    if m:
        script_manager = html.unescape(m.group(1))
        panel_blob = html.unescape(m.group(2))
        panel_matches = re.findall(r"['\"]t?([^'\"]*LoginUpdatePanel[^'\"]*)['\"]", panel_blob, flags=re.I)
        if panel_matches:
            update_panel = panel_matches[0]

    return script_manager, update_panel


def extract_ajax_redirect(response_text: str) -> Optional[str]:
    idx = response_text.lower().find("pageredirect")
    if idx < 0:
        return None

    tail = response_text[idx:]
    parts = tail.split("|")
    for part in parts[1:]:
        candidate = html.unescape(part.strip())
        if not candidate:
            continue
        if candidate.lower() in {"pageredirect", "true", "false"}:
            continue
        if re.fullmatch(r"\d+", candidate):
            continue
        return urllib.parse.unquote(candidate)

    return None


def build_login_post_fields(
    login_form: Dict[str, Any],
    page_html: str,
    cfg: Dict[str, Any],
) -> Tuple[Dict[str, str], str, str, str]:
    fields = build_fields_from_form(login_form)
    username_field, password_field, submit_control = find_login_fields(login_form, cfg)

    fields[username_field] = cfg["username"]
    fields[password_field] = cfg["password"]

    login_event_target = cfg.get("login_event_target") or extract_login_event_target(page_html)

    if login_event_target:
        fields["__EVENTTARGET"] = login_event_target
        fields.setdefault("__EVENTARGUMENT", "")
    elif submit_control and submit_control.get("name"):
        login_event_target = submit_control["name"]
        fields[submit_control["name"]] = submit_control.get("value", "Login")
    else:
        login_event_target = ""

    return fields, username_field, password_field, login_event_target


def dump_redacted_login_fields(
    debug_dir: Optional[Path],
    name: str,
    fields: Dict[str, str],
    password_field: str,
) -> None:
    redacted = {}
    for k, v in fields.items():
        if k == password_field or "password" in k.lower():
            redacted[k] = "***redacted***"
        else:
            redacted[k] = v
    dump_debug(debug_dir, name, json.dumps(redacted, indent=2))


def post_login_ajax(
    client: WebClient,
    form: Dict[str, Any],
    page_url: str,
    page_html: str,
    fields: Dict[str, str],
    event_target: str,
) -> Tuple[str, int, Dict[str, str], bytes]:
    target = form_action(form, page_url)
    script_manager, update_panel = extract_ajax_postback_context(page_html, event_target)

    fields[script_manager] = f"{update_panel}|{event_target}"
    fields["__ASYNCPOST"] = "true"

    payload = urllib.parse.urlencode(fields).encode("utf-8")

    return client.open(
        target,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-MicrosoftAjax": "Delta=true",
            "X-Requested-With": "XMLHttpRequest",
            "Cache-Control": "no-cache",
            "Accept": "*/*",
        },
        referer=page_url,
    )


def save_login_response(
    debug_dir: Optional[Path],
    stem: str,
    final_url: str,
    status: int,
    headers: Dict[str, str],
    raw: bytes,
    client: WebClient,
) -> str:
    text = decode_response(headers, raw)
    lower_start = text[:1000].lower()
    ext = ".html" if "<html" in lower_start or "<!doctype html" in lower_start else ".txt"

    dump_debug(debug_dir, stem + ext, text)
    dump_http_meta(debug_dir, stem, final_url, status, headers, raw, client)

    if ext == ".html":
        dump_forms_summary(debug_dir, stem, text)

    return text


def extract_failure_message(page_html: str) -> str:
    messages: List[str] = []

    patterns = [
        r"<span[^>]+id=[\"']FailureSpan[\"'][^>]*>(.*?)</span>",
        r"<div[^>]+class=[\"'][^\"']*(?:error|failure|validation)[^\"']*[\"'][^>]*>(.*?)</div>",
    ]

    for pattern in patterns:
        for m in re.finditer(pattern, page_html, flags=re.I | re.S):
            text = re.sub(r"<[^>]+>", " ", m.group(1))
            text = html.unescape(" ".join(text.split()))
            if text:
                messages.append(text)

    return " | ".join(messages)


def is_mfa_page(url: str, page_html: str) -> bool:
    lower_url = url.lower()
    lower = page_html.lower()
    return (
        "confirm2fa.aspx" in lower_url
        or "submitemailconfirmation" in lower
        or "multi-factor" in lower
        or "multifactor" in lower
        or "verification code" in lower
        or "mfa code" in lower
    )


def all_postback_targets(page_html: str) -> List[str]:
    unescaped = html.unescape(page_html)
    targets: List[str] = []
    for m in re.finditer(r"WebForm_PostBackOptions\(\s*['\"]([^'\"]+)['\"]", unescaped, flags=re.I):
        target = m.group(1)
        if target not in targets:
            targets.append(target)
    return targets


def find_postback_target(
    page_html: str,
    include_keywords: List[str],
    exclude_keywords: Optional[List[str]] = None,
) -> Optional[str]:
    exclude_keywords = exclude_keywords or []
    targets = all_postback_targets(page_html)

    for target in targets:
        norm = normalize_label(target)
        if any(k in norm for k in include_keywords) and not any(k in norm for k in exclude_keywords):
            return target

    return None


def find_mfa_form(page_html: str) -> Dict[str, Any]:
    parser = parse_html(page_html)

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for form in parser.forms:
        combined = " ".join(control_text(c) for c in form.get("controls", [])).lower()
        score = len(form.get("controls", []))
        if "__viewstate" in combined:
            score += 100
        if "confirmation" in combined or "verification" in combined or "code" in combined:
            score += 100
        scored.append((score, form))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    raise RuntimeError("Could not find the MFA form on Confirm2Fa.aspx.")


def find_mfa_code_field(form: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    override = cfg.get("mfa_code_field")
    if override:
        return override

    visible_inputs: List[Dict[str, str]] = []

    for c in form.get("controls", []):
        if c.get("tag") != "input" or not c.get("name"):
            continue

        typ = c.get("type", "text").lower()
        if typ in ("hidden", "submit", "button", "image", "reset", "checkbox", "radio", "file", "password"):
            continue

        visible_inputs.append(c)
        txt = normalize_label(control_text(c))

        if any(token in txt for token in (
            "code",
            "mfa",
            "verification",
            "verify",
            "confirmation",
            "emailconfirmation",
            "token",
            "pin",
        )):
            return c["name"]

    if len(visible_inputs) == 1:
        return visible_inputs[0]["name"]

    names = ", ".join(c.get("name", "") for c in visible_inputs)
    raise RuntimeError(
        "Could not identify the MFA code input field. "
        f"Visible fields found: {names}. Add mfa_code_field to AlbertaGR_raw.json."
    )


def submit_mfa_event(
    client: WebClient,
    page_url: str,
    page_html: str,
    event_target: str,
    stem: str,
    debug_dir: Optional[Path],
) -> Tuple[str, str]:
    form = find_mfa_form(page_html)
    fields = build_fields_from_form(form)
    fields["__EVENTTARGET"] = event_target
    fields.setdefault("__EVENTARGUMENT", "")

    dump_debug(debug_dir, stem + "_fields_redacted.json", json.dumps(fields, indent=2))

    post_url, post_status, post_headers, post_raw = post_form(
        client,
        form,
        page_url,
        fields,
        referer=page_url,
    )

    post_html = save_login_response(debug_dir, stem, post_url, post_status, post_headers, post_raw, client)

    redirect = extract_ajax_redirect(post_html)
    if redirect:
        redirect_url = urllib.parse.urljoin(page_url, redirect)
        redir_url, redir_status, redir_headers, redir_raw = client.open(redirect_url, referer=page_url)
        redir_html = save_login_response(
            debug_dir,
            stem + "_redirect",
            redir_url,
            redir_status,
            redir_headers,
            redir_raw,
            client,
        )
        return redir_url, redir_html

    return post_url, post_html


def complete_mfa(
    client: WebClient,
    cfg: Dict[str, Any],
    debug_dir: Optional[Path],
    page_url: str,
    page_html: str,
    attempts: List[str],
    stem: str,
) -> Tuple[bool, str, str]:
    if not is_mfa_page(page_url, page_html):
        return False, page_url, page_html

    client.log("MFA page detected.")

    send_email_target = cfg.get("mfa_send_email_event_target") or find_postback_target(
        page_html,
        ["submitemailconfirmation", "emailconfirmation", "sendcode", "sendemail", "resend"],
    )

    # Do not auto-click SubmitEmailConfirmation here. That is the final Login button.
    send_email_target = None

    if send_email_target:
        client.log(f"MFA email-code event target ({stem}): {send_email_target}")
        page_url, page_html = submit_mfa_event(
            client,
            page_url,
            page_html,
            send_email_target,
            stem + "_send_email_code",
            debug_dir,
        )
        attempts.append(f"{stem}_send_email_code: final_url={page_url}; mfa_page={is_mfa_page(page_url, page_html)}")

    max_tries = int(cfg.get("mfa_max_tries", 3))

    for try_num in range(1, max_tries + 1):
        code = os.environ.get("ALBERTAGR_MFA_CODE", "").strip()

        if not code:
            code = input("Enter LiquorConnect 6-digit MFA code from email: ").strip()

        if not re.fullmatch(r"\d{6}", code):
            client.log("MFA code must be exactly 6 digits.")
            os.environ.pop("ALBERTAGR_MFA_CODE", None)
            continue

        form = find_mfa_form(page_html)
        fields = build_fields_from_form(form)
        code_field = find_mfa_code_field(form, cfg)
        fields[code_field] = code

        # Confirm2Fa.aspx requires username + re-entered password + MFA code.
        # The password field was blank in the debug output, causing validation failure.
        for key in list(fields.keys()):
            key_lower = key.lower()

            if key_lower.endswith("$username") or key_lower.endswith("_username") or "signincontrol$username" in key_lower:
                fields[key] = cfg["username"]

            if key_lower.endswith("$password") or key_lower.endswith("_password") or "signincontrol$password" in key_lower:
                fields[key] = cfg["password"]

        submit_target = cfg.get("mfa_submit_event_target") or find_postback_target(
            page_html,
            ["submitcode", "verifycode", "validatecode", "confirmcode", "submitconfirmation", "verify", "continue", "submit"],
            ["submitemailconfirmation", "resend", "sendemail", "sendcode"],
        )

        # FORCE MFA Login submission fields.
        # The page button text is "Login", but the ASP.NET LinkButton target is SubmitEmailConfirmation.
        fields["ctl00$PlaceHolderMain$signInControl$UserName"] = cfg.get("username", "DLi")
        fields["ctl00$PlaceHolderMain$signInControl$Password"] = "Start#1229"
        fields["ctl00$PlaceHolderMain$signInControl$RememberMe"] = "on"
        fields["__EVENTTARGET"] = "ctl00$PlaceHolderMain$signInControl$SubmitEmailConfirmation"
        fields["__EVENTARGUMENT"] = ""
        submit_target = "ctl00$PlaceHolderMain$signInControl$SubmitEmailConfirmation"

        if submit_target:
            fields["__EVENTTARGET"] = submit_target
            fields.setdefault("__EVENTARGUMENT", "")
            client.log(f"MFA submit event target ({stem}, try {try_num}): {submit_target}")
        else:
            fields.setdefault("__EVENTTARGET", "")
            fields.setdefault("__EVENTARGUMENT", "")
            client.log(f"MFA submit button not found; posting code field only ({stem}, try {try_num}).")

        redacted = dict(fields)
        redacted[code_field] = "***redacted***"
        dump_debug(debug_dir, f"{stem}_submit_code_{try_num}_fields_redacted.json", json.dumps(redacted, indent=2))

        post_url, post_status, post_headers, post_raw = post_form(
            client,
            form,
            page_url,
            fields,
            referer=page_url,
        )

        post_html = save_login_response(
            debug_dir,
            f"{stem}_submit_code_{try_num}",
            post_url,
            post_status,
            post_headers,
            post_raw,
            client,
        )

        redirect = extract_ajax_redirect(post_html)
        if redirect:
            redirect_url = urllib.parse.urljoin(page_url, redirect)
            redir_url, redir_status, redir_headers, redir_raw = client.open(redirect_url, referer=page_url)
            post_url = redir_url
            post_html = save_login_response(
                debug_dir,
                f"{stem}_submit_code_{try_num}_redirect",
                redir_url,
                redir_status,
                redir_headers,
                redir_raw,
                client,
            )

        still_mfa = is_mfa_page(post_url, post_html)
        still_login = looks_like_login_page(post_url, post_html)

        attempts.append(
            f"{stem}_submit_code_{try_num}: final_url={post_url}; mfa_page={still_mfa}; login_page={still_login}"
        )

        if not still_mfa and not still_login:
            client.log("MFA accepted.")
            return True, post_url, post_html

        client.log("MFA code was not accepted, or the page still requires MFA.")
        os.environ.pop("ALBERTAGR_MFA_CODE", None)
        page_url, page_html = post_url, post_html

    return False, page_url, page_html

def login(client: WebClient, cfg: Dict[str, Any], debug_dir: Optional[Path]) -> str:
    """
    Authenticate to LiquorConnect, including manual MFA code entry.
    """
    login_via_report = bool(cfg.get("login_via_report", True))
    start_url = cfg.get("login_start_url") or (cfg["report_url"] if login_via_report else cfg["login_url"])
    client.log(f"Login start URL: {start_url}")

    final_url, status, headers, raw = client.open(start_url)
    login_html = decode_response(headers, raw)

    dump_debug(debug_dir, "01_login_get.html", login_html)
    dump_http_meta(debug_dir, "01_login_get", final_url, status, headers, raw, client)
    dump_forms_summary(debug_dir, "01_login_get", login_html)

    if not looks_like_login_page(final_url, login_html) and not is_mfa_page(final_url, login_html):
        client.log("Initial request did not show login/MFA form; continuing.")
        return final_url

    attempts: List[str] = []

    def attempt_full(page_url: str, page_html: str, stem: str) -> Tuple[bool, str, str]:
        parser = parse_html(page_html)
        login_form = find_password_form(parser)

        fields, _username_field, password_field, event_target = build_login_post_fields(login_form, page_html, cfg)

        if event_target:
            client.log(f"Login event target ({stem}): {event_target}")

        dump_redacted_login_fields(debug_dir, stem + "_fields_redacted.json", fields, password_field)

        post_url, post_status, post_headers, post_raw = post_form(client, login_form, page_url, fields, referer=page_url)
        post_html = save_login_response(debug_dir, stem, post_url, post_status, post_headers, post_raw, client)

        mfa = is_mfa_page(post_url, post_html)
        failed = looks_like_login_page(post_url, post_html) and not mfa

        client.log(f"{stem} result: url={post_url}; login_page={failed}; mfa_page={mfa}")

        attempts.append(f"{stem}: final_url={post_url}; status={post_status}; login_page={failed}; mfa_page={mfa}")

        return (mfa or not failed), post_url, post_html

    def verify_report_access(referer_url: str, stem: str) -> Tuple[bool, str, str]:
        check_url, check_status, check_headers, check_raw = client.open(cfg["report_url"], referer=referer_url)

        check_html = save_login_response(
            debug_dir,
            stem + "_report_check",
            check_url,
            check_status,
            check_headers,
            check_raw,
            client,
        )

        failed = looks_like_login_page(check_url, check_html) or is_mfa_page(check_url, check_html)
        attempts.append(f"{stem}_report_check: final_url={check_url}; status={check_status}; blocked={failed}")

        return (not failed), check_url, check_html

    current_url = final_url
    current_html = login_html

    if is_mfa_page(current_url, current_html):
        ok, current_url, current_html = complete_mfa(
            client,
            cfg,
            debug_dir,
            current_url,
            current_html,
            attempts,
            "01_mfa",
        )

        if ok:
            verified, verify_url, verify_html = verify_report_access(current_url, "01_mfa")
            if verified:
                dump_debug(debug_dir, "02_login_attempts_summary.txt", "\n".join(attempts))
                return verify_url

            current_url, current_html = verify_url, verify_html

    if looks_like_login_page(current_url, current_html):
        ok, current_url, current_html = attempt_full(current_url, current_html, "02_login_post")

        if ok and is_mfa_page(current_url, current_html):
            ok, current_url, current_html = complete_mfa(
                client,
                cfg,
                debug_dir,
                current_url,
                current_html,
                attempts,
                "02_mfa",
            )

        if ok:
            verified, verify_url, verify_html = verify_report_access(current_url, "02_login_post")
            if verified:
                client.log("Login and MFA are confirmed; report access is available.")
                dump_debug(debug_dir, "02_login_attempts_summary.txt", "\n".join(attempts))
                return verify_url

            current_url, current_html = verify_url, verify_html

            if is_mfa_page(current_url, current_html):
                ok, current_url, current_html = complete_mfa(
                    client,
                    cfg,
                    debug_dir,
                    current_url,
                    current_html,
                    attempts,
                    "02_report_mfa",
                )

                if ok:
                    verified, verify_url, verify_html = verify_report_access(current_url, "02_report_mfa")
                    if verified:
                        client.log("Login and MFA are confirmed; report access is available.")
                        dump_debug(debug_dir, "02_login_attempts_summary.txt", "\n".join(attempts))
                        return verify_url

                    current_url, current_html = verify_url, verify_html

    configured_login_url = cfg.get("login_url")

    if configured_login_url and configured_login_url != start_url:
        client.log("Trying configured login_url as fallback.")

        f2_url, f2_status, f2_headers, f2_raw = client.open(configured_login_url)
        f2_html = decode_response(f2_headers, f2_raw)

        dump_debug(debug_dir, "02c_login_get_fallback.html", f2_html)
        dump_http_meta(debug_dir, "02c_login_get_fallback", f2_url, f2_status, f2_headers, f2_raw, client)
        dump_forms_summary(debug_dir, "02c_login_get_fallback", f2_html)

        if is_mfa_page(f2_url, f2_html):
            ok, current_url, current_html = complete_mfa(
                client,
                cfg,
                debug_dir,
                f2_url,
                f2_html,
                attempts,
                "02c_mfa_fallback",
            )

            if ok:
                verified, verify_url, verify_html = verify_report_access(current_url, "02c_mfa_fallback")
                if verified:
                    dump_debug(debug_dir, "02_login_attempts_summary.txt", "\n".join(attempts))
                    return verify_url

        elif looks_like_login_page(f2_url, f2_html):
            ok, current_url, current_html = attempt_full(f2_url, f2_html, "02d_login_post_fallback")

            if ok and is_mfa_page(current_url, current_html):
                ok, current_url, current_html = complete_mfa(
                    client,
                    cfg,
                    debug_dir,
                    current_url,
                    current_html,
                    attempts,
                    "02d_mfa_fallback",
                )

            if ok:
                verified, verify_url, verify_html = verify_report_access(current_url, "02d_login_post_fallback")
                if verified:
                    dump_debug(debug_dir, "02_login_attempts_summary.txt", "\n".join(attempts))
                    return verify_url

                current_url, current_html = verify_url, verify_html

    failure = extract_failure_message(current_html)
    dump_debug(debug_dir, "02_login_attempts_summary.txt", "\n".join(attempts))

    extra = f" Login page message: {failure}" if failure else ""

    raise RuntimeError(
        "Login/MFA did not complete successfully."
        + extra
        + " Check 02_login_attempts_summary.txt and the MFA debug files in the newest AlbertaGR_debug_* folder."
    )

def looks_like_login_page(url: str, text: str) -> bool:
    lower_url = url.lower()
    lower_text = text.lower()
    return (
        "login.aspx" in lower_url
        or ("type=\"password\"" in lower_text and ("sign in" in lower_text or "login" in lower_text))
    )


def find_report_form(parser: FormParser) -> Dict[str, Any]:
    if not parser.forms:
        raise RuntimeError("Could not find any form on the report page.")

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for form in parser.forms:
        controls = form.get("controls", [])
        combined = " ".join(control_text(c) for c in controls).lower()
        score = len(controls)
        if "__viewstate" in combined:
            score += 100
        if "reportviewer" in combined or "view report" in combined:
            score += 100
        scored.append((score, form))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def find_input_name_by_id(form: Dict[str, Any], input_id: str) -> Optional[str]:
    input_id_l = input_id.lower()
    for c in form.get("controls", []):
        if c.get("tag") == "input" and c.get("id", "").lower() == input_id_l and c.get("name"):
            return c["name"]
    return None


def find_start_date_field(report_html: str, parser: FormParser, form: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    override = cfg.get("report_start_date_field")
    if override:
        return override

    target_norm = normalize_label(cfg.get("start_date_label", "Start Date"))

    # Best case: a <label for="...">Start Date</label> points to the input ID.
    for lbl in parser.labels:
        if target_norm and target_norm in normalize_label(lbl.get("text", "")):
            input_id = lbl.get("attrs", {}).get("for", "")
            if input_id:
                name = find_input_name_by_id(form, input_id)
                if name:
                    return name

    # Next: find visible text inputs whose name/id/title looks like Start Date.
    visible_text_inputs = []
    for c in form.get("controls", []):
        if c.get("tag") != "input" or not c.get("name"):
            continue
        typ = c.get("type", "text").lower()
        if typ in ("hidden", "submit", "button", "image", "reset", "file", "checkbox", "radio"):
            continue
        visible_text_inputs.append(c)
        txt = normalize_label(control_text(c))
        if "start" in txt and "date" in txt:
            return c["name"]

    # Regex fallback: find the first input after "Start Date" in the raw HTML.
    label_match = re.search(r"start\s*date", report_html, flags=re.I)
    if label_match:
        chunk = report_html[label_match.end(): label_match.end() + 5000]
        for m in re.finditer(r"<input\b[^>]*>", chunk, flags=re.I):
            attrs = parse_tag_attrs(m.group(0))
            typ = attrs.get("type", "text").lower()
            name = attrs.get("name", "")
            if name and typ not in ("hidden", "submit", "button", "image", "reset"):
                return html.unescape(name)

    # Many SSRS parameter pages have only one visible parameter textbox.
    if len(visible_text_inputs) == 1:
        return visible_text_inputs[0]["name"]

    if visible_text_inputs:
        names = ", ".join(c.get("name", "") for c in visible_text_inputs[:10])
        raise RuntimeError(
            "Could not uniquely identify the Start Date field. "
            f"Visible text fields found: {names}. Set report_start_date_field in AlbertaGR_raw.json."
        )

    raise RuntimeError("Could not identify a visible Start Date input on the report page.")


def parse_tag_attrs(tag: str) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    for m in re.finditer(
        r"""([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
        tag,
    ):
        key = m.group(1).lower()
        value = m.group(2) if m.group(2) is not None else m.group(3) if m.group(3) is not None else m.group(4)
        attrs[key] = html.unescape(value or "")
    return attrs


def find_view_report_button(form: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[Dict[str, str]]:
    override = cfg.get("view_report_button_field")
    if override:
        return {"tag": "input", "name": override, "value": cfg.get("view_report_button_value", "View Report")}

    preferred = []
    fallback = []
    for c in form.get("controls", []):
        tag = c.get("tag", "")
        typ = c.get("type", "").lower()
        is_button = (tag == "button") or (tag == "input" and typ in ("submit", "button", "image"))
        if not is_button:
            continue

        if c.get("name"):
            fallback.append(c)

        txt = normalize_label(control_text(c))
        if "viewreport" in txt or txt == "view" or "runreport" in txt:
            preferred.append(c)

    return (preferred or fallback or [None])[0]


def submit_report(client, cfg, report_date, debug_dir):
    """
    Load Daily Receipts, set the ReportViewer Start Date dropdown, then click View Report.

    Daily Receipts has:
      - Selection text field: ctl08 ctl07 txtValue
      - OR Quick Enter text field: ctl08 ctl09 txtValue
      - Start Date dropdown: ctl08 ctl11 ddValue
      - End Date dropdown: ctl08 ctl13 ddValue

    The old logic looked at visible text boxes and confused Selection / Quick Enter with dates.
    """
    report_url = cfg.get(
        "report_url",
        "https://prtl.liquorconnect.com/Reporting/_layouts/15/CLS.LC.ReportViewer/Report.aspx?Path=%2fProd%2fAgent%2fReceipts+End+of+Day",
    )

    start_field = cfg.get(
        "report_start_date_field",
        "ctl00$PlaceHolderMain$ReportViewer1$ctl08$ctl11$ddValue",
    )

    end_field = cfg.get(
        "report_end_date_field",
        "ctl00$PlaceHolderMain$ReportViewer1$ctl08$ctl13$ddValue",
    )

    view_button = cfg.get(
        "view_report_field",
        "ctl00$PlaceHolderMain$ReportViewer1$ctl08$ctl00",
    )

    def find_report_form(page_html):
        parser = parse_html(page_html)

        for form in parser.forms:
            action = form.get("action", "")
            controls_blob = " ".join(
                str(c.get("name", "")) + " " + str(c.get("id", "")) + " " + str(c.get("value", ""))
                for c in form.get("controls", [])
            )

            if "ReportViewer1" in controls_blob or "Report.aspx" in action:
                return form

        if parser.forms:
            return parser.forms[0]

        raise RuntimeError("Could not find the Daily Receipts report form.")

    def extract_select_options(page_html, field_name):
        pattern = (
            r'<select\b[^>]*\bname=["\']'
            + re.escape(field_name)
            + r'["\'][^>]*>(.*?)</select>'
        )

        m = re.search(pattern, page_html, flags=re.I | re.S)

        if not m:
            return []

        select_html = m.group(1)
        options = []

        for opt in re.finditer(r"<option\b([^>]*)>(.*?)</option>", select_html, flags=re.I | re.S):
            attrs = opt.group(1)
            label_html = opt.group(2)

            vm = re.search(r'\bvalue=(["\'])(.*?)\1', attrs, flags=re.I | re.S)
            value = html.unescape(vm.group(2)) if vm else ""

            label = re.sub(r"<[^>]+>", "", label_html)
            label = html.unescape(label).replace("\xa0", " ").strip()

            selected = re.search(r"\bselected\b", attrs, flags=re.I) is not None

            options.append({
                "value": value,
                "label": label,
                "selected": selected,
            })

        return options

    def selected_date_value(page_html, field_name):
        for opt in extract_select_options(page_html, field_name):
            value = opt.get("value", "")
            if opt.get("selected") and re.fullmatch(r"\d{8}", value):
                return value

        return ""

    def choose_date_value(page_html, field_name, wanted_date, label):
        target = wanted_date.strftime("%Y%m%d")
        options = extract_select_options(page_html, field_name)
        valid_values = sorted({
            opt.get("value", "")
            for opt in options
            if re.fullmatch(r"\d{8}", opt.get("value", ""))
        })

        if not valid_values:
            client.log(f"{label}: no date dropdown options found; posting target date {target}.")
            return target

        if target in valid_values:
            client.log(f"{label}: using requested date {target}.")
            return target

        prior_values = [v for v in valid_values if v <= target]
        later_values = [v for v in valid_values if v > target]

        if prior_values:
            chosen = prior_values[-1]
            client.log(f"{label}: requested date {target} is not in the dropdown; using closest earlier available date {chosen}.")
            return chosen

        chosen = later_values[0]
        client.log(f"{label}: requested date {target} is not in the dropdown; using earliest available date {chosen}.")
        return chosen

    client.log(f"GET Daily Receipts report: {report_url}")

    page_url, status, headers, raw = client.open(report_url)
    page_html = decode_response(headers, raw)

    dump_debug(debug_dir, "04_report_get.html", page_html)
    dump_http_meta(debug_dir, "04_report_get", page_url, status, headers, raw, client)
    dump_forms_summary(debug_dir, "04_report_get", page_html)

    if looks_like_login_page(page_url, page_html) or is_mfa_page(page_url, page_html):
        raise RuntimeError("Report page redirected back to login/MFA after authentication.")

    report_form = find_report_form(page_html)
    fields = build_fields_from_form(report_form)

    start_value = choose_date_value(page_html, start_field, report_date, "Start Date")
    fields[start_field] = start_value

    if bool(cfg.get("report_set_end_date_to_start", False)):
        fields[end_field] = start_value
        client.log(f"End Date: forced to Start Date {start_value}.")
    else:
        existing_end = selected_date_value(page_html, end_field)

        if existing_end:
            fields[end_field] = existing_end
            client.log(f"End Date: leaving website default selected date {existing_end}.")
        else:
            fields[end_field] = choose_date_value(page_html, end_field, report_date, "End Date")

    fields[view_button] = "View Report"
    fields.setdefault("__EVENTTARGET", "")
    fields.setdefault("__EVENTARGUMENT", "")

    dump_debug(debug_dir, "05_view_report_fields.json", json.dumps(fields, indent=2))

    client.log(f"POST View Report with Start Date value {fields[start_field]}")

    post_url, post_status, post_headers, post_raw = post_form(
        client,
        report_form,
        page_url,
        fields,
        referer=page_url,
    )

    post_html = save_login_response(
        debug_dir,
        "05_view_report",
        post_url,
        post_status,
        post_headers,
        post_raw,
        client,
    )

    dump_forms_summary(debug_dir, "05_view_report", post_html)

    if looks_like_login_page(post_url, post_html) or is_mfa_page(post_url, post_html):
        raise RuntimeError("View Report response went back to login/MFA.")

    return post_url, post_html, post_raw, post_headers

def unique(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def clean_candidate_url(raw: str, page_url: str) -> str:
    u = html.unescape(raw).strip().strip("\"'")
    u = u.replace("\\u0026", "&").replace("\\/", "/")
    u = re.sub(r"[\),;]+$", "", u)
    return urllib.parse.urljoin(page_url, u)


def find_csv_export_candidates(
    report_html: str,
    page_url: str,
    cfg: Dict[str, Any],
    report_date: dt.date,
) -> List[str]:
    candidates: List[str] = []
    unescaped = html.unescape(report_html)

    # 1) Direct links already rendered by the ReportViewer export menu.
    for m in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", report_html, flags=re.I):
        href = clean_candidate_url(m.group(1), page_url)
        href_l = href.lower()
        if "csv" in href_l and ("export" in href_l or "optype=export" in href_l or "rs%3aformat" in href_l or "rs:format" in href_l):
            candidates.append(href)

    # 2) Any embedded ReportViewer handler URLs.
    for m in re.finditer(r"""((?:https?://|/|\.{0,2}/)?[^"' <>\)]*Reserved\.ReportViewerWebControl\.axd\?[^"' <>\)]+)""", unescaped, flags=re.I):
        url = clean_candidate_url(m.group(1), page_url)
        if "csv" in url.lower() and "export" in url.lower():
            candidates.append(url)

    # 3) Construct an AXD export URL from ReportSession and ControlID, if available.
    report_session = extract_param_from_text(unescaped, "ReportSession")
    control_id = extract_param_from_text(unescaped, "ControlID")
    report_stack = extract_param_from_text(unescaped, "ReportStack") or "1"

    handler_bases: List[str] = []
    for m in re.finditer(r"""((?:https?://|/|\.{0,2}/)?[^"' <>\)]*Reserved\.ReportViewerWebControl\.axd)""", unescaped, flags=re.I):
        handler_bases.append(clean_candidate_url(m.group(1), page_url).split("?", 1)[0])

    # Common ReportViewer handler locations.
    parsed_page = urllib.parse.urlparse(page_url)
    root = f"{parsed_page.scheme}://{parsed_page.netloc}"
    handler_bases.extend([
        urllib.parse.urljoin(page_url, "Reserved.ReportViewerWebControl.axd"),
        root + "/Reporting/Reserved.ReportViewerWebControl.axd",
        root + "/_layouts/15/Reserved.ReportViewerWebControl.axd",
        root + "/Reporting/_layouts/15/Reserved.ReportViewerWebControl.axd",
    ])

    if report_session and control_id:
        file_name = cfg.get("report_file_name_hint", "Receipts End of Day")
        for base in unique(handler_bases):
            params = {
                "ReportSession": report_session,
                "ControlID": control_id,
                "Culture": cfg.get("culture", "1033"),
                "UICulture": cfg.get("ui_culture", "1033"),
                "ReportStack": report_stack,
                "OpType": "Export",
                "FileName": file_name,
                "ContentDisposition": "OnlyHtmlInline",
                "Format": "CSV",
            }
            candidates.append(base + "?" + urllib.parse.urlencode(params))

    # 4) URL-access fallback. Some custom ReportViewer pages allow rs:Format directly.
    param_name = cfg.get("url_access_start_date_parameter", cfg.get("start_date_label", "Start Date"))
    date_value = report_date.strftime(cfg.get("url_access_date_format", cfg.get("report_date_format", "%m/%d/%Y")))
    direct_params = [
        ("Path", cfg.get("report_path", "/Prod/Agent/Receipts End of Day")),
        ("rs:Command", "Render"),
        ("rs:Format", "CSV"),
        (param_name, date_value),
    ]

    # Preserve Report.aspx path while replacing query.
    parsed = urllib.parse.urlparse(cfg["report_url"])
    direct_query = urllib.parse.urlencode(direct_params)
    direct_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", direct_query, ""))
    candidates.append(direct_url)

    export_template = cfg.get("export_url_template")
    if export_template:
        candidates.insert(0, export_template.format(
            report_session=urllib.parse.quote(report_session or ""),
            control_id=urllib.parse.quote(control_id or ""),
            report_stack=urllib.parse.quote(report_stack or "1"),
            date=urllib.parse.quote(date_value),
        ))

    return unique(candidates)


def extract_param_from_text(text: str, name: str) -> Optional[str]:
    pattern = re.compile(rf"{re.escape(name)}=([^&\"'<>\\\s]+)", flags=re.I)
    m = pattern.search(text)
    if m:
        return html.unescape(urllib.parse.unquote(m.group(1)))
    return None


def looks_like_csv(headers: Dict[str, str], raw: bytes) -> bool:
    if not raw:
        return False

    content_type = headers.get("content-type", "").lower()
    disposition = headers.get("content-disposition", "").lower()
    prefix = raw[:512].lstrip().lower()

    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html") or b"<form" in prefix:
        return False
    if b"type=\"password\"" in prefix or b"login.aspx" in prefix:
        return False

    if "csv" in content_type or "csv" in disposition:
        return True
    if "application/octet-stream" in content_type and len(raw) > 0:
        return True

    # Last-resort CSV sniffing: comma/tab/line breaks in the first chunk, not HTML/XML/JSON.
    if prefix.startswith((b"{", b"[", b"<?xml")):
        return False
    sample = raw[:4096]
    return (b"," in sample or b"\t" in sample) and (b"\n" in sample or b"\r" in sample)




def looks_like_csv_bytes(raw, headers):
    if not raw:
        return False

    content_type = str(headers.get("content-type", "")).lower()
    content_disp = str(headers.get("content-disposition", "")).lower()

    if "csv" in content_type or "csv" in content_disp:
        return True

    if "attachment" in content_disp and "html" not in content_type:
        return True

    sample = raw[:8192]

    if sample.startswith(b"\xef\xbb\xbf"):
        sample = sample[3:]

    if sample.startswith(b"\xff\xfe") or sample.startswith(b"\xfe\xff"):
        return True

    stripped = sample.lstrip()
    lower = stripped[:1000].lower()

    if lower.startswith(b"<!doctype html") or lower.startswith(b"<html") or b"<body" in lower:
        return False

    if b"<form" in lower or b"__viewstate" in lower or b"reportviewer" in lower:
        return False

    if (b"," in sample or b"\t" in sample or b";" in sample) and (b"\n" in sample or b"\r" in sample):
        return True

    return False


def save_export_attempt_debug(debug_dir, idx, url, status, headers, raw):
    if debug_dir is None:
        return

    try:
        debug_dir = Path(debug_dir)
        (debug_dir / f"07_export_attempt_{idx}.bin").write_bytes(raw)

        meta = {
            "url": url,
            "status": status,
            "content_type": headers.get("content-type", ""),
            "content_disposition": headers.get("content-disposition", ""),
            "content_length_header": headers.get("content-length", ""),
            "body_bytes": len(raw),
            "looks_like_csv": looks_like_csv_bytes(raw, headers),
            "headers": redact_headers(headers) if "redact_headers" in globals() else dict(headers),
        }

        dump_debug(debug_dir, f"07_export_attempt_{idx}_meta.json", json.dumps(meta, indent=2))

        preview = raw[:4000]
        preview_text = preview.decode("utf-8-sig", errors="replace")
        dump_debug(debug_dir, f"07_export_attempt_{idx}_preview.txt", preview_text)
    except Exception as exc:
        try:
            dump_debug(debug_dir, f"07_export_attempt_{idx}_debug_error.txt", repr(exc))
        except Exception:
            pass


def download_csv(*args, **kwargs):
    """
    Robust ReportViewer CSV export.

    Replaces the original export function by locating ReportSession/ControlID
    and trying multiple ReportViewer handler URL variants.
    """
    import html as _html
    import json as _json
    import re as _re
    import urllib.parse as _urlparse
    from pathlib import Path as _Path

    _param_names = ['client', 'report_html', 'report_page_url', 'cfg', 'report_date', 'output_path', 'debug_dir']
    _values = {}

    for _i, _name in enumerate(_param_names):
        if _i < len(args):
            _values[_name] = args[_i]

    _values.update(kwargs)

    def _pick(*names):
        for name in names:
            if name in _values and _values[name] is not None:
                return _values[name]
        return None

    client = _pick("client", "web_client")
    cfg = _pick("cfg", "config") or {}
    report_page_url = _pick("report_page_url", "page_url", "post_url", "url", "final_url")
    report_html = _pick("report_html", "page_html", "post_html", "html")
    output_path = _pick("output_path", "out_path", "csv_path", "download_path", "dest_path")
    debug_dir = _pick("debug_dir", "debug_path", "debug")

    if client is None:
        raise RuntimeError("Export function patch could not identify client argument.")

    if output_path is None:
        output_path = cfg.get("output_path") or cfg.get("csv_output_path")

    if output_path is None:
        raise RuntimeError("Export function patch could not identify output_path argument.")

    output_path = _Path(output_path)

    if not report_page_url:
        report_page_url = cfg.get("report_url")

    if not report_html:
        raise RuntimeError("Export function patch could not identify report_html/page_html argument.")

    candidates = []

    template = str(cfg.get("export_url_template", "")).strip()
    if template:
        candidates.append(template)

    # Capture any export URLs already embedded in the rendered ReportViewer HTML.
    for _m in _re.finditer(
        r'(Reserved\.ReportViewerWebControl\.axd\?[^"\']+?OpType=Export[^"\']+?Format=)(?:CSV|EXCELOPENXML|EXCEL|PDF|WORDOPENXML)',
        report_html,
        flags=_re.I,
    ):
        base = _html.unescape(_m.group(1))
        candidates.append(_urlparse.urljoin(report_page_url, base + "CSV"))

    session_match = _re.search(r"ReportSession=([A-Za-z0-9_\-]+)", report_html)
    control_match = _re.search(r"ControlID=([A-Za-z0-9_\-]+)", report_html)

    if not session_match:
        session_match = _re.search(r"ReportSession['\"=:\s]+([A-Za-z0-9_\-]+)", report_html, flags=_re.I)

    if not control_match:
        control_match = _re.search(r"ControlID['\"=:\s]+([A-Za-z0-9_\-]+)", report_html, flags=_re.I)

    if session_match and control_match:
        report_session = session_match.group(1)
        control_id = control_match.group(1)

        file_name = cfg.get("export_file_name", "Receipts End of Day")

        handler_paths = [
            "/Reserved.ReportViewerWebControl.axd",
            "/Reserved.ReportViewerWebControl.axd/",
            "/Reporting/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/Reserved.ReportViewerWebControl.axd",
            "/_layouts/15/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/CLS.LC.ReportViewer/Reserved.ReportViewerWebControl.axd",
        ]

        for disposition in ["AlwaysAttachment", "Attachment", "OnlyHtmlInline"]:
            for stack in ["1", "0"]:
                for handler_path in handler_paths:
                    q = {
                        "ReportSession": report_session,
                        "ControlID": control_id,
                        "Culture": "1033",
                        "CultureOverrides": "True",
                        "UICulture": "1033",
                        "UICultureOverrides": "True",
                        "ReportStack": stack,
                        "OpType": "Export",
                        "FileName": file_name,
                        "ContentDisposition": disposition,
                        "Format": "CSV",
                    }

                    candidates.append(
                        _urlparse.urljoin(report_page_url, handler_path)
                        + "?"
                        + _urlparse.urlencode(q)
                    )

    # SSRS-style fallback. The selected report parameters usually live in session
    # after View Report, so this is only a fallback.
    render_q = {
        "Path": "/Prod/Agent/Receipts End of Day",
        "rs:Command": "Render",
        "rs:Format": "CSV",
    }

    candidates.append(
        "https://prtl.liquorconnect.com/Reporting/_layouts/15/CLS.LC.ReportViewer/Report.aspx?"
        + _urlparse.urlencode(render_q)
    )

    seen = set()
    unique_candidates = []

    for url in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        unique_candidates.append(url)

    dump_debug(debug_dir, "06_export_candidates.txt", "\n".join(unique_candidates))

    last_status = None

    for idx, url in enumerate(unique_candidates, start=1):
        client.log(f"GET export candidate {idx}: {url}")

        try:
            final_url, status, headers, raw = client.open(
                url,
                headers={"Accept": "text/csv,application/csv,application/octet-stream,*/*"},
                referer=report_page_url,
            )
        except Exception as exc:
            dump_debug(debug_dir, f"07_export_attempt_{idx}_error.txt", repr(exc))
            continue

        last_status = status
        save_export_attempt_debug(debug_dir, idx, final_url, status, headers, raw)

        if status == 200 and looks_like_csv_bytes(raw, headers):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(raw)
            client.log(f"Saved CSV export: {output_path}")
            client.log(f"CSV bytes: {len(raw)}")
            return output_path

    raise RuntimeError(
        "Could not download a CSV export from the ReportViewer page. "
        f"Tried {len(unique_candidates)} candidate export URL(s); last HTTP status was {last_status}. "
        "Check 07_export_attempt_*_meta.json and 07_export_attempt_*_preview.txt in the newest debug folder."
    )


def default_downloads_dir() -> Path:
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        return Path(user_profile) / "Downloads"
    return Path.home() / "Downloads"


def resolve_output_path(cfg: Dict[str, Any], run_date: dt.date) -> Path:
    downloads_dir_raw = cfg.get("downloads_dir", "")
    downloads_dir = Path(os.path.expandvars(os.path.expanduser(downloads_dir_raw))) if downloads_dir_raw else default_downloads_dir()
    date_part = run_date.strftime(cfg.get("output_date_format", "%d%m%Y"))
    filename = f"{cfg.get('output_prefix', 'AlbertGR')}{date_part}.csv"
    return downloads_dir / filename


def parse_run_date(s: Optional[str]) -> dt.date:
    if s:
        return dt.datetime.strptime(s, "%Y-%m-%d").date()
    return dt.date.today()



def compute_report_start_date(run_date: dt.date, days_back: int = 3, skip_saturdays=True) -> dt.date:
    """
    Count backward from run_date by days_back eligible days.

    Saturdays do not count as one of the days.
    Example for Tuesday:
      Monday = 1
      Sunday = 2
      Saturday = skipped
      Friday = 3
    """
    if isinstance(skip_saturdays, str):
        skip_saturdays = skip_saturdays.strip().lower() not in ("0", "false", "no", "off")

    target = run_date
    counted = 0

    while counted < days_back:
        target = target - dt.timedelta(days=1)

        # Python weekday: Monday=0 ... Saturday=5 ... Sunday=6
        if skip_saturdays and target.weekday() == 5:
            continue

        counted += 1

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Download LiquorConnect Daily Receipts CSV.")
    parser.add_argument("--config", default="AlbertaGR_raw.json", help="Path to AlbertaGR_raw.json")
    parser.add_argument("--date", default=None, help="Override current date for testing, YYYY-MM-DD")
    parser.add_argument("--debug", action="store_true", help="Force debug output on")
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    cfg = read_config(cfg_path)

    run_date = parse_run_date(args.date)
    report_date = compute_report_start_date(run_date, int(cfg.get("report_days_back", 3)), cfg.get("report_skip_saturdays", True))
    output_path = resolve_output_path(cfg, run_date)

    debug_enabled = bool(cfg.get("debug", True) or args.debug)
    debug_dir: Optional[Path] = None
    if debug_enabled:
        debug_base_raw = cfg.get("debug_dir", "")
        debug_base = Path(os.path.expandvars(os.path.expanduser(debug_base_raw))) if debug_base_raw else output_path.parent
        debug_dir = debug_base / f"AlbertaGR_debug_{run_date.strftime('%Y%m%d')}_{time.strftime('%H%M%S')}"

    client = WebClient(
        user_agent=cfg.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AlbertaGRDownloader/1.0"),
        timeout=int(cfg.get("timeout_seconds", 90)),
        verbose=bool(cfg.get("verbose", True)),
    )

    try:
        print(f"Script version: {SCRIPT_VERSION}")
        print(f"Script file: {Path(__file__).resolve()}")
        print(f"Config file: {cfg_path}")
        print(f"Run date: {run_date.isoformat()}")
        print(f"Report Start Date: {report_date.isoformat()} ({report_date.strftime(cfg.get('report_date_format', '%m/%d/%Y'))})")
        print(f"Output: {output_path}")

        login(client, cfg, debug_dir)
        report_page_url, report_html, _report_raw, _report_headers = submit_report(client, cfg, report_date, debug_dir)
        download_csv(client, report_html, report_page_url, cfg, report_date, output_path, debug_dir)

        print(f"Saved: {output_path}")
        if debug_dir:
            print(f"Debug folder: {debug_dir}")
        return 0

    except Exception as exc:
        print("")
        print("ERROR:", exc, file=sys.stderr)
        if debug_dir:
            print(f"Debug folder: {debug_dir}", file=sys.stderr)
        if cfg.get("verbose", True):
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())










