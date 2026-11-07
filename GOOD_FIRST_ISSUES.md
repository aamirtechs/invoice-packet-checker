# Good first issues

Small, testable tasks for first-time contributors. No network access needed.

1. Extract amounts from invoice and ratecon text and flag a total
   mismatch. Scope: parse dollar amounts, compare, add tests.
2. Read text out of PDFs for the load-number check using only the
   standard library (compressed streams are the hard part; a
   documented partial parser is acceptable). Scope: add the parser,
   add tests on a generated PDF.
3. Add a `--strict` flag that turns warnings (unclassified files,
   multiple invoices) into failures. Scope: add the flag, wire it
   into the exit code, add a CLI test.
4. Support a second packet layout: one folder per load, checked in
   a single run with a per-load summary line. Scope: add the mode,
   add tests, document it.
