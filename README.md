# invoice-packet-checker
**Live tool:** https://aamirtechs.github.io/invoice-packet-checker/ (runs in your browser, no install)

Check an invoice packet folder before a factoring submission, so a
missing document is caught by a script instead of a rejection email.
It reads files only, never modifies them, and needs no dependencies.

## What it checks

A complete packet needs four documents for the same load:

- BOL (bill of lading)
- POD (proof of delivery)
- Rate confirmation (ratecon)
- Invoice

The tool classifies files by name (so PDFs work), then reports:

- which required documents are missing
- which classified files are empty
- whether the load numbers found in the text documents disagree
  with each other
- whether the invoice total and the ratecon total disagree

Unclassified files and multiple invoices are warnings, not failures.
Load-number consistency only runs over readable text files (.txt,
.md, .csv, .json); a packet of PDFs still gets the missing-document
check. Use `--required` to check a smaller set, for example
`--required bol,pod,invoice`.

The total check reads dollar amounts from the invoice and ratecon
text files, written as `$2,400.00` or `2400 USD` (bare numbers are
never taken as amounts). The largest amount in each category is
taken as the total, so line items plus a grand total still compare
by the total, and a disagreement is reported as a problem (so
`--check` exits non-zero). When either category has no readable
amounts, the check is skipped. In the JSON output, `amounts` maps
each file name to the amounts found, in integer cents.

## Usage

```sh
python3 invoice_packet_checker.py examples/complete
python3 invoice_packet_checker.py packet/ --json
python3 invoice_packet_checker.py packet/ --check
python3 invoice_packet_checker.py packet/ --required bol,pod,invoice
```

`--check` exits non-zero when the packet is not ready, so it works
as a gate in a script.

## Real example

Running it on `examples/complete` gives:

```
Invoice packet check
=====================
Folder: examples/complete

bol: BOL-48210.txt
pod: POD-48210.txt
ratecon: RateCon-48210.txt
invoice: Invoice-48210.txt

Load numbers found:
  BOL-48210.txt: 48210
  Invoice-48210.txt: 48210
  POD-48210.txt: 48210
  RateCon-48210.txt: 48210

Amounts found:
  Invoice-48210.txt: $2,400.00
  RateCon-48210.txt: $2,400.00

Problems: none. Packet is ready.

Warnings: none
```

Running it on `examples/missing-pod` gives:

```
Invoice packet check
=====================
Folder: examples/missing-pod

bol: BOL-48210.txt
pod: MISSING
ratecon: RateCon-48210.txt
invoice: Invoice-48210.txt

Load numbers found:
  BOL-48210.txt: 48210
  Invoice-48210.txt: 48210
  RateCon-48210.txt: 48210

Amounts found:
  Invoice-48210.txt: $2,400.00
  RateCon-48210.txt: $2,400.00

Problems:
  missing document: pod

Warnings: none
```

With mismatched totals (an invoice saying `Invoice total: 2300 USD`
against a ratecon saying `Rate: 2400 USD`) the packet is not ready
and `--check` exits 1:

```
Amounts found:
  Invoice-1.txt: $2,300.00
  RateCon-1.txt: $2,400.00

Problems:
  amount mismatch: invoice total $2,300.00 vs ratecon total $2,400.00
```

## Tests

```sh
python3 -m unittest discover -s tests
```

23 tests, covering classification (including lookalikes like
`symbol.pdf` and `inventory.pdf`), a complete packet, each failure
mode, amount parsing in `$` and `USD` formats, the largest-amount
total rule, the invoice/ratecon total mismatch and its skip cases,
the `--required` subset, nested folders, and the CLI exit codes.

## License

MIT. See `LICENSE`.
