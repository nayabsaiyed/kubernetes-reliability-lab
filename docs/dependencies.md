# Dependency provenance

Pins were checked against upstream publisher repositories and release endpoints on 2026-09-05. Pins improve reproducibility; they are not a claim that an image or action has no vulnerabilities. Review updates and rerun the exercise regularly.

| Dependency | Pin | Publisher source |
|---|---|---|
| Python base image | `python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285` | [Docker Official Python image](https://hub.docker.com/_/python), verified using `docker buildx imagetools inspect python:3.13-slim` |
| kind | v0.32.0; Linux amd64 SHA256 `50030de23cf40a18505f20426f6a8506bedf13c6e509244bd1fa9463721b0f54` | [Release](https://github.com/kubernetes-sigs/kind/releases/tag/v0.32.0), [checksum](https://github.com/kubernetes-sigs/kind/releases/download/v0.32.0/kind-linux-amd64.sha256sum) |
| kind node | `v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5` | [kind v0.32.0 release image list](https://github.com/kubernetes-sigs/kind/releases/tag/v0.32.0) |
| kubectl | v1.36.1; Linux amd64 SHA256 `629d3f410e09bf49b64ae7079f7f0bda1191efed311f7d37fdbab0ad5b0ec2b7` | [Official checksum](https://dl.k8s.io/release/v1.36.1/bin/linux/amd64/kubectl.sha256) |
| actions/checkout | v5.0.0 → `08c6903cd8c0fde910a37f88322edcfb5dd907a8` | [Publisher tag](https://github.com/actions/checkout/tree/v5.0.0) |
| actions/setup-python | v5.6.0 → `a26af69be951a213d495a4c3e4e4022e16d87065` | [Publisher tag](https://github.com/actions/setup-python/tree/v5.6.0) |
| actions/upload-artifact | v4.6.2 → `ea165f8d65b6e75b540449e92b4886f43607fa02` | [Publisher tag](https://github.com/actions/upload-artifact/tree/v4.6.2) |

Action SHAs were resolved with `git ls-remote` against their official repositories. Tool checksums are embedded in CI so a changed binary fails validation. The workflow uses `contents: read`, disables checkout credential persistence, and runs on ordinary `pull_request` events with no deployment secrets. It does not use `pull_request_target`.

For local setup, follow [kind's installation guide](https://kind.sigs.k8s.io/docs/user/quick-start/) and [kubectl's installation guide](https://kubernetes.io/docs/tasks/tools/). Use the binary for your own OS and CPU; the checksums above are specifically Linux amd64 for CI.
