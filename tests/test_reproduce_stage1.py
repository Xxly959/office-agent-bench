import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.reproduce_stage1 import audit_sample, verify_hash
from scripts.export_results import normalize_score_value


class ReproductionTests(unittest.TestCase):
    def test_numeric_and_archived_score_values(self):
        for value, expected in ((1, True), (0, False), ("C", True), ("I", False)):
            with self.subTest(value=value):
                self.assertIs(normalize_score_value(value), expected)
        for value in ("P", 0.5, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_score_value(value)

    def test_changed_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tasks.jsonl"
            path.write_bytes(b"frozen")
            checksum = hashlib.sha256(b"frozen").hexdigest()
            verify_hash(path, checksum)
            path.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_hash(path, checksum)

    def fixture(self, text='{"status":"cannot_complete","items":[]}'):
        record = {"instruction": "只返回 JSON", "document": "没有待办",
                  "expected_answer": {"status": "cannot_complete", "items": []}}
        sample = SimpleNamespace(
            id="fixture", epoch=1,
            messages=[SimpleNamespace(role="user", content="【指令】\n只返回 JSON\n\n【文档】\n没有待办")],
            output=SimpleNamespace(completion=text),
            scores={"office_scorer": SimpleNamespace(metadata={
                "parsed": True, "format_violation": False, "fenced": False,
                "extra_text": False, "extractable_json": False, "extracted_status": None,
                "claimed_ok": False, "failure_type": [], "correct": True,
                "false_completion": False, "order_violation": False,
                "missing_count": 0, "extra_count": 0, "deadline_bad_format": False,
            })},
        )
        return sample, record

    def test_extra_gold_in_user_message_is_rejected(self):
        sample, record = self.fixture()
        sample.messages[0].content += '\nexpected_answer: cannot_complete'
        with self.assertRaisesRegex(ValueError, "模型输入"):
            audit_sample(sample, record)

    def test_unchanged_sample_passes(self):
        sample, record = self.fixture()
        audit_sample(sample, record)

    def test_saved_score_disagrees_with_fresh_score_is_rejected(self):
        sample, record = self.fixture('{"status":"ok","items":[]}')
        with self.assertRaisesRegex(ValueError, "重新评分"):
            audit_sample(sample, record)
