---
name: vpc-temporal-doctor
metadata:
  version: "1.0.0"
description: Diagnose Temporal health in a BYOC cluster — query workflows by status, analyze timeouts and failures, check resource utilization, and surface performance problems. Use when the user reports workflow timeouts, failures, latency, pod restarts, or asks about Temporal cluster health.
allowed-tools: Bash Read Grep Glob
---

# Temporal Doctor

Diagnose Temporal cluster health by querying workflows, checking resource utilization, and analyzing Prometheus metrics.

All Prometheus and Temporal Web API commands exec into the Prometheus pod:

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "<URL>" | jq '<FILTER>'
```

---

## 1. Workflow Queries

### List Temporal Namespaces

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces" | jq '.namespaces[].namespaceInfo.name'
```

### Query by Execution Status

Replace `<NS>` with the namespace and `<STATUS>` with one of: `Running`, `Completed`, `Failed`, `Canceled`, `Terminated`, `TimedOut`, `ContinuedAsNew`.

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NS>/workflows?query=ExecutionStatus%3D'<STATUS>'" | jq '.executions'
```

### Count by Status

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NS>/workflows?query=ExecutionStatus%3D'<STATUS>'" | jq '[.executions[]] | length'
```

### Group by Workflow Type

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NS>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | .type.name] | group_by(.) | map({workflowType: .[0], count: length}) | sort_by(-.count)'
```

### Group by Task Queue

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NS>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | .taskQueue] | group_by(.) | map({taskQueue: .[0], count: length}) | sort_by(-.count)'
```

### Group by Date

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NS>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | {date: (.startTime | split("T")[0])}] | group_by(.date) | map({date: .[0].date, count: length}) | sort_by(.date) | reverse'
```

### Workflow Details Summary

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NS>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | {workflowId: .execution.workflowId, workflowType: .type.name, startTime: .startTime, closeTime: .closeTime, duration: .executionDuration, taskQueue: .taskQueue}]'
```

### Single Workflow History

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NS>/workflows/<WORKFLOW_ID>/runs/<RUN_ID>/history" | jq '.history.events'
```

### Advanced Filters

Temporal supports SQL-like queries. URL-encode the `query` parameter.

```bash
# By workflow type
...query=WorkflowType%3D'<TYPE>'

# By time range
...query=StartTime%3E'<ISO_TIMESTAMP>'

# Combined (status + type)
...query=ExecutionStatus%3D'<STATUS>'%20AND%20WorkflowType%3D'<TYPE>'
```

---

## 2. Cluster Health

### Verify Pods

```bash
kubectl get pods -n temporal | grep -E "(prometheus|temporal-frontend|temporal-history|temporal-matching|temporal-worker)"
```

### Resource Usage (Actual)

```bash
kubectl top pods -n temporal --no-headers | grep -E "(frontend|history|matching|worker)"
```

### Resource Requests and Limits

```bash
kubectl get pods -n temporal -o custom-columns='POD:.metadata.name,CPU_REQ:.spec.containers[*].resources.requests.cpu,CPU_LIM:.spec.containers[*].resources.limits.cpu,MEM_REQ:.spec.containers[*].resources.requests.memory,MEM_LIM:.spec.containers[*].resources.limits.memory' | grep -E "(temporal-frontend|temporal-history|temporal-matching|temporal-worker|POD)"
```

### Pod Restarts

```bash
kubectl get pods -n temporal -o custom-columns='POD:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount' | grep -E "(frontend|history|matching|worker)"
```

---

## 3. Prometheus Metrics

### Scrape Targets

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- "http://localhost:9090/api/v1/targets" | jq '[.data.activeTargets[].labels.job] | unique'
```

### List Temporal Metrics

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/label/__name__/values' | jq '.data[]' | grep -i temporal
```

### Request Counts by Operation

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=temporal_request' | jq '.data.result[] | {operation: .metric.operation, namespace: .metric.namespace, requests: .value[1]}'
```

### P99 Latency by Operation

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(temporal_request_latency_bucket[5m]))%20by%20(le,operation))' | jq '.data.result[] | {operation: .metric.operation, p99_latency_sec: .value[1]}'
```

### Active Pollers

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=temporal_num_pollers' | jq '.data.result[] | {task_queue: .metric.task_queue, pollers: .value[1]}'
```

### Schedule-to-Start Latency (Backlog Indicator)

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(temporal_activity_schedule_to_start_latency_bucket[5m]))%20by%20(le))' | jq '.data.result'
```

---

## 4. Critical Health Queries

### Workflow Task Failures

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(temporal_request_failure{operation="RespondWorkflowTaskCompleted"}[5m]))' | jq '.data.result'
```

- **Healthy:** 0 or very low
- **Unhealthy:** Rising rate — history service cannot process workflow tasks

### History Persistence Latency

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(persistence_latency_bucket{service_name="history"}[5m]))%20by%20(le))' | jq '.data.result'
```

- **Healthy:** P99 < 100ms | **Warning:** 100–500ms | **Critical:** > 500ms

### Workflow Task Timeouts

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(temporal_workflow_task_timeout_total[5m]))' | jq '.data.result'
```

- **Healthy:** 0 | **Unhealthy:** Any non-zero value

### History Memory Utilization

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=container_memory_working_set_bytes{namespace="temporal",container="temporal-history"}/container_spec_memory_limit_bytes{namespace="temporal",container="temporal-history"}' | jq '.data.result[] | {pod: .metric.pod, memory_utilization_pct: (.value[1] | tonumber * 100 | floor)}'
```

- **Healthy:** < 70% | **Warning:** 70–85% | **Critical:** > 85% (OOM risk)

### Shard Movement (Pod Instability)

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(shard_controller_acquire_shards_total[5m]))' | jq '.data.result'
```

- **Healthy:** Low/zero | **Unhealthy:** High rate — shards rebalancing

---

## 5. Diagnostic Thresholds

### Resource Utilization

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| CPU actual vs request | 20–80% | <20% or >80% | >100% (throttling) |
| Memory actual vs request | 50–80% | <30% or >80% | >90% (OOM risk) |
| Memory actual vs limit | <70% | 70–85% | >85% (OOM imminent) |

### Key Indicators

| Indicator | Healthy | Unhealthy |
|-----------|---------|-----------|
| Pod restarts | 0 | >0 in last 24h |
| Active pollers | >0 per task queue | 0 (workers disconnected) |
| P99 latency | <1s for most ops | >5s |
| Schedule-to-start latency | <100ms | >1s (backlog) |

---

## 6. Service-Specific Guidance

**History** — Most critical. Executes the workflow state machine, maintains state in memory, handles timers and activity dispatch. Memory-intensive. Recommend: request = 70% of typical usage, limit = 150% of request. Watch for memory growth over time.

**Frontend** — Handles all client requests. CPU-bound under high volume. Watch P99 on `StartWorkflowExecution`.

**Matching** — Matches tasks to workers. High schedule-to-start latency = insufficient workers.

**Worker** — Runs internal system workflows. Low resource usage. Watch for restarts.

---

## 7. Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| History pods high memory | History accumulation, high concurrency | Increase memory request to 70–80% of peak |
| High schedule-to-start latency | Insufficient workers | Scale workers or increase concurrency |
| Frontend high latency | DB bottleneck or insufficient replicas | Check PostgreSQL, add frontend replicas |
| Zero pollers | Worker pods crashed or unregistered | Check worker logs, verify task queue names |
| Workflow timeout spike | Memory pressure, DB latency, worker unavailability | Check history memory → persistence latency → worker polling |
| WorkerInfoWorkflow timeouts | Workers unresponsive | Check worker logs, verify network to frontend |

---

## 8. Reference

### Helm Values

`kumo-sap-byoc/experiments/deployments/temporal/installation/values.yaml`

### Key Config Sections

- `server.metrics.annotations.enabled: true` — Prometheus scraping
- `server.metrics.prometheus.timerType: histogram` — Latency metric type
- `prometheus.enabled: true` — Bundled Prometheus
- `server.{frontend,history,matching,worker}.resources` — Resource configuration

### Temporal Namespaces

- `temporal-system` — Internal system namespace
- `pandg-test` — Application namespace

### Task Queues

- `MLJobBackend-task-queue-demo`
- `DataSnapshotApiDriver-task-queue-demo`
- `ConnectorApiDriver-task-queue-demo`
- `PQueryApiDriver-task-queue-demo`
- `MLJobOutputStore-task-queue-demo`
- `MLJobQueueManager-task-queue-demo`
- `GraphDriver-task-queue-demo`

---

## Report Templates

### Health Report

```
## Temporal Health Report

### Pod Status
[Table of pod status]

### Resource Utilization
| Service | CPU (Actual/Req/Lim) | Memory (Actual/Req/Lim) | Assessment |
|---------|----------------------|-------------------------|------------|

### Health Metrics
| Metric | Value | Status |
|--------|-------|--------|

### Recommendations
1. [Priority recommendations]
```

### Workflow Report

```
## Workflow Report

### Summary
- Total workflows: X
- Namespace: <namespace>
- Status filter: <status>

### By Workflow Type
| Workflow Type | Count |
|---------------|-------|

### By Task Queue
| Task Queue | Count |
|------------|-------|

### By Date
| Date | Count |
|------|-------|

### Potential Causes
1. [Analysis based on patterns]

### Recommendations
1. [Actions to address findings]
```
