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

Unclassified files and multiple invoices are warnings, not failures.
Load-number consistency only runs over readable text files (.txt,
.md, .csv, .json); a packet of PDFs still gets the missing-document
check. Use `--required` to check a smaller set, for example
`--required bol,pod,invoice`.

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

Problems:
  missing document: pod

Warnings: none
```

## Tests

```sh
python3 -m unittest discover -s tests
```

14 tests, covering classification (including lookalikes like
`symbol.pdf` and `inventory.pdf`), a complete packet, each failure
mode, the `--required` subset, nested folders, and the CLI exit
codes.

## License

MIT. See `LICENSE`.
