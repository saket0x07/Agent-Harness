import time
from typing import Dict, Any, List
from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

class MockAgentAdapter(AgentAdapter):
    """A mock agent adapter that simulates different agent behaviors.
    
    This adapter is used to verify the harness tracing, cost/latency tracking, 
    and regression detection logic without invoking real external APIs.
    """
    def run(self, task: TaskSpec) -> AgentResult:
        start_time = time.time()
        
        # Determine behavior from task input payload
        behavior = task.input.get("mock_behavior", "success")
        topic = task.input.get("topic", "Default Topic")
        
        # Start trace collection session
        with TraceCollector() as tc:
            trace_id = tc.trace_id
            
            if behavior == "premature_termination":
                # Returns output instantly without steps
                final_output = "Draft outline completed."
                
            elif behavior == "infinite_loop":
                # Simulated loops: Planning LLM call -> repeating tool calls
                with trace_span(node="planner", type="llm_call") as span:
                    span["tokens_in"] = 200
                    span["tokens_out"] = 50
                    span["cost_usd"] = 0.0003
                    span["output_summary"] = "Deciding to query Google Search for " + topic
                
                # Execute identical search tool calls to trigger loop checks
                for i in range(4):
                    with trace_span(node="web_search", type="tool_call", tool_name="google_search", tool_args={"query": topic}) as span:
                        span["output_summary"] = f"Result iteration {i} empty."
                
                final_output = "Search timed out."
                
            elif behavior == "fail_tool":
                # Simulated tool failure
                with trace_span(node="planner", type="llm_call") as span:
                    span["tokens_in"] = 150
                    span["tokens_out"] = 40
                    span["cost_usd"] = 0.0002
                
                try:
                    with trace_span(node="db_lookup", type="tool_call", tool_name="query_knowledge_base", tool_args={"id": "doc_1"}) as span:
                        raise ConnectionResetError("Connection refused by SQLite database cluster host.")
                except ConnectionResetError:
                    # Capture and handle internal exception (tracer logs it automatically)
                    pass
                
                final_output = "Failed due to internal lookup error."
                
            else:  # "success"
                # A standard healthy agent trajectory: Planning LLM -> Search Tool -> Writing LLM
                
                # 1. Planning Step
                with trace_span(node="planner", type="llm_call") as span:
                    span["tokens_in"] = 250
                    span["tokens_out"] = 80
                    span["cost_usd"] = 0.0004
                    span["output_summary"] = "Identified keywords: " + topic
                    time.sleep(0.01) # minor latency simulation
                    
                # 2. Tool Execution Step
                with trace_span(node="web_search", type="tool_call", tool_name="google_search", tool_args={"query": topic}) as span:
                    span["output_summary"] = "Found 3 relevant sources for: " + topic
                    time.sleep(0.02)
                    
                # 3. Drafting Step
                with trace_span(node="writer", type="llm_call") as span:
                    span["tokens_in"] = 600
                    span["tokens_out"] = 400
                    span["cost_usd"] = 0.002
                    # Construct a sample draft satisfying expected sections & word limit
                    sections_markdown = "\n\n".join(f"## {sec}\nThis is content discussing {topic}." for sec in task.input.get("required_sections", ["Content"]))
                    
                    # Dynamically append keywords for mock validation success
                    expected_kws = task.expected.get("required_keywords", [])
                    keyword_suffix = f"\n\nIndex of keywords: {', '.join(expected_kws)}" if expected_kws else ""
                    
                    final_output = f"# Draft: {topic}\n\n{sections_markdown}\n\nCitations: [1] Saket's Blog researcher.{keyword_suffix}"
                    span["output_summary"] = final_output[:100] + "..."
                    time.sleep(0.03)

            # Retrieve all events logged during the TraceCollector context session
            collected_traces = list(TraceCollector.get_events())
            
        end_time = time.time()
        total_latency_ms = int((end_time - start_time) * 1000)
        
        # Aggregate trace costs
        total_cost = sum(event.cost_usd for event in collected_traces if event.cost_usd is not None)

        return AgentResult(
            task_id=task.task_id,
            final_output=final_output,
            trace=collected_traces,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency_ms
        )
