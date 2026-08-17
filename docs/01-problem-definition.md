# 1. Problem Definition & Scope

## 1.1 Problem Statement

The organization is developing multiple agentic and AI-based solutions across different teams. These solutions may use different LLM providers, agent frameworks, tools, APIs, retrieval systems, and deployment architectures.

While these applications can perform business tasks autonomously, there is no standardized platform for understanding and measuring their execution.

Currently, it can be difficult to answer questions such as:

- What did an agent do during a specific execution?
- Which LLMs and tools were used?
- How many input and output tokens were consumed?
- How long did the execution take?
- How much did a task cost?
- How much does an agentic workflow cost per client?
- Which workflows are inefficient?
- Which agents consume unusually large amounts of resources?
- How does the cost of an agentic process compare with the traditional/manual process?

This creates both a technical observability problem and a financial management problem.

The proposed project addresses this gap by creating a centralized **Agentic Observability and FinOps Platform** that can be used by multiple teams and multiple agentic applications.

---

## 1.2 Project Objective

The objective is to develop a centralized platform capable of:

1. Collecting execution traces from agentic applications.
2. Capturing LLM, tool, retrieval, and application-level execution information.
3. Associating technical executions with business context such as client, project, workflow, and business transaction.
4. Calculating the cost of agentic executions.
5. Aggregating costs by client, project, workflow, agent, and team.
6. Providing dashboards for technical, operational, and management users.
7. Detecting abnormal consumption and inefficient executions.
8. Providing a foundation for future AI service pricing and unit economics.

---

## 1.3 Scope

### In Scope

- OpenTelemetry-based observability
- OpenInference instrumentation
- Phoenix as a self-hosted trace backend
- Custom observability SDK
- Agent and workflow instrumentation
- LLM usage tracking
- Token tracking
- Tool-call tracking
- Retrieval tracing where applicable
- Latency and error tracking
- Business-context enrichment
- Trace normalization
- Cost calculation
- Cost attribution
- Analytics
- Dashboards
- Consumption alerts
- Budget monitoring
- Technical trace visualization

### Out of Scope

The project will not:

- Build the business agents monitored by the platform.
- Replace LLM providers.
- Train or fine-tune foundation models.
- Implement a general-purpose RAG platform.
- Automatically modify production agents.
- Automatically optimize agent behavior without human approval.
- Replace Phoenix as the underlying trace infrastructure.
- Become a general-purpose enterprise monitoring platform for all IT systems.

---

## 1.4 Target Users

### Engineers

Need to understand:

- Agent execution
- LLM calls
- Tool calls
- Errors
- Latency
- Trace hierarchy

### Service Delivery Managers / Managers

Need to understand:

- Cost per workflow
- Cost per client
- Cost per ticket/task where applicable
- Consumption trends
- Budget utilization
- Agent efficiency

### Finance / Senior Management

Need to understand:

- Total AI operating cost
- Cost per client
- Cost per service
- Unit economics
- Forecasted cost
- Potential margin

---

## 1.5 Assumptions

The project assumes:

- Agentic applications can expose or generate OpenTelemetry-compatible telemetry.
- Phoenix can be self-hosted within the organization's infrastructure.
- Teams can integrate a common observability SDK.
- LLM providers expose token usage or equivalent usage information.
- Model/API pricing information can be configured in the platform.
- Business identifiers can be provided by monitored applications when available.

---

## 1.6 Success Definition

The platform is successful if it can take executions from multiple independent agentic applications and provide a standardized view of:

**what happened, how it happened, how long it took, how much it consumed, and how much it cost.**