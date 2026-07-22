from pathlib import Path
import ast
import datetime as dt
import re
import textwrap

py_path = Path("AlbertaGR.py")
src = py_path.read_text(encoding="utf-8-sig")

needle = "Could not download a CSV export from the ReportViewer page"
idx = src.find(needle)

if idx < 0:
    print("Could not find the export error text.")
    print("Nearby export/search lines:")
    for n, line in enumerate(src.splitlines(), start=1):
        if "export" in line.lower() or "06_export" in line or "07_export" in line:
            print(f"{n}: {line[:200]}")
    raise SystemExit(1)

defs = list(re.finditer(r"(?m)^def\s+([A-Za-z_]\w*)\s*\(", src[:idx]))

if not defs:
    raise SystemExit("Could not find the function that contains the export error.")

func_start = defs[-1].start()
func_name = defs[-1].group(1)

next_top = re.search(r"(?m)^(?:def|class)\s+[A-Za-z_]\w*", src[func_start + 1:])
func_end = func_start + 1 + next_top.start() if next_top else len(src)

sig_match = re.match(
    r"(?s)def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*(?:->\s*[^:]+)?\:",
    src[func_start:func_end],
)

if not sig_match:
    raise SystemExit(f"Could not parse function signature for {func_name}.")

try:
    parsed = ast.parse(sig_match.group(0) + "\n    pass")
    param_names = [a.arg for a in parsed.body[0].args.args]
except Exception:
    param_names = ["client", "cfg", "report_page_url", "report_html", "output_path", "debug_dir"]

backup = py_path.with_name(f"AlbertaGR_backup_export_by_error_{dt.datetime.now():%Y%m%d_%H%M%S}.py")
backup.write_text(src, encoding="utf-8")
print(f"Backup saved to: {backup}")
print(f"Found export function: {func_name}({', '.join(param_names)})")

helpers = r'''

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

'''

if "def looks_like_csv_bytes(" not in src:
    src = src[:func_start] + helpers + "\n" + src[func_start:]
    func_start += len(helpers) + 1
    func_end += len(helpers) + 1

param_names_literal = repr(param_names)

replacement = f'''def {func_name}(*args, **kwargs):
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

    _param_names = {param_names_literal}
    _values = {{}}

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
    cfg = _pick("cfg", "config") or {{}}
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
        r'(Reserved\\.ReportViewerWebControl\\.axd\\?[^"\\']+?OpType=Export[^"\\']+?Format=)(?:CSV|EXCELOPENXML|EXCEL|PDF|WORDOPENXML)',
        report_html,
        flags=_re.I,
    ):
        base = _html.unescape(_m.group(1))
        candidates.append(_urlparse.urljoin(report_page_url, base + "CSV"))

    session_match = _re.search(r"ReportSession=([A-Za-z0-9_\\-]+)", report_html)
    control_match = _re.search(r"ControlID=([A-Za-z0-9_\\-]+)", report_html)

    if not session_match:
        session_match = _re.search(r"ReportSession['\\"=:\\s]+([A-Za-z0-9_\\-]+)", report_html, flags=_re.I)

    if not control_match:
        control_match = _re.search(r"ControlID['\\"=:\\s]+([A-Za-z0-9_\\-]+)", report_html, flags=_re.I)

    if session_match and control_match:
        report_session = session_match.group(1)
        control_id = control_match.group(1)

        file_name = cfg.get("export_file_name", "Receipts End of Day")

        handler_paths = [
            "/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/CLS.LC.ReportViewer/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/Reserved.ReportViewerWebControl.axd",
            "/Reporting/Reserved.ReportViewerWebControl.axd",
            "/_layouts/15/Reserved.ReportViewerWebControl.axd",
        ]

        for disposition in ["AlwaysAttachment", "Attachment", "OnlyHtmlInline"]:
            for stack in ["1", "0"]:
                for handler_path in handler_paths:
                    q = {{
                        "ReportSession": report_session,
                        "ControlID": control_id,
                        "Culture": "1033",
                        "UICulture": "1033",
                        "ReportStack": stack,
                        "OpType": "Export",
                        "FileName": file_name,
                        "ContentDisposition": disposition,
                        "Format": "CSV",
                    }}

                    candidates.append(
                        _urlparse.urljoin(report_page_url, handler_path)
                        + "?"
                        + _urlparse.urlencode(q)
                    )

    # SSRS-style fallback. The selected report parameters usually live in session
    # after View Report, so this is only a fallback.
    render_q = {{
        "Path": "/Prod/Agent/Receipts End of Day",
        "rs:Command": "Render",
        "rs:Format": "CSV",
    }}

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

    dump_debug(debug_dir, "06_export_candidates.txt", "\\n".join(unique_candidates))

    last_status = None

    for idx, url in enumerate(unique_candidates, start=1):
        client.log(f"GET export candidate {{idx}}: {{url}}")

        try:
            final_url, status, headers, raw = client.open(
                url,
                headers={{"Accept": "text/csv,application/csv,application/octet-stream,*/*"}},
                referer=report_page_url,
            )
        except Exception as exc:
            dump_debug(debug_dir, f"07_export_attempt_{{idx}}_error.txt", repr(exc))
            continue

        last_status = status
        save_export_attempt_debug(debug_dir, idx, final_url, status, headers, raw)

        if status == 200 and looks_like_csv_bytes(raw, headers):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(raw)
            client.log(f"Saved CSV export: {{output_path}}")
            client.log(f"CSV bytes: {{len(raw)}}")
            return output_path

    raise RuntimeError(
        "Could not download a CSV export from the ReportViewer page. "
        f"Tried {{len(unique_candidates)}} candidate export URL(s); last HTTP status was {{last_status}}. "
        "Check 07_export_attempt_*_meta.json and 07_export_attempt_*_preview.txt in the newest debug folder."
    )

'''

src = src[:func_start] + replacement + "\n" + src[func_end:]
py_path.write_text(src, encoding="utf-8")

print(f"Patched export function: {func_name}")
print("Done.")
