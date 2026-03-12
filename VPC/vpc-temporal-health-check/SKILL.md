---
name: vpc-temporal-health-check
metadata:
  version: "1.0.0"
description: Monitor Temporal cluster health, resource utilization, and performance metrics in a BYOC environment. Use when the user reports workflow timeouts, latency issues, pod restarts, or asks about Temporal resource usage, memory pressure, or performance degradation.
allowed-tools: Bash Read Grep Glob
---

# Temporal Health Check

Diagnose Temporal cluster health by checking pod status, resource utilization, Prometheus metrics, and known failure patterns.

## Step 1: Verify Pods Are Running

```bash
kubectl get pods -n temporal | grep -E "(prometheus|temporal-frontend|temporal-history|temporal-matching|temporal-worker)"
```

All pods should be `Running` with full `READY` status.

## Step 2: Collect Resource Usage

```bash
kubectl top pods -n temporal --no-headers | grep -E "(frontend|history|matching|worker)"
```

## Step 3: Get Configured Resource Requests and Limits

```bash
kubectl get pods -n temporal -o custom-columns='POD:.metadata.name,CPU_REQ:.spec.containers[*].resources.requests.cpu,CPU_LIM:.spec.containers[*].resources.limits.cpu,MEM_REQ:.spec.containers[*].resources.requests.memory,MEM_LIM:.spec.containers[*].resources.limits.memory' | grep -E "(temporal-frontend|temporal-history|temporal-matching|temporal-worker|POD)"
```

## Step 4: Prometheus Metrics

### Check Scrape Targets

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- "http://localhost:9090/api/v1/targets" | jq '[.data.activeTargets[].labels.job] | unique'
```

### List Available Temporal Metrics

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

### Activity Schedule-to-Start Latency (Backlog Indicator)

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(temporal_activity_schedule_to_start_latency_bucket[5m]))%20by%20(le))' | jq '.data.result'
```

## Step 5: Check Pod Restarts

```bash
kubectl get pods -n temporal -o custom-columns='POD:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount' | grep -E "(frontend|history|matching|worker)"
```

## Step 6: Critical Health Queries

### Workflow Task Failures

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(temporal_request_failure{operation="RespondWorkflowTaskCompleted"}[5m]))' | jq '.data.result'
```

- **Healthy:** 0 or very low
- **Unhealthy:** Rising rate — history service cannot process workflow tasks

### History Service Persistence Latency

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,sum(rate(persistence_latency_bucket{service_name="history"}[5m]))%20by%20(le))' | jq '.data.result'
```

- **Healthy:** P99 < 100ms
- **Warning:** P99 100–500ms (database or memory pressure)
- **Critical:** P99 > 500ms (likely to cause workflow task timeouts)

### Workflow Task Timeouts

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(temporal_workflow_task_timeout_total[5m]))' | jq '.data.result'
```

- **Healthy:** 0
- **Unhealthy:** Any non-zero value

### History Service Memory Utilization

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=container_memory_working_set_bytes{namespace="temporal",container="temporal-history"}/container_spec_memory_limit_bytes{namespace="temporal",container="temporal-history"}' | jq '.data.result[] | {pod: .metric.pod, memory_utilization_pct: (.value[1] | tonumber * 100 | floor)}'
```

- **Healthy:** < 70%
- **Warning:** 70–85%
- **Critical:** > 85% (OOM risk, GC pressure)

### Shard Movement (Pod Instability)

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- wget -qO- 'http://localhost:9090/api/v1/query?query=sum(rate(shard_controller_acquire_shards_total[5m]))' | jq '.data.result'
```

- **Healthy:** Low or zero during steady state
- **Unhealthy:** High rate — history pods are unhealthy, shards rebalancing

## Resource Utilization Assessment

| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| CPU actual vs request | 20–80% | <20% or >80% | >100% (throttling) |
| Memory actual vs request | 50–80% | <30% or >80% | >90% (OOM risk) |
| Memory actual vs limit | <70% | 70–85% | >85% (OOM imminent) |

## Key Health Indicators

| Indicator | Healthy | Unhealthy |
|-----------|---------|-----------|
| Pod restarts | 0 | >0 in last 24h |
| Active pollers | >0 per task queue | 0 (workers disconnected) |
| P99 latency | <1s for most ops | >5s |
| Schedule-to-start latency | <100ms | >1s (backlog) |

## Service-Specific Guidance

**History Service** — Most critical and memory-intensive. Executes workflow state machine, maintains workflow state in memory, handles timer management, activity dispatch, signal/query processing. Recommend: memory request = 70% of typical usage, limit = 150% of request. Watch for memory growth over time.

**Frontend Service** — Handles all client requests, CPU-bound under high volume. Watch for high P99 on StartWorkflowExecution.

**Matching Service** — Matches tasks to workers. Watch for high schedule-to-start latency (insufficient workers).

**Worker Service** — Runs internal system workflows. Typically low resource usage. Watch for restarts.

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| History pods high memory | Workflow history accumulation, high concurrency | Increase memory request to 70–80% of peak |
| High schedule-to-start latency | Insufficient workers | Scale up workers or increase concurrency |
| Frontend high latency | Database bottleneck or insufficient replicas | Check PostgreSQL, add frontend replicas |
| Zero pollers | Worker pods crashed or not registered | Check worker logs, verify task queue names |
| Workflow timeout spike | Memory pressure, DB latency, worker unavailability | Check history memory, persistence latency, worker polling |
| WorkerInfoWorkflow timeouts | Workers unresponsive | Check worker logs, verify network to frontend |

## Report Template

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
1. [Priority recommendations based on findings]
```
