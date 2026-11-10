import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import invoice_packet_checker as ipc

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def packet(files):
    """Create a temp packet folder from {name: content} and return it."""
    folder = tempfile.mkdtemp()
    for name, content in files.items():
        path = os.path.join(folder, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
    return folder


class TestClassify(unittest.TestCase):
    def test_each_category(self):
        self.assertEqual(ipc.classify("BOL-48210.pdf"), "bol")
        self.assertEqual(ipc.classify("bill_of_lading.pdf"), "bol")
        self.assertEqual(ipc.classify("POD-48210.pdf"), "pod")
        self.assertEqual(ipc.classify("proof-of-delivery.pdf"), "pod")
        self.assertEqual(ipc.classify("RateCon-48210.pdf"), "ratecon")
        self.assertEqual(ipc.classify("rate-confirmation.pdf"), "ratecon")
        self.assertEqual(ipc.classify("Invoice-48210.pdf"), "invoice")
        self.assertEqual(ipc.classify("inv-48210.pdf"), "invoice")

    def test_lookalikes_are_not_classified(self):
        self.assertIsNone(ipc.classify("symbol.pdf"))
        self.assertIsNone(ipc.classify("inventory.pdf"))
        self.assertIsNone(ipc.classify("ipod-manual.pdf"))
        self.assertIsNone(ipc.classify("notes.txt"))


class TestCheck(unittest.TestCase):
    def test_complete_packet_is_ready(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])
        self.assertEqual(result["problems"], [])

    def test_missing_pod(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertFalse(result["ready"])
        self.assertIn("missing document: pod", result["problems"])

    def test_load_number_mismatch(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 99999\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertFalse(result["ready"])
        self.assertTrue(any("load number mismatch" in p
                            for p in result["problems"]))

    def test_empty_bol_is_a_problem(self):
        folder = packet({
            "BOL-1.txt": "",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertFalse(result["ready"])
        self.assertTrue(any("empty" in p for p in result["problems"]))

    def test_unclassified_file_is_a_warning_not_a_failure(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\n",
            "photo.jpg": "",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])
        self.assertTrue(any("unclassified" in w
                            for w in result["warnings"]))

    def test_multiple_invoices_warns(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\n",
            "Invoice-2.txt": "Load 48210\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])
        self.assertTrue(any("multiple invoices" in w
                            for w in result["warnings"]))

    def test_required_subset(self):
        folder = packet({"BOL-1.txt": "Load 48210\n"})
        result = ipc.check_packet(folder, ["bol"])
        self.assertTrue(result["ready"])

    def test_nested_folder_is_scanned(self):
        folder = packet({"scans/BOL-1.txt": "Load 48210\n",
                         "scans/POD-1.txt": "Load 48210\n",
                         "RateCon-1.txt": "Load 48210\n",
                         "Invoice-1.txt": "Load 48210\n"})
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])


class TestAmounts(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(ipc.parse_amount("2,400.00"), 240000)
        self.assertEqual(ipc.parse_amount("2400"), 240000)
        self.assertEqual(ipc.parse_amount("0.5"), 50)

    def test_amounts_in_dollar_and_usd_formats(self):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8")
        handle.write("Total: $2,400.00\nDeposit: $200.50\n"
                     "Rate: 2400 USD\n")
        handle.close()
        try:
            self.assertEqual(
                ipc.amounts_in(handle.name), [240000, 20050])
        finally:
            os.unlink(handle.name)

    def test_bare_numbers_are_not_amounts(self):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8")
        handle.write("Load 48210\nInvoice total 2400\n")
        handle.close()
        try:
            self.assertEqual(ipc.amounts_in(handle.name), [])
        finally:
            os.unlink(handle.name)

    def test_amount_mismatch_is_a_problem(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\nRate: 2400 USD\n",
            "Invoice-1.txt": "Load 48210\nInvoice total: $2,300.00\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertFalse(result["ready"])
        self.assertTrue(any("amount mismatch" in p
                            for p in result["problems"]))
        self.assertEqual(result["amounts"]["Invoice-1.txt"], [230000])
        self.assertEqual(result["amounts"]["RateCon-1.txt"], [240000])

    def test_matching_totals_are_ready(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\nRate: 2400 USD\n",
            "Invoice-1.txt": "Load 48210\nInvoice total: $2,400.00\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])
        self.assertEqual(result["problems"], [])

    def test_total_is_the_largest_amount(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\nRate: 2400 USD\n",
            "Invoice-1.txt": "Linehaul: $2,000.00\n"
                             "Fuel surcharge: $400.00\n"
                             "Invoice total: $2,400.00\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])
        self.assertEqual(result["amounts"]["Invoice-1.txt"],
                         [200000, 40000, 240000])

    def test_no_amounts_skips_the_check(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])
        self.assertEqual(result["amounts"], {})

    def test_one_sided_amounts_skip_the_check(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\n",
            "Invoice-1.txt": "Load 48210\nInvoice total: $2,400.00\n",
        })
        result = ipc.check_packet(folder, list(ipc.CATEGORIES))
        self.assertTrue(result["ready"])


class TestCli(unittest.TestCase):
    def run_cli(self, args):
        return subprocess.run(
            [sys.executable,
             os.path.join(ROOT, "invoice_packet_checker.py")] + args,
            capture_output=True, text=True)

    def test_example_folders(self):
        complete = self.run_cli(
            [os.path.join(ROOT, "examples", "complete"), "--check"])
        self.assertEqual(complete.returncode, 0)
        self.assertIn("Packet is ready", complete.stdout)
        missing = self.run_cli(
            [os.path.join(ROOT, "examples", "missing-pod"), "--check"])
        self.assertEqual(missing.returncode, 1)
        self.assertIn("missing document: pod", missing.stdout)

    def test_json_output(self):
        proc = self.run_cli(
            [os.path.join(ROOT, "examples", "complete"), "--json"])
        data = json.loads(proc.stdout)
        self.assertTrue(data["ready"])
        self.assertEqual(data["documents"]["bol"], ["BOL-48210.txt"])

    def test_missing_folder_exits_two(self):
        proc = self.run_cli(["/nonexistent-folder-xyz"])
        self.assertEqual(proc.returncode, 2)

    def test_unknown_category_exits_two(self):
        proc = self.run_cli(
            [os.path.join(ROOT, "examples", "complete"),
             "--required", "bol,banana"])
        self.assertEqual(proc.returncode, 2)

    def test_amount_mismatch_exits_one(self):
        folder = packet({
            "BOL-1.txt": "Load 48210\n",
            "POD-1.txt": "Load 48210\n",
            "RateCon-1.txt": "Load 48210\nRate: 2400 USD\n",
            "Invoice-1.txt": "Load 48210\nInvoice total: $2,300.00\n",
        })
        proc = self.run_cli([folder, "--check"])
        data = json.loads(self.run_cli([folder, "--json"]).stdout)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("amount mismatch", proc.stdout)
        self.assertIn("$2,400.00", proc.stdout)
        self.assertIn("$2,300.00", proc.stdout)
        self.assertEqual(data["amounts"]["Invoice-1.txt"], [230000])
        self.assertEqual(data["amounts"]["RateCon-1.txt"], [240000])


if __name__ == "__main__":
    unittest.main()
