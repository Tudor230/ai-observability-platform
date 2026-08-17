
# 2. Understanding of the Process

## 2.1 Current Situation

Agentic applications are developed and operated independently by different teams.

A simplified current process is:

```text
Business Request
      |
      v
Agentic Application
      |
      +----> LLM
      |
      +----> Tool / API
      |
      +----> Database
      |
      +----> Retrieval
      |
      v
Business Result
```

At organizational level, the process can look like:

```text
Team A --> Agent A --> Local Logs
Team B --> Agent B --> Local Metrics
Team C --> Agent C --> Different Framework
Team D --> Agent D --> Manual Cost Estimation
```

There is no common observability and FinOps layer.

## 2.2 Traditional / Manual Process

For a business process such as customer ticket resolution, the traditional process may be:

```text
Customer Request
      |
      v
Human receives ticket
      |
      v
Human searches information
      |
      v
Human checks systems
      |
      v
Human decides action
      |
      v
Human updates system
      |
      v
Customer receives response
```

The organization may measure:

* Number of tickets
* Resolution time
* Employee effort
* SLA compliance

However, when an agentic solution replaces parts of this process, additional information becomes necessary:

* Number of LLM calls
* Token consumption
* Tool calls
* Model used
* Agent execution time
* API costs
* Cost per execution

## 2.3 Main Bottlenecks

### Lack of Standardized Telemetry

Different teams may use different frameworks and logging approaches.

This makes it difficult to obtain a consistent view of agent execution across projects.

### Lack of Cost Visibility

Token consumption does not directly translate into business cost unless provider and model pricing is applied.

### Lack of Business Attribution

A technical trace does not automatically indicate which client, workflow, project, or business process generated it.

### Lack of Historical Analysis

Without centralized storage and aggregation, it is difficult to identify consumption trends and changes over time.

### Lack of Anomaly Detection

Large increases in token consumption, latency, retries, tool calls, or execution frequency may not be detected quickly.

### Lack of Comparison

It is difficult to consistently compare:

* Agent A vs Agent B
* Client A vs Client B
* Workflow A vs Workflow B
* AI process vs manual process

## 2.4 Opportunities for AI / Agentic Automation

Agentic systems can automate repetitive and multi-step business processes.

They can reduce manual effort by:

* Processing requests automatically
* Searching information
* Calling enterprise systems
* Making decisions based on available information
* Executing multiple steps without human intervention
* Producing structured outputs

However, increased autonomy creates a new operational requirement:

> The organization must be able to observe, measure, and understand the behavior and cost of autonomous systems.

The proposed observability and FinOps platform addresses this requirement without replacing the agentic applications themselves.

## 2.5 Proposed Improvement

The current fragmented approach is replaced by a centralized observability layer.

Instead of:

```text
Team A --> Agent A --> Local Monitoring
Team B --> Agent B --> Local Monitoring
Team C --> Agent C --> Local Monitoring
```

the proposed process is:

```text
Team A --> Agent A --+
Team C --> Agent C --+--> Central Observability Platform
Team B --> Agent B --+
```

The centralized platform collects standardized telemetry from all monitored applications.

## 2.6 Future Process

The improved process becomes:

```text
Business Request
      |
      v
Agentic Application
      |
      +----> LLM
      |
      +----> Tools
      |
      +----> Retrieval
      |
      v
Business Result
      |
      +----------------------+
      |                      |
      v                      v
Execution Trace        Business Context
      |                      |
      +----------+-----------+
                 |
                 v
        Agentic FinOps Platform
                 |
        +--------+--------+
        |        |        |
        v        v        v
      Cost   Analytics  Alerts
        |        |        |
        +--------+--------+
                 |
                 v
             Dashboard
```

## 2.7 Expected Improvement

The proposed process enables the organization to move from fragmented application-level monitoring to a standardized platform that provides:

* Centralized trace visibility
* Standardized agent telemetry
* Cost per execution
* Cost per workflow
* Cost per client
* Token consumption
* Tool-call visibility
* Latency analysis
* Error analysis
* Consumption anomaly detection
* Historical cost analysis

The result is a common operational and financial view of agentic solutions across teams.


