"""企业可合法使用的专利查新评测；严格缺失归零，不需要联网/模型。"""
import json
from pathlib import Path
import tempfile
import unittest

from mechanical_patent.core import PatentWorkflowError
from mechanical_patent.benchmarks import (
    evaluate_retrieval, normalize_publication, run_benchmark, validate_dataset_rights,
)


RIGHTS = {
    "license": "INTERNAL-OWNED",
    "rights_holder": "内部测试数据权利人",
    "source_url": "https://example.org/internal-verified-benchmark",
    "commercial_evaluation_approved": True,
}


class BenchmarkTests(unittest.TestCase):
    def test_strict_family_aware_recall_and_mrr(self):
        truth = [
            {"case_id": "P1", "relevant_families": [
                ["CN123456789A", "US9999999B2"], ["WO202600001A1"]
            ]},
            {"case_id": "P2", "relevant_publications": ["CN888888888A"]},
            {"case_id": "P3", "relevant_publications": ["EP7777777A1"]},
        ]
        predictions = [
            {"case_id": "P1", "ranked_publications": [
                "US-9999999-B2", "WO202600001A1",
            ]},
            {"case_id": "P2", "ranked_publications": [
                "CN111111111A", "CN888888888A",
            ]},
        ]
        report = evaluate_retrieval(truth, predictions, RIGHTS)
        self.assertEqual(report["case_count"], 3)
        self.assertEqual(report["missing_predictions_count"], 1)
        self.assertAlmostEqual(report["metrics"]["hit@1"], 1/3, places=5)
        self.assertAlmostEqual(report["metrics"]["recall@5"], 2/3, places=5)
        self.assertEqual(report["metrics"]["mrr@5"], 0.5)
        self.assertTrue(all("case_id" in x for x in report["cases"]))
        self.assertEqual(report["mode"], "strict_all_cases")

    def test_license_gate_rejects_noncommercial_and_unknown_dataset(self):
        for license_value in ["CC BY-NC 4.0", "CC-BY-NC-4.0", "UNKNOWN", "NO-LICENSE"]:
            with self.subTest(license=license_value):
                with self.assertRaises(PatentWorkflowError):
                    validate_dataset_rights({**RIGHTS, "license": license_value})
        with self.assertRaises(PatentWorkflowError):
            validate_dataset_rights({**RIGHTS, "commercial_evaluation_approved": False})

    def test_duplicate_case_or_family_is_blocked(self):
        with self.assertRaises(PatentWorkflowError):
            evaluate_retrieval([
                {"case_id": "a", "relevant_publications": ["CN12345678A"]},
                {"case_id": "a", "relevant_publications": ["CN98765432A"]},
            ], [], RIGHTS)
        with self.assertRaises(PatentWorkflowError):
            evaluate_retrieval([{
                "case_id": "a",
                "relevant_families": [["CN12345678A"], ["CN-12345678-A"]]
            }], [], RIGHTS)
        with self.assertRaises(PatentWorkflowError):
            evaluate_retrieval([{"case_id": "a", "relevant_publications": ["CN12345678A"]}],
                               [{"case_id": "other", "ranked_publications": []}], RIGHTS)

    def test_file_based_benchmark_report_is_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            gold = root / "gold.jsonl"
            ranked = root / "ranked.jsonl"
            rights = root / "rights.json"
            output = root / "scores.json"
            gold.write_text(
                '{"case_id":"one","relevant_publications":["CN123456789A"]}\n'
                '{"case_id":"two","relevant_publications":["US7654321B2"]}\n',
                encoding="utf-8"
            )
            ranked.write_text(
                '{"case_id":"one","ranked_publications":["CN-123456789-A"]}\n',
                encoding="utf-8"
            )
            rights.write_text(json.dumps(RIGHTS, ensure_ascii=False), encoding="utf-8")
            result = run_benchmark(gold, ranked, rights, output)
            self.assertEqual(result["case_count"], 2)
            self.assertEqual(result["metrics"]["hit@1"], 0.5)
            self.assertEqual(json.loads(output.read_text())["metrics"]["hit@1"], 0.5)


if __name__ == "__main__":
    unittest.main()
