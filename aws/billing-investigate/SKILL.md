---
name: billing-investigate
metadata:
  version: "1.0.0"
description: Investigate AWS cost surges or anomalies on the Kumo SaaS account using the CUR (Cost and Usage Report) in Athena. Use when the user reports a billing spike, month-over-month cost increase, needs a "where is the money going" breakdown, or wants to track cost per customer/nodepool/environment. Read-only — never mutates AWS resources.
allowed-tools: Bash Read Write
---

# AWS Billing Investigation (CUR via Athena)

The Kumo SaaS AWS account (`926922431314`, admin role assumable from the bastion) does **not** grant `ce:GetCostAndUsage` to the admin role. All cost analysis must go through the **Cost and Usage Report (CUR)** that is crawled into an Athena table.

This skill gives you the table layout, the canonical query patterns, and the gotchas so you can go from "the bill is up $X/mo" to "here's exactly which usage types / tenants / nodepools drove it" in under 15 minutes.

## When to use this skill

- "AWS bill surged last month — what happened?"
- "Break down EC2 cost per customer / environment / region"
- "Is this growth organic or a leak?"
- "What did we run on [date]?"
- "How is our Savings Plan coverage trending?"
- Anomaly follow-up from Grafana cost dashboards or the `customer_7day_alert_query` saved query.

Do **not** use this skill for live resource counts (`kubectl get`, EC2 describe). CUR has 1-2 day lag and includes forward-dated RI/SP reservation lines.

## Prerequisites

- AWS CLI authenticated as a role that can run Athena on the `primary` workgroup in `us-west-2`.
- No external setup. The table, workgroup, and result bucket already exist.

## The CUR table

| Item | Value |
|---|---|
| Region | `us-west-2` |
| Database | `athenacurcfn_cost_and_usage_report` |
| Table | `cost_and_usage_report` |
| Workgroup | `primary` (saved queries) or `cost_usage_workgroup` |
| Result bucket | `s3://aws-athena-query-results-926922431314-us-west-2/` |
| Source S3 | `s3://kumo-aws-usage-bucket/kumo/cost-and-usage-report/YYYYMMDD-YYYYMMDD/` |
| Refresh | Daily crawler; 1-2 day lag |

## Key columns

Slicing dimensions you will use constantly:

| Column | Type | Purpose |
|---|---|---|
| `line_item_usage_start_date` | timestamp | **Always partition on this.** |
| `line_item_unblended_cost` | string → `CAST(... AS double)` | The money number. |
| `line_item_line_item_type` | string | `Usage`, `DiscountedUsage`, `SavingsPlanCoveredUsage`, `SavingsPlanNegation`, `Fee`, `Credit`, `EdpDiscount`, `Tax` |
| `line_item_product_code` | string | `AmazonEC2`, `AmazonS3`, `AWSCloudTrail`, `ElasticMapReduce`, marketplace SKUs (cryptic) |
| `line_item_usage_type` | string | e.g. `USW2-BoxUsage:g4dn.16xlarge`, `USW2-NatGateway-Bytes` |
| `line_item_usage_account_id` | string | Main `926922431314`; `103083060647` exists but is cross-account and not queryable here |
| `resource_tags_user_infra_full_name` | string | `prod-uw4`, `staging-uw2`, `dev-uw2`, `testing-uw4` — env tag |
| `resource_tags_user_karpenter_sh_nodepool` | string | `trainer-<customer>`, `graphstore-<customer>`, `trainer-ui-test`, `spark-<customer>` — customer-level attribution for compute |
| `line_item_usage_amount` | double | Instance-hours (for BoxUsage), bytes, requests, depending on usage_type |
| `product_product_name` | string | Human-readable — useful for decoding marketplace SKUs |
| `pricing_term` | string | `OnDemand`, `Spot`, `Reserved` |

## Gotchas before you query

1. **`line_item_unblended_cost` is stored as a string.** Always `CAST(... AS double)`. No exceptions.
2. **`line_item_line_item_type` filter matters.** For "actual consumption" use `IN ('Usage','DiscountedUsage')`. Including `SavingsPlanCoveredUsage` double-counts (there's a matching `SavingsPlanNegation`). Total monthly bill = **sum of all types**.
3. **CUR contains forward-dated rows.** If today is day 15, the current month's partition has rows for days 15–30 already — these are pre-allocated RI/SP reservation fees and distort daily averages. Always verify cutoff before projecting: `SELECT date(line_item_usage_start_date), SUM(...), COUNT(*) ... GROUP BY 1 ORDER BY 1`. Real usage days have line counts ~400k; forward-dated days have ~200.
4. **Marketplace SKUs have cryptic product codes** (e.g. `9i4t6z0fbfyrm1idabwl2wam`). Join or decode via `product_product_name`.
5. **`<untagged>` is not a leak.** It's mostly shared infra (S3, CloudTrail, NAT, VPC endpoints, marketplace subscriptions) that cannot carry karpenter/infra tags. Don't chase it unless it's large *and* you can identify the line items.
6. **Enterprise Support is a derived fee** (~7-10% of monthly spend). It will "grow" whenever usage grows. Separate it before reporting.

## Query recipes

### 1. Monthly totals split by line-item type (always run first)

```sql
SELECT
  date_format(line_item_usage_start_date, '%Y-%m') AS month,
  ROUND(SUM(CAST(line_item_unblended_cost AS double)), 2) AS total_cost,
  ROUND(SUM(CASE WHEN line_item_line_item_type = 'Usage' THEN CAST(line_item_unblended_cost AS double) ELSE 0 END), 2) AS usage_cost,
  ROUND(SUM(CASE WHEN line_item_line_item_type = 'DiscountedUsage' THEN CAST(line_item_unblended_cost AS double) ELSE 0 END), 2) AS discounted_usage,
  ROUND(SUM(CASE WHEN line_item_line_item_type = 'Credit' THEN CAST(line_item_unblended_cost AS double) ELSE 0 END), 2) AS credits,
  ROUND(SUM(CASE WHEN line_item_line_item_type = 'Fee' THEN CAST(line_item_unblended_cost AS double) ELSE 0 END), 2) AS fees
FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
WHERE line_item_usage_start_date >= TIMESTAMP '2026-01-01 00:00:00'
  AND line_item_usage_start_date <  TIMESTAMP '2026-05-01 00:00:00'
GROUP BY 1 ORDER BY 1;
```

### 2. Verify CUR data cutoff for the current month

```sql
SELECT
  date(line_item_usage_start_date) AS day,
  ROUND(SUM(CAST(line_item_unblended_cost AS double)), 2) AS daily_cost,
  COUNT(*) AS line_count
FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
WHERE line_item_usage_start_date >= TIMESTAMP '2026-04-01 00:00:00'
  AND line_item_usage_start_date <  TIMESTAMP '2026-05-01 00:00:00'
GROUP BY 1 ORDER BY 1;
```

Days with `line_count` ~400k are real usage. Drops to <5k = forward-dated reservation/fee rows only.

### 3. Service breakdown month-over-month (find the driver service)

```sql
SELECT
  date_format(line_item_usage_start_date, '%Y-%m') AS month,
  line_item_product_code AS service,
  ROUND(SUM(CAST(line_item_unblended_cost AS double)), 2) AS cost
FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
WHERE line_item_usage_start_date >= TIMESTAMP '2026-01-01 00:00:00'
  AND line_item_usage_start_date <  DATE '2026-04-16'  -- cutoff from step 2
  AND line_item_line_item_type IN ('Usage','DiscountedUsage')
GROUP BY 1, 2 ORDER BY 1, 3 DESC;
```

### 4. Delta query: top contributors to a month-over-month surge

```sql
WITH t AS (
  SELECT
    date_format(line_item_usage_start_date, '%Y-%m') AS m,
    line_item_product_code AS svc,
    line_item_usage_type AS utype,
    COALESCE(NULLIF(resource_tags_user_infra_full_name,''), '<untagged>') AS infra,
    CAST(line_item_unblended_cost AS double) AS c
  FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
  WHERE line_item_usage_start_date >= TIMESTAMP '2026-02-01 00:00:00'
    AND line_item_usage_start_date <  TIMESTAMP '2026-04-01 00:00:00'
    AND line_item_line_item_type IN ('Usage','DiscountedUsage')
)
SELECT svc, utype, infra,
  ROUND(SUM(CASE WHEN m='2026-02' THEN c ELSE 0 END), 2) AS feb,
  ROUND(SUM(CASE WHEN m='2026-03' THEN c ELSE 0 END), 2) AS mar,
  ROUND(SUM(CASE WHEN m='2026-03' THEN c ELSE 0 END)
      - SUM(CASE WHEN m='2026-02' THEN c ELSE 0 END), 2) AS delta
FROM t GROUP BY svc, utype, infra
HAVING (SUM(CASE WHEN m='2026-03' THEN c ELSE 0 END)
      - SUM(CASE WHEN m='2026-02' THEN c ELSE 0 END)) > 1500
ORDER BY delta DESC LIMIT 40;
```

This is the single most useful query. It ranks `(service, usage_type, environment)` triples by the raw dollar increase — the drivers sit at the top.

### 5. Customer/nodepool attribution for EC2

```sql
SELECT
  date_format(line_item_usage_start_date, '%Y-%m') AS m,
  COALESCE(NULLIF(resource_tags_user_karpenter_sh_nodepool,''), '<no-np>') AS nodepool,
  line_item_usage_type,
  ROUND(SUM(CAST(line_item_unblended_cost AS double)), 2) AS cost,
  ROUND(SUM(line_item_usage_amount), 0) AS instance_hours
FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
WHERE line_item_usage_start_date >= TIMESTAMP '2026-01-01 00:00:00'
  AND line_item_product_code = 'AmazonEC2'
  AND line_item_line_item_type IN ('Usage','DiscountedUsage')
  AND line_item_usage_type LIKE '%BoxUsage:g4dn.16xlarge%'  -- narrow to the problem SKU
GROUP BY 1, 2, 3
HAVING SUM(CAST(line_item_unblended_cost AS double)) > 500
ORDER BY 1, 4 DESC;
```

Customer ID is in the nodepool name: `trainer-doordash`, `graphstore-tubi`, `spark-reddit`. Nodepools that don't map to a customer: `trainer`, `trainer-ui-test`, `dataworkflow`, `default` (shared or internal).

### 6. Savings Plan / Reservation coverage trend

```sql
SELECT
  date_format(line_item_usage_start_date, '%Y-%m') AS month,
  line_item_line_item_type AS lit,
  pricing_term AS term,
  ROUND(SUM(CAST(line_item_unblended_cost AS double)), 2) AS cost
FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
WHERE line_item_usage_start_date >= TIMESTAMP '2026-01-01 00:00:00'
  AND line_item_product_code = 'AmazonEC2'
GROUP BY 1, 2, 3 ORDER BY 1, 4 DESC;
```

Coverage = `SavingsPlanCoveredUsage / (SavingsPlanCoveredUsage + Usage[term=OnDemand])`. A drop over time = usage grew but SP commit stayed flat → headroom workload is paying full on-demand.

### 7. Identify a specific date spike

```sql
SELECT line_item_product_code AS svc,
       line_item_usage_type AS utype,
       COALESCE(NULLIF(resource_tags_user_infra_full_name,''), '<untagged>') AS infra,
       COALESCE(NULLIF(resource_tags_user_karpenter_sh_nodepool,''), '<no-np>') AS nodepool,
       ROUND(SUM(CAST(line_item_unblended_cost AS double)), 2) AS cost
FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
WHERE date(line_item_usage_start_date) = DATE '2026-04-14'
  AND line_item_line_item_type IN ('Usage','DiscountedUsage','Fee')
GROUP BY 1, 2, 3, 4
HAVING SUM(CAST(line_item_unblended_cost AS double)) > 500
ORDER BY cost DESC LIMIT 30;
```

If the top line is a Marketplace product code you don't recognize, look it up:

```sql
SELECT product_product_name, line_item_line_item_description
FROM athenacurcfn_cost_and_usage_report.cost_and_usage_report
WHERE line_item_product_code = '<cryptic_code>' LIMIT 5;
```

### 8. Saved queries already in the workgroup

Reusable templates (workgroup `primary`):

- `customer_7day_alert_query` — 7-day rolling z-score anomaly per `(customer, infra)`
- `customer_7day_withstats` — same with full baseline stats
- `customer_7day_totalsforperjob` — Grafana-friendly time series
- `allproducts_7day_ratioquery` — service-level ratio check across all AWS products
- `Billanomalydeepdive` — product drill-down (edit `LIKE '%EKS%'` to the service of interest)

List them:

```bash
aws athena list-named-queries --work-group primary --region us-west-2
aws athena batch-get-named-query --work-group primary --region us-west-2 \
  --named-query-ids <id1> <id2>
```

## Investigation runbook

1. **Step 0 — memory check.** If you previously wrote `aws_billing_analysis.md` in project memory, it has the same table/workgroup pointers. Refresh if stale.
2. **Bound the problem.** Monthly totals (recipe 1) for the affected period + at least one baseline month.
3. **Verify CUR cutoff** (recipe 2). Forward-dated rows will mislead any "current month" number.
4. **Find the service** (recipe 3). Usually one service (EC2, S3, CloudTrail, or EMR) owns ≥70% of the delta.
5. **Rank the deltas** (recipe 4). Top 10 rows typically explain 80% of the surge.
6. **Attribute to customer/env** (recipe 5). Karpenter nodepool tag is the primary customer-level dimension.
7. **Check SP coverage** (recipe 6). Coverage dropping while usage grows = commit needs resizing. Independent of the delta analysis — can be a silent amplifier.
8. **One-day spikes** (recipe 7). Often an annual Marketplace payment, an EDP credit, or a backfilled line — rule out before chasing.
9. **Write it up.** Separate *organic* (customer ramp) from *actionable* (leaks, untuned SP, runaway internal pools). Dollar-quantify each recommendation.
10. **Read-only boundary.** Do **not** delete resources, modify SP commits, or stop instances. Report findings; let the user decide.

## Query-runner helper

Athena's `get-query-results` paginates and returns JSON — inconvenient for CSV. Use this wrapper (drop into `/tmp/runq.sh`):

```bash
#!/bin/bash
SQL="$1"
QID=$(aws athena start-query-execution \
  --region us-west-2 --work-group primary \
  --query-string "$SQL" \
  --query-execution-context Database=athenacurcfn_cost_and_usage_report \
  --result-configuration OutputLocation=s3://aws-athena-query-results-926922431314-us-west-2/ \
  --output text --query QueryExecutionId)
echo "QID=$QID" >&2
while true; do
  S=$(aws athena get-query-execution --region us-west-2 --query-execution-id "$QID" \
        --output text --query 'QueryExecution.Status.State')
  [ "$S" = "SUCCEEDED" ] && break
  if [ "$S" = "FAILED" ] || [ "$S" = "CANCELLED" ]; then
    aws athena get-query-execution --region us-west-2 --query-execution-id "$QID" \
      --output text --query 'QueryExecution.Status.StateChangeReason' >&2
    exit 1
  fi
  sleep 2
done
LOC=$(aws athena get-query-execution --region us-west-2 --query-execution-id "$QID" \
      --output text --query 'QueryExecution.ResultConfiguration.OutputLocation')
aws s3 cp "$LOC" - 2>/dev/null
```

Usage: `./runq.sh "SELECT ..." | column -t -s ','`

## Common pitfalls to avoid

- **Don't use Cost Explorer API.** `ce:GetCostAndUsage` is denied for the admin role on this account. Always go through the CUR.
- **Don't forget to cast cost to double.** It's a string. Silent wrong-shape errors otherwise.
- **Don't project the current month from the full partition.** Use the `date(line_item_usage_start_date)` cutoff from recipe 2.
- **Don't file customer names or account IDs in public repos.** `kumo-ai/kumo` is internal; other repos may not be.
- **Don't declare "$X is growing" from a single month.** Always include a baseline — ideally 2+ months before.
- **Don't touch resources.** This is a reporting skill. Write findings, not `aws ec2 stop-instances`.

## Related memory / artifacts

- Project memory: `aws_billing_analysis.md` (table/workgroup/result-bucket reference).
- Grafana cost dashboards live in the `grafana` Athena workgroup — a separate set of queries feeds them.
- The `customer_7day_alert_query` saved query is the cron basis for cost alerts; extend it rather than inventing a parallel one.
