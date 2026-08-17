# 4. High-Level Architecture

## 4.1 Purpose

This document describes the technical architecture of the solution proposed in [03 — Proposed Solution / TO-BE Flow](./03-to-be-solution.md).

It defines:

- Major technical components
- Component responsibilities
- Interfaces between components
- Main data flows
- Integration boundaries
- Deployment model
- Proposed technology stack

The functional requirements and TO-BE behavior are defined in Document 3. This document focuses on the technical implementation of those requirements.

## 4.2 Architecture Overview

```text
+------------------------------------------------------------------+
|                    AGENTIC APPLICATIONS                          |
|                                                                  |
|   Team A              Team B              Team C                 |
|   Agent A             Agent B             Agent C                |
+----------------------------+-------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                    OBSERVABILITY SDK                             |
|                                                                  |
|              OpenTelemetry / OpenInference                       |
+----------------------------+-------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                         PHOENIX                                 |
|                                                                  |
|             Trace Collection & Trace Storage                     |
+----------------------------+-------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                    PLATFORM BACKEND                              |
|                                                                  |
|  +----------------+  +----------------+  +------------------+   |
|  | Trace          |  | Cost           |  | Analytics        |   |
|  | Processing     |  | Engine         |  | Engine           |   |
|  +----------------+  +----------------+  +------------------+   |
|                                                                  |
|                     +----------------+                            |
|                     | Alert Engine   |                            |
|                     +----------------+                            |
+----------------------------+-------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                         DATA LAYER                               |
|                                                                  |
|                       PostgreSQL                                |
+----------------------------+-------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                       PLATFORM API                              |
+----------------------------+-------------------------------------+
                             |
                             v
+------------------------------------------------------------------+
|                       WEB DASHBOARD                              |
+------------------------------------------------------------------+
````

## 4.3 Architecture Layers

The solution is divided into five technical layers.

### Layer 1 — Agentic Applications

Applications developed by the individual project teams.

These applications remain responsible for their own:

* Business logic
* Agent logic
* LLM interactions
* Tools
* Retrieval
* External system integrations

The platform observes these applications without owning their business functionality.

### Layer 2 — Observability

Provides the common integration mechanism between agentic applications and the platform.

Main technologies:

* OpenTelemetry
* OpenInference
* Internal Observability SDK

### Layer 3 — Processing and FinOps

Processes telemetry and transforms it into normalized execution, usage, cost, and analytics data.

Main components:

* Trace Processing
* Cost Engine
* Analytics Engine
* Alert Engine

### Layer 4 — Data and API

Provides persistent storage and a controlled interface for accessing processed information.

Main components:

* PostgreSQL
* Platform API

### Layer 5 — Presentation

Provides the user interface for exploring traces, usage, costs, and analytics.

Main component:

* Web Dashboard

## 4.4 Component Responsibilities

### 4.4.1 Observability SDK

The SDK is the main integration point for project teams.

It provides:

* Telemetry initialization
* Automatic instrumentation
* Custom spans
* Trace context propagation
* Business metadata
* Telemetry export

The SDK should minimize the amount of observability-specific code that individual teams need to add to their applications.

### 4.4.2 OpenTelemetry / OpenInference

OpenTelemetry provides the distributed tracing foundation.

OpenInference adds AI-specific semantic conventions and instrumentation.

Together they provide a standardized telemetry interface independent of a specific agent framework.

### 4.4.3 Phoenix

Phoenix is used as the self-hosted trace infrastructure.

Responsibilities:

* Receive telemetry
* Store traces and spans
* Maintain span relationships
* Provide trace infrastructure

Phoenix is therefore the underlying technical trace layer, while the custom platform provides the additional processing, FinOps, and business-oriented functionality.

### 4.4.4 Trace Processing Service

The Trace Processing Service consumes telemetry and converts it into a normalized internal representation.

Responsibilities:

* Validate telemetry
* Normalize different telemetry structures
* Extract relevant metadata
* Associate business context
* Extract resource consumption
* Prepare data for downstream processing

### 4.4.5 Cost Engine

The Cost Engine converts captured resource consumption into financial cost.

Primary inputs include:

* LLM provider
* Model
* Input tokens
* Output tokens
* Pricing configuration
* Applicable tool/API costs

The engine should support multiple providers and models.

### 4.4.6 Analytics Engine

The Analytics Engine aggregates normalized execution and cost data.

It produces metrics required for:

* Operational monitoring
* Consumption analysis
* Cost analysis
* Client attribution
* Workflow analysis
* Management reporting

### 4.4.7 Alert Engine

The Alert Engine evaluates platform metrics against configured rules.

Possible rule inputs include:

* Cost
* Token consumption
* Latency
* Error rate
* Budget utilization
* Execution frequency

The engine produces alerts that can be exposed through the dashboard.

### 4.4.8 Data Layer

PostgreSQL is proposed for platform-specific structured data.

Possible entities include:

```text
Team
Project
Client
Agent
Workflow
Pricing
Cost Record
Metric
Budget
Alert
```

Detailed trace data is maintained by Phoenix.

The database therefore stores the information required by the custom platform rather than acting as a replacement for the trace backend.

### 4.4.9 Platform API

The Platform API provides a stable interface between the backend and frontend.

Conceptual resources include:

```text
/api/traces
/api/workflows
/api/agents
/api/clients
/api/costs
/api/metrics
/api/alerts
```

The frontend should access platform information through this API rather than directly querying internal services or databases.

### 4.4.10 Dashboard

The dashboard provides the presentation layer for the platform.

It consumes processed information through the Platform API.

The dashboard should support the different user perspectives described in [03 — Proposed Solution / TO-BE Flow](./03-to-be-solution.md).

## 4.5 Main Data Flows

### 4.5.1 Telemetry Flow

```text
Agentic Application
        |
        v
Observability SDK
        |
        v
OpenTelemetry / OpenInference
        |
        v
Phoenix
        |
        v
Trace Processing
```

### 4.5.2 Cost Flow

```text
Trace Processing
        |
        v
Resource Consumption
        |
        v
Cost Engine
        |
        v
Cost Records
        |
        v
Analytics
```

### 4.5.3 Dashboard Flow

```text
Processed Data
      |
      v
Platform API
      |
      v
Dashboard
```

### 4.5.4 Alert Flow

```text
Metrics
   |
   v
Alert Engine
   |
   v
Configured Rules
   |
   v
Alerts
```

## 4.6 Integration Boundary

The primary integration boundary for project teams is the Observability SDK.

```text
                     CENTRAL PLATFORM
                            |
                  +---------+---------+
                  | Observability SDK |
                  +---------+---------+
                            ^
                            |
                     Integration Point
                            |
          +-----------------+-----------------+
          |                 |                 |
       Team A            Team B            Team C
          |                 |                 |
       Agent A            Agent B            Agent C
```

Individual teams should not need to integrate directly with:

* Phoenix
* Cost Engine
* Analytics Engine
* PostgreSQL
* Alert Engine
* Platform API
* Dashboard

This creates a clear separation between application development and platform infrastructure.

## 4.7 Deployment Architecture

The platform can be deployed as a set of containerized services.

```text
+---------------------------------------------------------------+
|                       Kubernetes Cluster                      |
|                                                               |
|  +-------------+   +-------------+   +--------------------+   |
|  | Phoenix     |   | Backend     |   | PostgreSQL         |   |
|  |             |   | Services    |   |                    |   |
|  +-------------+   +------+------+   +--------------------+   |
|                           |                                   |
|              +------------+------------+                      |
|              |            |            |                      |
|              v            v            v                      |
|          Processing     Cost       Analytics                  |
|                                                               |
|  +---------------------------------------------------------+  |
|  |                    Platform API                         |  |
|  +---------------------------------------------------------+  |
|                           |                                   |
|                           v                                   |
|  +---------------------------------------------------------+  |
|  |                    Dashboard                            |  |
|  +---------------------------------------------------------+  |
+---------------------------------------------------------------+

        ^                 ^                 ^
        |                 |                 |
      Team A            Team B            Team C
      Agent             Agent             Agent
```

The exact deployment configuration can be determined according to the organization's infrastructure and security requirements.

## 4.8 Technology Stack

| Component            | Proposed Technology           |
| -------------------- | ----------------------------- |
| Instrumentation      | OpenTelemetry / OpenInference |
| Observability SDK    | Python                        |
| Trace infrastructure | Phoenix                       |
| Backend              | Python                        |
| API                  | FastAPI                       |
| Processing           | Python                        |
| Database             | PostgreSQL                    |
| Frontend             | React                         |
| Containerization     | Docker                        |
| Orchestration        | Kubernetes                    |

These technologies are proposed implementation choices and can be adjusted without changing the overall architecture.

## 4.9 Architectural Principles

### Shared Platform

The architecture supports multiple independent agentic applications and teams.

### Low Integration Effort

The Observability SDK provides a single integration point for application teams.

### Framework Independence

The platform should not depend on a single agent framework.

### Separation of Concerns

Application logic, observability, processing, FinOps, storage, API, and presentation remain separate responsibilities.

### Extensibility

Additional teams, models, providers, and frameworks should be integrable without major architectural changes.

### Fault Isolation

Failure of the observability platform should not prevent the underlying agentic application from performing its business function.

### Security

Telemetry and business-context data should be protected through appropriate access controls, data minimization, and sensitive-data handling.

## 4.10 Architecture Boundaries

### Inside the Platform

* Observability SDK
* Telemetry processing
* Phoenix
* Cost Engine
* Analytics Engine
* Alert Engine
* Platform database
* Platform API
* Dashboard

### Outside the Platform

* Individual agentic business logic
* Individual team's applications
* External LLM providers
* External business systems
* External tools and APIs
