from pathlib import Path
import datetime as dt
import re
import json

py_path = Path("AlbertaGR.py")
json_path = Path("AlbertaGR_raw.json")

src = py_path.read_text(encoding="utf-8-sig")

backup = py_path.with_name(f"AlbertaGR_backup_skip_saturdays_{dt.datetime.now():%Y%m%d_%H%M%S}.py")
backup.write_text(src, encoding="utf-8")
print(f"Backup saved to: {backup}")

helper = r'''

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

'''

if "def compute_report_start_date(" not in src:
    src = src.replace("\ndef main(", helper + "\ndef main(", 1)
    print("Inserted compute_report_start_date().")
else:
    print("compute_report_start_date() already exists.")

lines = src.splitlines()
report_print_idx = None

for i, line in enumerate(lines):
    if "Report Start Date:" in line:
        report_print_idx = i
        break

if report_print_idx is None:
    raise SystemExit("Could not find the Report Start Date print line.")

assignment_idx = None

for i in range(max(0, report_print_idx - 80), report_print_idx):
    if re.match(r"\s*report_date\s*=", lines[i]):
        assignment_idx = i

if assignment_idx is None:
    raise SystemExit("Could not find report_date assignment before the Report Start Date print line.")

indent = re.match(r"(\s*)", lines[assignment_idx]).group(1)

new_line = (
    indent
    + 'report_date = compute_report_start_date('
    + 'run_date, '
    + 'int(cfg.get("report_days_back", 3)), '
    + 'cfg.get("report_skip_saturdays", True)'
    + ')'
)

print("Replacing:")
print(lines[assignment_idx])
print("With:")
print(new_line)

lines[assignment_idx] = new_line
src = "\n".join(lines) + "\n"

py_path.write_text(src, encoding="utf-8")

# Update JSON config without BOM.
cfg = json_path.read_text(encoding="utf-8-sig")
data = json.loads(cfg)

data["report_days_back"] = 3
data["report_skip_saturdays"] = True

json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

print("Updated AlbertaGR_raw.json:")
print("  report_days_back = 3")
print("  report_skip_saturdays = true")
print("Done.")
