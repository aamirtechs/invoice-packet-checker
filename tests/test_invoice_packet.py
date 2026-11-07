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


if __name__ == "__main__":
    unittest.main()
