---
name: vpc-temporal-workflow-query
metadata:
  version: "1.0.0"
description: Query and analyze Temporal workflows in a BYOC cluster — find timed-out, failed, running, or completed workflows, group by type/queue/date, and inspect workflow history. Use when the user asks about workflow statuses, wants to find problematic workflows, or needs workflow execution analytics.
allowed-tools: Bash Read Grep Glob
---

# Temporal Workflow Query

Query the Temporal Web API from within the cluster to find and analyze workflows.

All commands exec into the Prometheus pod (which has `wget` and network access to `temporal-web:8080`).

## Querying Workflows by Status

### List All Namespaces

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces" | jq '.namespaces[].namespaceInfo.name'
```

### Query by Execution Status

Replace `<NAMESPACE>` with the Temporal namespace and `<STATUS>` with one of the statuses below:

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'<STATUS>'" | jq '.executions'
```

| Status | Description |
|--------|-------------|
| Running | Currently executing |
| Completed | Finished successfully |
| Failed | Failed with an error |
| Canceled | Canceled by request |
| Terminated | Forcefully terminated |
| TimedOut | Exceeded timeout |
| ContinuedAsNew | Continued as new execution |

## Workflow Analysis

### Count Workflows by Status

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'<STATUS>'" | jq '[.executions[]] | length'
```

### Group by Workflow Type

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | .type.name] | group_by(.) | map({workflowType: .[0], count: length}) | sort_by(-.count)'
```

### Group by Task Queue

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | .taskQueue] | group_by(.) | map({taskQueue: .[0], count: length}) | sort_by(-.count)'
```

### Group by Date

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | {date: (.startTime | split("T")[0])}] | group_by(.date) | map({date: .[0].date, count: length}) | sort_by(.date) | reverse'
```

### Get Workflow Details Summary

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'<STATUS>'" | \
  jq '[.executions[] | {workflowId: .execution.workflowId, workflowType: .type.name, startTime: .startTime, closeTime: .closeTime, duration: .executionDuration, taskQueue: .taskQueue}]'
```

### Get Single Workflow History

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows/<WORKFLOW_ID>/runs/<RUN_ID>/history" | jq '.history.events'
```

## Advanced Query Filters

Temporal supports SQL-like queries. URL-encode the query parameter.

### By Workflow Type

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=WorkflowType%3D'<WORKFLOW_TYPE>'" | jq '.executions'
```

### By Time Range

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=StartTime%3E'<ISO_TIMESTAMP>'" | jq '.executions'
```

### Combined (Status + Type)

```bash
kubectl exec -n temporal deployment/temporal-prometheus-server -c prometheus-server -- \
  wget -qO- "http://temporal-web:8080/api/v1/namespaces/<NAMESPACE>/workflows?query=ExecutionStatus%3D'<STATUS>'%20AND%20WorkflowType%3D'<WORKFLOW_TYPE>'" | jq '.executions'
```

## Report Template

When reporting workflow query results, use this structure:

```
## Workflow Report

### Summary
- Total workflows: X
- Namespace: <namespace>
- Time range: <start> to <end>

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

## Important Task Queues

- `MLJobBackend-task-queue-demo`
- `DataSnapshotApiDriver-task-queue-demo`
- `ConnectorApiDriver-task-queue-demo`
- `PQueryApiDriver-task-queue-demo`
- `MLJobOutputStore-task-queue-demo`
- `MLJobQueueManager-task-queue-demo`
- `GraphDriver-task-queue-demo`
