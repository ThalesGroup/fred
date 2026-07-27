#!/usr/bin/env python3

import argparse
import contextlib
import io
import unittest

import run_campaign


class CampaignRunnerTest(unittest.TestCase):
    def test_default_budget(self) -> None:
        args = argparse.Namespace(allow_overload=False)
        stages = run_campaign.stages_for(args)
        self.assertEqual(max(stage.clients for stage in stages), 50)
        self.assertEqual(sum(stage.total for stage in stages), 266)

    def test_overload_budget_is_separately_bounded(self) -> None:
        args = argparse.Namespace(allow_overload=True)
        stages = run_campaign.stages_for(args)
        self.assertEqual(max(stage.clients for stage in stages), 75)
        self.assertEqual(sum(stage.total for stage in stages), 344)
        self.assertEqual(stages[-1].name, "recovery")

    def test_non_loopback_target_is_refused(self) -> None:
        with self.assertRaises(run_campaign.CampaignError):
            run_campaign.ensure_loopback("https://example.com/execute", "target")

    def test_url_credentials_are_refused(self) -> None:
        for url in [
            "http://user:password@127.0.0.1:8000/execute",
            "http://127.0.0.1:8000/execute?access_token=secret",
        ]:
            with self.subTest(url=url), self.assertRaises(run_campaign.CampaignError):
                run_campaign.ensure_loopback(url, "target")

    def test_mock_profile_must_be_exact(self) -> None:
        args = argparse.Namespace(
            mock_delay_ms=1000,
            mock_summary_interval_ms=1000,
        )
        health = {
            "status": "ok",
            "performance_profile": {
                "response_delay_enabled": True,
                "response_delay_min_ms": 1000,
                "response_delay_max_ms": 1000,
                "summary_log_interval_ms": 1000,
            },
        }
        run_campaign.verify_mock_profile(health, args)
        health["performance_profile"]["response_delay_max_ms"] = 2000
        with self.assertRaises(run_campaign.CampaignError):
            run_campaign.verify_mock_profile(health, args)

    def test_three_times_baseline_guard(self) -> None:
        result = {
            "benchmark": {
                "total_requests": 30,
                "errors": 0,
                "latency": {"p50_ms": 3001},
            },
            "mock_delta": {"errors": 0},
            "resources_after": {"healthy": True},
        }
        reason = run_campaign.stage_stop_reason(result, baseline_p50=1000)
        self.assertIn("exceeds 3x baseline", reason or "")

    def test_plan_does_not_need_identifiers_or_token(self) -> None:
        args = argparse.Namespace(
            allow_overload=False,
            target=run_campaign.DEFAULT_TARGET,
            mock_url=run_campaign.DEFAULT_MOCK_URL,
            mock_delay_ms=1000,
            stage_timeout_seconds=180,
            cooldown_seconds=8,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            run_campaign.print_plan(args)
        self.assertIn("Total requests: 266", output.getvalue())
        self.assertIn("Max clients: 50", output.getvalue())


if __name__ == "__main__":
    unittest.main()
