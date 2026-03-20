---
name: kumo-rfm-agent
metadata:
  version: "1.0.0"
description: Use when a coding agent needs to use KumoRFM to translate natural-language prediction requests into valid queries, inspect relational schema, construct or repair the graph, run instant predictions or evaluations, and return concrete outputs.
allowed-tools: Bash Read Write Edit Grep Glob Agent WebFetch
---

# KumoRFM Agent

Use this skill when the user wants an agent to work with `kumoai.experimental.rfm` for zero-training prediction or evaluation over relational data.

Use `kumoai.experimental.rfm` with `kumoai==2.16.1` unless the user explicitly asks for a different version.

## Required Inputs

- RFM environment setup and API access
- Data location: local dataframes, Snowflake tables, or a Semantic View
- Tables in scope for the task
- Natural-language prediction request

## Workflow

1. Initialize RFM and load or connect to the relevant tables.
2. Construct a graph from local data, Snowflake tables, or a Semantic View.
3. Inspect table metadata and links before writing any query.
4. Confirm inferred time columns manually.
5. Repair links manually when inference is wrong or incomplete.
6. Translate the user request into a valid predictive query or `TaskTable` flow.
7. Run prediction or evaluation and return sample output rows.

## Graph Construction

Public graph entry points:

```python
import kumoai.experimental.rfm as rfm

graph = rfm.Graph.from_data(...)
graph = rfm.Graph.from_snowflake(...)
graph = rfm.Graph.from_snowflake_semantic_view(...)
model = rfm.KumoRFM(graph)
```

Local pandas data:

```python
graph = rfm.Graph.from_data({
    "users": users_df,
    "orders": orders_df,
    "items": items_df,
})
```

Snowflake without a Semantic View:

```python
graph = rfm.Graph.from_snowflake(
    connection=connection,
    database="MY_DATABASE",
    schema="MY_SCHEMA",
    tables=["USERS", "ORDERS", "ITEMS"],
)
```

Manual Snowflake graph pattern:

```python
from kumoai.experimental.rfm.backend.snow import SnowTable

graph = rfm.Graph(
    tables=[
        SnowTable(connection, name="USERS", database="MY_DATABASE", schema="MY_SCHEMA"),
        SnowTable(connection, name="ORDERS", database="MY_DATABASE", schema="MY_SCHEMA"),
    ],
    edges=[],
)
graph.infer_metadata()
graph.infer_links()
```

Semantic View pattern:

```python
graph = rfm.Graph.from_snowflake_semantic_view(
    semantic_view_name="MY_SCHEMA.MY_SEMANTIC_VIEW",
    connection=connection,
)
```

Semantic View caveats:

- composite primary keys are not fully supported
- some cross-table expressions may be dropped during conversion

## Hard Rules

- Never invent tables, columns, IDs, timestamps, links, or categorical values.
- Prefer query-driven `model.predict(...)` or `model.evaluate(...)` by default.
- Use `TaskTable` only when the request already provides explicit scoring rows or the task is easier to express directly than as one query.
- Do not trust inferred links blindly.
- Inspect every relevant table column-by-column before querying.
- Confirm each inferred time column manually, especially create-time columns such as `created_at`.
- Do not claim success unless prediction or evaluation ran and you can show sample outputs.

## Validation Workflow

Always inspect before querying:

```python
graph.print_metadata()
graph.print_links()

for table in graph.tables.values():
    table.print_metadata()

graph.validate()
```

Verify all of the following:

- every relevant table was inspected column-by-column
- the entity table exists
- the entity key is a real PK or ID
- each relevant table has the correct inferred time column
- links support the requested prediction path
- inferred links are semantically correct, not just name-matched

Graph rules:

- all tables in one graph must use the same backend
- PK and FK dtypes must be compatible
- a foreign key cannot be the same as the source table primary key

Missing or ambiguous links:

1. Inspect metadata and printed links.
2. Inspect all columns in the involved tables.
3. Identify plausible FK to PK pairs using names, dtypes, and business semantics.
4. Add only confident missing links manually.
5. If more than one plausible link remains, ask the user the minimum necessary clarification.

Manual repair:

```python
graph.link(src_table="ORDERS", fkey="USER_ID", dst_table="USERS")
graph.link(src_table="ORDERS", fkey="ITEM_ID", dst_table="ITEMS")
graph.print_links()
graph.validate()
```

## Query Mapping Rules

- Use boolean conditions for "will", "likely", or "any" outcomes.
- Use raw aggregations for "how much", "how many", or "total".
- Use direct column prediction for status, class, or value imputation.
- Use ranking queries for recommendations or related-ID tasks.
- Put target filters inside aggregations and eligibility filters in the top-level `WHERE`.

## Entity Anchoring

Identify:

- who is being predicted for
- the entity table
- the entity primary key
- whether explicit IDs were given

Accepted forms include:

```sql
FOR users.user_id = 42
FOR users.user_id IN (42, 123)
FOR EACH users.user_id
```

Do not apply outdated guidance that says `FOR EACH` is invalid.

## Static Vs Temporal

Static classification:

```sql
PREDICT TABLE.COLUMN FOR TABLE.PK = 'ID'
```

Static regression:

```sql
PREDICT TABLE.NUMERIC_COLUMN FOR TABLE.PK = 'ID'
```

Temporal binary classification:

```sql
PREDICT COUNT(EVENTS.*, 0, N, DAYS) > 0 FOR ENTITY.PK = 'ID'
PREDICT COUNT(EVENTS.*, 0, N, DAYS) = 0 FOR ENTITY.PK = 'ID'
PREDICT SUM(EVENTS.AMOUNT, 0, N, DAYS) >= THRESHOLD FOR ENTITY.PK = 'ID'
```

Temporal regression:

```sql
PREDICT SUM(EVENTS.AMOUNT, 0, N, DAYS) FOR ENTITY.PK = 'ID'
PREDICT COUNT(EVENTS.*, 0, N, DAYS) FOR ENTITY.PK = 'ID'
PREDICT AVG(EVENTS.VALUE, 0, N, DAYS) FOR ENTITY.PK = 'ID'
```

Filtered temporal prediction:

```sql
PREDICT SUM(TABLE.VALUE WHERE TABLE.DIMENSION = 'VALUE', 0, N, DAYS) FOR ENTITY.PK = 'ID'
PREDICT COUNT(TABLE.* WHERE TABLE.STATUS = 'VALUE', 0, N, DAYS) FOR ENTITY.PK = 'ID'
```

Forecasting:

- supported as a distinct task type
- usually expects one entity at prediction time
- `use_prediction_time=True` can help for time-series tasks

Ranking or link prediction:

- use only when schema relationships and target ID columns support it clearly
- be conservative when graph support is ambiguous

## Filters, Counterfactuals, And Time

Put target filters inside aggregations:

```sql
PREDICT COUNT(CLAIMS.* WHERE CLAIMS.CLAIM_STATUS = 'Approved', 0, 365, DAYS) FOR INSURANCE_POLICIES.POLICY_ID = 'POL-1'
```

Put eligibility filters at top-level `WHERE`:

```sql
PREDICT COUNT(ORDERS.*, 0, 90, DAYS) > 0 FOR EACH USERS.USER_ID WHERE COUNT(ORDERS.*, -90, 0, DAYS) > 0
```

Use `ASSUMING` only for true counterfactuals:

```sql
PREDICT COUNT(OPP_CLOSE.* WHERE OPP_CLOSE.TERMINAL_STATUS = 'CLOSED_WON', 0, 90, DAYS) > 0
FOR OPPORTUNITY.OPP_ID = 'o23'
ASSUMING COUNT(OPPORTUNITY_DAILY_SNAPSHOT.HAS_DISCOUNT, 0, 14, DAYS) > 0
```

Time mapping rules:

- next 7 days -> `(0, 7, DAYS)`
- next 30 days -> `(0, 30, DAYS)`
- next quarter -> often `(0, 90, DAYS)` unless business context says otherwise
- next 6 months -> often `(0, 180, DAYS)`

Non-overlapping forecasting windows:

```sql
COUNT(ORDERS.*, 0, 7, DAYS)
COUNT(ORDERS.*, 7, 14, DAYS)
COUNT(ORDERS.*, 14, 21, DAYS)
```

SDK time rules:

- `anchor_time=None` derives from the latest relevant timestamp
- `anchor_time="entity"` is valid only for static predictive queries and requires the entity table to have a time column

## Refuse Or Reframe

Refuse or reframe when:

- the task is clustering or segmentation without a prediction target
- the task is anomaly detection without an explicit target
- required columns do not exist
- the task requires invented labels or facts
- the needed relationship is unsupported or unresolved

When refusing:

1. State what is missing or unsupported.
2. Name the exact schema gap or graph ambiguity.
3. Offer the closest supported alternative if one exists.

## Minimal Execution Patterns

Query-driven prediction:

```python
import kumoai.experimental.rfm as rfm

model = rfm.KumoRFM(graph)

query = "PREDICT COUNT(orders.*, 0, 90, DAYS) = 0 FOR users.user_id IN (42, 123)"
pred_df = model.predict(query, run_mode="fast")
print(pred_df.head())
```

Query-driven evaluation:

```python
metrics_df = model.evaluate(query, run_mode="fast")
print(metrics_df)
```

TaskTable flow:

```python
task = rfm.TaskTable(
    task_type=...,
    context_df=context_df,
    pred_df=pred_df,
    entity_table_name="users",
    entity_column="user_id",
    target_column="target",
    time_column="anchor_time",
)

pred_df = model.predict_task(task, run_mode="fast")
metrics_df = model.evaluate_task(task, run_mode="fast")
```

Explainability:

```python
result = model.predict(
    query,
    explain=rfm.ExplainConfig(),
    run_mode="fast",
)
```

Explainability is effectively a single-entity FAST-mode feature.

## Output Contract

For every task, return:

1. Graph source and graph code
2. Inspected entity table, relevant target tables, and link reasoning
3. Confirmation that relevant columns and inferred time columns were checked
4. Final query or `TaskTable` code
5. Exact prediction or evaluation call
6. Sample outputs
7. Assumptions, unresolved ambiguities, and any user clarifications requested
