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
@click.pass_context
def restart(ctx):
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
    ctx.invoke(start)



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


# ─── SETUP ────────────────────────────────────────────────────────────

@cli.command()
def setup():
    """Download required Ollama models from config.yaml."""
    import yaml

    config_path = os.path.join(PROJECT_ROOT, "config.yaml")
    if not os.path.exists(config_path):
        click.secho("✗ config.yaml not found", fg=RED)
        return

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    # Collect model names from config
    model_keys = ["MODEL", "VISION_MODEL", "MATH_MODEL", "OCR_MODEL"]
    rag_config = cfg.get("RAG", {})
    models = []

    for key in model_keys:
        val = cfg.get(key)
        if val:
            models.append((key, val))

    embed_model = rag_config.get("EMBEDDING_MODEL")
    if embed_model:
        models.append(("EMBEDDING_MODEL", embed_model))

    if not models:
        click.secho("No models found in config.yaml", fg=YELLOW)
        return

    # Check Ollama
    if not _check_ollama():
        click.secho("✗ Ollama is not running. Start it with 'ollama serve'", fg=RED)
        return

    # Get already-downloaded models
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=5)
        existing = {m["name"] for m in r.json().get("models", [])}
    except Exception:
        existing = set()

    click.secho("=== FemtoBot Setup ===\n", fg=CYAN, bold=True)

    for key, model_name in models:
        if model_name in existing:
            click.secho(f"  ✓ {key}: {model_name} (already downloaded)", fg=GREEN)
        else:
            click.secho(f"  ⬇ {key}: {model_name} — pulling...", fg=CYAN)
            result = subprocess.run(
                ["ollama", "pull", model_name],
                capture_output=False,
            )
            if result.returncode == 0:
                click.secho(f"  ✓ {model_name} downloaded", fg=GREEN)
            else:
                click.secho(f"  ✗ Failed to pull {model_name}", fg=RED)

    click.echo()
    click.secho("✓ Setup complete!", fg=GREEN)


# ─── UPDATE ───────────────────────────────────────────────────────────

@cli.command()
def update():
    """Update FemtoBot (git pull + install dependencies)."""
    click.secho("=== FemtoBot Update ===\n", fg=CYAN, bold=True)

    # Git pull
    click.secho("  Pulling latest changes...", fg=CYAN)
    result = subprocess.run(
        ["git", "pull"],
        cwd=PROJECT_ROOT,
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        output = result.stdout.strip()
        if "Already up to date" in output:
            click.secho("  ✓ Already up to date", fg=GREEN)
        else:
            click.secho(f"  ✓ Updated:\n{output}", fg=GREEN)
    else:
        click.secho(f"  ✗ Git pull failed: {result.stderr.strip()}", fg=RED)
        return

    # Install deps
    click.secho("  Installing dependencies...", fg=CYAN)
    python = _get_python()
    result = subprocess.run(
        [python, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"],
        cwd=PROJECT_ROOT,
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.secho("  ✓ Dependencies updated", fg=GREEN)
    else:
        click.secho(f"  ✗ pip install failed: {result.stderr.strip()}", fg=RED)
        return

    # Re-install package
    result = subprocess.run(
        [python, "-m", "pip", "install", "-e", ".", "--quiet"],
        cwd=PROJECT_ROOT,
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.secho("  ✓ CLI re-installed", fg=GREEN)

    click.echo()
    click.secho("✓ Update complete!", fg=GREEN)


# ─── MEMORY ───────────────────────────────────────────────────────────

@cli.group()
def memory():
    """Manage FemtoBot's vector memory (RAG)."""
    pass


@memory.command("search")
@click.argument("query")
@click.option("-n", "--limit", default=5, help="Max results to show")
@click.option("-t", "--type", "collection_type", default="memory",
              type=click.Choice(["memory", "documents"]),
              help="Collection to search")
def memory_search(query, limit, collection_type):
    """Search the vector memory for a query."""
    import asyncio

    sys.path.insert(0, PROJECT_ROOT)

    click.secho(f"🔍 Searching '{query}' in {collection_type}...\n", fg=CYAN)

    async def _search():
        from utils.config_loader import get_all_config
        from src.client import OllamaClient
        from src.memory.vector_store import VectorManager

        vm = VectorManager(get_all_config(), OllamaClient())

        # Use raw ChromaDB query for broader results (ignore threshold)
        query_embedding = await vm._get_embedding(query)
        if not query_embedding:
            click.secho("✗ Failed to generate embedding (is Ollama running?)", fg=RED)
            return

        collection = vm.memory_collection if collection_type == "memory" else vm.documents_collection
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
        )

        if not results["documents"] or not results["documents"][0]:
            click.secho("No results found.", fg=YELLOW)
            return

        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i] if results["distances"] else 0
            similarity = 1 - distance
            # Color based on similarity
            if similarity >= 0.6:
                color = GREEN
            elif similarity >= 0.4:
                color = YELLOW
            else:
                color = RED

            click.secho(f"  [{i+1}] ", fg=CYAN, nl=False)
            click.secho(f"({similarity:.1%}) ", fg=color, nl=False)
            # Truncate long docs
            preview = doc[:120].replace("\n", " ")
            if len(doc) > 120:
                preview += "..."
            click.echo(preview)

    asyncio.run(_search())


@memory.command("status")
def memory_status():
    """Show vector memory statistics."""
    sys.path.insert(0, PROJECT_ROOT)

    click.secho("=== Memory Status ===\n", fg=CYAN, bold=True)

    try:
        import chromadb
        from src.constants import DATA_DIR

        db_path = os.path.join(DATA_DIR, "chroma_db")

        if not os.path.exists(db_path):
            click.secho("  No vector database found yet.", fg=YELLOW)
            return

        client = chromadb.PersistentClient(path=db_path)

        # Memory collection
        try:
            mem = client.get_collection("memory")
            mem_count = mem.count()
            click.secho(f"  🧠 Memories:  {mem_count} entries", fg=GREEN)
        except Exception:
            click.echo("  🧠 Memories:  (collection not created)")

        # Documents collection
        try:
            docs = client.get_collection("documents")
            docs_count = docs.count()
            click.secho(f"  📄 Documents: {docs_count} chunks", fg=GREEN)
        except Exception:
            click.echo("  📄 Documents: (collection not created)")

        # DB size on disk
        total_size = 0
        for dirpath, _, filenames in os.walk(db_path):
            for f in filenames:
                total_size += os.path.getsize(os.path.join(dirpath, f))

        if total_size > 1024 * 1024:
            click.echo(f"  💾 DB size:   {total_size / 1024 / 1024:.1f} MB")
        else:
            click.echo(f"  💾 DB size:   {total_size / 1024:.1f} KB")

        click.echo(f"  📂 Path:      {db_path}")

    except Exception as e:
        click.secho(f"  ✗ Error reading database: {e}", fg=RED)


# ─── BACKUP / RESTORE ────────────────────────────────────────────────

@cli.command()
@click.option("-o", "--output", default=None, help="Output file path")
def backup(output):
    """Backup data directory (memory, events, instructions)."""
    import tarfile
    from datetime import datetime

    data_dir = os.path.join(PROJECT_ROOT, "data")
    config_file = os.path.join(PROJECT_ROOT, "config.yaml")
    env_file = os.path.join(PROJECT_ROOT, ".env")

    if not os.path.exists(data_dir):
        click.secho("✗ data/ directory not found", fg=RED)
        return

    _ensure_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = output or os.path.join(FEMTOBOT_DIR, f"backup_{timestamp}.tar.gz")

    click.secho(f"📦 Creating backup...", fg=CYAN)

    with tarfile.open(backup_path, "w:gz") as tar:
        tar.add(data_dir, arcname="data")
        if os.path.exists(config_file):
            tar.add(config_file, arcname="config.yaml")
        if os.path.exists(env_file):
            tar.add(env_file, arcname=".env")

    size = os.path.getsize(backup_path)
    if size > 1024 * 1024:
        size_str = f"{size / 1024 / 1024:.1f} MB"
    else:
        size_str = f"{size / 1024:.1f} KB"

    click.secho(f"✓ Backup created: {backup_path} ({size_str})", fg=GREEN)


@cli.command()
@click.argument("backup_file", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Overwrite existing files without asking")
def restore(backup_file, force):
    """Restore data from a backup file."""
    import tarfile

    if not tarfile.is_tarfile(backup_file):
        click.secho("✗ Not a valid backup file", fg=RED)
        return

    if not force:
        click.confirm(
            "⚠ This will overwrite current data. Continue?",
            abort=True,
        )

    click.secho(f"📦 Restoring from {backup_file}...", fg=CYAN)

    with tarfile.open(backup_file, "r:gz") as tar:
        tar.extractall(path=PROJECT_ROOT)

    click.secho("✓ Restore complete!", fg=GREEN)
    click.echo("  Restart FemtoBot to apply changes: femtobot restart")


# ─── DOCTOR ───────────────────────────────────────────────────────────

@cli.command()
def doctor():
    """Run diagnostic checks on FemtoBot."""
    import yaml

    click.secho("=== FemtoBot Doctor ===\n", fg=CYAN, bold=True)
    issues = 0

    # 1. Python version
    v = sys.version_info
    if v.major == 3 and v.minor == 12:
        click.secho(f"  ✓ Python {v.major}.{v.minor}.{v.micro}", fg=GREEN)
    else:
        click.secho(f"  ✗ Python {v.major}.{v.minor} (3.12 required)", fg=RED)
        issues += 1

    # 2. Venv
    venv_path = os.path.join(PROJECT_ROOT, "venv_bot")
    if os.path.exists(venv_path):
        click.secho("  ✓ venv_bot exists", fg=GREEN)
    else:
        click.secho("  ✗ venv_bot not found (run ./run.sh first)", fg=RED)
        issues += 1

    # 3. Config files
    for name in ["config.yaml", ".env"]:
        path = os.path.join(PROJECT_ROOT, name)
        if os.path.exists(path):
            click.secho(f"  ✓ {name} found", fg=GREEN)
        else:
            click.secho(f"  ✗ {name} missing", fg=RED)
            issues += 1

    # 4. Data directory
    data_dir = os.path.join(PROJECT_ROOT, "data")
    if os.path.exists(data_dir) and os.access(data_dir, os.W_OK):
        click.secho("  ✓ data/ writable", fg=GREEN)
    else:
        click.secho("  ✗ data/ not writable or missing", fg=RED)
        issues += 1

    # 5. Environment variables
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

    env_checks = {
        "TELEGRAM_TOKEN": "Telegram bot token",
        "AUTHORIZED_USERS": "Authorized user IDs",
    }
    optional_env = {
        "BRAVE_API_KEY": "Brave Search API",
        "GMAIL_USER": "Gmail integration",
        "NOTIFICATION_CHAT_ID": "Notification chat",
    }

    for var, desc in env_checks.items():
        val = os.getenv(var)
        if val and val.strip():
            click.secho(f"  ✓ {var} set", fg=GREEN)
        else:
            click.secho(f"  ✗ {var} not set ({desc})", fg=RED)
            issues += 1

    for var, desc in optional_env.items():
        val = os.getenv(var)
        if val and val.strip():
            click.secho(f"  ✓ {var} set", fg=GREEN)
        else:
            click.secho(f"  ⚠ {var} not set ({desc}, optional)", fg=YELLOW)

    # 6. Ollama
    click.echo()
    if _check_ollama():
        click.secho("  ✓ Ollama running", fg=GREEN)

        # Check required models
        try:
            import httpx
            r = httpx.get("http://localhost:11434/api/tags", timeout=3)
            existing = {m["name"] for m in r.json().get("models", [])}

            config_path = os.path.join(PROJECT_ROOT, "config.yaml")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    cfg = yaml.safe_load(f) or {}

                for key in ["MODEL", "VISION_MODEL", "MATH_MODEL", "OCR_MODEL"]:
                    model = cfg.get(key)
                    if model:
                        if model in existing:
                            click.secho(f"  ✓ {key}: {model}", fg=GREEN)
                        else:
                            click.secho(f"  ✗ {key}: {model} (not downloaded — run 'femtobot setup')", fg=RED)
                            issues += 1

                embed = cfg.get("RAG", {}).get("EMBEDDING_MODEL")
                if embed:
                    if embed in existing:
                        click.secho(f"  ✓ EMBEDDING: {embed}", fg=GREEN)
                    else:
                        click.secho(f"  ✗ EMBEDDING: {embed} (not downloaded)", fg=RED)
                        issues += 1
        except Exception:
            pass
    else:
        click.secho("  ✗ Ollama not running", fg=RED)
        issues += 1

    # 7. FFmpeg
    click.echo()
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        click.secho("  ✓ FFmpeg installed", fg=GREEN)
    except (FileNotFoundError, subprocess.CalledProcessError):
        click.secho("  ✗ FFmpeg not found (needed for audio)", fg=RED)
        issues += 1

    # 8. ChromaDB
    try:
        import chromadb
        click.secho(f"  ✓ ChromaDB {chromadb.__version__}", fg=GREEN)
    except ImportError:
        click.secho("  ✗ ChromaDB not installed", fg=RED)
        issues += 1

    # Summary
    click.echo()
    if issues == 0:
        click.secho("  🎉 All checks passed!", fg=GREEN, bold=True)
    else:
        click.secho(f"  ⚠ {issues} issue(s) found", fg=YELLOW, bold=True)


if __name__ == "__main__":
    cli()

