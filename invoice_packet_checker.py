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

The total check reads dollar amounts from the invoice and ratecon
text, written as ``$2,400.00`` or ``2400 USD``. The largest amount
in each category is taken as the total, and a disagreement is
reported as a problem. When either category has no readable
amounts, the check is skipped.

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
AMOUNT_RE = re.compile(
    r"\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
    r"|([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*USD\b",
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


def parse_amount(text):
    """Parse an amount string like ``2,400.00`` into integer cents.

    One decimal digit reads as tenths, so ``0.5`` is 50 cents.
    """
    cleaned = text.replace(",", "")
    if "." in cleaned:
        dollars, _, cents = cleaned.partition(".")
        cents = (cents + "00")[:2]
    else:
        dollars, cents = cleaned, "00"
    return int(dollars) * 100 + int(cents)


def amounts_in(path):
    """Extract dollar amounts (as integer cents) from a readable
    text file, or [].

    Amounts must be marked with a leading ``$`` or a trailing
    ``USD``; bare numbers are never taken as amounts.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError):
        return []
    found = []
    for match in AMOUNT_RE.finditer(text):
        value = parse_amount(match.group(1) or match.group(2))
        if value not in found:
            found.append(value)
    return found


def format_cents(cents):
    """Format an amount in integer cents as ``$1,234.56``."""
    sign = "-" if cents < 0 else ""
    return "%s$%s.%02d" % (sign, "{:,}".format(abs(cents) // 100),
                           abs(cents) % 100)


def largest_amount(amounts_by_file, names):
    """Largest amount across the named files, or None.

    The largest dollar amount in a document is taken as its
    total, so line items plus a grand total still compare by the
    total.
    """
    totals = [max(amounts_by_file[name]) for name in names
              if name in amounts_by_file]
    return max(totals) if totals else None


def check_packet(folder, required):
    files = []
    for root, _dirs, names in os.walk(folder):
        for name in sorted(names):
            files.append(os.path.join(root, name))
    files.sort()
    by_category = {category: [] for category in CATEGORIES}
    unclassified = []
    load_by_file = {}
    amounts_by_file = {}
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
            if category in ("invoice", "ratecon"):
                amounts = amounts_in(path)
                if amounts:
                    amounts_by_file[os.path.relpath(path, folder)] = amounts

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

    invoice_total = largest_amount(amounts_by_file,
                                   by_category["invoice"])
    ratecon_total = largest_amount(amounts_by_file,
                                   by_category["ratecon"])
    if (invoice_total is not None and ratecon_total is not None
            and invoice_total != ratecon_total):
        problems.append(
            "amount mismatch: invoice total %s vs ratecon total %s"
            % (format_cents(invoice_total), format_cents(ratecon_total)))

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
        "amounts": {name: amounts
                    for name, amounts in sorted(amounts_by_file.items())},
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
    if result["amounts"]:
        lines.append("Amounts found:")
        for name, amounts in result["amounts"].items():
            lines.append("  %s: %s" % (name, ", ".join(
                format_cents(amount) for amount in amounts)))
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
