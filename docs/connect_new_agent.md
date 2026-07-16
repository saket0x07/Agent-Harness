# Connecting and Tracking a New Agent Project

This guide provides a step-by-step overview of how to connect and track a new agent project using the Agent Evaluation Harness.

---

## Step 1: Define a Task Suite

First, create a JSON or YAML file containing the tasks you want to test and grade the agent on. This file should be placed under the task suites directory (e.g., in a directory like `data/` or a dedicated `data/suites/` directory).

Each task in the file must conform to the `TaskSpec` schema:
*   `task_id`: A unique identifier for the task.
*   `agent_target`: The identifier/name string of your target agent (e.g., `my_new_agent`).
*   `input`: Input parameters that your agent will receive (e.g., query, parameters, files).
*   `expected`: Expected outcomes, keywords, or constraints used by the grader to verify correctness.
*   `grading_strategy`: An array of grading modes to apply, such as `deterministic_keyword_match` or `llm_judge_technical_accuracy`.
*   `difficulty`: `easy`, `medium`, or `hard`.
*   `tags`: Category tags for filtering runs.

### Example Task Suite (`data/my_new_agent_suite.yaml`)

```yaml
tasks:
  - task_id: "task_001"
    agent_target: "my_new_agent"
    input:
      query: "Analyze current market trends for EV vehicles in 2026."
      output_format: "bullet_points"
    expected:
      required_keywords:
        - "EV"
        - "market"
        - "2026"
      min_sections: 1
    grading_strategy:
      - "deterministic_keyword_match"
      - "llm_judge_technical_accuracy"
    difficulty: "medium"
    tags:
      - "market_analysis"
      - "ev"
```

---

## Step 2: Implement a Custom Agent Adapter

The Harness decouples the evaluation logic from the underlying framework (LangGraph, AutoGen, CrewAI, Custom Loop, etc.) using adapters. 

1. Create a new adapter file under `src/adapters/` (e.g., `src/adapters/my_new_agent_adapter.py`).
2. Inherit from the `AgentAdapter` protocol class defined in `src/adapters/base.py`.
3. Implement the `run` method, ensuring you collect traces (nodes/spans) using the `TraceCollector` context manager and return an `AgentResult` object.

### Example Adapter Implementation

```python
import sys
import os
import time
from typing import Dict, Any
from dotenv import load_dotenv

# 1. Setup path/env to reference the new agent project codebase
NEW_PROJECT_PATH = "D:/Fxis.ai/FX_NewProject"
if NEW_PROJECT_PATH not in sys.path:
    sys.path.append(NEW_PROJECT_PATH)

# Load configuration/environment variables for the new project
load_dotenv(os.path.join(NEW_PROJECT_PATH, ".env"))

from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

class MyNewAgentAdapter(AgentAdapter):
    """Adapter wrapper for My New Agent project."""
    
    def run(self, task: TaskSpec) -> AgentResult:
        # Delay import to run-time to avoid build issues
        from my_new_agent.main import run_my_agent_graph
        
        start_time = time.time()
        query = task.input.get("query")
        
        if not query:
            raise ValueError("Task input is missing 'query'.")
            
        final_output = ""
        
        # 2. Collect step-by-step traces using TraceCollector
        with TraceCollector() as tc:
            try:
                # Run the agent steps/workflow (modify this to match your project's run cycle)
                # Example: Streaming agent graph nodes
                for step_name, step_result in run_my_agent_graph(query):
                    with trace_span(node=step_name, type="state_transition") as span:
                        span["output_summary"] = str(step_result)[:500]
                        span["tokens_out"] = len(str(step_result)) // 4
                        span["cost_usd"] = (span["tokens_out"] / 1000) * 0.0015
                        
                        # Store output
                        if step_name == "final_node":
                            final_output = step_result.get("response")
                            
            except Exception as e:
                with trace_span(node="agent_error", type="error") as span:
                    span["error"] = str(e)
                final_output = f"Execution failed: {str(e)}"
                
            collected_traces = list(TraceCollector.get_events())
            
        end_time = time.time()
        total_latency_ms = int((end_time - start_time) * 1000)
        total_cost = sum(event.cost_usd for event in collected_traces if event.cost_usd is not None)
        
        if not final_output:
            final_output = "No content generated."
            
        # 3. Return the normalized AgentResult
        return AgentResult(
            task_id=task.task_id,
            final_output=final_output,
            trace=collected_traces,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency_ms
        )
```

---

## Step 3: Register the Adapter

Register your new adapter in the harness registry so the CLI and runners can locate it.

Open `src/runner.py` and:
1. Import your adapter class.
2. Add your new agent mapping to `ADAPTER_REGISTRY`:

```python
# In src/runner.py:
from src.adapters.my_new_agent_adapter import MyNewAgentAdapter  # <-- Import here

ADAPTER_REGISTRY = {
    "blog_researcher_writer_agent": BlogWriterAPIAdapter,
    "blog_researcher_writer_agent_local": BlogWriterAdapter,
    "my_new_agent": MyNewAgentAdapter,                           # <-- Register here
    "mock": MockAgentAdapter
}
```

---

## Step 4: Run the Evaluation

You can run the suite or evaluate interactively from the command line:

### 1. Running the entire suite:
```powershell
python main.py run --suite data/my_new_agent_suite.yaml --agent my_new_agent --version v1.0
```

### 2. Running an Interactive Single Query:
```powershell
python main.py interactive --agent my_new_agent --version v1.0-interactive
```

---

## Step 5: Analyze and Monitor

Once the runs complete:
1. **Metrics & Results Database**: The logs, success rate, token costs, latencies, and LLM judge critiques are saved to SQLite (default path is `data/harness.db`).
2. **Reviewing Traces**: Run the trace viewer script to inspect span-by-span executions:
   ```powershell
   python scripts/view_traces.py
   ```

---

## Example: Testing a LangChain RAG-based Chatbot Running on Port 8000

If you have a LangChain RAG-based chatbot running as an API server (e.g., using FastAPI, LangServe, etc.) on port `8000` (e.g., at endpoint `http://localhost:8000/chat`), you can connect and track it by doing the following:

### 1. Create the RAG Task Suite (`data/rag_chatbot_suite.yaml`)
Define a suite targeting the RAG agent (`rag_chatbot_agent`) with specific questions and expectations (e.g. required sources, retrieved documents, keywords).

```yaml
tasks:
  - task_id: "rag_task_001"
    agent_target: "rag_chatbot_agent"
    input:
      question: "How do I setup a custom LLM model in the LangChain project?"
    expected:
      required_keywords:
        - "LLM"
        - "LangChain"
      must_have_citations: true
    grading_strategy:
      - "deterministic_keyword_match"
      - "llm_judge_technical_accuracy"
    difficulty: "easy"
    tags:
      - "rag"
      - "setup"
```

### 2. Implement the API Adapter (`src/adapters/rag_chatbot_api.py`)
Create a custom adapter that sends HTTP POST requests to the local server and traces the result. If the API returns intermediate retrieval logs (like document search latencies or chunks retrieved), parse them to populate trace spans.

```python
import os
import time
import requests
from typing import Dict, Any

from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

class RAGChatbotAPIAdapter(AgentAdapter):
    """Adapter for RAG chatbot project running on localhost:8000."""

    def __init__(self, api_url: str = None):
        # Default endpoint for the LangChain project server
        self.api_url = api_url or os.environ.get("RAG_CHATBOT_API_URL", "http://localhost:8000/chat")

    def run(self, task: TaskSpec) -> AgentResult:
        start_time = time.time()
        question = task.input.get("question")

        if not question:
            raise ValueError("Task input is missing 'question'.")

        final_output = ""

        # Collect execution traces
        with TraceCollector() as tc:
            # Span representing the API HTTP request execution
            with trace_span(node="http_request", type="api_call") as request_span:
                request_span["output_summary"] = f"Sending request to: {self.api_url}"
                
                try:
                    payload = {"question": question}
                    response = requests.post(self.api_url, json=payload, timeout=30)
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Extract final answer
                        final_output = data.get("answer") or data.get("response") or ""
                        
                        # Trace the retrieval step if metadata is provided by the server
                        retrieved_docs = data.get("source_documents", [])
                        with trace_span(node="retriever", type="tool_call") as retrieval_span:
                            retrieval_span["output_summary"] = f"Retrieved {len(retrieved_docs)} source documents."
                            retrieval_span["tool_args"] = {"docs": [str(d)[:100] for d in retrieved_docs]}
                            
                        # Trace the LLM generation step
                        llm_meta = data.get("llm_metadata", {})
                        with trace_span(node="llm_generation", type="llm_call") as llm_span:
                            llm_span["tokens_in"] = llm_meta.get("prompt_tokens")
                            llm_span["tokens_out"] = llm_meta.get("completion_tokens")
                            llm_span["cost_usd"] = llm_meta.get("cost", 0.0)
                            
                    else:
                        request_span["error"] = f"API responded with status {response.status_code}: {response.text}"
                        final_output = f"API Error {response.status_code}"
                except Exception as e:
                    request_span["error"] = f"Failed to connect to chatbot server: {str(e)}"
                    final_output = f"Connection failure: {str(e)}"

            collected_traces = list(TraceCollector.get_events())

        end_time = time.time()
        total_latency_ms = int((end_time - start_time) * 1000)
        total_cost = sum(event.cost_usd for event in collected_traces if event.cost_usd is not None)

        return AgentResult(
            task_id=task.task_id,
            final_output=final_output,
            trace=collected_traces,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency_ms
        )
```

### 3. Register the RAG Adapter (`src/runner.py`)
Import and add the adapter to the mapping registry in `src/runner.py`:
```python
from src.adapters.rag_chatbot_api import RAGChatbotAPIAdapter

ADAPTER_REGISTRY = {
    # ... other agents ...
    "rag_chatbot_agent": RAGChatbotAPIAdapter,
}
```

### 4. Start the Chatbot & Run Evaluation
1. Start your LangChain project server on port 8000:
   ```powershell
   # Run the server command inside your chatbot project folder
   python main.py  # or uvicorn app.main:app --port 8000
   ```
2. Execute the evaluation suite in the Agent Harness:
   ```powershell
   python main.py run --suite data/rag_chatbot_suite.yaml --agent rag_chatbot_agent --version v1.0
   ```

