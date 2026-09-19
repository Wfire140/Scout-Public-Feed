import copy
import json
import tempfile
import unittest
from pathlib import Path

import mirror


def sample():
    return {
        "schemaVersion": 1, "status": "online", "publisher": "Scout", "scoutVersion": "1.3.0",
        "generatedUtc": "2026-09-19T13:49:55Z", "project": "Scout", "receivedUtc": "2026-09-19T13:49:56Z",
        "searches": [{"id": "a", "name": "GPU", "query": "GPU", "checkedUtc": "2026-09-19T13:49:38Z",
                      "resultCount": 0, "pricing": {"calculatorVersion": 1, "target": 500,
                      "freshReferenceSources": 0, "currentConfidence": "None", "coverage30": "Insufficient",
                      "validDays30": 0, "coverage90": "Insufficient", "validDays90": 0,
                      "trend": "InsufficientData"}}]
    }


def encoded(value):
    return json.dumps(value).encode()


class MirrorTests(unittest.TestCase):
    def test_valid_schema_v1(self):
        self.assertEqual(mirror.decode(encoded(sample())), sample())

    def test_malformed_json(self):
        with self.assertRaises(ValueError):
            mirror.decode(b"{")

    def test_private_path_field(self):
        value = sample()
        value["searches"][0]["profilePath"] = "C:\\Users\\someone"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_private_path_in_allowed_text_field(self):
        value = sample()
        value["searches"][0]["name"] = "C:\\Users\\someone\\profile"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_token_field(self):
        value = sample()
        value["apiToken"] = "abc"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_postal_context_in_allowed_text_field(self):
        value = sample()
        value["searches"][0]["query"] = "ZIP 60601"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_unexpected_field(self):
        value = sample()
        value["newPublicField"] = "hello"
        with self.assertRaises(ValueError):
            mirror.decode(encoded(value))

    def test_identical_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            self.assertTrue(mirror.update(path, lambda: encoded(sample())))
            old = path.read_bytes()
            self.assertFalse(mirror.update(path, lambda: encoded(sample())))
            self.assertEqual(path.read_bytes(), old)

    def test_changed_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            mirror.update(path, lambda: encoded(sample()))
            changed = copy.deepcopy(sample())
            changed["searches"][0]["resultCount"] = 1
            self.assertTrue(mirror.update(path, lambda: encoded(changed)))
            self.assertEqual(json.loads(path.read_text())["searches"][0]["resultCount"], 1)

    def test_failed_fetch_preserves_prior(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            mirror.update(path, lambda: encoded(sample()))
            old = path.read_bytes()
            def fail():
                raise ConnectionError("source unavailable")
            with self.assertRaises(ConnectionError):
                mirror.update(path, fail)
            self.assertEqual(path.read_bytes(), old)

    def test_bad_payload_preserves_prior(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scout-current.json"
            mirror.update(path, lambda: encoded(sample()))
            old = path.read_bytes()
            with self.assertRaises(ValueError):
                mirror.update(path, lambda: b"not json")
            self.assertEqual(path.read_bytes(), old)


if __name__ == "__main__":
    unittest.main()
