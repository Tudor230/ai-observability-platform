# 3. Proposed Solution / TO-BE Flow

## 3.1 Solution Overview

The proposed solution is a centralized **Agentic Observability and FinOps Platform** that provides a common observability and cost-management layer for agentic applications developed by multiple teams.

The platform does not replace or modify the core business logic of the agentic applications. Instead, it provides a shared layer for collecting telemetry, processing execution data, calculating costs, attributing consumption, and exposing the resulting information to different users.

The platform should allow multiple independent agentic projects to use the same observability and FinOps capabilities without each team having to build its own monitoring solution.

## 3.2 Main Objectives

The platform should enable the organization to:

- Observe agentic applications developed by different teams.
- Standardize the telemetry collected from these applications.
- Understand how agents execute individual tasks and workflows.
- Capture LLM, tool, retrieval, and application-level activity.
- Associate executions with relevant business context.
- Calculate the cost of agentic executions.
- Attribute costs to workflows, agents, projects, teams, and clients.
- Identify abnormal consumption and inefficient executions.
- Provide technical, managerial, and executive views of agentic usage.

## 3.3 TO-BE Flow

```text
Business Request
      |
      v
Agentic Application
      |
      +----> LLM
      |
      +----> Tools / APIs
      |
      +----> Retrieval
      |
      v
Business Result
      |
      v
Observability Layer
      |
      v
Trace Processing
      |
      +----> Cost Calculation
      |
      +----> Analytics
      |
      +----> Alerts
      |
      v
Central Dashboard
````

The key difference from a traditional application monitoring approach is that the platform connects technical agent execution with business and financial context.

```text
Agent Execution
      |
      v
Telemetry
      |
      v
Resource Consumption
      |
      v
Cost
      |
      v
Business Context
      |
      v
Client / Project / Workflow
```

## 3.4 Integration with Existing Agentic Applications

Each team integrates its agentic application with the common observability layer.

The integration should require minimal changes to the existing application.

The common SDK provides a standardized integration mechanism for:

* Trace generation
* Span generation
* OpenTelemetry configuration
* OpenInference instrumentation
* Trace context propagation
* Trace export
* Business-context enrichment
* Custom business spans

The goal is to make observability a reusable platform capability rather than something each team implements independently.

## 3.5 Automatic Instrumentation

Where supported, telemetry should be collected automatically from the application.

The platform should capture relevant information from the following categories.

### LLM Calls

* Provider
* Model
* Input tokens
* Output tokens
* Latency
* Status
* Errors

### Tool Calls

* Tool name
* Number of calls
* Execution status
* Latency
* Errors

### Retrieval

Where applicable:

* Retrieval operation
* Query
* Retrieval source
* Number of retrieved documents
* Retrieval latency

### Application Execution

* Trace ID
* Span ID
* Parent span
* Workflow
* Agent
* Execution duration
* Status
* Exceptions

## 3.6 Custom Business Instrumentation

Automatic instrumentation cannot capture every business-level operation.

Teams should therefore be able to add custom business spans when required.

For example:

```python
with observe_step("customer_lookup"):
    customer = crm.lookup(customer_id)
```

or:

```python
with observe_step("ticket_update"):
    ticket_system.update(ticket)
```

This allows the execution trace to contain meaningful business operations in addition to infrastructure-level operations.

For example:

```text
Ticket Resolution
|
+-- Customer Lookup
|     |
|     +-- CRM API
|
+-- Knowledge Search
|     |
|     +-- Vector Search
|
+-- AI Decision
|     |
|     +-- LLM
|
+-- Ticket Update
|     |
|     +-- Ticketing API
|
+-- Customer Notification
      |
      +-- Email API
```

## 3.7 Business Context

The platform should support dynamic business identifiers.

A single identifier such as `ticket_id` should not be mandatory because different agentic projects may operate on different business objects.

Examples include:

```text
ticket_id
order_id
customer_id
invoice_id
case_id
request_id
```

A generic context structure can be used:

```python
with observe_workflow(
    "ticket_resolution",
    context={
        "ticket_id": ticket.id,
        "customer_id": ticket.customer_id
    }
):
    agent.run(ticket)
```

This allows technical executions to be connected to the business process that generated them.

The identifiers should be supplied dynamically by the originating application rather than being hardcoded into the observability platform.

## 3.8 Trace Processing

Once telemetry has been collected, it is processed into a standardized representation.

The processing flow is:

```text
Raw Telemetry
      |
      v
Validation
      |
      v
Normalization
      |
      v
Business Enrichment
      |
      v
Resource Extraction
      |
      v
Cost + Metrics
```

The processing layer should:

* Validate incoming telemetry.
* Normalize information from different frameworks.
* Extract tokens and model information.
* Identify tool and retrieval operations.
* Associate executions with business context.
* Build workflow-level information from individual spans.
* Prepare data for cost and analytics processing.

## 3.9 Cost Calculation

The platform calculates the cost associated with agentic resource consumption.

For LLM calls:

```text
Input Token Cost
=
Input Tokens × Input Token Price
```

```text
Output Token Cost
=
Output Tokens × Output Token Price
```

Therefore:

```text
LLM Cost
=
(Input Tokens × Input Price)
+
(Output Tokens × Output Price)
```

A complete workflow may contain multiple LLM calls and other billable operations:

```text
Workflow Cost
=
LLM Costs
+
Tool/API Costs
+
Other Applicable Costs
```

The pricing model should support:

* Multiple LLM providers
* Multiple models
* Input and output token pricing
* Different pricing configurations
* Pricing changes over time

## 3.10 Cost Attribution

After the cost of an execution has been calculated, it should be possible to attribute it to different dimensions.

```text
Execution
 |
 +-- Client
 +-- Project
 +-- Team
 +-- Service
 +-- Workflow
 +-- Agent
```

This allows the platform to answer questions such as:

* How much did a client consume?
* Which workflow is the most expensive?
* Which agent generates the highest cost?
* Which team has the highest AI consumption?
* What is the average cost per execution?
* How much does a specific business process cost?

The attribution should work across different projects without requiring the platform to understand the internal business logic of each application.

## 3.11 Analytics

The platform aggregates execution data into operational and financial metrics.

### Execution Metrics

* Number of executions
* Successful executions
* Failed executions
* Error rate
* Retry rate
* Average latency
* P95 latency

### AI Usage Metrics

* Input tokens
* Output tokens
* Total tokens
* LLM calls
* Tool calls
* Retrieval calls
* Model usage

### Financial Metrics

* Total cost
* Average cost per execution
* Cost per workflow
* Cost per agent
* Cost per client
* Cost per team


## 3.12 Alerts

The platform should identify abnormal or undesirable consumption patterns.

Potential conditions include:

```text
Cost exceeds threshold
        |
        v
      Alert
```

```text
Token consumption increases unexpectedly
        |
        v
      Alert
```

```text
Tool calls exceed expected range
        |
        v
Potential inefficient execution
```

Possible alert categories include:

* Cost threshold exceeded
* Token threshold exceeded
* Latency threshold exceeded
* Error-rate increase
* Excessive tool calls
* Budget exceeded
* Unusual consumption compared with historical behavior

## 3.13 Dashboard

The platform provides different levels of visibility depending on the user.

### Engineering View

Focuses on technical execution:

* Individual traces
* Agent execution
* LLM calls
* Tool calls
* Retrieval
* Errors
* Latency
* Token consumption

### SDM / Manager View

Focuses on operational and financial information:

* Cost per client
* Cost per workflow
* Consumption trends
* Budget utilization
* Agent efficiency
* Cost per ticket/task where applicable

### Executive View

Focuses on business-level unit economics:

* Total AI cost
* Cost per client
* Cost per service
* Cost per execution
* Cost trends
* Forecasting
* Potential margin

## 3.14 End-to-End Example

Consider a ticket-resolution agent.

The business process is:

```text
Customer
   |
   v
Ticketing System
   |
   v
Ticket Resolution Agent
   |
   +----> CRM Lookup
   |
   +----> Knowledge Retrieval
   |
   +----> LLM
   |
   +----> Ticket Update
   |
   v
Customer Response
```

The observability platform associates the technical execution with the relevant business context.

A resulting execution could contain:

```text
Trace: ticket_resolution
Client: Client-A
Ticket: INC-12345

Duration: 3.2 seconds

Spans:
    Customer Lookup
    Knowledge Search
    LLM Call #1
    Ticket Update
    LLM Call #2

Tokens:
    Input:  1,800
    Output:   500
```

The platform can then expose:

```text
Client A
|
+-- Ticket Resolution
      |
      +-- Executions
      +-- Total Cost
      +-- Average Cost
      +-- Average Latency
      +-- Success Rate
```

This creates a direct connection between:

```text
Technical Execution
        |
        v
Business Process
        |
        v
Resource Consumption
        |
        v
Financial Cost
```

## 3.15 Expected Outcome

The proposed solution creates a shared observability and FinOps capability that can be reused across agentic applications developed by different teams.

The platform should make it possible to answer four fundamental questions:

1. **What did the agent do?**
2. **How did the agent execute the task?**
3. **How much did the execution consume?**
4. **How much did the execution cost the organization or client?**

The solution should therefore transform raw agent execution data into a consistent view of:

```text
Agent
  ↓
Execution
  ↓
Telemetry
  ↓
Consumption
  ↓
Cost
  ↓
Business Context
  ↓
Client / Project / Team
```

