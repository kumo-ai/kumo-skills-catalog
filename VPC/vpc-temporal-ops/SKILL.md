---
name: vpc-temporal-ops
metadata:
  version: "1.0.0"
description: Perform operational tasks on Temporal in a BYOC cluster — force Flux reconciliation, check HelmRelease status, watch rolling updates, and inspect pod annotations. Use when the user needs to trigger a Temporal redeploy, check deployment status, or perform Temporal maintenance.
allowed-tools: Bash Read Grep Glob
---

# Temporal Operations

Operational tasks for managing Temporal deployments in a BYOC cluster using Flux GitOps.

## Force Flux Reconciliation

Trigger an immediate reconciliation of the Temporal HelmRelease:

```bash
kubectl annotate helmrelease temporal -n temporal reconcile.fluxcd.io/requestedAt="$(date +%s)" --overwrite
```

## Check HelmRelease Status

```bash
kubectl get helmrelease temporal -n temporal -o jsonpath='{.status.conditions[0].message}' && echo ""
```

For full status:

```bash
kubectl get helmrelease temporal -n temporal -o yaml | grep -A 20 'status:'
```

## Watch Rolling Update

```bash
kubectl get pods -n temporal -w
```

## Check Prometheus Annotations on Pods

```bash
kubectl get pods -n temporal -l app.kubernetes.io/instance=temporal -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.annotations}{"\n"}{end}' | head -20
```

For a specific pod:

```bash
kubectl get pods -n temporal <POD_NAME> -o jsonpath='{.metadata.annotations}' | jq .
```

## Reference

### Helm Values Location

`kumo-sap-byoc/experiments/deployments/temporal/installation/values.yaml`

### Key Helm Configuration Sections

- `server.metrics.annotations.enabled: true` — Enables Prometheus scraping
- `server.metrics.prometheus.timerType: histogram` — Latency metric type
- `prometheus.enabled: true` — Deploys bundled Prometheus
- `server.frontend/history/matching/worker.resources` — Resource configuration

### Temporal Namespaces in This Cluster

- `temporal-system` — Internal Temporal system namespace
- `pandg-test` — Application namespace
