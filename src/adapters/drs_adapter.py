import os
import time
import requests
from typing import Dict, Any

from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

class DRSAdapter(AgentAdapter):
    """Adapter for Document Retrieval System (DRS) running on port 8000."""

    def __init__(self, api_url: str = None):
        self.api_url = api_url or os.environ.get("DRS_API_URL", "http://localhost:8000/ask")

    def run(self, task: TaskSpec) -> AgentResult:
        start_time = time.time()
        
        # Support question, query, or topic
        question = task.input.get("question") or task.input.get("query") or task.input.get("topic")
        if not question:
            raise ValueError("Task input is missing 'question', 'query', or 'topic'.")

        final_output = ""
        
        with TraceCollector() as tc:
            try:
                # 1. API Call Span wrapped in outer try-except to log exception to trace correctly
                with trace_span(node="drs_api_request", type="api_call") as api_span:
                    api_span["output_summary"] = f"Sending question to DRS: '{question}'"
                    
                    payload = {"question": question}
                    response = requests.post(self.api_url, json=payload, timeout=60)
                    
                    if response.status_code == 200:
                        data = response.json()
                        final_output = data.get("answer") or ""
                        api_span["output_summary"] = f"Received response: {final_output[:200]}..."
                        
                        # 2. Sub-spans representing pipeline steps
                        # Simulating similarity search retrieval
                        with trace_span(node="retriever", type="tool_call", tool_name="similarity_search", tool_args={"query": question}) as ret_span:
                            ret_span["output_summary"] = "Retrieved candidate documents matching query context."
                            
                        # Simulating LLM response generation
                        with trace_span(node="llm_generation", type="llm_call") as llm_span:
                            prompt_tokens = len(question) // 4 + 150  # estimated prompt tokens
                            completion_tokens = len(final_output) // 4
                            llm_span["tokens_in"] = prompt_tokens
                            llm_span["tokens_out"] = completion_tokens
                            # Calculate estimated cost using typical API rates
                            llm_span["cost_usd"] = (prompt_tokens * 0.15 / 1_000_000) + (completion_tokens * 0.60 / 1_000_000)
                            llm_span["output_summary"] = final_output[:300]
                    else:
                        raise RuntimeError(f"DRS API responded with status {response.status_code}: {response.text}")
            except RuntimeError as e:
                # Capture status code / API error outcome
                final_output = f"API Error: {str(e)}"
            except Exception as e:
                # Capture connection / other failure outcome
                final_output = f"Connection Failure: {str(e)}"

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
