# Rehearse and recover a blocked rollout

Run `python3 scripts/lab.py --keep` first. A successful run has already demonstrated the full sequence and leaves a healthy baseline cluster for manual practice. Set `RUN_DIR` to the exact evidence directory printed at completion, from this repository root:

```bash
RUN_DIR=.lab/runs/laniakea-reliability-<run-id>
LAB_NAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["cluster"])' "$RUN_DIR/metadata.json")
LAB_CONTEXT="kind-$LAB_NAME"
k() { kubectl --kubeconfig "$RUN_DIR/kubeconfig" --context "$LAB_CONTEXT" --namespace reliability-lab "$@"; }
k get deployment,pods,service
```

The `k` helper always specifies the lab's kubeconfig, context and namespace. Do not substitute a production context. The commands below create only a deliberate failure in this disposable demonstration workload.

## 1. Establish the baseline

```bash
k rollout status deployment/reliability-api --timeout=120s
k get endpointslices -l kubernetes.io/service-name=reliability-api -o yaml
k get pods -l app=reliability-api
```

Confirm two ready pods, available replicas = 2, and two ready Service endpoints. If baseline deployment fails, inspect `k describe pods` and `k get events --sort-by=.metadata.creationTimestamp`. Common causes include Docker resource exhaustion, a mismatched kind/node version, or an image not loaded into this cluster. Recover the baseline before injecting a failure.

## 2. Introduce the readiness regression

```bash
k set env deployment/reliability-api READY=false RELEASE=bad-readiness
k rollout status deployment/reliability-api --timeout=90s
```

The second command must return nonzero. The lab's deployment has a 45-second progress deadline, so normally the output reports that the deployment exceeded that deadline before the client's 90-second timeout. A generic timeout alone is insufficient proof; inspect the condition:

```bash
k get deployment reliability-api -o jsonpath='{.status.conditions}'
k get pods -l app=reliability-api
k get endpointslices -l kubernetes.io/service-name=reliability-api -o yaml
k get events --sort-by=.metadata.creationTimestamp
```

Expected: `Progressing=False`, reason `ProgressDeadlineExceeded`; one unready candidate with zero restarts; two ready baseline pods. Only the original ready endpoints should serve the app. Identify the candidate by its `RELEASE=bad-readiness` environment value when inspecting the pods.

If the candidate restarts, investigate liveness, resource limits and process errors. If it never starts, investigate scheduling and image loading. Those are different failure modes and the automated exercise rejects them as proof of a readiness regression.

## 3. Roll back explicitly

```bash
k rollout history deployment/reliability-api
k rollout undo deployment/reliability-api
k rollout status deployment/reliability-api --timeout=120s
k get pods -l app=reliability-api
k get deployment reliability-api -o jsonpath='{.spec.template.spec.containers[0].env}'
```

Confirm two ready baseline pods, `READY=true`, `RELEASE=baseline`, and eventual deletion of the unready candidate. The automated exercise also sends 10 HTTP requests through the Service after recovery and asserts that each returns the baseline release.

Do not equate a successful rollback command with restored application service. Check ready endpoints and actual application requests. Do not reuse `rollout undo` as a database migration recovery plan: it restores a pod template only.

## 4. Preserve evidence and clean up

The runner saves `summary.json`, phase snapshots and `commands.log` under `RUN_DIR`. These are synthetic lab observations. The directory also contains a **kubeconfig with cluster credentials**: never publish or upload the entire directory. CI uploads only the named diagnostic files and excludes kubeconfig and metadata.

```bash
python3 scripts/lab.py --cleanup "$RUN_DIR"
```

Cleanup accepts only this repository's run directories with a matching lab cluster identity. It deletes the recorded cluster and app image tag. It keeps evidence files for review. The shared base-image cache remains available in Docker; the script never prunes other images, volumes, networks, or clusters.
