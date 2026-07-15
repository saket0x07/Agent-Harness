import sys
import os
import time
from typing import Dict, Any, List
from pathlib import Path
from dotenv import load_dotenv

# Add FX_LangGraph directory to sys.path so we can import blog_agent
LANGGRAPH_PROJECT_PATH = "D:/Fxis.ai/FX_LangGraph"
if LANGGRAPH_PROJECT_PATH not in sys.path:
    sys.path.append(LANGGRAPH_PROJECT_PATH)

# Load the specific environment variables for blog_agent (Tavily, HF_TOKEN, etc.)
load_dotenv(os.path.join(LANGGRAPH_PROJECT_PATH, ".env"))

from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

class BlogWriterAdapter(AgentAdapter):
    """Agent adapter for the live LangGraph-based blog writer agent."""
    
    def run(self, task: TaskSpec) -> AgentResult:
        # Delay import to run-time to prevent import issues if paths are configured dynamically
        from blog_agent.graph.workflow import blog_agent_graph
        
        start_time = time.time()
        topic = task.input.get("topic")
        
        if not topic:
            raise ValueError("Task input is missing 'topic'.")
            
        final_output = ""
        
        # Initialize trace collector
        with TraceCollector() as tc:
            graph_inputs = {"topic": topic}
            
            last_time = time.time()
            
            try:
                # Stream the graph execution nodes step-by-step
                for event in blog_agent_graph.stream(graph_inputs, stream_mode="updates"):
                    for node_name, output in event.items():
                        now = time.time()
                        latency_ms = int((now - last_time) * 1000)
                        last_time = now
                        
                        # Log a trace span for the node execution
                        with trace_span(node=node_name, type="state_transition") as span:
                            # Record metadata
                            span["output_summary"] = str(output)[:500]
                            span["tokens_out"] = len(str(output)) // 4
                            span["cost_usd"] = (span["tokens_out"] / 1000) * 0.0015  # simple estimation of cost
                            
                            # Check if this is the final reducer node which contains the output
                            if node_name == "reducer" and "final_blog" in output:
                                final_output = output["final_blog"]
                                
                            if "error" in output:
                                span["error"] = str(output["error"])
                                
            except Exception as e:
                # Log exception in a span
                with trace_span(node="graph_runner", type="error") as span:
                    span["error"] = str(e)
                final_output = f"Execution failed: {str(e)}"
                
            collected_traces = list(TraceCollector.get_events())
            
        end_time = time.time()
        total_latency_ms = int((end_time - start_time) * 1000)
        total_cost = sum(event.cost_usd for event in collected_traces if event.cost_usd is not None)
        
        # Fallback if final_output wasn't caught in reducer (e.g. if reducer ran, but output wasn't returned in updates, or exception occurred before reducer)
        if not final_output:
            final_output = "No content generated."
            
        return AgentResult(
            task_id=task.task_id,
            final_output=final_output,
            trace=collected_traces,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency_ms
        )
