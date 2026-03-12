---
name: vpc-ucv-probe-diagnose
metadata:
  version: "1.0.0"
description: Diagnose Databricks Unity Catalog Volumes (UCV) probe results and correlate UCV failures with Temporal workflow timeouts. Use when the user reports Databricks storage issues, UCV probe failures, or wants to correlate workflow timeouts with UCV availability.
allowed-tools: Bash Read Grep Glob
---

# UCV Probe Diagnosis

A CronJob runs every 5 minutes to probe Databricks Unity Catalog Volumes (UCV) health. Use this skill to check probe results and correlate with Temporal workflow timeouts.

**Deployment:** `kumo-sap-byoc/experiments/deployments/ucv-probe/`
**Namespace:** `kumo-dataplane-demo`
**Volume Path:** `/Volumes/loft_test_data/loft_schema/kumo_test/ucv_test`

## Probe Operations

| Operation | Description |
|-----------|-------------|
| `create_directory` | Create test directory |
| `write_small_1kb` | Upload 1KB file |
| `write_medium_100kb` | Upload 100KB file |
| `list_directory` | List directory contents |
| `get_metadata` | Get file metadata |
| `read_small_1kb` | Download and verify 1KB file |
| `read_medium_100kb` | Download and verify 100KB file |
| `delete_small_file` | Delete small file |
| `delete_medium_file` | Delete medium file |
| `delete_directory` | Remove test directory |

## Access HTML Reports

```bash
kubectl port-forward -n kumo-dataplane-demo svc/ucv-probe-reports 8080:80
open http://localhost:8080
```

Reports include:
- `index.html` — List of all reports (last 100)
- `latest.html` — Most recent probe result
- `probe_<timestamp>_<id>.html` — Individual probe reports

## Query UCV Metrics in Prometheus

Metrics are pushed to Temporal's Prometheus pushgateway.

### Overall Probe Success

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=ucv_probe_success' | jq '.data.result[] | {volume_path: .metric.volume_path, success: .value[1]}'
```

### Total Probe Duration

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=ucv_probe_duration_ms' | jq '.data.result[] | {volume_path: .metric.volume_path, duration_ms: .value[1]}'
```

### Per-Operation Latency

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=ucv_probe_operation_latency_ms' | jq '.data.result[] | {operation: .metric.operation, latency_ms: .value[1]}'
```

### Per-Operation Success

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=ucv_probe_operation_success' | jq '.data.result[] | {operation: .metric.operation, success: .value[1]}'
```

### Last Probe Timestamp

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=ucv_probe_last_timestamp' | jq '.data.result[] | {volume_path: .metric.volume_path, timestamp: .value[1]}'
```

## Correlating UCV Failures with Workflow Timeouts

### 1. Get workflow timeout timestamps

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'TimedOut'%20AND%20WorkflowType%3D'RpcWorkflow_DataSnapshotApiDriver'" | jq '[.executions[].startTime] | sort'
```

### 2. Check UCV probe failures around those times

Use HTML reports or Prometheus queries above.

### 3. Look for patterns

- Do timeouts cluster when `ucv_probe_success = 0`?
- Are `write_*` or `read_*` operations showing high latency before timeouts?

## Health Thresholds

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| `ucv_probe_success` | 1 | — | 0 |
| `ucv_probe_duration_ms` | < 5000 | 5000–15000 | > 15000 |
| `write_medium_100kb` latency | < 1000ms | 1000–5000ms | > 5000ms |
| `read_medium_100kb` latency | < 1000ms | 1000–5000ms | > 5000ms |

## Manual Probe Trigger

```bash
kubectl create job --from=cronjob/ucv-probe ucv-probe-manual -n kumo-dataplane-demo
kubectl logs -n kumo-dataplane-demo -l job-name=ucv-probe-manual -f
```

## Cleanup Old Manual Jobs

```bash
kubectl delete jobs -n kumo-dataplane-demo -l job-name=ucv-probe-manual
```
