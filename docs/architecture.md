# Architecture and decisions

The buyer problem is operational ambiguity during a failed deployment: is the process dead, still initializing, or alive but unable to serve? The lab gives each condition an observable signal and verifies a limited recovery path.

## Components

| Component | Responsibility |
|---|---|
| `app/server.py` | Serve a tiny JSON response and three health endpoints |
| `manifests/deployment.json` | Pod security, probes, resources, and rolling update policy |
| `manifests/service.json` | Route ClusterIP traffic to ready workload endpoints |
| `scripts/lab.py` | Own the local cluster, assert phase transitions, collect evidence, clean up |
| `tests/` | Exercise real HTTP behavior and check important rollout/security/evidence contracts |
| `.github/workflows/ci.yml` | Validate changes and rehearse the same local recovery path on a hosted runner |

## Health model

`/livez` only confirms the process can respond. `/startupz` checks whether the configured initialization interval has elapsed. `/readyz` requires initialization and `READY=true`. The root endpoint follows the same readiness decision. Setting `READY=false` therefore models a deployment configuration error without causing a restart loop.

A startup probe is illustrative here: initialization is a two-second timer, not application migrations or dependency setup. The signal handler marks the app unready and asks the HTTP server to stop on SIGTERM. That is a bounded shutdown behavior, not a demonstrated end-to-end traffic-draining guarantee.

## Why plain manifests and kind

Plain manifests expose the operational controls with little indirection. Helm adds packaging features this one-workload lab does not need. A managed cloud cluster would add account setup, expenditure, and infrastructure cleanup unrelated to the rollout behavior. kind provides a real local Kubernetes API, Deployment controller, kubelet probes, and Service routing.

The node image matches kind 0.32.0 and Kubernetes 1.36.1 and is pinned by digest. The lab app image is built locally and loaded into that cluster. `imagePullPolicy: Never` intentionally prevents a similarly named remote image from being fetched. A real release system would publish, scan, and deploy an immutable application image digest.

## Isolation and limits

Every invocation generates its own cluster name, image tag, kubeconfig, and evidence directory. All cluster commands specify that context. No command switches the user's current context or applies to an existing cluster. There are no host port mappings for the app or cloud resources.

The API listens on host loopback. App traffic samples originate in an existing baseline pod and traverse the Service ClusterIP. This proves that the Service serves the expected release at those sampling points. It does not measure ingress, external load balancers, or uninterrupted traffic during the entire rollout.

All pods run on one node. Two app replicas protect this exercise from an unready candidate, not from loss of that node. The deliberately short 45-second deadline must be tuned to real image pulls and startup behavior before reuse.
