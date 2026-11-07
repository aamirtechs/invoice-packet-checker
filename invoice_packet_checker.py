#!/usr/bin/env python3
"""Check an invoice packet folder before a factoring submission.

A complete packet needs four documents for the same load:

- BOL (bill of lading)
- POD (proof of delivery)
- Rate confirmation (ratecon)
- Invoice

Point this tool at a folder and it classifies files by name, then
reports what is missing, which classified files are empty, and
whether the load numbers found in the text documents disagree with
each other. Files are only read, never modified.

Classification is by file name, so it works for PDFs too: a file
named ``BOL-48210.pdf`` counts as the BOL. Load-number consistency
needs readable text, so it only runs over .txt, .md, .csv, and .json
files; a packet of PDFs still gets the missing-document check.

Usage:

    python3 invoice_packet_checker.py examples/complete
    python3 invoice_packet_checker.py packet/ --json
    python3 invoice_packet_checker.py packet/ --check
    python3 invoice_packet_checker.py packet/ --required bol,pod,invoice
"""

import argparse
import json
import os
import re
import sys

CATEGORIES = ("bol", "pod", "ratecon", "invoice")

TEXT_EXTENSIONS = (".txt", ".md", ".csv", ".json")
LOAD_RE = re.compile(
    r"load\s*(?:no\.?|number|#)?\s*:?\s*([A-Za-z0-9][A-Za-z0-9\-]{2,19})",
    re.IGNORECASE)


def classify(name):
    """Return the packet category for a file name, or None.

    Names are split into word tokens first, so "symbol.pdf" is not a
    BOL and "inventory.pdf" is not an invoice.
    """
    stem = os.path.splitext(name.lower())[0]
    tokens = set(re.split(r"[^a-z0-9]+", stem))
    if "bol" in tokens or ("bill" in tokens and "lading" in tokens):
        return "bol"
    if "pod" in tokens or ("proof" in tokens and "delivery" in tokens) \
            or ("delivery" in tokens and "receipt" in tokens):
        return "pod"
    if "ratecon" in tokens or ("rate" in tokens and
                               tokens & {"confirmation", "conf"}):
        return "ratecon"
    if "invoice" in tokens or "inv" in tokens:
        return "invoice"
    return None


def load_numbers_in(path):
    """Extract load numbers from a readable text file, or []."""
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return []
    found = []
    for match in LOAD_RE.finditer(text):
        value = match.group(1).strip("-")
        if value and value not in found:
            found.append(value)
    return found


def check_packet(folder, required):
    files = []
    for root, _dirs, names in os.walk(folder):
        for name in sorted(names):
            files.append(os.path.join(root, name))
    files.sort()
    by_category = {category: [] for category in CATEGORIES}
    unclassified = []
    load_by_file = {}
    problems = []
    warnings = []

    for path in files:
        name = os.path.basename(path)
        category = classify(name)
        if category is None:
            unclassified.append(os.path.relpath(path, folder))
            continue
        by_category[category].append(os.path.relpath(path, folder))
        if os.path.getsize(path) == 0:
            problems.append(
                "%s file is empty: %s"
                % (category, os.path.relpath(path, folder)))
        if os.path.splitext(name)[1].lower() in TEXT_EXTENSIONS:
            numbers = load_numbers_in(path)
            if numbers:
                load_by_file[os.path.relpath(path, folder)] = numbers

    for category in required:
        if not by_category.get(category):
            problems.append("missing document: %s" % category)

    all_numbers = set()
    for numbers in load_by_file.values():
        all_numbers.update(numbers)
    if len(all_numbers) > 1:
        detail = "; ".join(
            "%s: %s" % (name, ", ".join(numbers))
            for name, numbers in sorted(load_by_file.items()))
        problems.append(
            "load number mismatch across documents: %s" % detail)

    if len(by_category["invoice"]) > 1:
        warnings.append(
            "multiple invoices found (%d); confirm only one is current"
            % len(by_category["invoice"]))
    for name in unclassified:
        warnings.append("unclassified file (ignored): %s" % name)

    return {
        "folder": folder,
        "documents": by_category,
        "unclassified": unclassified,
        "load_numbers": {name: numbers
                         for name, numbers in sorted(load_by_file.items())},
        "problems": problems,
        "warnings": warnings,
        "ready": not problems,
    }


def render_text(result):
    lines = ["Invoice packet check", "====================="]
    lines.append("Folder: %s" % result["folder"])
    lines.append("")
    for category in CATEGORIES:
        names = result["documents"][category]
        if names:
            lines.append("%s: %s" % (category, ", ".join(names)))
        else:
            lines.append("%s: MISSING" % category)
    lines.append("")
    if result["load_numbers"]:
        lines.append("Load numbers found:")
        for name, numbers in result["load_numbers"].items():
            lines.append("  %s: %s" % (name, ", ".join(numbers)))
        lines.append("")
    if result["problems"]:
        lines.append("Problems:")
        for problem in result["problems"]:
            lines.append("  " + problem)
    else:
        lines.append("Problems: none. Packet is ready.")
    lines.append("")
    if result["warnings"]:
        lines.append("Warnings:")
        for warning in result["warnings"]:
            lines.append("  " + warning)
    else:
        lines.append("Warnings: none")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check an invoice packet folder for factoring.")
    parser.add_argument("folder", help="folder holding the packet files")
    parser.add_argument("--json", action="store_true",
                        help="print machine-readable JSON")
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the packet is not ready")
    parser.add_argument(
        "--required", default="bol,pod,ratecon,invoice",
        help="comma-separated required categories "
             "(default: bol,pod,ratecon,invoice)")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.folder):
        print("error: not a folder: %s" % args.folder, file=sys.stderr)
        return 2
    required = [item.strip() for item in args.required.split(",") if item.strip()]
    known = set(CATEGORIES)
    unknown = [item for item in required if item not in known]
    if unknown:
        print("error: unknown categories: %s" % ", ".join(unknown),
              file=sys.stderr)
        return 2
    result = check_packet(args.folder, required)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result), end="")
    if args.check and not result["ready"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
