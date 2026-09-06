-- Sample queries for inspecting SDK traces stored by Phoenix in Postgres.
--
-- Phoenix stores one row per span in `spans`; OpenInference flat attribute
-- keys are stored as NESTED jsonb (e.g. `sdk.workflow_id` ->
-- attributes->'sdk'->>'workflow_id'). Business context rides on the
-- workflow-root CHAIN span (parent_id IS NULL).

-- 1. Recent workflow roots (business context at a glance)
SELECT s.name,
       s.attributes->'sdk'->>'project_id'  AS project_id,
       s.attributes->'sdk'->>'client_id'   AS client_id,
       s.attributes->'sdk'->>'workflow_id' AS workflow_id,
       s.attributes->'session'->>'id'      AS session_id,
       s.status_code,
       s.start_time
FROM spans s
WHERE s.parent_id IS NULL
ORDER BY s.start_time DESC
LIMIT 20;

-- 2. Everything under the latest workflow (workflow -> agent -> LLM/tool)
SELECT s.name,
       s.attributes->'openinference'->'span'->>'kind' AS kind,
       s.attributes->'llm'->'token_count'->>'prompt'  AS prompt_tokens,
       s.attributes->'llm'->'token_count'->>'completion' AS completion_tokens,
       s.attributes->'sdk'->'error'->>'kind'          AS error_kind,
       s.attributes->'sdk'->'retry'->>'count'         AS retry_count,
       s.status_code
FROM spans s
JOIN traces t ON t.id = s.trace_rowid
WHERE t.trace_id = (SELECT t.trace_id FROM spans s2
                    JOIN traces t ON t.id = s2.trace_rowid
                    WHERE s2.attributes->'sdk'->>'workflow_id' IS NOT NULL
                    ORDER BY s2.start_time DESC LIMIT 1)
ORDER BY s.start_time;

-- 3. Payload content captured (opt-in workflows only)
SELECT s.name,
       s.attributes->'input'->>'value' AS input,
       s.attributes->'output'->>'value' AS output
FROM spans s
WHERE s.parent_id IS NOT NULL
ORDER BY s.start_time DESC
LIMIT 20;

-- 4. Failure summary: workflow roots that failed, with the primary hint
SELECT s.name,
       s.attributes->'sdk'->'error'->>'kind' AS primary_failure_kind,
       s.status_code,
       s.attributes->'sdk'->>'workflow_id' AS workflow_id
FROM spans s
WHERE s.parent_id IS NULL AND s.status_code = 'ERROR'
ORDER BY s.start_time DESC;