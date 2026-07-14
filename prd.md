# PRD: Agent Evaluation Harness

## 1. One-Line Summary
An evaluation platform that runs AI agents against benchmark task suites, captures their full execution trace (not just the final answer), scores them on task success, cost, latency, and failure mode, and flags regressions when a prompt, model, or architecture change silently degrades performance. This is infrastructure, not a domain agent — it's the thing you run every other agent in your portfolio *through*.

## 2. Problem Statement
Evaluating a model is a solved problem: one input, one output, compare against a label or a human judge. Evaluating an agent is not, because an agent doesn't produce an answer — it produces a **trajectory**: a sequence of planning, tool calls, retries, and reasoning steps that only terminates in an answer at the end. Two runs of the identical task can take entirely different paths and both be correct, or both be wrong for unrelated reasons. One path costs $0.03 and takes 3 tool calls; another reaches the same answer at $1.50 and 25 tool calls. "Did it get the right answer" doesn't distinguish these, and most portfolio projects never measure past that question.

The practical failure mode this produces: someone changes a single prompt in their agent, ships it, and has no idea that success rate quietly dropped 10% until a user complains. Without a harness, there is no equivalent of `pytest` or CI for an agentic system — every change is a blind deploy.

## 3. Goals (MVP)
- Provide one common interface (`run(task) -> AgentResult`) that any of your existing agents can be wrapped in, regardless of their internal framework.
- Capture a full execution trace per run: every LLM call, tool call, and state transition, with tokens, cost, and latency attached.
- Score each run on three levels: end-to-end (did it succeed), trajectory (was the path sound), and component (which sub-agent/tool was responsible for failure).
- Classify failures into a fixed taxonomy rather than a binary pass/fail.
- Detect regressions automatically when comparing two versions of the same agent on the same task suite.
- Produce a report that answers, per agent version: success rate, average cost, average latency, and a ranked list of failure modes.

## 3.1 Non-Goals (v1)
- Not building a general-purpose eval product (LangSmith/Braintrust already exist) — building enough of one to deeply understand the pattern and to actually use on your own agents.
- Not covering real-time production monitoring/alerting in v1 — batch evaluation against a fixed task suite first; streaming/production telemetry is a stretch goal.
- Not attempting to eval every agent type on day one — start with 2-3 seed agents (see Section 17) rather than building a harness with nothing to run it against.
- Not fine-tuning or RL from the collected trajectories in v1 — that's a natural extension once the data exists, not part of the initial build.

## 4. Users / Use Cases
- **You, evaluating your own portfolio agents** — the primary use case. Every project you've scoped so far (Code Review Agent, Deep Research Agent, Financial Analyst, etc.) becomes a task suite target.
- **Anyone hiring for agent/infra roles** — this project is the artifact you show when the question shifts from "can you build an agent" to "can you tell me it's actually reliable."
- **Future you, mid-iteration** — the regression detector is what stops you from shipping a "improvement" that actually made things worse without noticing.

## 5. High-Level Architecture

```
Task Suite (YAML/JSON per task: input, expected outcome, grading strategy)
      │
      ▼
Agent Adapter Layer ── wraps each target agent behind one common interface: run(task) -> AgentResult
      │
      ▼
Instrumented Execution ── every LLM call, tool call, and state transition recorded as a span
      │
      ▼
Trace Store ── structured, queryable log of the full run (not just the final output)
      │
      ▼
Grading Engine
   ├── Deterministic checks (tests pass? schema valid? line-number match?) — prefer these
   └── LLM-as-Judge (rubric-based, 0-5 scale) — for anything with no objective ground truth
      │
      ▼
Metrics Aggregator ── success rate, cost, latency, tool-usage stats, failure-mode counts
      │
      ▼
Regression Engine ── diffs current run against the last baseline, flags significant drops
      │
      ▼
Report / Dashboard
```

The **Agent Adapter Layer** is what separates this from a one-off eval script — every agent, regardless of whether it's built on LangGraph, a raw loop, or an SDK, gets normalized into the same `run(task) -> AgentResult` contract, so the rest of the pipeline never needs to know which agent it's looking at.

## 6. Detailed Pipeline Stages

| Stage                 | Input                                     | Output                                                              | Notes                                                                                                                |
| --------------------- | ----------------------------------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Task loading          | Task suite files (YAML/JSON)              | Validated `TaskSpec` objects                                        | Fail fast on malformed tasks — a bad task definition is worse than a bad agent run                                   |
| Adapter dispatch      | `TaskSpec` + target agent name            | Agent invoked via its `run(task)` wrapper                           | Adapter is the only place that knows agent-specific internals                                                        |
| Instrumentation       | Every LLM/tool call inside the run        | `TraceEvent` records (span tree)                                    | Wrap at the client/tool-call boundary, not inside each agent's internal logic — keeps instrumentation agent-agnostic |
| Deterministic grading | `AgentResult` + `TaskSpec.expected`       | Pass/fail per objective check                                       | No LLM call — this should be the majority of your grading where the domain allows it                                 |
| LLM-judge grading     | `AgentResult` + rubric                    | 0-5 scores per dimension + free-text critique                       | Only for genuinely subjective quality (tone, completeness, reasoning clarity)                                        |
| Trajectory analysis   | Full `TraceEvent` list                    | Failure-mode tags, redundant-call count, sub-agent invocation check | This is where most of the "why did it fail" signal lives                                                             |
| Aggregation           | All `GradingResult`s for a run            | `MetricsReport`                                                     | Per-task and rolled up across the whole suite                                                                        |
| Regression check      | Current `MetricsReport` + stored baseline | `RegressionAlert` (or none)                                         | Runs automatically after every suite execution                                                                       |

## 7. Tech Stack

| Layer                              | Tool                                                                                  | Purpose                                                                                                   |
| ---------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Agent frameworks under test        | LangGraph, raw Python loops, whatever your other projects use                         | The harness must stay framework-agnostic at the adapter boundary                                          |
| Tracing                            | OpenTelemetry conventions (or a lightweight custom span logger)                       | Structured, queryable execution traces                                                                    |
| Judge model                        | Claude Sonnet 5                                                                       | Rubric-based scoring; keep judge and generator model choices logged per run, since judge drift matters    |
| Grading engine                     | Custom Python (pydantic schemas) + `pytest`-style assertions for deterministic checks | Keep deterministic and judge-based grading as separate, independently testable code paths                 |
| Storage                            | SQLite (Postgres if you outgrow it)                                                   | Tasks, runs, traces, grading results, baselines                                                           |
| Dashboard                          | Streamlit or a small React app                                                        | Trend view across agent versions; not required for MVP, worth adding once you have 2+ versions to compare |
| Backend (if exposing as a service) | FastAPI                                                                               | Only needed if you want to trigger runs remotely (e.g., from a CI hook)                                   |

For context, this mirrors the shape of real tools in this space — LangSmith, Braintrust, Arize Phoenix, and DeepEval all follow some version of trace → grade → aggregate → regress, alongside benchmark suites like SWE-Bench and tau-bench for standardized task design. You're not competing with them; you're building enough of the pattern to genuinely understand what they do and to have something concrete to run your own agents through.

## 8. LLM Responsibilities

| Task                                                  | Model           | Input                                                        | Output                                           | Why                                                                                                                                                                                                                                                      |
| ----------------------------------------------------- | --------------- | ------------------------------------------------------------ | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rubric-based judging                                  | Claude Sonnet 5 | Full trajectory (not just final output) + rubric + task spec | Strict JSON: per-dimension 0-5 scores + critique | Judging the trajectory, not just the answer, is what makes this "Agent-as-a-Judge" rather than plain LLM-as-judge — it catches wasted steps and unsafe intermediate actions that output-only scoring misses                                              |
| Failure-mode classification (optional, vs rule-based) | Claude Sonnet 5 | Trace with a detected anomaly (e.g. repeated tool call)      | One of the fixed `FailureMode` enum values       | Only use an LLM here if rule-based detection (see Section 12) can't unambiguously classify it — prefer deterministic detection wherever the pattern is mechanical (e.g., loop detection is just "same tool + same args N times in a row," no LLM needed) |

Keep the judge model choice **logged per run** in the metrics report. If you ever change which model judges your agents, that's itself a change that needs a calibration re-check — a silent judge upgrade can shift your scores independent of any change to the agents being tested.

## 9. Data Schemas

**TaskSpec**
```json
{
  "task_id": "codereview_003",
  "agent_target": "code_review_agent",
  "input": { "pr_diff_path": "data/prs/003.diff" },
  "expected": {
    "injected_issues": [
      { "type": "sql_injection", "line": 42 },
      { "type": "n_plus_one_query", "line": 88 }
    ]
  },
  "grading_strategy": ["deterministic_line_match", "llm_judge_explanation_quality"],
  "difficulty": "medium",
  "tags": ["security", "performance"]
}
```

**TraceEvent** (one per span in the execution)
```json
{
  "trace_id": "run_2026-07-14_001",
  "task_id": "codereview_003",
  "span_id": "span_007",
  "parent_span_id": "span_003",
  "node": "security_agent",
  "type": "tool_call",
  "start_ts": 1752480000123,
  "end_ts": 1752480001876,
  "tokens_in": 412,
  "tokens_out": 88,
  "cost_usd": 0.0031,
  "tool_name": "grep_code",
  "tool_args": { "pattern": "SELECT .* WHERE" },
  "output_summary": "3 matches found",
  "error": null
}
```

**GradingResult**
```json
{
  "task_id": "codereview_003",
  "trace_id": "run_2026-07-14_001",
  "deterministic": {
    "sql_injection_caught": true,
    "n_plus_one_caught": false
  },
  "llm_judge": {
    "accuracy": 4, "completeness": 3, "clarity": 5, "reasoning": 4,
    "overall": 4,
    "critique": "Correctly flagged the SQL injection with a clear fix suggestion; missed the N+1 query entirely."
  },
  "trajectory": {
    "security_agent_invoked": true,
    "redundant_tool_calls": 1,
    "failure_modes": ["missed_issue"]
  },
  "pass": false
}
```

**RegressionAlert**
```json
{
  "agent": "code_review_agent",
  "baseline_version": "v3",
  "current_version": "v4",
  "metric": "success_rate",
  "baseline_value": 0.92,
  "current_value": 0.83,
  "delta": -0.09,
  "threshold": -0.05,
  "triggered": true,
  "likely_component": "security_agent"
}
```

## 10. Adapter Interface

```python
from typing import Protocol, Any
from pydantic import BaseModel

class AgentResult(BaseModel):
    task_id: str
    final_output: Any
    trace: list[TraceEvent]
    total_cost_usd: float
    total_latency_ms: int

class AgentAdapter(Protocol):
    def run(self, task: TaskSpec) -> AgentResult: ...
```

Every agent — Code Review, Deep Research, Financial Analyst, whatever you build next — gets one adapter implementation. The adapter's only job is translating that agent's native input/output shape into `TaskSpec` in, `AgentResult` out. Nothing downstream of the adapter layer should ever need an `if agent_type == ...` branch.

## 11. Grading Design

**Prefer deterministic checks wherever the domain allows it** — test pass/fail, schema validation, exact line-number matches, numeric correctness. These are free, fast, and have zero judge bias. Reach for LLM-as-judge only for genuinely subjective dimensions (explanation clarity, report completeness, reasoning quality).

**Judge calibration procedure** (do this before trusting any judge score):
1. Hand-grade 20-30 trajectories yourself using the same rubric.
2. Run the LLM judge on the same 20-30.
3. Compute agreement (simple % match, or Cohen's kappa if you want to be rigorous) between your labels and the judge's.
4. If agreement is low, the problem is almost always the rubric being ambiguous, not the model being bad — tighten the rubric definitions and re-check before scaling up.

**Known judge biases to actively guard against**: position bias (order of options affects the score), length bias (longer outputs scored higher regardless of quality), and self-preference bias (a model rating outputs from its own model family more favorably). Mitigation: randomize ordering where comparisons are involved, and periodically spot-check judge scores against your own manual read.

**Use a coarse 0-5 scale, not 1-10.** Coarser scales correlate better with human judgment in practice — a 10-point scale mostly adds noise without adding precision, since neither humans nor judges reliably distinguish a "7" from an "8."

**Judge the trajectory, not just the final output.** Give the judge the full execution path — plan, tool calls, reflection steps, final answer — not just the last message. This is the core idea behind "Agent-as-a-Judge": a judge that can see intermediate steps evaluates process quality (wasted calls, unsafe intermediate actions, ignored constraints) that a judge only shown the final answer structurally cannot detect.

## 12. Failure Taxonomy

```python
class FailureMode(str, Enum):
    WRONG_TOOL = "wrong_tool_selection"          # right task, wrong tool, or right tool wrong args
    HALLUCINATED_RESULT = "hallucinated_tool_result"  # treats empty/failed tool output as success
    INFINITE_LOOP = "infinite_loop"              # same tool + same args repeated without adapting
    PREMATURE_TERMINATION = "premature_termination"   # declares done before satisfying the task
    CASCADING_ERROR = "cascading_error"           # one wrong early assumption propagates downstream
    CONTEXT_LOSS = "context_loss"                 # forgets an earlier stated constraint
    MISSED_ISSUE = "missed_issue"                 # domain-specific: failed to catch what it should have
```

Most of these are detectable with simple rules, not an LLM call: `INFINITE_LOOP` is "identical tool name + identical args N times consecutively"; `HALLUCINATED_RESULT` is "tool response was an error/empty but the agent's next step assumes success." Reserve LLM classification for ambiguous cases only — it's slower, costs money, and adds its own error rate to something you're using to measure error rates.

## 13. Evaluating the Evaluator (meta-evaluation)

The harness itself needs a reliability check, or its output is just a number you're trusting blindly:
- **Judge-human agreement rate** from the calibration step in Section 11 — track this over time, not just once.
- **Judge self-consistency** — run the same trajectory through the judge multiple times; if scores swing wildly, the rubric is underspecified.
- **Judge drift** — if you ever change the judge model, re-run the calibration set before comparing new scores against historical baselines. A judge upgrade can look like an agent regression if you're not careful.

## 14. Regression Testing & CI Gating

1. Every suite run produces a `MetricsReport`, stored with a version tag for the agent under test.
2. Before each new run is accepted as a baseline, diff it against the previous stored baseline for that agent.
3. Define per-metric thresholds (e.g., success rate drop > 5 percentage points, cost increase > 50%, or any new `INFINITE_LOOP` occurrences where there were none before) that trigger a `RegressionAlert`.
4. Optionally wire this into a CI hook: any commit touching an agent's prompts/code triggers the suite automatically, and a triggered regression blocks merge until reviewed.

This is the single feature that turns the project from "a script that scores my agent once" into actual infrastructure — the value is in catching regressions you didn't know to look for, not in the one-time baseline number.

## 15. Success Criteria for the Harness Itself (v1)

| Criterion                                                  | Target                                                                                                         |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Adapter works for at least 2 different agent architectures | e.g., a LangGraph agent and a raw-loop agent, proving the abstraction actually generalizes                     |
| Judge-human agreement on calibration set                   | ≥ 80%                                                                                                          |
| Regression detection                                       | Correctly flags a manually-introduced regression (e.g., deliberately break a prompt) in a controlled test      |
| Full trace captured                                        | 100% of LLM/tool calls appear in the trace store for every run — a gap here undermines every downstream metric |
| Report generation                                          | One command produces a full `MetricsReport` + regression status for a given agent version                      |

## 16. Risks & Mitigations

| Risk                                                                                       | Mitigation                                                                                                                              |
| ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| Judge bias masquerading as agent quality signal                                            | Calibration against human labels (Section 11); recalibrate on any judge model change                                                    |
| Instrumentation overhead skewing latency numbers                                           | Keep span logging async/non-blocking; measure and subtract harness overhead from reported agent latency                                 |
| Task suite too small to detect real regressions                                            | Start with at least 10-15 tasks per agent with known expected outcomes, not 2-3                                                         |
| Deterministic checks that are actually too strict (penalizing valid alternative solutions) | Where multiple correct paths exist, design the check around the *outcome* (e.g., "flagged the vulnerable line") not the *exact wording* |
| Scope creep into building a full production observability platform                         | Stick to the v1 non-goals in Section 3.1 — batch eval against a fixed suite first, streaming/production monitoring later                |

## 17. Build Plan

- **Phase 0 (few days)** — Pick 2-3 existing agents to serve as the first adapter targets (Code Review Agent is the natural first choice, since you already scoped its multi-agent structure). Building the harness against zero real agents means testing against nothing.
- **Phase 1 (Week 1)** — Adapter layer + instrumentation. Get `run(task) -> AgentResult` working end to end for one agent, with a full trace captured, before grading anything.
- **Phase 2 (Week 1-2)** — Task suites. Write 10-15 tasks per seed agent with explicit expected outcomes and grading strategy tags.
- **Phase 3 (Week 2)** — Grading engine: deterministic checks first (they're free and fast to validate), then the LLM judge, then run the calibration procedure from Section 11 before trusting it.
- **Phase 4 (Week 3)** — Metrics aggregation + a basic report (even a printed table is fine for v1; a dashboard is a nice-to-have, not a blocker).
- **Phase 5 (Week 3-4)** — Regression engine: store a baseline, deliberately break something in one of your seed agents (bad prompt edit), confirm the harness catches it. This deliberate-break test is the single most convincing thing to show in a demo.

## 18. Resume / Portfolio Framing

- "Built an agent evaluation harness that traces, grades, and regression-tests AI agents across task success, cost, latency, and a formal failure-mode taxonomy — applied it to N of my own agent projects with a calibrated LLM-judge (X% agreement with human labels)."
- "Designed a common adapter interface enabling identical evaluation across differently-architected agents (LangGraph-based and custom-loop), plus a regression detector that catches silent quality drops after prompt/model changes."
- "Implemented trajectory-level evaluation (Agent-as-a-Judge pattern) rather than output-only scoring, surfacing failure modes — tool misselection, hallucinated tool results, infinite loops — invisible to a simple pass/fail check."

## 19. Why This Complements Everything Else in the Portfolio
Every other project on your list produces a demo. This one produces a number, a failure breakdown, and a regression check for every one of those demos — which is the actual difference between "I built an agent" and "I built an agent and I can tell you precisely how reliable it is and why." Build it early enough (right after your first one or two domain agents) and every subsequent project benefits from having a real eval attached from day one instead of retrofitted at the end.