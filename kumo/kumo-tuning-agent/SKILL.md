---
name: kumo-tuning-agent
metadata:
  version: "1.0.1"
description: Use when a coding agent needs to tune and run an end-to-end Kumo workflow with the Kumo SDK, including data connection, graph creation, predictive query validation, training, model-plan iteration, prediction, and reporting concrete outputs.
allowed-tools: Bash Read Write Edit Grep Glob Agent WebFetch
---

# Kumo Tuning Agent

Use this skill when the user wants an agent to execute a complete Kumo workflow with the `kumoai` SDK and iterate on model quality.

## Required Inputs

- Kumo endpoint and authentication method
- Data source location and connector type
- Table names or paths
- ML task description: entity, target, time horizon, and success metric if available

## Workflow

1. Initialize `kumoai` with the provided endpoint and credentials.
2. Connect to the source data.
3. Inspect every relevant source table before making assumptions.
4. Define tables and confirm primary keys, foreign keys, and time columns.
5. Build a graph and validate it.
6. Write a predictive query and validate it.
7. Generate a training table and immediately print the Kumo UI tracking URL.
8. Suggest a model plan, run training, and immediately print the Kumo UI tracking URL.
9. Generate a prediction table, run predictions, and immediately print the Kumo UI tracking URL for the prediction job.
10. Report metrics, output locations, sample rows, assumptions, and commands run.

## End-To-End Pattern

```python
import kumoai

kumoai.init(url="https://...", api_key="your-api-key")

connector = kumoai.S3Connector("s3://bucket/data/")

source_table = connector["customers"]
print(source_table.column_dict)

customer = kumoai.Table.from_source_table(
    source_table=connector["customers"],
    primary_key="customer_id",
).infer_metadata()
customer.validate()

graph = kumoai.Graph(
    tables={"customer": customer},
    edges=[],
)
graph.validate()

pquery = kumoai.PredictiveQuery(
    graph=graph,
    query="PREDICT SUM(orders.amount, 0, 30, days) FOR EACH customers.customer_id",
)
pquery.validate(verbose=True)

plan = pquery.suggest_training_table_plan(run_mode=RunMode.FAST)
train_table_job = pquery.generate_training_table(plan, non_blocking=True)
print(f"Training table job URL: {train_table_job.status().tracking_url}")
train_table = train_table_job.attach()

model_plan = pquery.suggest_model_plan(run_mode=RunMode.FAST)
trainer = kumoai.Trainer(model_plan)
training_job = trainer.fit(graph, train_table, non_blocking=True)
print(f"Training job URL: {training_job.tracking_url}")
result = training_job.attach()

pred_plan = PredictionTableGenerationPlan()
pred_table = pquery.generate_prediction_table(pred_plan)

prediction_job = trainer.predict(
    graph=graph,
    prediction_table=pred_table,
    output_config=OutputConfig(
        output_types={"predictions"},
        output_connector=connector,
        output_table_name="predictions",
    ),
    non_blocking=True,
)
print(f"Prediction job URL: {prediction_job.tracking_url}")
predictions = prediction_job.attach()
```

## Hard Rules

- Never invent columns, keys, timestamps, or relationships.
- Always inspect schemas first with `column_dict`, table metadata, or sample rows.
- Do not build a graph until PK and FK columns are confirmed.
- Always run `table.validate()`, `graph.validate()`, and `pquery.validate(verbose=True)`.
- When starting training table generation, print `train_table_job.status().tracking_url` before attaching so the user can follow it in the UI.
- When starting training, print `training_job.tracking_url` before attaching so the user can follow it in the UI.
- When starting batch prediction, print `prediction_job.tracking_url` before attaching so the user can follow it in the UI.
- Do not claim success unless both training and prediction completed and you can show metrics and sample outputs.
- If a critical relationship or timestamp is ambiguous, ask only for the minimum missing clarification.

## Job Tracking URLs

Verified against the installed `kumoai` SDK surface:

- Training table generation job: `train_table_job.status().tracking_url`
- Training job: `training_job.tracking_url`
- Batch prediction job: `prediction_job.tracking_url`

Print those URLs to the user immediately after job creation and before calling
`.attach()` or waiting on the result.

## SDK Initialization

Supported initialization patterns:

```python
import kumoai

kumoai.init(url="https://your-deployment.kumoai.cloud/api", api_key="your-api-key")
```

```python
import kumoai

# KUMO_API_KEY and KUMO_API_ENDPOINT set in the environment
```

```python
kumoai.init(
    url="https://...",
    snowflake_credentials={"user": "...", "password": "...", "account": "..."},
)
```

```python
kumoai.init(snowflake_application="MY_APP")
```

The SDK initializes a global singleton once per Python session. Avoid reinitializing it repeatedly in the same process.

## Connectors

Supported connectors in this workflow:

- `kumoai.S3Connector(root_dir="s3://...")`
- `kumoai.SnowflakeConnector(...)`
- `kumoai.DatabricksConnector(...)`
- `kumoai.BigQueryConnector(...)`
- `kumoai.FileUploadConnector(...)`
- `kumoai.GlueConnector(...)`

Inspection pattern:

```python
connector = kumoai.S3Connector("s3://my-bucket/data/")
print(connector.table_names())
source = connector["customers"]
print(source.column_dict)
```

`SourceTable` is lazy. Inspect `column_dict` before defining tables.

## Table Rules

- Prefer `Table.from_source_table(...).infer_metadata()`.
- Always validate each table after inference or manual edits.
- Every primary key must be a real ID column with a supported dtype.
- Any foreign key used in graph edges must also have a compatible dtype.
- If PK or FK columns were inferred as unsupported types, cast them to strings in the source data before continuing.
- If a `time_column` is set automatically, verify that it is actually a timestamp column.
- `table.primary_key` returns a `Column` object. Use `table.primary_key.name` when the query needs the string name.

Useful methods:

```python
table.infer_metadata()
table.validate()
table.metadata
table.print_definition()
table.get_stats(wait_for="minimal")
table.snapshot()
```

## Graph Construction

Use explicit edges when possible:

```python
graph = kumoai.Graph(
    tables={
        "customer": customer,
        "product": product,
        "transaction": transaction,
    },
    edges=[
        dict(src_table="transaction", fkey="customer_id", dst_table="customer"),
        dict(src_table="transaction", fkey="product_id", dst_table="product"),
    ],
)

graph.validate(verbose=True)
```

Edge semantics:

- `src_table.fkey` is the foreign key
- it points to the destination table primary key
- graph edges are bidirectional in the platform

Useful graph methods:

```python
graph.validate()
graph.visualize()
graph.get_table_stats()
graph.infer_metadata()
graph.infer_links()
graph.snapshot()
graph.get_edge_stats()
```

Call `graph.snapshot()` before `graph.get_edge_stats()`.

## Predictive Query Language

Base form:

```sql
PREDICT <target>
FOR EACH <entity>
[WHERE <condition>]
[ASSUMING <condition>]
```

Always validate:

```python
pquery = kumoai.PredictiveQuery(graph=graph, query="...")
pquery.validate(verbose=True)
task_type = pquery.get_task_type()
```

Supported target patterns:

- aggregation targets such as `SUM`, `AVG`, `MIN`, `MAX`, and `COUNT`
- direct column prediction for numerical or categorical columns
- binary classification using comparison operators
- ranking tasks such as `PREDICT RANK products.product_id FOR EACH users.user_id`

Examples:

```sql
PREDICT SUM(orders.amount, 0, 30, days) FOR EACH users.user_id
PREDICT COUNT(events.*, 0, 90, days) FOR EACH customers.customer_id
PREDICT users.membership_tier FOR EACH users.user_id
PREDICT COUNT(orders.*, 0, 30, days) > 0 FOR EACH users.user_id
PREDICT RANK products.product_id FOR EACH users.user_id
```

Time-window rules:

- windows are right-exclusive
- valid units include `days`, `hours`, `minutes`, and `months`
- forecasting should use consecutive non-overlapping windows

Examples:

```sql
SUM(orders.amount, 0, 7, days)
SUM(orders.amount, -7, 30, days)
COUNT(orders.*, 0, 7, days)
COUNT(orders.*, 7, 14, days)
```

Filtered aggregations:

```sql
PREDICT COUNT(orders.* WHERE orders.status = 'completed', 0, 30, days)
FOR EACH users.user_id
```

`WHERE` filters the scored entity population. Filters inside an aggregation determine what counts toward the target.

Use `ASSUMING` only for real counterfactual or what-if requests.

## Training And Tuning

Typical training sequence:

```python
plan = pquery.suggest_training_table_plan(run_mode=RunMode.FAST)
train_table_job = pquery.generate_training_table(plan, non_blocking=True)
train_table = train_table_job.attach()

model_plan = pquery.suggest_model_plan(run_mode=RunMode.FAST)
trainer = kumoai.Trainer(model_plan)
training_job = trainer.fit(graph, train_table, non_blocking=True)
result = training_job.attach()

print(result.metrics())
print(result.tracking_url)
```

Tuning loop:

- inspect the suggested model plan and reported metrics
- confirm the tune metric matches the business goal
- iterate on graph design, predictive query scope, and model-plan settings before claiming the workflow is complete
- use the Kumo model-plan and evaluation docs to justify any manual overrides

Typical prediction sequence:

```python
pred_plan = PredictionTableGenerationPlan()
pred_table = pquery.generate_prediction_table(pred_plan)

prediction_job = trainer.predict(
    graph=graph,
    prediction_table=pred_table,
    output_config=OutputConfig(
        output_types={"predictions"},
        output_connector=connector,
        output_table_name="predictions",
    ),
    non_blocking=True,
)
predictions = prediction_job.attach()
print(predictions.predictions_df().head(10))
```

## Validation Checklist

- PK and FK columns have compatible dtypes.
- Time columns are actual timestamp columns, not strings that only look like timestamps.
- The graph contains the entity table required by the predictive query.
- The target and prediction horizon match the user request.
- Prediction outputs are written to a confirmed destination.
- The selected metric and tuning objective match the task.

## Definition Of Done

Return all of the following:

1. Graph construction code
2. Final predictive query
3. Training job identifier and metrics
4. Prediction output location and sample rows
5. Commands run and files changed
6. Assumptions and how to verify them
