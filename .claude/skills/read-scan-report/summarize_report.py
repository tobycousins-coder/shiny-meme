#!/usr/bin/env python3
"""Summarise a DuckDetector "Export Report" text file.

The format is produced by DashboardReportRenderer
(feature/dashboard/presentation/.../export/DashboardReportRenderer.kt):
banner, EXECUTIVE SUMMARY, TOP FINDINGS, one section per detector
(a dashed rule, then "  [BADGE] Title" and "  Verdict      : ..."), then
DEVICE & SYSTEM SPECIFICATIONS and END OF REPORT.

Prints the header, the overall status, and every detector grouped by severity
with the line range of its section, so the full detail can be read on demand.

Usage: python3 -I summarize_report.py <report.txt> [--json]
"""

import json
import re
import sys

BADGES = {
    "[✖ DANGER]": "DANGER",
    "[▲ WARNING]": "WARNING",
    "[ℹ INFO]": "INFO",
    "[✔ CLEAR]": "CLEAR",
}
ORDER = ["DANGER", "WARNING", "INFO", "CLEAR"]
RULE = "-" * 80
DOUBLE_RULE = "=" * 80
HEADER_KEYS = ("Target Device", "App Version", "Build Commit", "Build Time", "Report Time")


def badge_of(text):
    for badge, name in BADGES.items():
        if text.startswith(badge):
            return name, text[len(badge):].strip()
    return None, text


def parse(lines):
    out = {"header": {}, "overall": None, "summary": None, "statistics": {},
           "detectors": [], "device_line": None}

    for line in lines[:15]:
        for key in HEADER_KEYS:
            prefix = f"  {key}"
            if line.startswith(prefix) and ":" in line:
                out["header"][key] = line.split(":", 1)[1].strip()

    in_summary = False
    for i, line in enumerate(lines):
        if line.strip() == "EXECUTIVE SUMMARY":
            in_summary = True
        elif line.strip() == "TOP FINDINGS":
            in_summary = False
        if line.startswith("  Overall Status :") and out["overall"] is None:
            sev, text = badge_of(line.split(":", 1)[1].strip())
            out["overall"] = {"severity": sev, "headline": text}
        elif line.startswith("  Summary        :") and out["summary"] is None:
            out["summary"] = line.split(":", 1)[1].strip()
        elif in_summary and re.match(r"^    \[[✖▲✔·]\] ", line) and ":" in line:
            label, value = line[8:].split(":", 1)
            out["statistics"][label.strip()] = value.strip()
        elif "DEVICE & SYSTEM SPECIFICATIONS" in line:
            out["device_line"] = i + 1

    # A detector section is a dashed rule, a badge line with the title, then a Verdict line.
    # A title can span several lines, so walk back from each Verdict line to its rule.
    starts = []
    for v, line in enumerate(lines):
        if not line.startswith("  Verdict      :"):
            continue
        r = v - 1
        while r > 0 and lines[r] != RULE and v - r <= 12:
            r -= 1
        if lines[r] != RULE:
            continue
        sev, first = badge_of(lines[r + 1].strip())
        if sev:
            title = " ".join([first] + [l.strip() for l in lines[r + 2:v] if l.strip()]).strip()
            starts.append((r, v, sev, title))

    end_of_detectors = (out["device_line"] - 2) if out["device_line"] else len(lines)
    for n, (r, v, sev, title) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else end_of_detectors
        verdict = lines[v].split(":", 1)[1].strip()
        facts = None
        if v + 1 < len(lines) and lines[v + 1].startswith("  Quick Facts  :"):
            facts = lines[v + 1].split(":", 1)[1].strip()
        out["detectors"].append({
            "severity": sev, "title": title or "(untitled)", "verdict": verdict,
            "quick_facts": facts, "lines": [r + 2, end],  # 1-based, inclusive
        })
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    with open(args[0], encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    if not any("DUCK DETECTOR" in l for l in lines[:5]):
        print("warning: this does not look like a DuckDetector export report", file=sys.stderr)
    banners = sum(1 for l in lines if "DUCK DETECTOR — SECURITY SCAN REPORT" in l)
    if banners > 1:
        print(f"warning: {banners} reports are concatenated in this file; split them and "
              "summarise each one separately", file=sys.stderr)
    result = parse(lines)
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for key, value in result["header"].items():
        print(f"{key}: {value}")
    if result["overall"]:
        print(f"Overall: {result['overall']['severity']} - {result['overall']['headline']}")
    if result["summary"]:
        print(f"Summary: {result['summary']}")
    if result["statistics"]:
        print("Statistics: " + ", ".join(f"{k} {v}" for k, v in result["statistics"].items()))
    print(f"Detectors parsed: {len(result['detectors'])}")
    for severity in ORDER:
        group = [d for d in result["detectors"] if d["severity"] == severity]
        if not group:
            continue
        print(f"\n== {severity} ({len(group)}) ==")
        for d in group:
            start, end = d["lines"]
            print(f"- {d['title']}  [lines {start}-{end}]")
            print(f"    Verdict: {d['verdict']}")
            if d["quick_facts"]:
                print(f"    Facts:   {d['quick_facts']}")
    if result["device_line"]:
        print(f"\nDevice specifications start at line {result['device_line']}.")


if __name__ == "__main__":
    main()
