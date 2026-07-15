import sys
import sqlite3
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Reconfigure stdout/stderr encoding on Windows to prevent character map encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_DB_PATH = Path("data/harness.db")

def main():
    console = Console()
    if not DEFAULT_DB_PATH.exists():
        console.print(f"[bold red]Database not found at {DEFAULT_DB_PATH}[/bold red]")
        return

    conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get the latest run
    cursor.execute("SELECT * FROM runs ORDER BY timestamp DESC LIMIT 1")
    run_row = cursor.fetchone()
    if not run_row:
        console.print("[bold yellow]No runs found in the database.[/bold yellow]")
        conn.close()
        return

    run_id = run_row["run_id"]
    agent_name = run_row["agent_name"]
    agent_version = run_row["agent_version"]
    timestamp = run_row["timestamp"]
    metrics = json.loads(run_row["metrics"]) if run_row["metrics"] else {}

    console.print(Panel(
        f"[bold cyan]Latest Run Details[/bold cyan]\n"
        f"[dim]Run ID:[/dim] {run_id}\n"
        f"[dim]Agent:[/dim] {agent_name} ({agent_version})\n"
        f"[dim]Timestamp:[/dim] {timestamp}\n"
        f"[dim]Success Rate:[/dim] {metrics.get('success_rate', 0.0) * 100:.1f}%\n"
        f"[dim]Avg Latency:[/dim] {metrics.get('average_latency_ms', 0):.0f}ms\n"
        f"[dim]Avg Cost:[/dim] ${metrics.get('average_cost_usd', 0.0):.5f}",
        title="Database Run Query",
        border_style="cyan"
    ))

    # Retrieve trace_ids belonging to this specific run from the MetricsReport
    detailed_results = metrics.get("detailed_results", [])
    if not detailed_results:
        console.print("[bold yellow]No task results found in the latest run metrics.[/bold yellow]")
        conn.close()
        return

    # Fetch traces for each trace_id in the run
    for result in detailed_results:
        tid = result.get("trace_id")
        task_id = result.get("task_id")
        is_pass = "Passed" if result.get("is_pass") else "Failed"
        pass_color = "green" if result.get("is_pass") else "red"

        if not tid:
            continue

        # Get spans matching the trace_id
        cursor.execute("""
            SELECT span_id, node, type, start_ts, end_ts, cost_usd, tool_name, tool_args, output_summary, error, tokens_in, tokens_out
            FROM traces
            WHERE trace_id = ?
            ORDER BY start_ts ASC
        """, (tid,))
        spans = cursor.fetchall()

        if not spans:
            console.print(f"[yellow]No trace spans found in database for task '{task_id}' (Trace ID: {tid})[/yellow]\n")
            continue

        table = Table(
            title=f"Execution Spans for Task: [magenta]{task_id}[/magenta] ({tid}) - [bold {pass_color}]{is_pass}[/bold {pass_color}]", 
            border_style="cyan"
        )
        table.add_column("Node Name", style="cyan")
        table.add_column("Type", style="dim")
        table.add_column("Latency", style="dim")
        table.add_column("Tokens (In/Out)", style="dim")
        table.add_column("Cost (USD)", style="green")
        table.add_column("Summary / Arguments", style="yellow")
        table.add_column("Errors", style="bold red")

        total_latency = 0
        total_cost = 0.0

        for span in spans:
            duration = (span["end_ts"] - span["start_ts"]) if span["end_ts"] else 0
            total_latency += duration
            cost = span["cost_usd"] or 0.0
            total_cost += cost

            summary = span["output_summary"] or ""
            # If tool arguments exist, include them in the summary display
            if span["tool_args"]:
                args_dict = json.loads(span["tool_args"])
                summary = f"[bold]Args:[/bold] {args_dict}\n{summary}"
            if span["tool_name"]:
                summary = f"Tool: [bold]{span['tool_name']}[/bold]\n" + summary
            
            t_in = span["tokens_in"] if span["tokens_in"] is not None else "-"
            t_out = span["tokens_out"] if span["tokens_out"] is not None else "-"
            tokens_str = f"{t_in} / {t_out}" if (t_in != "-" or t_out != "-") else "-"
            
            table.add_row(
                span["node"],
                span["type"],
                f"{duration}ms",
                tokens_str,
                f"${cost:.5f}",
                summary[:200] + "..." if len(summary) > 200 else summary,
                span["error"] or ""
            )

        console.print(table)
        console.print(f"💰 [bold]Trace Totals:[/bold] Latency: {total_latency}ms | Cost: ${total_cost:.5f}\n")

    conn.close()

if __name__ == "__main__":
    main()
