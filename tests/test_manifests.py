import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ManifestContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.deployment = json.loads((ROOT / "manifests/deployment.json").read_text())
        cls.pod = cls.deployment["spec"]["template"]["spec"]
        cls.container = cls.pod["containers"][0]

    def test_unready_candidate_cannot_replace_ready_replicas(self):
        spec = self.deployment["spec"]
        self.assertEqual(spec["replicas"], 2)
        self.assertEqual(spec["strategy"]["rollingUpdate"], {"maxUnavailable": 0, "maxSurge": 1})
        self.assertGreater(spec["progressDeadlineSeconds"], spec["minReadySeconds"])

    def test_restricted_security_context(self):
        self.assertFalse(self.pod["automountServiceAccountToken"])
        self.assertTrue(self.pod["securityContext"]["runAsNonRoot"])
        self.assertGreater(self.pod["securityContext"]["runAsUser"], 0)
        self.assertEqual(self.pod["securityContext"]["seccompProfile"]["type"], "RuntimeDefault")
        security = self.container["securityContext"]
        self.assertFalse(security["allowPrivilegeEscalation"])
        self.assertTrue(security["readOnlyRootFilesystem"])
        self.assertEqual(security["capabilities"]["drop"], ["ALL"])

    def test_resource_requests_and_limits_present(self):
        for kind in ("requests", "limits"):
            for resource in ("cpu", "memory"):
                self.assertIn(resource, self.container["resources"][kind])

    def test_probe_paths_have_distinct_meanings(self):
        for probe, path in (("livenessProbe", "/livez"), ("readinessProbe", "/readyz"), ("startupProbe", "/startupz")):
            self.assertEqual(self.container[probe]["httpGet"]["path"], path)
            self.assertGreater(self.container[probe]["timeoutSeconds"], 0)

    def test_service_selects_only_lab_workload(self):
        service = json.loads((ROOT / "manifests/service.json").read_text())
        self.assertEqual(service["spec"]["selector"], self.deployment["spec"]["selector"]["matchLabels"])
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertNotIn("publishNotReadyAddresses", service["spec"])

    def test_namespace_enforces_restricted_policy(self):
        namespace = json.loads((ROOT / "manifests/namespace.json").read_text())
        self.assertEqual(namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"], "restricted")


if __name__ == "__main__":
    unittest.main()
