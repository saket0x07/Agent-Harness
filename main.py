import click
import sys
import os
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from src.runner import execute_suite

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()

@click.group()
def cli():
    """Agent Evaluation Harness CLI - trace, grade, and compare agent runs."""
    pass

@cli.command()
@click.option(
    "--suite", "-s",
    required=True,
    type=click.Path(exists=True),
    help="Path to the task suite YAML/JSON file or directory."
)
@click.option(
    "--agent", "-a",
    required=True,
    help="Target agent identifier under evaluation (e.g., blog_researcher_writer_agent)."
)
@click.option(
    "--version", "-v",
    default="v1.0",
    help="Version tag for the agent configuration being evaluated."
)
@click.option(
    "--db", "-d",
    default="data/harness.db",
    help="Path to the SQLite storage destination."
)
@click.option(
    "--limit", "-l",
    type=int,
    default=None,
    help="Optional maximum number of tasks to execute."
)
def run(suite, agent, version, db, limit):
    """Executes a task suite for a target agent and logs traces & results to database."""
    console.print(Panel(
        f"[bold cyan]Agent Evaluation Harness[/bold cyan] - Run suite execution\n"
        f"[dim]Suite:[/dim] {suite}\n"
        f"[dim]Agent:[/dim] {agent}\n"
        f"[dim]Version:[/dim] {version}\n"
        f"[dim]Database:[/dim] {db}" + (f"\n[dim]Limit:[/dim] {limit}" if limit else ""),
        title="Execution Config",
        border_style="cyan"
    ))
    
    try:
        report = execute_suite(
            suite_path=suite,
            agent_name=agent,
            agent_version=version,
            db_path=Path(db),
            limit=limit
        )
        
        # Output summary table using Rich
        table = Table(title=f"Suite Run Outcomes: {report.run_id}", border_style="cyan")
        table.add_column("Task ID", style="magenta")
        table.add_column("Passed", style="bold green")
        table.add_column("Spans Captured", style="dim")
        
        for res in report.detailed_results:
            is_passed_str = "[green]Yes[/green]" if res.is_pass else "[red]No[/red]"
            table.add_row(
                res.task_id,
                is_passed_str,
                str(res.trajectory.get("total_spans", 0))
            )
            
        console.print(table)
        console.print(f"\n[bold green]Success Rate: {report.success_rate * 100:.1f}%[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Execution error: {e}[/bold red]")
        raise click.ClickException(str(e))

@cli.command()
@click.option(
    "--agent", "-a",
    required=True,
    help="Target agent identifier under evaluation (e.g. blog_researcher_writer_agent)."
)
@click.option(
    "--version", "-v",
    default="v1.0-interactive",
    help="Version tag for the agent configuration."
)
@click.option(
    "--db", "-d",
    default="data/harness.db",
    help="Path to the SQLite storage destination."
)
@click.option(
    "--no-judge",
    is_flag=True,
    help="Disable LLM-as-a-Judge evaluations and only use deterministic checks."
)
def interactive(agent, version, db, no_judge):
    """Interactively run a custom query against an agent and trace the evaluation."""
    console.print(Panel(
        f"[bold cyan]Interactive Evaluation Mode[/bold cyan]\n"
        f"[dim]Agent:[/dim] {agent}\n"
        f"[dim]Version:[/dim] {version}\n"
        f"[dim]Database:[/dim] {db}\n"
        f"[dim]LLM Judge:[/dim] {'Disabled' if no_judge else 'Enabled'}",
        title="Interactive Config",
        border_style="cyan"
    ))
    
    # Prompt the user for custom task inputs
    if agent in ["drs", "drs_agent"]:
        question = click.prompt("\n[bold yellow]❓ Enter your question for the Document Retrieval System[/bold yellow]", type=str)
        keywords_raw = click.prompt("[bold yellow]🔑 Enter expected keywords (comma-separated, optional)[/bold yellow]", default="", show_default=False, type=str)
        
        # Process keywords
        keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
        
        # Construct a TaskSpec dynamically
        import uuid
        task_id = f"interactive_{uuid.uuid4().hex[:6]}"
        
        from src.core.schemas import TaskSpec
        task = TaskSpec(
            task_id=task_id,
            agent_target=agent,
            input={
                "question": question
            },
            expected={
                "required_keywords": keywords,
                "must_have_citations": False
            },
            grading_strategy=["deterministic_keyword_match"] + ([] if no_judge else ["llm_judge_technical_accuracy"]),
            difficulty="medium",
            tags=["interactive"]
        )
    else:
        topic = click.prompt("\n[bold yellow]✍️ Enter the blog topic/title[/bold yellow]", type=str)
        audience = click.prompt("[bold yellow]👥 Enter target audience[/bold yellow]", default="Software Developers", type=str)
        keywords_raw = click.prompt("[bold yellow]🔑 Enter expected keywords (comma-separated, optional)[/bold yellow]", default="", show_default=False, type=str)
        
        # Process keywords
        keywords = [kw.strip() for kw in keywords_raw.split(",") if kw.strip()]
        
        # Construct a TaskSpec dynamically
        import uuid
        task_id = f"interactive_{uuid.uuid4().hex[:6]}"
        
        from src.core.schemas import TaskSpec
        task = TaskSpec(
            task_id=task_id,
            agent_target=agent,
            input={
                "topic": topic,
                "target_audience": audience,
                "required_sections": [] # Determined dynamically on the backend
            },
            expected={
                "required_keywords": keywords,
                "min_sections": 1,
                "must_have_citations": False
            },
            grading_strategy=["deterministic_keyword_match"] + ([] if no_judge else ["llm_judge_technical_accuracy"]),
            difficulty="medium",
            tags=["interactive"]
        )
    
    # Run suite logic manually for this single task
    from src.storage.db import init_db, save_task, save_run, save_trace_events, save_grading_result
    from src.runner import ADAPTER_REGISTRY
    from src.grading.grader import GraderEngine
    import time
    from datetime import datetime, timezone
    
    db_path = Path(db)
    init_db(db_path)
    
    # Save the dynamically created task in the DB so joins work
    save_task(
        task_id=task.task_id,
        agent_target=task.agent_target,
        input_data=task.input,
        expected=task.expected,
        grading_strategy=task.grading_strategy,
        difficulty=task.difficulty,
        tags=task.tags,
        db_path=db_path
    )
    
    # Resolve adapter
    adapter_class = ADAPTER_REGISTRY.get(agent)
    if not adapter_class:
        raise click.ClickException(f"No adapter registered for agent '{agent}'. Available: {list(ADAPTER_REGISTRY.keys())}")
        
    adapter = adapter_class()
    
    run_id = f"run_interactive_{int(time.time())}"
    trace_id = f"trace_{task_id}_{uuid.uuid4().hex[:6]}"
    
    console.print(f"\n🚀 Running interactive task: [bold magenta]{task_id}[/bold magenta]...")
    
    try:
        result = adapter.run(task)
    except Exception as e:
        console.print(f"[bold red]Critical adapter error: {e}[/bold red]")
        raise click.ClickException(str(e))
        
    # Overwrite trace_ids to align with runner
    for event in result.trace:
        event.trace_id = trace_id
        
    # Save traces to SQLite
    trace_dicts = [event.model_dump() for event in result.trace]
    save_trace_events(trace_dicts, db_path=db_path)
    
    # Grade the execution
    grader = GraderEngine(task)
    grading_res = grader.grade(result)
    grading_res.trace_id = trace_id
    
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
    
    # Save run metrics
    from src.core.schemas import MetricsReport
    report = MetricsReport(
        agent_name=agent,
        agent_version=version,
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_tasks=1,
        success_rate=1.0 if grading_res.is_pass else 0.0,
        average_cost_usd=result.total_cost_usd,
        average_latency_ms=result.total_latency_ms,
        failure_mode_counts={grading_res.trajectory["failure_mode"]: 1} if (not grading_res.is_pass and grading_res.trajectory.get("failure_mode")) else {},
        detailed_results=[grading_res]
    )
    
    save_run(
        run_id=run_id,
        agent_name=agent,
        agent_version=version,
        timestamp=report.timestamp,
        metrics=report.model_dump(),
        db_path=db_path
    )
    
    console.print("=" * 50)
    console.print("🏁 Execution Completed")
    is_passed_str = "[green]Passed[/green]" if grading_res.is_pass else "[red]Failed[/red]"
    console.print(f"Outcome: {is_passed_str}")
    console.print(f"⏱️ Latency: {result.total_latency_ms}ms | 💳 Cost: ${result.total_cost_usd:.5f}")
    
    if grading_res.deterministic:
        console.print(f"[dim]Deterministic Checks:[/dim] {grading_res.deterministic}")
    if grading_res.trajectory:
        console.print(f"[dim]Trajectory Auditing:[/dim] {grading_res.trajectory}")
    if grading_res.llm_judge:
        console.print(Panel(
            f"[bold green]LLM Judge Score Critique[/bold green]\n"
            f"[dim]Critique:[/dim] {grading_res.llm_judge.get('critique')}\n"
            f"[dim]Scores:[/dim] Clarity: {grading_res.llm_judge.get('clarity')}/5 | Accuracy: {grading_res.llm_judge.get('accuracy')}/5 | Completeness: {grading_res.llm_judge.get('completeness')}/5",
            title="Judge Feedback",
            border_style="cyan"
        ))
    console.print("=" * 50)
    console.print(f"\n💡 [bold]To see full execution trace logs, run: [/bold] [bold cyan]python scripts/view_traces.py[/bold cyan]\n")

if __name__ == "__main__":
    cli()
