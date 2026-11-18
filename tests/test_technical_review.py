"""阶段 A 无申请文稿的独立技术审阅和双人结案验签。"""
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mechanical_patent.technical_review import inspect_brief


class TechnicalReviewTests(unittest.TestCase):
    def test_missing_brief_does_not_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_brief(Path(tmp), case_id="CASE", run_id="RUN-X",
                                   candidate_id="INV-1")
            self.assertEqual(result["status"], "revision_required")
            self.assertFalse(result["engineering_review_approved"])

    def test_two_independent_human_signatures_allow_eng_completion_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = {
                "candidate_id": "INV-1", "title": "两级吸水阀控制",
                "technical_problem": "入口气塞", "solution": "两阀依次动作",
                "mechanism": "压力变化触发两阀切换", "expected_effect": "预期减小脉动",
                "verification_plan": "台架低压试验验证",
                "components": [{"number": "101", "name": "阀", "role": "限流"}],
                "innovation_points": [{
                    "feature": "双阀联动", "prior_difference": "与单阀公开方案对照",
                    "technical_effect": "气塞缓解假说", "evidence_ids": ["EV-REAL"],
                }],
                "prior_art": [{"evidence_id": "EV-REAL", "known_solution": "入口单阀",
                               "difference": "双阀联动"}],
            }
            evidence = {
                "records": [{
                    "publication": "CN000001A", "title": "模拟试验文献",
                    "url": "https://example.org/patent",
                    "source": "mock", "retrieved_at": "2026-11-18T00:00:00Z",
                    "kind": "patent", "verified": True, "claims": "1. 入口单阀。",
                }],
            }
            from mechanical_patent.core import Evidence, evidence_id
            data["innovation_points"][0]["evidence_ids"] = [
                evidence_id(Evidence.from_dict(evidence["records"][0]))]
            data["prior_art"][0]["evidence_id"] = data["innovation_points"][0]["evidence_ids"][0]
            paths = {
                "08a_technical_brief.json": data, "04_evidence.json": evidence,
                "06_countersearch.json": {"claim_charts": [{
                    "candidate_id": "INV-1", "evidence": [{"evidence_id": data["prior_art"][0]["evidence_id"],
                                                            "quote": "1. 入口单阀。"}]}]},
                "07_engineering.json": {"assessments": [{
                    "candidate_id": "INV-1", "physical_principle": "液力平衡",
                    "falsification_tests": ["比较瞬态压力"]}]},
            }
            for filename, body in paths.items():
                (folder / filename).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            args = dict(case_id="CASE", run_id="RUN-X", candidate_id="INV-1")
            result = inspect_brief(folder, **args)
            self.assertEqual(result["status"], "awaiting_dual_human_review")
            self.assertFalse(result["filing_authorized"])

            approval = {
                **args, "brief_sha256": sha256((folder / "08a_technical_brief.json").read_bytes()).hexdigest(),
                "decision": "approve_technical_brief",
                "engineering_reviewer": "engineer-123", "ip_reviewer": "ip-456",
                "engineering_finding": "机理与试验充分说明",
                "patent_screening_finding": "初步专利差异足以继续推进",
                "signed_at": datetime.now(timezone.utc).isoformat(),
            }
            secret = "secure-independent-human-technical-review-signing-key"
            body = json.dumps(approval, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            approval["signature"] = hmac.new(secret.encode(), body, sha256).hexdigest()
            (folder / "08c_technical_review.json").write_text(
                json.dumps(approval, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"PATENT_TECHNICAL_REVIEW_KEY": secret}):
                result = inspect_brief(folder, **args)
                self.assertEqual(result["status"], "technical_complete")
                self.assertTrue(result["engineering_review_approved"])
                self.assertFalse(result["filing_authorized"])
                (folder / "08a_technical_brief.json").write_text(
                    '{"title":"unapproved revision"}', encoding="utf-8")
                self.assertEqual(inspect_brief(folder, **args)["status"], "revision_required")
