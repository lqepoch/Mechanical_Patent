"""申请文本转换必须经过独立密钥审批，MCP Host 无权自签。"""
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from mechanical_patent.filing_gate import conversion_status, require_conversion_approval
from mechanical_patent.core import PatentWorkflowError


class ConversionGateTests(TestCase):
    def test_approval_requires_matching_hmac_and_current_technical_brief(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "08a_technical_brief.json").write_text('{"title":"初版方案"}', encoding="utf-8")
            secret = "secure-enterprise-approval-secret-0123456789"
            approval = {
                "case_id": "CASE1", "run_id": "RUN-A1", "candidate_id": "INV-1",
                "brief_sha256": sha256((root / "08a_technical_brief.json").read_bytes()).hexdigest(),
                "decision": "convert_to_application",
                "approved_by": "corporate-oidc-user-123",
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }
            body = json.dumps(approval, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            approval["signature"] = hmac.new(secret.encode(), body, sha256).hexdigest()
            (root / "08b_conversion_approval.json").write_text(
                json.dumps(approval, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"PATENT_CONVERSION_APPROVAL_KEY": secret}):
                self.assertTrue(conversion_status(root, "CASE1", "RUN-A1", "INV-1")["conversion_authorized"])
                self.assertFalse(conversion_status(root, "CASE1", "RUN-A1", "INV-1")["filing_authorized"])
                with self.assertRaises(PatentWorkflowError):
                    require_conversion_approval(root, "CASE1", "RUN-A1", "INV-2")
                (root / "08a_technical_brief.json").write_text('{"title":"未批准修改"}', encoding="utf-8")
                self.assertFalse(conversion_status(root, "CASE1", "RUN-A1", "INV-1")["conversion_authorized"])
            with patch.dict(os.environ, {"PATENT_CONVERSION_APPROVAL_KEY": ""}):
                self.assertFalse(conversion_status(root, "CASE1", "RUN-A1", "INV-1")["conversion_authorized"])

    def test_no_brief_or_approval_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(PatentWorkflowError):
                require_conversion_approval(Path(temp), "CASE1", "RUN-A1", "INV-1")
