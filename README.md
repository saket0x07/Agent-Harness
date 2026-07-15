# Agent-Harness 🤖

> **Evaluate, trace, and regression-test AI agents with deterministic and LLM-judge grading at scale.**

An evaluation platform that runs AI agents against benchmark task suites, captures their complete execution trace (not just the final answer), and scores them on task success, cost, latency, and failure modes. Built to detect silent regressions before they hit production.

## 📋 Overview

Evaluating a model is straightforward: one input, one output, compare against a label or a human judge. Evaluating an **agent** is fundamentally different—agents don't produce answers, they produce **trajectories**: sequences of decisions, tool calls, reflections, and pivots.

Agent-Harness solves the core problem: **How do you know if your agent is actually getting better, or just getting different?**

### Key Capabilities

- 🔍 **Full Execution Tracing** — Capture every LLM call, tool call, and state transition with token counts, cost, and latency
- 🎯 **Multi-Level Grading** — End-to-end success, trajectory soundness, and component-level failure classification
- 🚨 **Regression Detection** — Automatically compare agent versions to catch silent quality drops
- 📊 **Rich Taxonomy** — Classify failures systematically (wrong tool, infinite loops, hallucination, context loss, etc.)
- 🔌 **Framework Agnostic** — Adapter interface works with LangGraph, raw Python loops, or any agent architecture
- 📈 **Metrics & Reports** — Success rate, average cost/latency, failure-mode distribution, and trend analysis

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- SQLite3 (included with Python)

### Installation

```bash
git clone https://github.com/saket0x07/Agent-Harness.git
cd Agent-Harness
pip install -r requirements.txt
```

### Basic Usage

#### Run a Task Suite

```bash
python main.py run \
  --suite data/tasks/code_review_suite.yaml \
  --agent code_review_agent \
  --version v1.0 \
  --db data/harness.db
```

**Options:**
- `--suite, -s` — Path to YAML/JSON task suite file or directory *(required)*
- `--agent, -a` — Target agent identifier *(required)*
- `--version, -v` — Version tag for the agent configuration (default: `v1.0`)
- `--db, -d` — Path to SQLite database (default: `data/harness.db`)
- `--limit, -l` — Maximum number of tasks to execute (optional)

#### Interactive Evaluation

Run a single custom query interactively and get immediate feedback:

```bash
python main.py interactive \
  --agent code_review_agent \
  --version v1.0-dev \
  --db data/harness.db
```

This will prompt you for:
- Blog topic/title
- Target audience
- Expected keywords (optional)

**Options:**
- `--no-judge` — Skip LLM-as-Judge scoring; use deterministic checks only

---

## 🏗️ Architecture

```
Task Suite (YAML/JSON)
    ↓
Agent Adapter Layer (unified interface)
    ↓
Instrumented Execution (full trace capture)
    ↓
Trace Store (SQLite)
    ↓
Grading Engine (deterministic + LLM judge)
    ↓
Metrics Aggregator (success rate, cost, latency)
    ↓
Regression Engine (version comparison)
    ↓
Report & Dashboard
```

### Core Components

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| **Adapter Layer** | Wraps agents behind common `run(task) -> AgentResult` interface | `src/runner.py` |
| **Instrumentation** | Captures every LLM/tool call as `TraceEvent` spans | `src/core/instrumentation.py` |
| **Storage** | Structured, queryable execution logs in SQLite | `src/storage/db.py` |
| **Grading** | Deterministic checks + LLM-as-Judge scoring | `src/grading/grader.py` |
| **Metrics** | Aggregates results into `MetricsReport` | `src/metrics/aggregator.py` |

---

## 📝 Task Suite Format

Tasks are defined in YAML or JSON. Here's an example:

```yaml
task_id: "codereview_001"
agent_target: "code_review_agent"
input:
  pr_diff_path: "data/prs/001.diff"
expected:
  injected_issues:
    - type: "sql_injection"
      line: 42
    - type: "n_plus_one_query"
      line: 88
grading_strategy:
  - "deterministic_line_match"
  - "llm_judge_explanation_quality"
difficulty: "medium"
tags:
  - security
  - performance
```

### TaskSpec Fields

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Unique identifier for the task |
| `agent_target` | string | Name of the agent to evaluate |
| `input` | dict | Agent input (task-specific structure) |
| `expected` | dict | Expected outcome for grading |
| `grading_strategy` | list | Which grading methods to apply |
| `difficulty` | string | Task difficulty: `easy`, `medium`, or `hard` |
| `tags` | list | Task categories for analysis |

---

## 🔍 Tracing & Execution Flow

When an agent runs, every action is captured as a `TraceEvent`:

```json
{
  "trace_id": "run_2026-07-14_001",
  "task_id": "codereview_001",
  "span_id": "span_042",
  "parent_span_id": "span_040",
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

The trace is a **tree of spans**, where each span represents:
- An LLM call (with model, tokens, cost)
- A tool invocation (with arguments and output)
- A state transition or decision point
- A sub-agent execution

This enables deep debugging: you don't just know the agent failed, you know *which step* failed, *how long it took*, and *what it cost*.

---

## 🎯 Grading System

### Two-Tier Grading

#### 1. **Deterministic Checks** (Preferred)
No LLM call required—fast, free, and unbiased:

- ✅ Does the output match an expected schema?
- ✅ Were required fields populated?
- ✅ Did the agent flag all injected security issues?
- ✅ Is the numerical result within acceptable tolerance?

#### 2. **LLM-as-Judge** (For Subjective Quality)
Use Claude Sonnet 5 for dimensions without objective ground truth:

- Does the explanation make sense?
- Is the writing clear and well-structured?
- Did the agent show its reasoning?

**Design principle:** Deterministic checks should be the majority of your grading pipeline. LLM judge is only for genuinely subjective dimensions.

### Judge Calibration

Before trusting any LLM judge scores:

1. **Hand-grade 20–30 trajectories** yourself using the same rubric
2. **Run the LLM judge** on the same 20–30
3. **Calculate agreement** (simple % match or Cohen's kappa)
4. **Iterate on the rubric** if agreement is low (ambiguous rubric is the usual culprit, not a bad model)

Only scale up grading after achieving ≥80% agreement.

---

## 📊 Failure Taxonomy

Classify failures systematically instead of binary pass/fail:

| Failure Mode | Pattern | Example |
|--------------|---------|---------|
| `WRONG_TOOL` | Selected correct tool but with wrong args, or wrong tool altogether | Searching for code smell when you need to check syntax |
| `HALLUCINATED_RESULT` | Treated empty/error tool output as success | Tool returned "error: not found" but agent proceeded as if found |
| `INFINITE_LOOP` | Repeated same tool + same args without adapting | Tried grep 5 times with identical arguments |
| `PREMATURE_TERMINATION` | Declared done before satisfying the task | Stopped after finding 1 issue when task required 3 |
| `CASCADING_ERROR` | One wrong early assumption propagates downstream | Misidentified file type; all downstream analysis invalid |
| `CONTEXT_LOSS` | Forgot earlier stated constraints | Ignored "security-critical code only" constraint mid-run |
| `MISSED_ISSUE` | Failed to catch what it should have (domain-specific) | Code review agent missed the SQL injection entirely |

Most modes are detectable with simple rules (no LLM call needed):
- `INFINITE_LOOP` = identical tool name + args N times consecutively
- `HALLUCINATED_RESULT` = tool returned error but agent used the output
- `PREMATURE_TERMINATION` = trace ends before expected checks complete

---

## 📈 Metrics & Reports

After each run, you get a `MetricsReport`:

```json
{
  "agent_name": "code_review_agent",
  "agent_version": "v1.0",
  "run_id": "run_2026-07-14_001",
  "timestamp": "2026-07-14T15:30:00Z",
  "total_tasks": 15,
  "success_rate": 0.87,
  "average_cost_usd": 0.0412,
  "average_latency_ms": 3240,
  "failure_mode_counts": {
    "missed_issue": 2,
    "infinite_loop": 1
  },
  "detailed_results": [
    { "task_id": "codereview_001", "is_pass": true, ... },
    { "task_id": "codereview_002", "is_pass": false, ... }
  ]
}
```

Reports include:
- **Success rate** — % of tasks passed
- **Cost per run** — Aggregated LLM + tool usage
- **Latency** — E2E execution time
- **Failure breakdown** — Which failure modes occurred most
- **Per-task details** — Trace IDs for deep debugging

---

## 🚨 Regression Detection

Define thresholds for significant drops:

```yaml
regression_thresholds:
  success_rate_drop: 0.05          # Alert if success rate drops >5%
  cost_increase_percent: 50        # Alert if avg cost increases >50%
  new_infinite_loops: 1            # Alert if any new infinite loops occur
  new_failure_modes: true          # Alert if new failure modes appear
```

On each run, the harness compares against the previous baseline:

```
Baseline (v1.0): 92% success, $0.035 avg cost
Current (v1.1):  83% success, $0.052 avg cost
→ REGRESSION TRIGGERED: success_rate dropped 9% (threshold: 5%)
```

This is the feature that turns a one-off eval script into production infrastructure.

---

## 🔌 Building Adapters

### Adapter Interface

Every agent (regardless of framework) gets one adapter:

```python
from src.core.schemas import TaskSpec, AgentResult, TraceEvent

class MyAgentAdapter:
    def run(self, task: TaskSpec) -> AgentResult:
        """
        Execute the task and return the result with full trace.
        
        Args:
            task: The task spec with input, expected outcome, grading strategy
            
        Returns:
            AgentResult with:
              - final_output: The agent's answer
              - trace: List of TraceEvent spans capturing every LLM/tool call
              - total_cost_usd: Total API cost for this run
              - total_latency_ms: Total wall-clock time
        """
        # 1. Initialize agent with task inputs
        # 2. Set up instrumentation hook to capture spans
        # 3. Run the agent's main loop
        # 4. Collect trace events from instrumentation
        # 5. Return AgentResult
        pass
```

### Registration

Register adapters in the `ADAPTER_REGISTRY`:

```python
from src.runner import ADAPTER_REGISTRY

ADAPTER_REGISTRY["my_agent"] = MyAgentAdapter
```

---

## 📂 Project Structure

```
Agent-Harness/
├── main.py                          # CLI entry point (run, interactive)
├── requirements.txt                 # Dependencies
├── README.md                         # This file
├── prd.md                            # Full product requirements
├── changes_log.md                    # Changelog
│
├── src/
│   ├── core/
│   │   ├── schemas.py                # Pydantic models (TaskSpec, AgentResult, etc.)
│   │   ├── instrumentation.py        # Span capture & tracing
│   │   └── interfaces.py             # Abstract interfaces
│   │
│   ├── storage/
│   │   ├── db.py                     # SQLite schema & queries
│   │   └── migrations.py             # Schema versions
│   │
│   ├── grading/
│   │   ├── grader.py                 # Deterministic + LLM judge
│   │   ├── deterministic.py          # Rule-based checks
│   │   └── judge.py                  # Claude-based judging
│   │
│   ├── metrics/
│   │   └── aggregator.py             # MetricsReport generation
│   │
│   ├── runners/
│   │   ├── code_review_adapter.py    # Code Review Agent adapter
│   │   ├── research_adapter.py       # Research Agent adapter
│   │   └── registry.py               # Adapter registration
│   │
│   └── runner.py                    # Suite orchestration & execution
│
├── tests/
│   ├── test_adapters.py             # Adapter tests
│   ├── test_grading.py              # Grading engine tests
│   └── test_regression.py           # Regression detection tests
│
├── data/
│   ├── tasks/                       # Task suite YAML/JSON files
│   │   └── example_suite.yaml
│   ├── prs/                         # Test data (PR diffs, etc.)
│   └── harness.db                   # SQLite database
│
└── scripts/
    ├── view_traces.py               # Query & display execution traces
    ├── compare_versions.py          # Compare two agent versions
    └── calibrate_judge.py           # Judge calibration tool
```

---

## 🛠️ Dependencies

| Package | Purpose |
|---------|---------|
| `pydantic>=2.0` | Data validation & serialization |
| `pyyaml>=6.0` | Task suite parsing |
| `click>=8.0` | CLI framework |
| `rich>=13.0` | Pretty terminal output |
| `python-dotenv>=1.0.0` | Environment variable management |
| `requests>=2.20.0` | HTTP client |
| `google-genai>=0.1.0` | Google Gemini API |
| `langchain-core>=0.2.0` | LangChain core |
| `langchain-openai>=0.1.0` | OpenAI integration |
| `langgraph>=0.1.0` | LangGraph (for graph-based agents) |
| `tavily-python>=0.3.0` | Web search tool |
| `pillow>=10.0.0` | Image processing |
| `huggingface_hub>=0.33.0` | HuggingFace model access |
| `streamlit>=1.35.0` | Web dashboard (optional) |
| `fastapi>=0.100.0` | REST API backend (optional) |
| `uvicorn>=0.23.0` | ASGI server (optional) |

---

## 📚 Examples

### Example 1: Evaluating a Code Review Agent

```bash
# Run code review agent against 15 security + performance tasks
python main.py run \
  --suite data/tasks/code_review_full.yaml \
  --agent code_review_agent \
  --version v1.2 \
  --limit 15

# Output:
# ┌─ Suite Run Outcomes: run_2026_07_14_001 ─┐
# │ Task ID           Passed  Spans Captured │
# │ codereview_001    Yes     24              │
# │ codereview_002    No      19              │
# │ ...                                      │
# └────────────────────────────────────────────┘
# Success Rate: 86.7%
```

### Example 2: Interactive Evaluation

```bash
python main.py interactive --agent blog_writer_agent --no-judge

# Prompts:
# ✍️ Enter the blog topic/title: "How to Build Reliable AI Agents"
# 👥 Enter target audience: "ML Engineers"
# 🔑 Enter expected keywords (comma-separated): "evaluation,tracing,regression"

# Output:
# 🚀 Running interactive task: interactive_a1b2c3...
# ...
# 🏁 Execution Completed
# Outcome: Passed
# ⏱️ Latency: 4521ms | 💳 Cost: $0.01234
```

### Example 3: Regression Detection

```bash
# Previous run (baseline)
python main.py run --suite tasks.yaml --agent my_agent --version v1.0

# After a prompt change
python main.py run --suite tasks.yaml --agent my_agent --version v1.1

# Output:
# ⚠️  REGRESSION DETECTED:
# Metric: success_rate
# v1.0:  92%
# v1.1:  83%
# Delta: -9% (threshold: -5%)
# Likely Component: retrieval_agent
```

---

## 🔧 Configuration

Create a `.env` file for API keys and configuration:

```bash
# LLM Models
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...

# Judge Model (Claude Sonnet 5)
JUDGE_MODEL=claude-3-5-sonnet-20241022

# Database
HARNESS_DB_PATH=data/harness.db

# Regression Thresholds
REGRESSION_SUCCESS_RATE_THRESHOLD=-0.05
REGRESSION_COST_THRESHOLD=0.50
```

---

## 📊 Querying Results

### View Execution Trace

```bash
python scripts/view_traces.py --run-id run_2026_07_14_001 --format tree

# Output:
# trace_2026_07_14_001
# ├── [LLM] OpenAI GPT-4 (412 tokens in, 88 out) [5.2ms] [$0.0031]
# │   ├── [TOOL] grep_code (match: 3 results) [1.2ms] [$0.0000]
# │   └── [TOOL] analyze_syntax (error) [0.8ms] [$0.0000]
# └── [LLM] Claude Sonnet (200 tokens in, 45 out) [3.1ms] [$0.0018]
```

### Compare Two Agent Versions

```bash
python scripts/compare_versions.py \
  --agent code_review_agent \
  --version-a v1.0 \
  --version-b v1.1

# Output:
# ┌─ Comparison: v1.0 vs v1.1 ──────┐
# │ Metric                v1.0   v1.1  Δ     │
# │ Success Rate          92%    83%   -9%   │
# │ Avg Cost              $0.035 $0.052 +49% │
# │ Avg Latency           2.4s   3.1s  +29%  │
# │ Missed Issues         1      3     ↑     │
# │ Infinite Loops        0      1     ↑     │
# └────────────────────────────────────────┘
```

### Judge Calibration

```bash
python scripts/calibrate_judge.py \
  --hand_graded_file data/calibration_set.json \
  --judge_results data/judge_results.json

# Output:
# Judge-Human Agreement: 84%
# Cohen's Kappa: 0.79
# Status: APPROVED (≥80% threshold met)
```

---

## 🧪 Testing

Run the test suite:

```bash
pytest tests/ -v

# Run specific test module
pytest tests/test_grading.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

---

## 📈 Success Criteria (v1)

- [x] Adapter works for 2+ different agent architectures (LangGraph + raw loop)
- [x] Judge-human agreement ≥ 80% on calibration set
- [x] Regression detection catches manually-introduced regressions
- [x] Full trace captured (100% of LLM/tool calls in trace store)
- [x] Report generation (`MetricsReport` + regression status)

---

## 🚀 Roadmap

### Phase 1: MVP (Current)
- ✅ Adapter layer + instrumentation
- ✅ Task suite loading & execution
- ✅ Deterministic grading
- ✅ LLM-as-Judge implementation
- ✅ Metrics aggregation & reporting
- ✅ Regression detection

### Phase 2: Observability
- Interactive dashboard (Streamlit)
- Trace visualization
- Trend analysis across versions
- Judge calibration UI

### Phase 3: Production Ready
- REST API for remote runs
- CI/CD integration (GitHub Actions, etc.)
- Automatic baseline management
- Alert on regression triggers

### Phase 4: Advanced Analytics
- Failure pattern clustering
- Anomaly detection
- Trajectory-based fine-tuning data export
- RL reward signal generation

---

## 💡 Key Insights

> **The core value isn't in the first score—it's in catching when things get worse.**

Regressions are silent. A prompt change that seems like an improvement can quietly reduce success rate by 10% across a test suite, and you won't notice until a user complains. This harness makes that detection automatic.

> **Judge the trajectory, not just the final output.**

If an agent got the right answer but for the wrong reasons (hallucinated intermediate steps, missed a critical reasoning step), you need to know. Full trace grading surfaces this.

> **Deterministic checks scale, LLM judge calibrates.**

Use rules for anything objective (test pass/fail, schema validation, exact matches). Use the judge only for subjective quality—and only after calibrating against human labels.

---

## 📝 License

MIT License — See LICENSE file for details.

---

## 👤 Author

Built by [@saket0x07](https://github.com/saket0x07)

---

## 🤝 Contributing

Contributions welcome! To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit changes (`git commit -m "Add your feature"`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## 📞 Support

For issues, questions, or feedback:
- Open an issue on GitHub
- Check the [PRD](prd.md) for detailed requirements
- Review [changes_log.md](changes_log.md) for recent updates

---

**Last Updated:** July 15, 2026  
**Status:** Active Development (MVP Phase)
