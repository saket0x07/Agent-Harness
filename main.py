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
def run(suite, agent, version, db):
    """Executes a task suite for a target agent and logs traces & results to database."""
    console.print(Panel(
        f"[bold cyan]Agent Evaluation Harness[/bold cyan] - Run suite execution\n"
        f"[dim]Suite:[/dim] {suite}\n"
        f"[dim]Agent:[/dim] {agent}\n"
        f"[dim]Version:[/dim] {version}\n"
        f"[dim]Database:[/dim] {db}",
        title="Execution Config",
        border_style="cyan"
    ))
    
    try:
        report = execute_suite(
            suite_path=suite,
            agent_name=agent,
            agent_version=version,
            db_path=Path(db)
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

if __name__ == "__main__":
    cli()
