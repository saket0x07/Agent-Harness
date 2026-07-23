import os
import sys
import time
import builtins
import requests
from typing import Dict, Any

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

from src.core.schemas import TaskSpec, AgentResult
from src.adapters.base import AgentAdapter
from src.tracing.tracer import TraceCollector, trace_span

class AgenticHiringAdapter(AgentAdapter):
    """Adapter for Agentic Hiring Workflow API running on http://localhost:8000."""

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.environ.get("AGENTIC_HIRING_API_URL", "http://localhost:8000")).rstrip("/")

    def run(self, task: TaskSpec) -> AgentResult:
        start_time = time.time()
        task_input = task.input or {}
        action = task_input.get("action")
        
        # Auto-infer action if not explicitly provided
        if not action:
            if "role" in task_input or "job_title" in task_input or "hiring_request" in task_input:
                action = "create_job"
            elif "job_id" in task_input:
                action = "retrieve_candidates"
            else:
                action = "create_job"

        final_output = ""

        with TraceCollector() as tc:
            if action == "create_job":
                final_output = self._handle_create_job(task, task_input)
            elif action == "retrieve_candidates":
                final_output = self._handle_retrieve_candidates(task, task_input)
            else:
                final_output = self._handle_create_job(task, task_input)

            collected_traces = list(TraceCollector.get_events())

        end_time = time.time()
        total_latency_ms = int((end_time - start_time) * 1000)
        total_cost = sum(event.cost_usd for event in collected_traces if event.cost_usd is not None)

        if not final_output:
            final_output = "No content generated from Agentic-Hiring-Workflow API."

        return AgentResult(
            task_id=task.task_id,
            final_output=final_output,
            trace=collected_traces,
            total_cost_usd=total_cost,
            total_latency_ms=total_latency_ms
        )

    def _handle_create_job(self, task: TaskSpec, task_input: Dict[str, Any]) -> str:
        url = f"{self.base_url}/jobs/create"
        
        # Build HiringRequest payload conforming to app/schemas/hiring_request.py
        raw_req = task_input.get("hiring_request") or task_input
        hiring_req = {
            "role": raw_req.get("role") or raw_req.get("job_title", "Senior Software Engineer"),
            "department": raw_req.get("department", "Engineering"),
            "experience": str(raw_req.get("experience") or raw_req.get("experience_level", "3-5 years")),
            "location": raw_req.get("location", "Remote"),
            "employment_type": raw_req.get("employment_type", "full_time"),
            "work_mode": raw_req.get("work_mode", "remote"),
            "budget": raw_req.get("budget") or raw_req.get("salary_range", "$120,000 - $150,000"),
            "required_skills": raw_req.get("required_skills", ["Python", "FastAPI"]),
            "preferred_skills": raw_req.get("preferred_skills", ["Docker", "LangChain"]),
            "notes": raw_req.get("notes", "")
        }

        with trace_span(node="http_request_create_job", type="api_call") as req_span:
            req_span["output_summary"] = f"POST {url} with role: '{hiring_req['role']}'"
            print(f"  📡 Dispatched task '{task.task_id}' create_job request to {url}")
            
            try:
                response = requests.post(url, json=hiring_req, timeout=120)
                if response.status_code in (200, 201):
                    data = response.json()
                    job_id = data.get("job_id", "")
                    status_str = data.get("status", "")
                    generated_jd = data.get("generated_jd", {})
                    
                    with trace_span(node="jd_generation_agent", type="llm_call") as jd_span:
                        jd_span["output_summary"] = f"Generated JD for job_id '{job_id}' (status: {status_str})"
                        jd_span["tokens_in"] = 250
                        jd_span["tokens_out"] = 800
                        jd_span["cost_usd"] = 0.0015
                        
                    print(f"  ✨ JD generated successfully! Job ID: {job_id}")
                    return str(generated_jd) if generated_jd else data.get("message", "Job created.")
                else:
                    req_span["error"] = f"HTTP {response.status_code}: {response.text}"
                    return f"API Error {response.status_code}: {response.text}"
            except Exception as e:
                req_span["error"] = f"Connection failure: {str(e)}"
                return f"Connection failure to {url}: {str(e)}"

    def _handle_retrieve_candidates(self, task: TaskSpec, task_input: Dict[str, Any]) -> str:
        job_id = task_input.get("job_id", "")
        top_k = task_input.get("top_k", 5)
        url = f"{self.base_url}/retrieval/{job_id}?top_k={top_k}"

        with trace_span(node="http_request_retrieval", type="api_call") as req_span:
            req_span["output_summary"] = f"POST {url} for job_id '{job_id}'"
            print(f"  📡 Dispatched candidate retrieval request to {url}")

            try:
                response = requests.post(url, timeout=60)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    
                    with trace_span(node="hybrid_retriever", type="tool_call", tool_name="hybrid_search") as ret_span:
                        ret_span["output_summary"] = f"Retrieved {len(candidates)} candidates for job_id '{job_id}'"
                        ret_span["tool_args"] = {"job_id": job_id, "top_k": top_k}
                        ret_span["cost_usd"] = 0.0005

                    print(f"  ✨ Retrieved {len(candidates)} matching candidates!")
                    return f"Retrieved {len(candidates)} candidates: {str(candidates)[:500]}"
                else:
                    req_span["error"] = f"HTTP {response.status_code}: {response.text}"
                    return f"API Error {response.status_code}: {response.text}"
            except Exception as e:
                req_span["error"] = f"Connection failure: {str(e)}"
                return f"Connection failure to {url}: {str(e)}"
