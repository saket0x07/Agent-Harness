# Code Explanation & Change Log

This file details all implementations and holds a history of changes for the **Agent Evaluation Harness** project.

---

## 📂 Project Structure (Phase 4)
```
Agent-Harness/
├── data/
│   └── suites/
│       └── sample_suite.yaml  # Sample task specs YAML (31 tasks)
├── scripts/
│   └── calibrate_judge.py     # Script to calibrate LLM judge MAE error delta
├── src/
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py            # AgentAdapter Protocol interface
│   │   └── mock_agent.py      # MockAgent simulated adapter paths
│   ├── core/
│   │   ├── __init__.py
│   │   └── schemas.py         # Core Pydantic data models
│   ├── storage/
│   │   ├── __init__.py
│   │   └── db.py              # SQLite storage management & schemas
│   ├── loader/
│   │   ├── __init__.py
│   │   └── suite_loader.py    # YAML/JSON task specs loader
│   ├── tracing/
│   │   ├── __init__.py
│   │   └── tracer.py          # Thread-safe context manager / tracing collector
│   ├── grading/
│   │   ├── __init__.py
│   │   ├── grader.py          # GraderEngine orchestrator (det + trajectory)
│   │   └── llm_judge.py       # Subjective rubric rating via google.genai
│   └── runner.py              # Execution runner loop & database integration
├── tests/
│   ├── test_phase1.py         # Automated pytest suite for Phase 1
│   ├── test_phase2.py         # Automated pytest suite for Phase 2
│   ├── test_phase3.py         # Automated pytest suite for Phase 3
│   └── test_phase4.py         # Automated pytest suite for Phase 4
├── main.py                    # CLI entry point (run command)
├── prd.md                     # Product Requirement Document
├── requirements.txt           # Python dependency specifications
├── .gitignore                 # Files to ignore in Git
└── changes_log.md             # This file (Code documentation & history)
```

---

## 🛠️ Code Explanation

### 1. Core Data Models (`src/core/schemas.py`)
Provides runtime validation and type-safety for data moving through the harness:
- **`TraceEvent`**: Represents a single "span" in the execution path. Captures parent-child relationships, durations (`start_ts`, `end_ts`), token usage, estimated costs, tool parameters, and errors.
- **`TaskSpec`**: Defines a single evaluation check, specifying inputs, expected outputs, grading strategies, difficulty, and categorization tags.
- **`AgentResult`**: The standardized output contract returned by an agent adapter when a run completes.
- **`GradingResult`**: Captures evaluation metrics (deterministic, LLM-based, and structural path audits).
- **`MetricsReport`**: Summarizes rolled-up success rate, cost, and latency averages across a task suite run.
- **`RegressionAlert`**: Stores delta comparisons against baseline metrics to signal silent degradations.

### 2. SQLite Database & Storage (`src/storage/db.py`)
Provides persistence using Python's built-in `sqlite3` engine:
- **`init_db`**: Establishes schema tables for `tasks`, `runs`, `traces` (with index optimization on `trace_id`), `grading_results`, and `baselines`.
- **`save_task`**, **`save_run`**, **`save_trace_events`**, **`save_grading_result`**: Write operations mapping Pydantic specs and payloads into equivalent relational rows.
- **`get_baseline`** & **`set_baseline`**: Manages performance baselines to enable version comparison over time.

### 3. Task Suite Loader (`src/loader/suite_loader.py`)
- **`load_task_file`**: Parses JSON, YAML, and YML files. Supports single task specs or list declarations, validating contents against `TaskSpec`.
- **`load_task_suite`**: Reads individual task files or recursive folder contents, optionally inserting valid tasks into SQLite.

### 4. Agent Adapter Interface & Mock Implementation (`src/adapters/`)
- **`AgentAdapter` (`base.py`)**: A runtime-checkable Protocol defining the single entry-point execution contract `run(task) -> AgentResult`. Ensures framework-agnostic testing of any agent pipeline.
- **`MockAgentAdapter` (`mock_agent.py`)**: Conforming to the protocol, this adapter simulates various agent execution paths (`success`, `infinite_loop`, `fail_tool`, `premature_termination`), enabling testing of loop detection, trace logging, and traceback capturing.

### 5. Thread-Safe Instrumentation (`src/tracing/tracer.py`)
- **`TraceCollector`**: Thread-local execution collector tracking nested, concurrent agent executions without context bleed.
- **`trace_span`**: Context manager that nests parent-child spans, measures start/end latencies, captures error tracebacks on exceptions, and calculates total run costs and tokens.

### 6. Suite Execution Runner (`src/runner.py`)
- **`execute_suite`**: orchestrates benchmark task suite runs for a target agent. Loads task specifications, instantiates and dispatches to the correct adapter (registered in `ADAPTER_REGISTRY`), tracks run metadata, handles errors, conducts deterministic keyword matching checks, aggregates metric reports, and saves everything to SQLite.

### 7. Primary CLI (`main.py`)
- CLI built using `click` and styled with `rich` panels and tables. Exposes `python main.py run --suite <path> --agent <agent_name>` to trigger benchmark suite runs and display real-time progress and summary tables. Includes Windows console encoding reconfigure support.

### 8. Grading Engine (`src/grading/`)
- **`GraderEngine` (`grader.py`)**: Central grading orchestrator conducting deterministic audits (checks required keywords, count headings/sections, and parses citations for bracket tags or hyperlinks) and path checks (finds repeating tool-call loops and premature terminations).
- **`llm_judge.py`**: Invokes modern Google `gemini-2.5-flash` model via the `google.genai` SDK using strict Pydantic JSON schema configurations (`JudgeScore`). Returns fallback scores if `GEMINI_API_KEY` environment variable is not populated.

### 9. Judge Calibration Utility (`scripts/calibrate_judge.py`)
- Standard CLI script designed to import the LLM judge and calculate its Mean Absolute Error (MAE) score against manual, human-graded scores on baseline write-ups. Resolves console Unicode errors on Windows systems.

---

## 📝 Change Log

### **2026-07-14 (Phase 1 Baseline)**
- **Feature**: Initial workspace setup and core data model implementation.
  - Added Pydantic schemas in `src/core/schemas.py`.
  - Added SQLite schema initialization and database operation wrappers in `src/storage/db.py`.
  - Added file-loader supporting JSON/YAML task specs parsing and validation in `src/loader/suite_loader.py`.
- **Testing**: Added pytest integration in `tests/test_phase1.py`.
  - Verified Pydantic models validate raw JSON dictionaries correctly.
  - Verified SQLite table structures insert and query values properly.
  - Verified loader accurately parses single files and directories, checking error cases.
- **Result**: All tests executed and passed (`3 passed in 0.35s`).

### **2026-07-14 (Blog Researcher Suite Addition)**
- **Task Suite**: Overwrote `data/suites/sample_suite.yaml` to specify a comprehensive **30-task suite** tailored for the **Agentic Blog Researcher and Writer** agent (covering Tech/AI, Finance/Market, Reviews, Tutorials, and Industry Trends, including custom difficulty weights and grading strategies metadata).
  - Completed the *Product & Comparison Reviews* section (tasks `007` and `008`) and the *Tutorials & How-To* section (task `004`) to hit the full 30-task suite.
- **Result**: Verified that the loader successfully validates all 30 tasks against the `TaskSpec` schema (verified via test suite execution).

### **2026-07-14 (Phase 2 - Adapters & Instrumentation)**
- **Adapters**:
  - Implemented `AgentAdapter` Protocol class in `src/adapters/base.py` and decorated it with `@runtime_checkable` for dynamic typing support.
  - Implemented `MockAgentAdapter` in `src/adapters/mock_agent.py` to simulate four testable behaviors (`success`, `infinite_loop`, `fail_tool`, `premature_termination`).
- **Tracing**:
  - Implemented thread-safe `TraceCollector` using thread-local storage in `src/tracing/tracer.py`.
  - Implemented `trace_span` context manager which nests traces (parent/child relationships), tracks token cost and execution latencies, and formats traceback strings upon failure.
- **Testing**: Added pytest integration in `tests/test_phase2.py`.
  - Verified `MockAgentAdapter` protocol compliance.
  - Tested nested child parent span resolution, thread-safety separation (concurrent isolation), and exception capturing.
  - Verified adapter mock run paths capture traces.
- **Result**: All Phase 1 & 2 tests passed (`8 passed in 0.31s`).

### **2026-07-14 (Phase 3 - CLI Runner & Database Integration)**
- **Runner**:
  - Implemented `execute_suite` in `src/runner.py`. Routes agents to adapters via registry, initializes SQLite schemas, executes tasks, applies deterministic keyword grading, aggregates `MetricsReport`, and writes traces, results, and run statistics to SQLite.
  - Refined `TraceCollector` in `src/tracing/tracer.py` to support nested tracking.
- **CLI**:
  - Created `main.py` entry point. Implemented `click` commands for `run` with `rich` UI elements. Configured fallback encoding settings to prevent encoding errors on standard Windows terminals when rendering Unicode emoji symbols.
- **Testing**: Added `tests/test_phase3.py` verifying full end-to-end suite runner flow, CLI command invoke, trace persistence count, and SQLite row updates.
- **Result**: All 9 unit tests passed successfully, and the CLI execution completes end-to-end runs of the 31-task suite with clean formatting.

### **2026-07-14 (Phase 4 - Deterministic & LLM-as-Judge Grading Engine)**
- **Grader Engine**:
  - Implemented `GraderEngine` inside `src/grading/grader.py` conducting keyword presence checks, markdown heading section counts, and citation format verification (brackets/links).
  - Built trajectory auditing identifying repeating tool invocation loops (consecutive tool+args >= 3) and premature shutdowns.
  - Integrated `GraderEngine` into `src/runner.py` task execution loops.
- **LLM Judge**:
  - Built `llm_judge.py` using `google.genai` SDK and Pydantic schemas for structured grading inputs via Gemini.
  - Added offline mock fallback when `GEMINI_API_KEY` is not present in the shell.
- **Calibration**:
  - Created `scripts/calibrate_judge.py` comparing LLM judge metrics against manual annotations and compiling MAE delta reports.
- **Testing**:
  - Created `tests/test_phase4.py` verifying keyword triggers, citation searches, loop traces, premature timeouts, and offline score responses.
- **Result**: All 15 unit tests pass successfully, and calibration metrics execute with zero warning flags.



