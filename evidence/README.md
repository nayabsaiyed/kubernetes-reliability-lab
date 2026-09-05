# Verified local exercise — 2026-09-05

The complete recovery exercise ran successfully on a local ARM64 Docker host from **13:08:22 to 13:10:33 UTC**. This is synthetic lab evidence, not a production incident or service-level measurement.

| Check | Observed result |
|---|---|
| kind / Kubernetes | kind v0.32.0 on darwin/arm64; Kubernetes v1.36.1 |
| Baseline | Two ready replicas, 10/10 Service requests returned HTTP 200 and release `baseline` |
| Failed candidate | `/livez` = 200, `/readyz` = 503, zero container restarts |
| Deployment failure | `rollout status` exit 1; `ProgressDeadlineExceeded` |
| Failure containment | Two available baseline replicas; original two ready EndpointSlice members unchanged; 10/10 Service requests returned baseline HTTP 200 |
| Explicit recovery | `rollout undo` completed, failed candidate deleted, two ready replicas, 10/10 baseline HTTP 200 requests |
| Cleanup | Task-created cluster and app image removed; user kubeconfig file fingerprints unchanged |

The request samples were taken at the baseline, stalled, and recovered phases. They do not establish uninterrupted availability between those points.

## Inspect the evidence

- [Runner summary](2026-09-05-summary.json): timestamps, versions, assertions, request samples, cleanup outcome.
- [Command transcript](2026-09-05-commands.log): command output and exit status, with local task paths replaced by `$REPO` and `$RUN_DIR`.
- [Baseline objects](2026-09-05-baseline.json), [stalled objects](2026-09-05-stalled.json), [recovered objects](2026-09-05-recovered.json): actual Deployment, Pod, and EndpointSlice snapshots from this disposable cluster.

The transcript includes server-side dry-run validation, the intentional nonzero rollout result, rollback, and scoped cleanup. Credentials and kubeconfig were excluded. Synthetic cluster IP addresses and resource IDs remain in the snapshots to preserve the relationships between pods and endpoints.

Reproduce from the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/lab.py
```

Local checks also passed with Python 3.9 for the HTTP/manifest/evidence suite, Python compilation, and actionlint v1.7.12 for the workflow. After the recorded cluster run, only output-path sanitization and handling of cleanup exceptions changed in the runner; the workload and phase assertions stayed the same.

GitHub Actions executes the same exercise on Linux amd64. A workflow file alone does not prove a hosted run passed: inspect [the live Actions results](https://github.com/nayabsaiyed/kubernetes-reliability-lab/actions) after publication. Hosted CI status is separate from the local evidence above.
