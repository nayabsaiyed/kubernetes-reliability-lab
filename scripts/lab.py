#!/usr/bin/env python3
"""Run one isolated kind experiment; never select or modify a user's context."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
NODE_IMAGE = "kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5"
NAMESPACE = "reliability-lab"


def validate_stalled(deployment, pods, slices, original_pods):
    status = deployment["status"]
    assert status.get("availableReplicas", 0) == 2, "Baseline availability fell below two replicas"
    assert any(c["type"] == "Progressing" and c["status"] == "False" and c["reason"] == "ProgressDeadlineExceeded" for c in status.get("conditions", [])), "Expected ProgressDeadlineExceeded"
    candidates = [p for p in pods["items"] if any(e.get("name") == "RELEASE" and e.get("value") == "bad-readiness" for e in p["spec"]["containers"][0].get("env", []))]
    assert len(candidates) == 1, "Expected one surge candidate"
    candidate = candidates[0]
    containers = candidate["status"].get("containerStatuses", [])
    assert containers and all(not c["ready"] and c["restartCount"] == 0 for c in containers), "Candidate must be unready without restarts"
    ready_names = {e["targetRef"]["name"] for s in slices["items"] for e in s.get("endpoints", []) if e.get("conditions", {}).get("ready")}
    assert ready_names == original_pods, "Service ready endpoints changed during stalled rollout"
    return candidate["metadata"]["name"]


def kubeconfig_fingerprints():
    paths = os.environ.get("KUBECONFIG", str(Path.home() / ".kube/config")).split(os.pathsep)
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else None for p in paths if p}


class Lab:
    def __init__(self):
        self.name = "laniakea-reliability-" + uuid.uuid4().hex[:10]
        self.run_dir = ROOT / ".lab" / "runs" / self.name
        self.run_dir.mkdir(parents=True, mode=0o700)
        self.kubeconfig = self.run_dir / "kubeconfig"
        self.context = "kind-" + self.name
        self.image = "laniakea-reliability-api:" + self.name
        self.created = False
        self.image_built = False
        self.summary = {"started_at": datetime.now(timezone.utc).isoformat(), "cluster": self.name, "node_image": NODE_IMAGE, "phases": [], "result": "running"}
        self.original_config = kubeconfig_fingerprints()
        (self.run_dir / "metadata.json").write_text(json.dumps({"cluster": self.name, "image": self.image}, indent=2) + "\n")

    def command(self, args, timeout=120, check=True):
        printable = shlex.join(str(a) for a in args).replace(str(self.run_dir), "$RUN_DIR").replace(str(ROOT), "$REPO")
        print("+ " + printable, flush=True)
        with (self.run_dir / "commands.log").open("a") as log:
            log.write("+ " + printable + "\n")
            result = subprocess.run([str(a) for a in args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            log.write(result.stdout.replace(str(self.run_dir), "$RUN_DIR").replace(str(ROOT), "$REPO") + f"\n[exit {result.returncode}]\n")
        if check and result.returncode:
            print(result.stdout, file=sys.stderr)
            raise RuntimeError(f"Command exited {result.returncode}: {printable}")
        return result

    def kubectl(self, *args, **kwargs):
        return self.command(["kubectl", "--kubeconfig", self.kubeconfig, "--context", self.context, "--namespace", NAMESPACE, *args], **kwargs)

    def get(self, kind, *args):
        return json.loads(self.kubectl("get", kind, *args, "-o", "json").stdout)

    def snapshot(self, phase):
        data = {
            "deployment": self.get("deployment", "reliability-api"),
            "pods": self.get("pods", "-l", "app=reliability-api"),
            "endpointslices": self.get("endpointslices", "-l", "kubernetes.io/service-name=reliability-api"),
        }
        (self.run_dir / f"{phase}.json").write_text(json.dumps(data, indent=2) + "\n")
        return data

    def traffic(self, pod, count=10):
        # Requests traverse Service DNS + ClusterIP from an existing baseline pod.
        # This is snapshot sampling, not a continuous availability measurement.
        code = f'''import json, urllib.request
samples = []
for _ in range({count}):
    with urllib.request.urlopen("http://reliability-api.reliability-lab.svc.cluster.local:8080/", timeout=3) as response:
        body = json.load(response)
        assert response.status == 200 and body["release"] == "baseline", body
        samples.append({{"http_status": response.status, "release": body["release"]}})
print(json.dumps(samples))'''
        return json.loads(self.kubectl("exec", pod, "--", "python", "-c", code, timeout=60).stdout)

    def execute(self):
        for tool in ("docker", "kubectl", "kind"):
            if not shutil.which(tool):
                raise RuntimeError(f"Missing prerequisite: {tool}")
        self.command(["docker", "info", "--format", "{{.ServerVersion}}"])
        self.summary["kind_version"] = self.command(["kind", "version"]).stdout.strip()
        self.command(["docker", "build", "--tag", self.image, "."], timeout=300)
        self.image_built = True
        # Passing --kubeconfig confines all context writes to this experiment.
        self.created = True  # Also clean partial cluster creation on failure.
        self.command(["kind", "create", "cluster", "--name", self.name, "--kubeconfig", self.kubeconfig, "--image", NODE_IMAGE, "--config", "scripts/kind.yaml", "--wait", "120s"], timeout=240)
        self.command(["docker", "update", "--memory", "2g", "--memory-swap", "2g", "--cpus", "2", self.name + "-control-plane"])
        self.command(["kind", "load", "docker-image", self.image, "--name", self.name], timeout=120)
        self.summary["kubernetes_version"] = json.loads(self.kubectl("version", "-o", "json").stdout)["serverVersion"]["gitVersion"]
        deployment = json.loads((ROOT / "manifests/deployment.json").read_text())
        deployment["spec"]["template"]["spec"]["containers"][0]["image"] = self.image
        rendered = self.run_dir / "deployment.json"
        rendered.write_text(json.dumps(deployment, indent=2) + "\n")
        self.kubectl("apply", "--dry-run=server", "-f", "manifests/namespace.json")
        self.kubectl("apply", "-f", "manifests/namespace.json")
        for source in (rendered, ROOT / "manifests/service.json"):
            self.kubectl("apply", "--dry-run=server", "-f", source)
            self.kubectl("apply", "-f", source)
        self.kubectl("rollout", "status", "deployment/reliability-api", "--timeout=120s", timeout=135)
        baseline = self.snapshot("baseline")
        original_pods = {p["metadata"]["name"] for p in baseline["pods"]["items"]}
        assert len(original_pods) == 2, "Expected two baseline pods"
        client_pod = sorted(original_pods)[0]
        self.summary["phases"].append({"name": "baseline", "ready_replicas": baseline["deployment"]["status"].get("readyReplicas", 0), "samples": self.traffic(client_pod)})
        self.kubectl("set", "env", "deployment/reliability-api", "READY=false", "RELEASE=bad-readiness")
        failed = self.kubectl("rollout", "status", "deployment/reliability-api", "--timeout=90s", timeout=100, check=False)
        assert failed.returncode != 0, "Bad release unexpectedly completed"
        stalled = self.snapshot("stalled")
        bad_pod = validate_stalled(stalled["deployment"], stalled["pods"], stalled["endpointslices"], original_pods)
        probe_code = '''import json, urllib.request, urllib.error
statuses = {}
for path in ("/livez", "/readyz"):
    try:
        response = urllib.request.urlopen("http://127.0.0.1:8080" + path, timeout=3)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        statuses[path] = response.status
assert statuses == {"/livez": 200, "/readyz": 503}, statuses
print(json.dumps(statuses))'''
        probes = json.loads(self.kubectl("exec", bad_pod, "--", "python", "-c", probe_code).stdout)
        self.summary["phases"].append({"name": "stalled", "rollout_exit": failed.returncode, "rollout_output": failed.stdout.strip(), "condition": "ProgressDeadlineExceeded", "available_replicas": 2, "candidate_restarts": 0, "candidate_probe_statuses": probes, "ready_endpoints_unchanged": True, "samples": self.traffic(client_pod)})
        self.kubectl("rollout", "undo", "deployment/reliability-api")
        self.kubectl("rollout", "status", "deployment/reliability-api", "--timeout=120s", timeout=135)
        self.kubectl("wait", "--for=delete", "pod/" + bad_pod, "--timeout=60s", timeout=75)
        recovered = self.snapshot("recovered")
        assert recovered["deployment"]["status"].get("readyReplicas") == 2, "Rollback did not restore two ready replicas"
        assert len(recovered["pods"]["items"]) == 2, "Unexpected pods after rollback"
        self.summary["phases"].append({"name": "recovered", "ready_replicas": 2, "samples": self.traffic(client_pod)})
        self.summary["result"] = "passed"

    def cleanup(self):
        results = []
        if self.created:
            # kind deletion also touches kubeconfig; pass our private file here too.
            results.append(self.command(["kind", "delete", "cluster", "--name", self.name, "--kubeconfig", self.kubeconfig], timeout=120, check=False).returncode)
        if self.image_built:
            results.append(self.command(["docker", "image", "rm", self.image], check=False).returncode)
        return all(result == 0 for result in results)


def cleanup_saved(run_dir):
    path = Path(run_dir).resolve()
    if path.parent != (ROOT / ".lab/runs").resolve():
        raise ValueError("Cleanup accepts only this repository's .lab/runs/<name> directories")
    data = json.loads((path / "metadata.json").read_text())
    name = data["cluster"]
    if not re.fullmatch(r"laniakea-reliability-[a-f0-9]{10}", name) or path.name != name:
        raise ValueError("Invalid lab cluster identity")
    if data["image"] != "laniakea-reliability-api:" + name:
        raise ValueError("Invalid lab image identity")
    subprocess.run(["kind", "delete", "cluster", "--name", name, "--kubeconfig", str(path / "kubeconfig")], check=True, timeout=120)
    subprocess.run(["docker", "image", "rm", data["image"]], check=True, timeout=60)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="Keep the task cluster/image for manual runbook practice")
    parser.add_argument("--cleanup", metavar="RUN_DIR", help="Delete only the cluster/image recorded in this repository's run directory")
    args = parser.parse_args()
    if args.cleanup:
        cleanup_saved(args.cleanup)
        return 0
    if sys.flags.optimize:
        parser.error("Assertions are required; do not run with -O or PYTHONOPTIMIZE")
    lab = Lab()
    try:
        lab.execute()
    except Exception as error:
        lab.summary["result"] = "failed"
        lab.summary["error"] = str(error).replace(str(lab.run_dir), "$RUN_DIR").replace(str(ROOT), "$REPO")
        print(str(error), file=sys.stderr)
        if lab.created:
            try:
                lab.kubectl("get", "pods", "-o", "wide", check=False, timeout=15)
                lab.kubectl("get", "events", "--sort-by=.metadata.creationTimestamp", check=False, timeout=15)
            except Exception:
                pass
    finally:
        try:
            lab.summary["cleanup"] = "kept" if args.keep else ("complete" if lab.cleanup() else "failed")
        except Exception as error:
            lab.summary["cleanup"] = "failed"
            lab.summary["cleanup_error"] = str(error).replace(str(lab.run_dir), "$RUN_DIR").replace(str(ROOT), "$REPO")
        lab.summary["user_kubeconfig_unchanged"] = kubeconfig_fingerprints() == lab.original_config
        if not lab.summary["user_kubeconfig_unchanged"] or lab.summary["cleanup"] == "failed":
            lab.summary["result"] = "failed"
        lab.summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        (lab.run_dir / "summary.json").write_text(json.dumps(lab.summary, indent=2) + "\n")
        print(json.dumps(lab.summary, indent=2))
        print(f"Evidence: {lab.run_dir}")
    return 0 if lab.summary["result"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
