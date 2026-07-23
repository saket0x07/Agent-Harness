import time
import uuid
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.core.schemas import TaskSpec, AgentResult, GradingResult, MetricsReport
from src.loader.suite_loader import load_task_suite
from src.adapters.mock_agent import MockAgentAdapter
from src.adapters.blog_writer import BlogWriterAdapter
from src.adapters.blog_writer_api import BlogWriterAPIAdapter
from src.adapters.drs_adapter import DRSAdapter
from src.storage.db import init_db, save_run, save_trace_events, save_grading_result
from src.adapters.agentic_hiring_adapter import AgenticHiringAdapter

# Registry of available agent adapters
ADAPTER_REGISTRY = {
    "blog_researcher_writer_agent": BlogWriterAPIAdapter,
    "blog_researcher_writer_agent_local": BlogWriterAdapter,
    "mock": MockAgentAdapter,
    "drs": DRSAdapter,
    "drs_agent": DRSAdapter,
    "agentic_hiring_workflow": AgenticHiringAdapter,
    "hiring_agent": AgenticHiringAdapter
}

def execute_suite(
    suite_path: str,
    agent_name: str,
    agent_version: str,
    db_path: Optional[Path] = None,
    limit: Optional[int] = None
) -> MetricsReport:
    """Executes a benchmark task suite for a target agent, traces runs, and persists results.
    
    Args:
        suite_path: Path to the JSON/YAML task suite folder or file.
        agent_name: Target agent identifier.
        agent_version: Version identifier of the agent under evaluation.
        db_path: SQLite DB destination path.
        limit: Optional limit on the number of tasks to execute.
        
    Returns:
        MetricsReport: Aggregated report detailing the outcomes of the run.
    """
    # 1. Initialize database schemas
    init_db(db_path)
    
    # 2. Load all task specs and register them to SQLite
    tasks = load_task_suite(suite_path, save_to_db=True, db_path=db_path)
    
    # 3. Filter tasks targeting the specified agent
    agent_tasks = [t for t in tasks if t.agent_target == agent_name]
    if not agent_tasks:
        raise ValueError(f"No tasks in suite '{suite_path}' target agent '{agent_name}'.")

    # Apply limit if specified
    if limit is not None and limit > 0:
        agent_tasks = agent_tasks[:limit]

    # 4. Resolve the correct adapter class
    adapter_class = ADAPTER_REGISTRY.get(agent_name)
    if not adapter_class:
        raise ValueError(f"No adapter registered for agent '{agent_name}'. Available: {list(ADAPTER_REGISTRY.keys())}")
    
    adapter = adapter_class()
    
    # 5. Initialize the metrics aggregation variables
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    start_time = time.time()
    
    grading_results: List[GradingResult] = []
    total_cost = 0.0
    total_latency = 0
    passed_tasks_count = 0
    failure_mode_counts: Dict[str, int] = {}
    
    print(f"🚀 Starting Suite Run: {run_id}")
    print(f"🤖 Agent: {agent_name} ({agent_version})")
    print(f"📋 Found {len(agent_tasks)} tasks to execute.\n")

    # 6. Execute task loop
    for idx, task in enumerate(agent_tasks):
        print(f"[{idx+1}/{len(agent_tasks)}] Running task: {task.task_id} ({task.difficulty})")
        
        # Track trace ID
        trace_id = f"trace_{task.task_id}_{uuid.uuid4().hex[:6]}"
        
        task_start = time.time()
        
        # Execute the agent through its adapter
        # The adapter internally logs traces and returns them in the AgentResult
        try:
            result: AgentResult = adapter.run(task)
        except Exception as e:
            # Handle unexpected crash of wrapper run
            print(f"❌ Critical failure running adapter for task {task.task_id}: {e}")
            # Mock an empty result so the harness can log the crash trace
            result = AgentResult(
                task_id=task.task_id,
                final_output=f"Adapter Exception: {str(e)}",
                trace=[],
                total_cost_usd=0.0,
                total_latency_ms=int((time.time() - task_start) * 1000)
            )

        total_cost += result.total_cost_usd
        total_latency += result.total_latency_ms
        
        # Save traces to SQLite
        for event in result.trace:
            event.trace_id = trace_id
        trace_dicts = [event.model_dump() for event in result.trace]
        save_trace_events(trace_dicts, db_path=db_path)
        
        # Phase 4 Grader Engine integration
        from src.grading.grader import GraderEngine
        grader = GraderEngine(task)
        grading_res = grader.grade(result)
        
        # Ensure trace_id matches the run session
        grading_res.trace_id = trace_id
        
        if grading_res.is_pass:
            passed_tasks_count += 1
            print(f"  ✅ Pass")
        else:
            fail_reason = grading_res.trajectory.get("failure_mode") or "failed validation checks"
            print(f"  ❌ Fail (Reason: {fail_reason})")
            failure_mode = grading_res.trajectory.get("failure_mode")
            if failure_mode:
                failure_mode_counts[failure_mode] = failure_mode_counts.get(failure_mode, 0) + 1
                
        grading_results.append(grading_res)
        
        # Save grading outcomes to database
        save_grading_result(
            task_id=task.task_id,
            trace_id=trace_id,
            deterministic=grading_res.deterministic,
            llm_judge=grading_res.llm_judge,
            trajectory=grading_res.trajectory,
            is_pass=grading_res.is_pass,
            db_path=db_path
        )
        print(f"  ⏱️ Latency: {result.total_latency_ms}ms | 💳 Cost: ${result.total_cost_usd:.5f}\n")

    # 7. Aggregate final metrics
    end_time = time.time()
    success_rate = passed_tasks_count / len(agent_tasks) if agent_tasks else 0.0
    avg_cost = total_cost / len(agent_tasks) if agent_tasks else 0.0
    avg_latency = total_latency / len(agent_tasks) if agent_tasks else 0.0
    
    report = MetricsReport(
        agent_name=agent_name,
        agent_version=agent_version,
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_tasks=len(agent_tasks),
        success_rate=success_rate,
        average_cost_usd=avg_cost,
        average_latency_ms=avg_latency,
        failure_mode_counts=failure_mode_counts,
        detailed_results=grading_results
    )
    
    # Save the run metrics summary to SQLite
    save_run(
        run_id=run_id,
        agent_name=agent_name,
        agent_version=agent_version,
        timestamp=report.timestamp,
        metrics=report.model_dump(),
        db_path=db_path
    )
    
    print("=" * 50)
    print("🏁 Suite Execution Finished")
    print(f"📊 Success Rate: {success_rate * 100:.1f}% ({passed_tasks_count}/{len(agent_tasks)})")
    print(f"💳 Total Cost: ${total_cost:.5f} (Avg: ${avg_cost:.5f})")
    print(f"⏱️ Total Latency: {total_latency}ms (Avg: {avg_latency:.1f}ms)")
    print("=" * 50)
    
    return report
