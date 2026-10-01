"""Small synthetic checks; these data never enter formal result summaries."""
from pathlib import Path
import importlib.util
import statistics
import unittest

ENTRY = Path(__file__).resolve().parents[1] / "scripts" / "analyze.py"
SPEC = importlib.util.spec_from_file_location("core_rebuild_analysis", ENTRY)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


def fixture(ratios, *, shared=False, packed=None):
    roles = {"P": "packed", "R_matched": "repeated-matched", "R_independent": "repeated-matched" if shared else "repeated-independent"}
    rows, schedule = [], []
    for session_index, session_ratios in enumerate(ratios):
        session = f"S{session_index + 1}"
        for phase, blocks in (("warmup", [0]), ("measured", range(len(session_ratios)))):
            for block in blocks:
                for config in dict.fromkeys(roles.values()):
                    base = packed[session_index][block] if packed and phase == "measured" else 10
                    ratio = session_ratios[block] if phase == "measured" else 1
                    latency = base if config == "packed" else base * ratio
                    key = dict(condition_id="c1", session_id=session, block_id=block, phase=phase, config_id=config)
                    schedule.append(key)
                    rows.append(dict(key, observation_id=f"{session}/{phase}/{block}/{config}", status="COMPLETE", validated=True, task_latency_ns=latency, cpu_time_ns=latency * 2, preprocessing_ns=1, query_buffer_bytes=128, reply_buffer_bytes=256))
    return rows, schedule, roles


class SessionAnalysisTests(unittest.TestCase):
    def summarize(self, data, **kwargs):
        rows, schedule, roles = data
        return analysis.analyze_condition(rows, schedule, roles, condition_id="c1", seed=7, resamples=31, **kwargs)

    def test_direction_and_two_medians_not_pooled(self):
        ratios = [[1, 1, 1, 100, 100, 100], [2, 2, 2, 100, 100, 100], [3] * 6]
        result = self.summarize(fixture(ratios))
        self.assertEqual(result["ratios"]["R_independent"]["estimate"], 50.5)
        self.assertEqual(statistics.median([r for session in ratios for r in session]), 3)
        self.assertEqual([s["ratios"]["R_independent"] for s in result["sessions"]], [50.5, 51, 3])

    def test_paired_ratio_not_quotient_of_method_medians(self):
        result = self.summarize(fixture([[1, 1, 1, 2, 2, 2]], packed=[[1, 1, 1, 100, 100, 100]]))
        self.assertEqual(result["ratios"]["R_matched"]["estimate"], 1.5)
        self.assertNotEqual(result["ratios"]["R_matched"]["estimate"], result["absolute"]["R_matched"]["task_latency_ns"]["estimate"] / result["absolute"]["P"]["task_latency_ns"]["estimate"])

    def test_every_ten_session_effect_is_retained(self):
        result = self.summarize(fixture([[s] * 6 for s in range(1, 11)]))
        self.assertEqual(len(result["sessions"]), 10)
        self.assertEqual([s["ratios"]["R_matched"] for s in result["sessions"]], list(range(1, 11)))
        self.assertEqual(result["ratios"]["R_matched"]["estimate"], 5.5)
        self.assertEqual(result["bootstrap"]["unit"], "whole_session")
        self.assertEqual(analysis.BOOTSTRAP_RESAMPLES, 10_000)

    def test_one_failed_method_invalidates_entire_condition(self):
        for status in ("FAIL", "OOM", "TIMEOUT", "NOT_STARTED"):
            with self.subTest(status=status):
                rows, schedule, roles = fixture([[2] * 6, [3] * 6])
                rows[5]["status"] = status
                result = self.summarize((rows, schedule, roles))
                self.assertEqual(result["status"], "INCOMPLETE")
                self.assertNotIn("ratios", result)
                self.assertNotIn("bootstrap", result)
                self.assertTrue(result["issues"])

    def test_missing_method_cannot_create_success_subset(self):
        rows, schedule, roles = fixture([[2] * 6])
        rows.pop()
        result = self.summarize((rows, schedule, roles))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["issues"][0]["reason"], "missing_observation")
        self.assertNotIn("sessions", result)

    def test_unvalidated_and_failed_warmup_are_incomplete(self):
        rows, schedule, roles = fixture([[2] * 6])
        rows[0]["validated"] = False
        self.assertEqual(self.summarize((rows, schedule, roles))["status"], "INCOMPLETE")

    def test_baseline_dedup_uses_one_actual_observation(self):
        rows, schedule, roles = fixture([[2] * 6, [3] * 6], shared=True)
        result = self.summarize((rows, schedule, roles))
        self.assertEqual(len(rows), 2 * 7 * 2)
        self.assertTrue(result["shared_baseline_observations"])
        self.assertEqual(result["ratios"]["R_matched"], result["ratios"]["R_independent"])
        for session in result["sessions"]:
            self.assertEqual(session["role_observation_ids"]["R_matched"], session["role_observation_ids"]["R_independent"])

    def test_joint_cluster_resampling_preserves_contrast_relation(self):
        vectors = {f"S{i}": {"matched": i, "independent": i * 2, "absolute": 30 - i} for i in range(1, 11)}
        result = analysis.session_cluster_bootstrap(vectors, seed=123, resamples=101)
        self.assertEqual(result["replicates"]["independent"], [2 * x for x in result["replicates"]["matched"]])
        self.assertEqual(result["replicates"]["absolute"], [30 - x for x in result["replicates"]["matched"]])
        self.assertEqual(result["joint_index_draws_sha256"], analysis.session_cluster_bootstrap(vectors, seed=123, resamples=101)["joint_index_draws_sha256"])

    def test_duplicate_rows_do_not_inflate_sample_count(self):
        rows, schedule, roles = fixture([[2] * 6])
        rows.append(dict(rows[0]))
        result = self.summarize((rows, schedule, roles))
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertNotIn("ratios", result)

    def test_warmups_excluded_from_estimates(self):
        rows, schedule, roles = fixture([[2] * 6])
        for row in rows:
            if row["phase"] == "warmup":
                row["task_latency_ns"] = 100_000 if row["config_id"] != "packed" else 1
        self.assertEqual(self.summarize((rows, schedule, roles))["ratios"]["R_matched"]["estimate"], 2)

    def test_percentile_rule(self):
        self.assertEqual(analysis.percentile([0, 10], .25), 2.5)

    def test_mixed_run_versions_not_pooled(self):
        rows, schedule, roles = fixture([[2] * 6])
        for i, row in enumerate(rows):
            row["code_sha256"] = "old" if i == 0 else "new"
        self.assertEqual(self.summarize((rows, schedule, roles))["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
