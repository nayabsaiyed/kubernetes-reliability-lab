import unittest

from scripts.lab import validate_stalled


class StalledReleaseTests(unittest.TestCase):
    def state(self):
        deployment = {"status": {"availableReplicas": 2, "conditions": [{"type": "Progressing", "status": "False", "reason": "ProgressDeadlineExceeded"}]}}
        bad = {"metadata": {"name": "bad-pod"}, "spec": {"containers": [{"env": [{"name": "RELEASE", "value": "bad-readiness"}]}]}, "status": {"containerStatuses": [{"ready": False, "restartCount": 0}]}}
        slices = {"items": [{"endpoints": [{"targetRef": {"name": "old-a"}, "conditions": {"ready": True}}, {"targetRef": {"name": "old-b"}, "conditions": {"ready": True}}]}]}
        return deployment, {"items": [bad]}, slices

    def test_stalled_release_preserves_baseline_endpoints(self):
        self.assertEqual(validate_stalled(*self.state(), {"old-a", "old-b"}), "bad-pod")

    def test_no_rollout_progress_is_not_enough_without_deadline_failure(self):
        deployment, pods, slices = self.state()
        deployment["status"]["conditions"] = []
        with self.assertRaises(AssertionError):
            validate_stalled(deployment, pods, slices, {"old-a", "old-b"})

    def test_candidate_must_not_receive_service_traffic(self):
        deployment, pods, slices = self.state()
        slices["items"][0]["endpoints"][0]["targetRef"]["name"] = "bad-pod"
        with self.assertRaises(AssertionError):
            validate_stalled(deployment, pods, slices, {"old-a", "old-b"})

    def test_crashing_candidate_is_a_different_failure_mode(self):
        deployment, pods, slices = self.state()
        pods["items"][0]["status"]["containerStatuses"][0]["restartCount"] = 1
        with self.assertRaises(AssertionError):
            validate_stalled(deployment, pods, slices, {"old-a", "old-b"})


class RecordedEvidenceTests(unittest.TestCase):
    def test_published_snapshots_support_the_failure_claim(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "evidence"
        baseline = json.loads((root / "2026-09-05-baseline.json").read_text())
        stalled = json.loads((root / "2026-09-05-stalled.json").read_text())
        original = {p["metadata"]["name"] for p in baseline["pods"]["items"]}
        candidate = validate_stalled(stalled["deployment"], stalled["pods"], stalled["endpointslices"], original)
        self.assertNotIn(candidate, original)


if __name__ == "__main__":
    unittest.main()
