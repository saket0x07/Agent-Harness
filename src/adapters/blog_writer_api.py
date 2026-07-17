import os
import time
import requests
import sys
import builtins

# Local safe print definition to avoid UnicodeEncodeError in non-UTF-8 console environments
def safe_print(*args, **kwargs):
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or 'utf-8'
        new_args = [
            str(arg).encode(encoding, errors='replace').decode(encoding)
            for arg in args
        ]
        try:
            builtins.print(*new_args, **kwargs)
        except Exception:
            ascii_args = [
                str(arg).encode('ascii', errors='replace').decode('ascii')
                for arg in args
            ]
            builtins.print(*ascii_args, **kwargs)

print = safe_print
from typing import Dict, Any, List

from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

class BlogWriterAPIAdapter(AgentAdapter):
    """Agent adapter that interacts with the live Blog Agent API running via HTTP."""
    
    def __init__(self, api_url: str = None):
        self.api_url = api_url or os.environ.get("BLOG_AGENT_API_URL", "http://localhost:8000/generate")
        
    def run(self, task: TaskSpec) -> AgentResult:
        start_time = time.time()
        topic = task.input.get("topic")
        
        if not topic:
            raise ValueError("Task input is missing 'topic'.")
            
        final_output = ""
        
        # Initialize trace collector
        with TraceCollector() as tc:
            # We measure the HTTP request duration as the main duration
            with trace_span(node="api_client", type="llm_call") as main_span:
                main_span["output_summary"] = f"Sending topic to API: {self.api_url}"
                
                print(f"  📡 Dispatched task '{task.task_id}' topic to API: '{topic}'")
                print(f"  ⏳ Waiting for API response from {self.api_url} (runs planning, web research, writing, and image generation)...")
                
                try:
                    payload = {"topic": topic}
                    response = requests.post(self.api_url, json=payload, timeout=600)
                    
                    if response.status_code == 200:
                        print("  ✨ API response received successfully!")
                        data = response.json()
                        raw_state = data.get("raw_state") or {}
                        
                        # Extract final blog markdown (robust check for key variants)
                        final_output = data.get("final_blog") or raw_state.get("final_blog") or raw_state.get("final_blog_content") or ""
                        
                        # Reconstruct individual LangGraph execution traces from raw_state
                        node_traces = raw_state.get("node_traces", {})
                        
                        # 1. Router Node
                        category = raw_state.get("knowledge_category", "hybrid")
                        router_trace = node_traces.get("router", {})
                        with trace_span(node="router", type="state_transition") as span:
                            span["output_summary"] = f"Knowledge Category classified: {category}"
                            span["tokens_in"] = router_trace.get("prompt_tokens")
                            span["tokens_out"] = router_trace.get("completion_tokens")
                            span["cost_usd"] = router_trace.get("cost_usd", 0.0001)
                            
                        # 2. Research Node (if applicable)
                        queries = raw_state.get("search_queries", [])
                        evidence = raw_state.get("evidence", [])
                        research_trace = node_traces.get("research", {})
                        if queries or evidence:
                            with trace_span(node="research", type="tool_call", tool_name="tavily_search", tool_args={"queries": queries}) as span:
                                span["output_summary"] = f"Executed {len(queries)} search queries. Retrieved {len(evidence)} evidence sources."
                                span["tokens_in"] = research_trace.get("prompt_tokens")
                                span["tokens_out"] = research_trace.get("completion_tokens")
                                span["cost_usd"] = research_trace.get("cost_usd", 0.001)
                                
                        # 3. Planner Node
                        plan = raw_state.get("plan", {})
                        planner_trace = node_traces.get("planner", {})
                        if plan:
                            with trace_span(node="planner", type="llm_call") as span:
                                span["output_summary"] = f"Generated Plan Title: '{plan.get('title')}' with {len(plan.get('tasks', []))} sections."
                                span["tokens_in"] = planner_trace.get("prompt_tokens")
                                span["tokens_out"] = planner_trace.get("completion_tokens")
                                span["cost_usd"] = planner_trace.get("cost_usd", 0.0005)
                                
                        # 4. Worker Nodes (dynamic sections writing)
                        drafts = raw_state.get("section_drafts", [])
                        for idx, draft in enumerate(drafts):
                            task_id = draft.get("task_id", "unknown")
                            title = draft.get("title", "section")
                            # Parallel execution lookup: worker, worker_1, worker_2...
                            node_key = "worker" if idx == 0 else f"worker_{idx}"
                            worker_trace = node_traces.get(node_key, {})
                            with trace_span(node=f"worker_{task_id}", type="llm_call") as span:
                                span["output_summary"] = f"Drafted section: '{title}' ({len(draft.get('content', ''))} characters)"
                                span["tokens_in"] = worker_trace.get("prompt_tokens")
                                span["tokens_out"] = worker_trace.get("completion_tokens")
                                span["cost_usd"] = worker_trace.get("cost_usd", 0.0015)
                                
                        # 5. Reducer Node
                        images = raw_state.get("images", [])
                        reducer_trace = node_traces.get("reducer", {})
                        with trace_span(node="reducer", type="state_transition") as span:
                            span["output_summary"] = f"Stitched final blog post. Generated/fetched {len(images)} images."
                            span["tokens_in"] = reducer_trace.get("prompt_tokens")
                            span["tokens_out"] = reducer_trace.get("completion_tokens")
                            span["cost_usd"] = reducer_trace.get("cost_usd", 0.002)
                            
                    else:
                        main_span["error"] = f"API returned status code {response.status_code}: {response.text}"
                        final_output = f"API Execution failed with status {response.status_code}."
                except Exception as e:
                    main_span["error"] = f"Connection to API failed: {str(e)}"
                    final_output = f"API connection failure: {str(e)}"
                    
            collected_traces = list(TraceCollector.get_events())
            
        end_time = time.time()
        total_latency_ms = int((end_time - start_time) * 1000)
        total_cost = sum(event.cost_usd for event in collected_traces if event.cost_usd is not None)
        
        if not final_output:
            final_output = "No content generated from API."
            
        return AgentResult(
            task_id=task.task_id,
            final_output=final_output,
            trace=collected_traces,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency_ms
        )
