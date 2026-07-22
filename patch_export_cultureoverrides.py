from pathlib import Path
import datetime as dt
import re

py_path = Path("AlbertaGR.py")
src = py_path.read_text(encoding="utf-8-sig")

backup = py_path.with_name(f"AlbertaGR_backup_export_cultureoverrides_{dt.datetime.now():%Y%m%d_%H%M%S}.py")
backup.write_text(src, encoding="utf-8")
print(f"Backup saved to: {backup}")

# 1) Fix embedded ReportViewer URLs containing literal JS escapes like \u0026.
old = 'base = _html.unescape(_m.group(1))'
new = '''base = _html.unescape(_m.group(1))
        base = (
            base
            .replace("\\\\u0026", "&")
            .replace("\\\\x26", "&")
            .replace("&amp;", "&")
        )'''

if old in src and 'replace("\\\\u0026", "&")' not in src:
    src = src.replace(old, new)
    print("Patched embedded export URL decoding.")
else:
    print("Embedded URL decoding already patched or base line not found.")

# 2) Add required ReportViewer parameters to manually built export URLs.
pattern = r'("Culture"\s*:\s*"1033"\s*,\s*\n)(\s*)"UICulture"\s*:\s*"1033"\s*,'
replacement = r'\1\2"CultureOverrides": "True",\n\2"UICulture": "1033",\n\2"UICultureOverrides": "True",'

if "CultureOverrides" not in src or "UICultureOverrides" not in src:
    src, count = re.subn(pattern, replacement, src)
    print(f"Patched CultureOverrides/UICultureOverrides occurrences: {count}")
else:
    # If some CultureOverrides text exists only in comments/debug, still patch q dict if missing.
    if '"CultureOverrides": "True"' not in src:
        src, count = re.subn(pattern, replacement, src)
        print(f"Patched CultureOverrides/UICultureOverrides occurrences: {count}")
    else:
        print("CultureOverrides already present.")

# 3) Ensure handler candidates include the root handler first, since earlier logs show that one responds.
old_paths = '''handler_paths = [
            "/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/CLS.LC.ReportViewer/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/Reserved.ReportViewerWebControl.axd",
            "/Reporting/Reserved.ReportViewerWebControl.axd",
            "/_layouts/15/Reserved.ReportViewerWebControl.axd",
        ]'''

new_paths = '''handler_paths = [
            "/Reserved.ReportViewerWebControl.axd",
            "/Reserved.ReportViewerWebControl.axd/",
            "/Reporting/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/Reserved.ReportViewerWebControl.axd",
            "/_layouts/15/Reserved.ReportViewerWebControl.axd",
            "/Reporting/_layouts/15/CLS.LC.ReportViewer/Reserved.ReportViewerWebControl.axd",
        ]'''

if old_paths in src:
    src = src.replace(old_paths, new_paths)
    print("Patched handler path ordering.")
else:
    print("Handler path block not found or already changed.")

py_path.write_text(src, encoding="utf-8")
print("Done.")
