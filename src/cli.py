"""FemtoBot CLI - Command line interface for managing the bot."""
import os
import sys
import signal
import subprocess
import time
import click

# Resolve project root from this file's location
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEMTOBOT_DIR = os.path.expanduser("~/.femtobot")
PID_FILE = os.path.join(FEMTOBOT_DIR, "femtobot.pid")
LOG_FILE = os.path.join(FEMTOBOT_DIR, "femtobot.log")

# Colors
GREEN = "green"
RED = "red"
YELLOW = "yellow"
CYAN = "cyan"


def _ensure_dir():
    """Ensure ~/.femtobot directory exists."""
    os.makedirs(FEMTOBOT_DIR, exist_ok=True)


def _read_pid():
    """Read PID from file, return None if not found or invalid."""
    try:
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def _is_running(pid):
    """Check if a process with given PID is running."""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _get_python():
    """Get the Python executable path (prefer venv if available)."""
    venv_python = os.path.join(PROJECT_ROOT, "venv_bot", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def _check_ollama():
    """Check if Ollama is reachable."""
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@click.group()
@click.version_option(version="1.0.0", prog_name="FemtoBot")
def cli():
    """🤖 FemtoBot - Smart personal assistant for local LLMs.

    Manage your FemtoBot instance from the command line.
    """
    pass


@cli.command()
def serve():
    """Start the Telegram bot in foreground (blocking)."""
    click.secho("🚀 Starting FemtoBot (foreground)...", fg=CYAN)

    # Ensure we're in the project directory for relative imports
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

    # Check Ollama
    if _check_ollama():
        click.secho("✓ Ollama detected", fg=GREEN)
    else:
        click.secho("⚠ Ollama is not running. Start it with 'ollama serve'", fg=YELLOW)

    # Import and run the bot
    from src.telegram_bot import main
    main()


@cli.command()
def start():
    """Start the Telegram bot as a background daemon."""
    _ensure_dir()

    pid = _read_pid()
    if _is_running(pid):
        click.secho(f"⚠ FemtoBot is already running (PID {pid})", fg=YELLOW)
        return

    # Check Ollama
    if not _check_ollama():
        click.secho("⚠ Ollama is not running. Start it with 'ollama serve'", fg=YELLOW)

    click.secho("🚀 Starting FemtoBot daemon...", fg=CYAN)

    python = _get_python()
    bot_script = os.path.join(PROJECT_ROOT, "src", "telegram_bot.py")

    with open(LOG_FILE, "a") as log:
        proc = subprocess.Popen(
            [python, bot_script],
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    # Brief wait to check if process started successfully
    time.sleep(1)
    if _is_running(proc.pid):
        click.secho(f"✓ FemtoBot started (PID {proc.pid})", fg=GREEN)
        click.echo(f"  Logs: {LOG_FILE}")
    else:
        click.secho("✗ FemtoBot failed to start. Check logs:", fg=RED)
        click.echo(f"  {LOG_FILE}")


@cli.command()
def stop():
    """Stop the running FemtoBot daemon."""
    pid = _read_pid()

    if not _is_running(pid):
        click.secho("⚠ FemtoBot is not running", fg=YELLOW)
        # Clean stale PID file
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return

    click.secho(f"Stopping FemtoBot (PID {pid})...", fg=CYAN)

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait for graceful shutdown
        for _ in range(10):
            if not _is_running(pid):
                break
            time.sleep(0.5)
        else:
            # Force kill if still running
            click.secho("Forcing shutdown...", fg=YELLOW)
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
    except ProcessLookupError:
        pass

    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

    click.secho("✓ FemtoBot stopped", fg=GREEN)


@cli.command()
def restart():
    """Restart the FemtoBot daemon (stop + start)."""
    # Stop
    pid = _read_pid()
    if _is_running(pid):
        click.secho(f"Stopping FemtoBot (PID {pid})...", fg=CYAN)
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                if not _is_running(pid):
                    break
                time.sleep(0.5)
            else:
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
        except ProcessLookupError:
            pass
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        click.secho("✓ Stopped", fg=GREEN)

    # Start
    click.invoke(start)


@cli.command()
def status():
    """Show FemtoBot status (running, PID, Ollama, etc)."""
    click.secho("=== FemtoBot Status ===", fg=CYAN, bold=True)

    # Bot process
    pid = _read_pid()
    if _is_running(pid):
        click.secho(f"  Bot:    ✓ Running (PID {pid})", fg=GREEN)
        # Show uptime via /proc if available
        try:
            stat = os.stat(f"/proc/{pid}")
            import datetime
            started = datetime.datetime.fromtimestamp(stat.st_mtime)
            uptime = datetime.datetime.now() - started
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            click.echo(f"  Uptime: {hours}h {minutes}m {seconds}s")
        except (FileNotFoundError, OSError):
            pass
    else:
        click.secho("  Bot:    ✗ Stopped", fg=RED)

    # Ollama
    if _check_ollama():
        click.secho("  Ollama: ✓ Running", fg=GREEN)
        try:
            import httpx
            r = httpx.get("http://localhost:11434/api/tags", timeout=3)
            models = r.json().get("models", [])
            if models:
                loaded = [m["name"] for m in models]
                click.echo(f"  Models: {', '.join(loaded)}")
        except Exception:
            pass
    else:
        click.secho("  Ollama: ✗ Not running", fg=RED)

    # Log file
    if os.path.exists(LOG_FILE):
        size = os.path.getsize(LOG_FILE)
        if size > 1024 * 1024:
            click.echo(f"  Log:    {LOG_FILE} ({size / 1024 / 1024:.1f} MB)")
        else:
            click.echo(f"  Log:    {LOG_FILE} ({size / 1024:.1f} KB)")
    else:
        click.echo("  Log:    (no logs yet)")


@cli.command()
@click.option("-f", "--follow", is_flag=True, help="Follow log output in real-time")
@click.option("-n", "--lines", default=50, help="Number of lines to show")
def logs(follow, lines):
    """Show FemtoBot logs."""
    if not os.path.exists(LOG_FILE):
        click.secho("No logs found yet. Start the bot first with 'femtobot start'", fg=YELLOW)
        return

    if follow:
        click.secho(f"Following {LOG_FILE} (Ctrl+C to stop)...\n", fg=CYAN)
        try:
            proc = subprocess.run(
                ["tail", "-f", "-n", str(lines), LOG_FILE],
            )
        except KeyboardInterrupt:
            click.echo("\n")
    else:
        try:
            result = subprocess.run(
                ["tail", "-n", str(lines), LOG_FILE],
                capture_output=True, text=True,
            )
            click.echo(result.stdout)
        except FileNotFoundError:
            # tail not available, read manually
            with open(LOG_FILE, "r") as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    click.echo(line, nl=False)


@cli.command()
def tui():
    """Launch the TUI (terminal) interface."""
    click.secho("🖥️  Starting FemtoBot TUI...", fg=CYAN)

    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, PROJECT_ROOT)

    from src.tui import FemtoBotApp
    app = FemtoBotApp()
    app.run()


@cli.command()
def config():
    """Show current configuration."""
    config_path = os.path.join(PROJECT_ROOT, "config.yaml")

    if not os.path.exists(config_path):
        click.secho("✗ config.yaml not found", fg=RED)
        return

    click.secho("=== FemtoBot Configuration ===\n", fg=CYAN, bold=True)

    with open(config_path, "r") as f:
        content = f.read()

    # Colorize YAML output
    for line in content.splitlines():
        if line.strip().startswith("#"):
            click.secho(line, fg="bright_black")
        elif ":" in line and not line.strip().startswith("-"):
            key, _, value = line.partition(":")
            click.secho(key + ":", fg=CYAN, nl=False)
            click.echo(value)
        else:
            click.echo(line)


if __name__ == "__main__":
    cli()
