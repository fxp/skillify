"""Offline unit tests for ark_afp_quota (no network, no credentials).

Run:  python3 -m unittest test_ark_afp_quota -v
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from unittest import mock

import ark_afp_quota as mod

SAMPLE_RESULT = {
    "PlanType": "Medium",
    "AFPFiveHour": {"Quota": "10000", "Used": "9200",
                    "SubscribeTime": 1756800000000, "ResetTime": 1756818000000},
    "AFPDaily": {"Quota": "50000", "Used": "100",
                 "SubscribeTime": 1756742400000, "ResetTime": 1756828800000},
    "AFPWeekly": {"Quota": "35000", "Used": "12000",
                  "SubscribeTime": 1756656000000, "ResetTime": 1757260800000},
    "AFPMonthly": {"Quota": "100000", "Used": "99999.5",
                   "SubscribeTime": 1754064000000, "ResetTime": 1756742400000},
}
ENVELOPE = {"ResponseMetadata": {"RequestId": "req-1", "Action": "GetAFPUsage",
                                 "Version": "2024-01-01", "Service": "ark", "Region": "cn-beijing"},
            "Result": SAMPLE_RESULT}


class ParsingTests(unittest.TestCase):
    def test_from_result_parses_strings_and_ms_timestamps(self):
        usage = mod.AfpUsage.from_result(SAMPLE_RESULT)
        self.assertEqual(usage.plan_type, "Medium")
        self.assertEqual([w.key for w in usage.windows],
                         ["AFPFiveHour", "AFPDaily", "AFPWeekly", "AFPMonthly"])
        five = usage.window("AFPFiveHour")
        self.assertEqual(five.quota, Decimal("10000"))
        self.assertEqual(five.remaining, Decimal("800"))
        self.assertEqual(five.remaining_percent, Decimal("8"))
        self.assertEqual(five.reset_time,
                         dt.datetime.fromtimestamp(1756818000, tz=dt.timezone.utc).astimezone())

    def test_missing_windows_raise(self):
        with self.assertRaises(mod.ArkMgmtError):
            mod.AfpUsage.from_result({"PlanType": "Medium"})

    def test_non_numeric_quota_raises(self):
        bad = {"AFPFiveHour": {"Quota": "abc", "Used": "1"}}
        with self.assertRaises(mod.ArkMgmtError):
            mod.AfpUsage.from_result(bad)

    def test_used_over_quota_clamps_remaining_to_zero(self):
        w = mod.AfpWindow("AFPWeekly", Decimal(100), Decimal(150))
        self.assertEqual(w.remaining, Decimal(0))
        self.assertEqual(w.remaining_percent, Decimal(0))
        self.assertTrue(w.is_below(10))

    def test_zero_quota_never_alerts(self):
        w = mod.AfpWindow("AFPDaily", Decimal(0), Decimal(0))
        self.assertIsNone(w.remaining_percent)
        self.assertFalse(w.is_below(10))


class ThresholdTests(unittest.TestCase):
    def setUp(self):
        self.usage = mod.AfpUsage.from_result(SAMPLE_RESULT)

    def test_default_primary_windows_only(self):
        low = mod.find_low_windows(self.usage, 10, list(mod.PRIMARY_WINDOWS))
        self.assertEqual([w.key for w in low], ["AFPFiveHour", "AFPMonthly"])

    def test_threshold_is_inclusive(self):
        usage = mod.AfpUsage.from_result({"AFPWeekly": {"Quota": "1000", "Used": "900"}})
        self.assertEqual(len(mod.find_low_windows(usage, 10)), 1)
        self.assertEqual(len(mod.find_low_windows(usage, 9.99)), 0)

    def test_all_windows_includes_daily(self):
        usage = mod.AfpUsage.from_result({"AFPDaily": {"Quota": "100", "Used": "95"},
                                          "AFPWeekly": {"Quota": "100", "Used": "0"}})
        self.assertEqual([w.key for w in mod.find_low_windows(usage, 10)], ["AFPDaily"])
        self.assertEqual(mod.find_low_windows(usage, 10, list(mod.PRIMARY_WINDOWS)), [])


class EnvelopeTests(unittest.TestCase):
    def test_unwrap_result(self):
        self.assertEqual(mod._unwrap_result(ENVELOPE, "GetAFPUsage"), SAMPLE_RESULT)

    def test_unwrap_already_unwrapped(self):
        self.assertEqual(mod._unwrap_result(SAMPLE_RESULT, "GetAFPUsage"), SAMPLE_RESULT)

    def test_api_error_in_metadata(self):
        payload = {"ResponseMetadata": {"RequestId": "r", "Error": {
            "Code": "ResourceNotFound.Plan", "Message": "plan not found"}}}
        with self.assertRaises(mod.ArkMgmtError) as ctx:
            mod._unwrap_result(payload, "GetPersonalPlan")
        self.assertEqual(ctx.exception.code, "ResourceNotFound.Plan")
        self.assertEqual(ctx.exception.request_id, "r")


class SignerTests(unittest.TestCase):
    """The signature is deterministic for a fixed clock; these tests pin the
    canonical shape (headers, credential scope, signed-headers list) so a refactor
    cannot silently change the algorithm."""

    def setUp(self):
        self.signer = mod.StdlibSigner("AKID", "SECRET")
        self.now = dt.datetime(2026, 9, 4, 3, 4, 5, tzinfo=dt.timezone.utc)

    def test_header_shape(self):
        body = b"{}"
        headers = self.signer.sign("POST", {"Version": "2024-01-01", "Action": "GetAFPUsage"},
                                   body, now=self.now)
        self.assertEqual(headers["X-Date"], "20260904T030405Z")
        self.assertEqual(headers["Host"], "ark.cn-beijing.volcengineapi.com")
        self.assertEqual(headers["X-Content-Sha256"],
                         "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")
        auth = headers["Authorization"]
        self.assertTrue(auth.startswith(
            "HMAC-SHA256 Credential=AKID/20260904/cn-beijing/ark/request, "
            "SignedHeaders=content-type;host;x-content-sha256;x-date, Signature="))
        self.assertRegex(auth.rsplit("Signature=", 1)[1], r"^[0-9a-f]{64}$")
        self.assertNotIn("X-Security-Token", headers)

    def test_signature_is_deterministic_and_key_sensitive(self):
        q = {"Action": "GetAFPUsage", "Version": "2024-01-01"}
        a = self.signer.sign("POST", q, b"{}", now=self.now)["Authorization"]
        b = self.signer.sign("POST", q, b"{}", now=self.now)["Authorization"]
        c = mod.StdlibSigner("AKID", "OTHER").sign("POST", q, b"{}", now=self.now)["Authorization"]
        d = self.signer.sign("POST", q, b'{"Plan":"AgentPlan"}', now=self.now)["Authorization"]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, d)

    def test_query_is_sorted_and_encoded(self):
        self.assertEqual(mod.StdlibSigner.canonical_query({"Version": "2024-01-01", "Action": "X"}),
                         "Action=X&Version=2024-01-01")

    def test_session_token_header(self):
        s = mod.StdlibSigner("AK", "SK", session_token="tok")
        self.assertEqual(s.sign("POST", {}, b"{}", now=self.now)["X-Security-Token"], "tok")


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class StdlibTransportTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"VOLC_ACCESSKEY": "AK", "VOLC_SECRETKEY": "SK"},
                                   clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_success_roundtrip(self):
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["body"] = req.data
            captured["headers"] = dict(req.header_items())
            return _FakeResponse(json.dumps(ENVELOPE).encode())

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            client = mod.ArkManagementClient(transport="stdlib")
            usage = client.get_afp_usage()
        self.assertEqual(client.transport_name, "stdlib")
        self.assertEqual(captured["url"],
                         "https://ark.cn-beijing.volcengineapi.com/?Action=GetAFPUsage&Version=2024-01-01")
        self.assertEqual(captured["body"], b"{}")
        self.assertIn("Authorization", captured["headers"])
        self.assertEqual(usage.plan_type, "Medium")

    def test_http_error_with_api_code(self):
        err_body = json.dumps({"ResponseMetadata": {"RequestId": "r2", "Error": {
            "Code": "InvalidAccessKey", "Message": "The access key is invalid"}}}).encode()
        http_err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(err_body))
        with mock.patch("urllib.request.urlopen", side_effect=http_err):
            client = mod.ArkManagementClient(transport="stdlib")
            with self.assertRaises(mod.ArkMgmtError) as ctx:
                client.get_afp_usage()
        self.assertEqual(ctx.exception.code, "InvalidAccessKey")
        self.assertEqual(ctx.exception.http_status, 401)

    def test_network_error(self):
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("dns down")):
            with self.assertRaises(mod.ArkMgmtError):
                mod.ArkManagementClient(transport="stdlib").get_afp_usage()


class ClientTests(unittest.TestCase):
    def test_missing_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(mod.ArkMgmtError):
                mod.ArkManagementClient(transport="stdlib")

    def test_get_personal_plan_body(self):
        with mock.patch.dict(os.environ, {"VOLC_ACCESSKEY": "AK", "VOLC_SECRETKEY": "SK"}):
            client = mod.ArkManagementClient(transport="stdlib")
        with mock.patch.object(client, "_transport") as t:
            t.call.return_value = {"PlanType": "Medium", "Status": "Running"}
            self.assertEqual(client.get_personal_plan()["Status"], "Running")
            t.call.assert_called_once_with("GetPersonalPlan", {"Plan": "AgentPlan"})


class CliTests(unittest.TestCase):
    def _run(self, argv, result=SAMPLE_RESULT, plan=None):
        fake = mock.MagicMock()
        fake.transport_name = "stdlib"
        fake.get_afp_usage.return_value = mod.AfpUsage.from_result(result)
        if plan is not None:
            fake.get_personal_plan.return_value = plan
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(mod, "ArkManagementClient", return_value=fake), \
                redirect_stdout(out), redirect_stderr(err):
            code = mod.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_alert_exit_code_and_message(self):
        code, out, err = self._run([])
        self.assertEqual(code, 2)
        self.assertIn("[ALERT] 5 小时", out)
        self.assertIn("[ALERT] 月", out)
        self.assertNotIn("[ALERT] 周", out)
        self.assertIn("[ALERT]", err)

    def test_ok_when_threshold_low(self):
        code, out, _ = self._run(["--threshold", "0.0001"])
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_json_output(self):
        code, out, _ = self._run(["--json", "--plan"], plan={"Status": "Running"})
        self.assertEqual(code, 2)
        data = json.loads(out)
        self.assertEqual(data["plan_type"], "Medium")
        self.assertEqual(data["alerts"], ["AFPFiveHour", "AFPMonthly"])
        self.assertEqual(data["plan"]["Status"], "Running")
        five = next(w for w in data["windows"] if w["window"] == "AFPFiveHour")
        self.assertEqual(five["remaining"], "800")
        self.assertEqual(five["remaining_percent"], 8.0)

    def test_error_path(self):
        fake_cls = mock.MagicMock(side_effect=mod.ArkMgmtError("boom", code="ResourceNotFound.Plan"))
        err = io.StringIO()
        with mock.patch.object(mod, "ArkManagementClient", fake_cls), redirect_stderr(err):
            self.assertEqual(mod.main([]), 1)
        self.assertIn("ResourceNotFound.Plan", err.getvalue())
        self.assertIn("没有生效中的 Agent Plan", err.getvalue())


if __name__ == "__main__":
    unittest.main()
