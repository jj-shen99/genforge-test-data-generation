"""
GenForge CLI — generate and push test data from the command line.

Usage:
    python -m datagen.cli generate --schema schema.json --count 100 --output data.json
    python -m datagen.cli push --schema schema.json --target connection.json --count 50
    python -m datagen.cli pipeline --config pipeline.json
    python -m datagen.cli connectors
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

try:
    import click
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    import click

from datagen.engine.schema_parser import SchemaParser
from datagen.engine.pipeline import GenerationPipeline, servicenow_itsm_pipeline
from datagen.engine.timeseries import generate_metrics, generate_log_entries
from datagen.connectors.base import AuthConfig, AuthMethod, ConnectionConfig
from datagen.connectors.registry import create_connector, list_connectors

console = Console() if HAS_RICH else None


def _print(msg: str, style: str = ""):
    if console:
        console.print(msg, style=style)
    else:
        print(msg)


@click.group()
@click.version_option("0.1.0", prog_name="genforge")
def cli():
    """GenForge — Test Data Generation Framework"""
    pass


@cli.command()
@click.option("--schema", "-s", required=True, help="Path to JSON schema file")
@click.option("--count", "-n", default=10, help="Number of records to generate")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout)")
@click.option("--format", "-f", "fmt", default="json", type=click.Choice(["json", "jsonl", "csv"]))
@click.option("--pretty", is_flag=True, help="Pretty-print JSON output")
def generate(schema: str, count: int, output: str | None, fmt: str, pretty: bool):
    """Generate test data from a JSON schema."""
    _print(f"[bold]Loading schema:[/bold] {schema}", style="blue")

    start = time.time()
    parser = SchemaParser(Path(schema))
    records = parser.generate(count=count)
    duration = time.time() - start

    _print(f"Generated [bold green]{len(records)}[/bold green] records in {duration:.2f}s")

    # Format output
    if fmt == "json":
        text = json.dumps(records, indent=2 if pretty else None, default=str)
    elif fmt == "jsonl":
        text = "\n".join(json.dumps(r, default=str) for r in records)
    elif fmt == "csv":
        if records:
            headers = list(records[0].keys())
            lines = [",".join(headers)]
            for r in records:
                lines.append(",".join(str(r.get(h, "")) for h in headers))
            text = "\n".join(lines)
        else:
            text = ""
    else:
        text = json.dumps(records, default=str)

    if output:
        Path(output).write_text(text)
        _print(f"Written to [bold]{output}[/bold]")
    else:
        print(text)


@cli.command()
@click.option("--schema", "-s", required=True, help="Path to JSON schema file")
@click.option("--target", "-t", required=True, help="Path to connection config JSON")
@click.option("--count", "-n", default=100, help="Number of records")
@click.option("--batch-size", "-b", default=500, help="Batch size for pushing")
def push(schema: str, target: str, count: int, batch_size: int):
    """Generate and push test data to a target application."""
    _print(f"[bold]Schema:[/bold] {schema}")
    _print(f"[bold]Target:[/bold] {target}")

    # Load connection config
    with open(target) as f:
        conn_data = json.load(f)

    config = ConnectionConfig(
        name=conn_data.get("name", "cli-target"),
        connector_type=conn_data["connector_type"],
        host=conn_data["host"],
        port=conn_data.get("port"),
        auth=AuthConfig(
            method=AuthMethod(conn_data.get("auth_method", "basic")),
            credentials=conn_data.get("credentials", {}),
        ),
        options=conn_data.get("options", {}),
    )

    # Generate
    _print(f"\nGenerating {count} records...")
    start = time.time()
    parser = SchemaParser(Path(schema))
    records = parser.generate(count=count)
    gen_time = time.time() - start
    _print(f"Generated in {gen_time:.2f}s")

    # Push
    _print(f"\nConnecting to {config.connector_type}://{config.host}...")
    connector = create_connector(config)
    connector.authenticate()

    health = connector.validate_connection()
    if not health.healthy:
        _print(f"[red]Connection unhealthy: {health.message}[/red]")
        sys.exit(1)
    _print(f"[green]Connected[/green] ({health.latency_ms:.0f}ms)")

    _print(f"\nPushing {len(records)} records in batches of {batch_size}...")
    total_sent = 0
    total_failed = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        result = connector.push_batch(batch)
        total_sent += result.records_sent
        total_failed += result.records_failed
        pct = min(100, round((i + len(batch)) / len(records) * 100))
        _print(f"  [{pct:3d}%] Sent {result.records_sent}, failed {result.records_failed}")
        for err in result.errors[:3]:
            _print(f"    [red]Error: {err}[/red]")

    connector.close()
    total_time = time.time() - start

    _print(f"\n[bold]Results:[/bold]")
    _print(f"  Records sent:   {total_sent}")
    _print(f"  Records failed: {total_failed}")
    _print(f"  Total time:     {total_time:.2f}s")
    _print(f"  Throughput:     {total_sent / max(total_time, 0.01):.0f} records/sec")


@cli.command()
@click.option("--template", "-t", default="servicenow_itsm",
              type=click.Choice(["servicenow_itsm", "custom"]),
              help="Pipeline template to use")
@click.option("--config", "-c", default=None, help="Custom pipeline config JSON")
@click.option("--output", "-o", default=None, help="Output directory for generated data")
def pipeline(template: str, config: str | None, output: str | None):
    """Run a multi-schema generation pipeline."""
    if template == "servicenow_itsm":
        _print("[bold]Running ServiceNow ITSM pipeline[/bold]")
        pipe = servicenow_itsm_pipeline(
            user_count=50, ci_count=200,
            incident_count=500, change_count=100,
        )
    elif config:
        _print(f"[bold]Loading pipeline config:[/bold] {config}")
        # Custom pipeline from JSON config
        with open(config) as f:
            pipe_config = json.load(f)
        pipe = GenerationPipeline()
        for step in pipe_config.get("steps", []):
            pipe.add_schema(**step)
    else:
        _print("[red]Either --template or --config is required[/red]")
        sys.exit(1)

    def on_progress(name, done, total):
        _print(f"  [green]✓[/green] {name}: {done}/{total} records")

    result = pipe.execute(on_progress=on_progress)

    _print(f"\n[bold]Pipeline complete[/bold]")
    _print(f"  Execution order: {' → '.join(result.execution_order)}")
    _print(f"  Total records:   {result.total_records}")
    _print(f"  Duration:        {result.duration_seconds:.2f}s")

    if result.errors:
        for err in result.errors:
            _print(f"  [red]Error: {err}[/red]")

    if output:
        out_dir = Path(output)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, records in result.datasets.items():
            path = out_dir / f"{name}.json"
            path.write_text(json.dumps(records, indent=2, default=str))
            _print(f"  Written {len(records)} records to {path}")


@cli.command()
def connectors():
    """List all available connectors."""
    catalog = list_connectors()

    if HAS_RICH:
        table = Table(title="Available Connectors")
        table.add_column("Type", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Category", style="magenta")
        table.add_column("Auth Methods")
        for c in catalog:
            table.add_row(
                c["type"], c["name"], c["category"],
                ", ".join(c["auth_methods"]),
            )
        console.print(table)
    else:
        print(f"\n{'Type':<20} {'Name':<30} {'Category':<15} Auth Methods")
        print("-" * 80)
        for c in catalog:
            print(f"{c['type']:<20} {c['name']:<30} {c['category']:<15} {', '.join(c['auth_methods'])}")


if __name__ == "__main__":
    cli()
