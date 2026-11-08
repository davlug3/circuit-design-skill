"""Structural checks for the curated model catalog.

The catalog is a claim that a part can be fetched from a stable URL. These
tests keep the claim honest about shape and uniqueness; they do not hit the
network. Run ``scripts/model_fetch.py --part <part>`` to verify a source.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import model_fetch  # noqa: E402


class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = model_fetch.load_catalog(ROOT / "catalog" / "models.json")
        self.entries = self.catalog["entries"]

    def test_entries_have_provenance(self):
        self.assertTrue(self.entries)
        for entry in self.entries:
            for key in ("part", "model", "vendor", "source"):
                self.assertTrue(entry.get(key), f"{entry.get('part')}: missing {key}")
            self.assertRegex(entry["source"], r"^https?://|^file://")
            if "checked" in entry:
                self.assertRegex(entry["checked"], r"^\d{4}-\d{2}-\d{2}$")

    def test_parts_and_aliases_are_unique(self):
        seen: dict[str, str] = {}
        for entry in self.entries:
            names = [entry["part"], entry["model"], *(entry.get("aliases") or [])]
            for name in names:
                key = name.lower()
                if key in seen:
                    self.assertEqual(seen[key], entry["part"],
                                     f"{name} is ambiguous: {seen[key]} and {entry['part']}")
                seen[key] = entry["part"]

    def test_subckt_entries_declare_pin_order(self):
        for entry in self.entries:
            pins = entry.get("subckt_pins")
            if pins is None:
                continue
            self.assertIsInstance(pins, list, entry["part"])
            self.assertTrue(pins, entry["part"])
            self.assertTrue(all(isinstance(pin, str) and pin for pin in pins),
                            entry["part"])

    def test_no_entry_pins_a_sha256(self):
        # A pinned upstream hash would make every legitimate vendor update a
        # failure. The fetcher records the hash of the file actually used.
        for entry in self.entries:
            self.assertNotIn("sha256", entry, entry["part"])

    def test_json_is_loadable(self):
        raw = (ROOT / "catalog" / "models.json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw)["version"], 1)


if __name__ == "__main__":
    unittest.main()
