"""Unit tests: run with  python -m unittest test_ark_afp_quota -v"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import ark_afp_quota as mod
from volc_signer import Credentials, sign_request


class SignerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.creds = Credentials("AKLTtest", "SKtest")
        self.now = dt.datetime(2026, 9, 4, 2, 3, 4, tzinfo=dt.timezone.utc)

    def _sign(self, **kw):
        base = dict(
            credentials=self.creds, method="POST", host="open.volcengineapi.com",
            path="/", query={"Version": "2024-01-01", "Action": "GetAgentPlanQuota"},
            body=b'{"PlanType":"Personal"}', region="cn-beijing", service="ark", now=self.now,
        )
        base.update(kw)
        return sign_request(**base)

    def test_headers_and_url(self):
        s = self._sign()
        self.assertEqual(s.headers["X-Date"], "20260904T020304Z")
        self.assertEqual(s.url, "https://open.volcengineapi.com/?Action=GetAgentPlanQuota&Version=2024-01-01")
        auth = s.headers["Authorization"]
        self.assertTrue(auth.startswith("HMAC-SHA256 Credential=AKLTtest/20260904/cn-beijing/ark/request, "))
        self.assertIn("SignedHeaders=content-type;host;x-content-sha256;x-date", auth)
        self.assertRegex(auth, r"Signature=[0-9a-f]{64}$")
        self.assertEqual(len(s.headers["X-Content-Sha256"]), 64)

    def test_deterministic_and_sensitive(self):
        a = self._sign().headers["Authorization"]
        b = self._sign().headers["Authorization"]
        c = self._sign(body=b'{"PlanType":"Team"}').headers["Authorization"]
        d = self._sign(credentials=Credentials("AKLTtest", "other")).headers["Authorization"]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)

    def test_session_token_header(self):
        s = self._sign(credentials=Credentials("ak", "sk", session_token="tok"))
        self.assertEqual(s.headers["X-Security-Token"], "tok")
        self.assertIn("x-security-token", s.headers["Authorization"])

    def test_empty_credentials_rejected(self):
        with self.assertRaises(ValueError):
            Credentials("", "sk")


class ParseTests(unittest.TestCase):
    def test_list_shape(self):
        resp = {"Result": {"Quotas": [
            {"Window": "FiveHour", "Total": 100, "Used": 95},
            {"Window": "Week", "Limit": 1000, "Remaining": 500},
            {"Period": "Monthly", "Used": 10, "Remaining": 90, "ResetTime": "2026-10-01"},
        ]}}
        q = {x.window: x for x in mod.parse_quotas(resp)}
        self.assertEqual(set(q), {"5h", "week", "month"})
        self.assertEqual(q["5h"].remaining, 5)
        self.assertAlmostEqual(q["5h"].remaining_pct, 5.0)
        self.assertEqual(q["week"].used, 500)
        self.assertEqual(q["month"].total, 100)
        self.assertEqual(q["month"].reset_time, "2026-10-01")

    def test_mapping_shape_nested(self):
        resp = {"Result": {"Plan": {"Usage": {
            "five_hour": {"total_afp": 2000, "remaining_afp": 150},
            "weekly": {"quota": 20000, "used": 100},
            "monthly": {"quota": 60000, "used": 0},
        }}}}
        q = {x.window: x for x in mod.parse_quotas(resp)}
        self.assertEqual(q["5h"].used, 1850)
        self.assertEqual(q["week"].remaining, 19900)
        self.assertEqual(q["month"].remaining_pct, 100.0)

    def test_partial_windows(self):
        resp = {"Result": {"Quotas": [{"Window": "Week", "Total": 10, "Used": 1}]}}
        q = mod.parse_quotas(resp)
        self.assertEqual([x.window for x in q], ["week"])

    def test_nothing_found(self):
        with self.assertRaises(mod.QuotaError):
            mod.parse_quotas({"Result": {"Foo": 1}})

    def test_zero_total(self):
        q = mod.WindowQuota("5h", total=0, remaining=0)
        self.assertEqual(q.remaining_pct, 0.0)
        self.assertTrue(q.below(10))


class AlertAndCliTests(unittest.TestCase):
    def _run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = mod.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_alert_threshold_boundary(self):
        qs = [mod.WindowQuota("5h", 100, 10), mod.WindowQuota("week", 100, 9.99)]
        alerts = mod.alerts_for(qs, 10)
        self.assertEqual(len(alerts), 1)
        self.assertIn("本周", alerts[0])

    def test_cli_mock_alert_exit_code(self):
        here = os.path.dirname(os.path.abspath(__file__))
        code, out, _ = self._run("--mock-file", os.path.join(here, "sample_response.json"))
        self.assertEqual(code, 1)  # 5h window is at 7.5%
        self.assertIn("[ALERT]", out)
        self.assertIn("5 小时", out)

    def test_cli_json_output(self):
        data = {"Result": {"Quotas": [
            {"Window": "FiveHour", "Total": 100, "Remaining": 50},
            {"Window": "Week", "Total": 100, "Remaining": 50},
            {"Window": "Month", "Total": 100, "Remaining": 50},
        ]}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(data, fh)
        try:
            code, out, _ = self._run("--mock-file", fh.name, "--json")
        finally:
            os.unlink(fh.name)
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertEqual(len(parsed["windows"]), 3)
        self.assertEqual(parsed["alerts"], [])
        self.assertFalse(any(w["alert"] for w in parsed["windows"]))

    def test_cli_missing_credentials(self):
        saved = {k: os.environ.pop(k, None) for k in
                 ("VOLC_ACCESSKEY", "VOLC_SECRETKEY", "VOLC_ACCESS_KEY", "VOLC_SECRET_KEY")}
        try:
            code, _, err = self._run()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        self.assertEqual(code, 2)
        self.assertIn("VOLC_ACCESSKEY", err)

    def test_cli_bad_threshold(self):
        code, _, _ = self._run("--threshold", "150", "--mock-file", "/nonexistent")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
