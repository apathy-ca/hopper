"""Server management commands."""

import subprocess
import time
from typing import Optional

import click
from rich.prompt import Confirm

from hopper.cli.main import Context
from hopper.cli.client import HopperClient, APIError
from hopper.cli.output import (
    print_json,
    print_success,
    print_error,
    print_info,
    print_warning,
    console,
)


@click.group(name="server")
def server() -> None:
    """Manage Hopper API server.

    These commands help you start, stop, and monitor the Hopper API server
    locally for development and testing.
    """
    pass


@server.command(name="start")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", type=int, default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
@click.option("--workers", type=int, default=1, help="Number of worker processes")
@click.pass_obj
def start_server(
    ctx: Context,
    host: str,
    port: int,
    reload: bool,
    workers: int,
) -> None:
    """Start the Hopper API server.

    Examples:
        hopper server start
        hopper server start --reload
        hopper server start --host 0.0.0.0 --port 9000
    """
    print_info(f"Starting Hopper server on {host}:{port}...")

    cmd = [
        "uvicorn",
        "hopper.api.main:app",
        "--host", host,
        "--port", str(port),
    ]

    if reload:
        cmd.append("--reload")
    else:
        cmd.extend(["--workers", str(workers)])

    try:
        console.print(f"[dim]Command: {' '.join(cmd)}[/dim]\n")
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print_info("\nServer stopped")
    except FileNotFoundError:
        print_error("uvicorn not found. Is Hopper installed?")
        print_info("Try: pip install hopper[dev]")
        raise click.Abort()
    except Exception as e:
        print_error(f"Failed to start server: {e}")
        raise click.Abort()


@server.command(name="stop")
@click.option("--force", "-f", is_flag=True, help="Force stop")
@click.pass_obj
def stop_server(ctx: Context, force: bool) -> None:
    """Stop the Hopper API server.

    This attempts to gracefully stop the server process.

    Examples:
        hopper server stop
        hopper server stop --force
    """
    if not force:
        if not Confirm.ask("Stop Hopper server?", default=True):
            print_info("Cancelled")
            return

    try:
        # Try to find and kill uvicorn process
        result = subprocess.run(
            ["pkill", "-f", "uvicorn.*hopper.api.main"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print_success("Server stopped")
        else:
            print_warning("No running server found")

    except Exception as e:
        print_error(f"Failed to stop server: {e}")
        raise click.Abort()


@server.command(name="status")
@click.pass_obj
def server_status(ctx: Context) -> None:
    """Check Hopper API server status.

    Examples:
        hopper server status
    """
    console.print(f"\n[bold cyan]Server Status[/bold cyan]\n")

    # Check if server is reachable
    try:
        with HopperClient(ctx.config) as client:
            health = client.get("/api/v1/health")

        if ctx.json_output:
            print_json(health)
        else:
            print_success("Server is running")
            console.print(f"[bold]Endpoint:[/bold] {ctx.config.current_profile.api.endpoint}")

            if isinstance(health, dict):
                if version := health.get("version"):
                    console.print(f"[bold]Version:[/bold] {version}")
                if status := health.get("status"):
                    console.print(f"[bold]Status:[/bold] {status}")

            console.print()

    except Exception as e:
        if ctx.json_output:
            print_json({"status": "offline", "error": str(e)})
        else:
            print_error("Server is not reachable")
            console.print(f"[bold]Endpoint:[/bold] {ctx.config.current_profile.api.endpoint}")
            console.print(f"[dim]Error: {e}[/dim]\n")


@server.command(name="logs")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--lines", "-n", type=int, default=50, help="Number of lines to show")
@click.pass_obj
def server_logs(ctx: Context, follow: bool, lines: int) -> None:
    """Tail Hopper server logs.

    Examples:
        hopper server logs
        hopper server logs --follow
        hopper server logs -n 100
    """
    # This is a placeholder - actual log location would depend on deployment
    log_file = "/var/log/hopper/server.log"

    print_warning("Log viewing depends on your deployment configuration")
    console.print(f"[dim]Default log location: {log_file}[/dim]")

    cmd = ["tail"]
    if follow:
        cmd.append("-f")
    cmd.extend(["-n", str(lines), log_file])

    console.print(f"[dim]Try: {' '.join(cmd)}[/dim]\n")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print_info("\nStopped following logs")
    except FileNotFoundError:
        print_error(f"Log file not found: {log_file}")
        print_info("Server logs location depends on your configuration")
