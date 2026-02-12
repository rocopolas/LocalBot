"""FemtoBot CLI - Command line interface for managing the bot."""
import os
import sys
import signal
import subprocess
import time
import click
import tempfile

# Resolve project root from this file's location
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from src.constants import CONFIG_DIR, DATA_DIR

PID_FILE = os.path.join(CONFIG_DIR, "femtobot.pid")
LOG_FILE = os.path.join(CONFIG_DIR, "femtobot.log")
BOT_SCRIPT_NAME = "telegram_bot.py"

# Colors
GREEN = "green"
RED = "red"
YELLOW = "yellow"
CYAN = "cyan"


def _ensure_dir():
    """Ensure ~/.femtobot directory exists."""
    os.makedirs(CONFIG_DIR, exist_ok=True)


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


def _ensure_psutil():
    """Ensure psutil is installed, install if missing."""
    try:
        import psutil
        return psutil
    except ImportError:
        click.secho("⚠ Installing required dependency: psutil...", fg=YELLOW)
        python = _get_python()
        result = subprocess.run(
            [python, "-m", "pip", "install", "psutil>=5.9.0", "--quiet"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            click.secho(f"✗ Failed to install psutil: {result.stderr}", fg=RED)
            click.secho("  Please install manually: pip install psutil>=5.9.0", fg=YELLOW)
            sys.exit(1)
        # Reimport after installation
        import psutil
        click.secho("✓ psutil installed successfully", fg=GREEN)
        return psutil


def _kill_all_bot_processes():
    """Kill all processes related to the bot including children."""
    psutil = _ensure_psutil()
    
    killed = []
    errors = []
    
    # Find all python processes running telegram_bot.py
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pinfo = proc.info
            if pinfo['name'] and 'python' in pinfo['name'].lower():
                cmdline = ' '.join(pinfo['cmdline'] or [])
                if BOT_SCRIPT_NAME in cmdline or 'femtobot' in cmdline:
                    try:
                        # Kill the process tree
                        parent = psutil.Process(pinfo['pid'])
                        children = parent.children(recursive=True)
                        
                        # Kill children first
                        for child in children:
                            try:
                                child.terminate()
                            except psutil.NoSuchProcess:
                                pass
                        
                        # Wait for children
                        gone, alive = psutil.wait_procs(children, timeout=2)
                        
                        # Force kill if still alive
                        for child in alive:
                            try:
                                child.kill()
                            except psutil.NoSuchProcess:
                                pass
                        
                        # Kill parent
                        parent.terminate()
                        try:
                            parent.wait(timeout=2)
                        except psutil.TimeoutExpired:
                            parent.kill()
                        
                        killed.append(pinfo['pid'])
                    except Exception as e:
                        errors.append(f"PID {pinfo['pid']}: {e}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    # Also try to kill by PID file if exists
    pid = _read_pid()
    if pid and pid not in killed:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            if _is_running(pid):
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
        except ProcessLookupError:
            pass
        except Exception as e:
            errors.append(f"PID file {pid}: {e}")
    
    return killed, errors


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

    # Check if daemon is running
    pid = _read_pid()
    if _is_running(pid):
        click.secho(f"⚠ FemtoBot daemon is already running (PID {pid})", fg=RED)
        click.secho("  Run 'femtobot stop' first, or 'femtobot logs -f' to monitor it.", fg=YELLOW)
        return

    # Ensure we're in the config directory for relative paths
    _ensure_dir()
    os.chdir(CONFIG_DIR)
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
            cwd=CONFIG_DIR,
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
    """Stop the running FemtoBot daemon (kills all processes)."""
    pid = _read_pid()
    
    # Ensure psutil is available
    psutil = _ensure_psutil()
    
    # Check if any bot processes are running
    bot_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pinfo = proc.info
            if pinfo['name'] and 'python' in pinfo['name'].lower():
                cmdline = ' '.join(pinfo['cmdline'] or [])
                if BOT_SCRIPT_NAME in cmdline or 'femtobot' in cmdline:
                    bot_procs.append(pinfo['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if not bot_procs and not _is_running(pid):
        click.secho("⚠ FemtoBot is not running", fg=YELLOW)
        # Clean stale PID file
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        return

    if bot_procs:
        click.secho(f"Found {len(bot_procs)} bot process(es): {bot_procs}", fg=CYAN)
    elif pid:
        click.secho(f"Stopping FemtoBot (PID {pid})...", fg=CYAN)

    # Kill all bot processes
    killed, errors = _kill_all_bot_processes()
    
    if killed:
        click.secho(f"✓ Killed {len(killed)} process(es): {killed}", fg=GREEN)
    
    if errors:
        click.secho(f"⚠ Errors during kill: {errors}", fg=YELLOW)

    # Clean PID file
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    
    # Double check no processes remain
    time.sleep(0.5)
    remaining = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pinfo = proc.info
            if pinfo['name'] and 'python' in pinfo['name'].lower():
                cmdline = ' '.join(pinfo['cmdline'] or [])
                if BOT_SCRIPT_NAME in cmdline or 'femtobot' in cmdline:
                    remaining.append(pinfo['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if remaining:
        click.secho(f"✗ Warning: {len(remaining)} process(es) still alive: {remaining}", fg=RED)
        click.secho("  You may need to kill them manually with: kill -9 " + " ".join(map(str, remaining)))
    else:
        click.secho("✓ FemtoBot stopped completely (0 processes remaining)", fg=GREEN)


@cli.command()
@click.pass_context
def restart(ctx):
    """Restart the FemtoBot daemon (stop all processes + start)."""
    # Ensure psutil is available
    psutil = _ensure_psutil()
    
    # Check for existing processes
    bot_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            pinfo = proc.info
            if pinfo['name'] and 'python' in pinfo['name'].lower():
                cmdline = ' '.join(pinfo['cmdline'] or [])
                if BOT_SCRIPT_NAME in cmdline or 'femtobot' in cmdline:
                    bot_procs.append(pinfo['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    pid = _read_pid()
    
    # Stop all processes
    if bot_procs or _is_running(pid):
        if bot_procs:
            click.secho(f"Stopping {len(bot_procs)} bot process(es): {bot_procs}...", fg=CYAN)
        else:
            click.secho(f"Stopping FemtoBot (PID {pid})...", fg=CYAN)
        
        killed, errors = _kill_all_bot_processes()
        
        if killed:
            click.secho(f"✓ Killed {len(killed)} process(es)", fg=GREEN)
        
        if errors:
            click.secho(f"⚠ Some errors occurred: {errors}", fg=YELLOW)
        
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        
        # Wait to ensure all processes are dead
        time.sleep(1)
        
        # Verify all processes are dead
        remaining = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pinfo = proc.info
                if pinfo['name'] and 'python' in pinfo['name'].lower():
                    cmdline = ' '.join(pinfo['cmdline'] or [])
                    if BOT_SCRIPT_NAME in cmdline or 'femtobot' in cmdline:
                        remaining.append(pinfo['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if remaining:
            click.secho(f"⚠ Warning: {len(remaining)} process(es) still alive, attempting force kill...", fg=YELLOW)
            for rpid in remaining:
                try:
                    os.kill(rpid, signal.SIGKILL)
                except:
                    pass
            time.sleep(0.5)
        
        click.secho("✓ All bot processes stopped", fg=GREEN)
    else:
        click.secho("⚠ No running bot processes found", fg=YELLOW)

    # Start
    click.echo()
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

    os.chdir(CONFIG_DIR)
    sys.path.insert(0, PROJECT_ROOT)

    from src.tui import FemtoBotApp
    app = FemtoBotApp()
    app.run()


@cli.command()
def config():
    """Show current configuration."""
    config_path = os.path.join(CONFIG_DIR, "config.yaml")

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

    # Check Python version
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 12):
        click.secho(f"⚠ Warning: You are running Python {v.major}.{v.minor}.{v.micro}", fg=YELLOW)
        click.secho("  FemtoBot is designed for Python 3.12+. Some features may not work.", fg=YELLOW)
        if not click.confirm("  Do you want to continue anyway?", default=False):
            return
    else:
        click.secho(f"✓ Python {v.major}.{v.minor}.{v.micro} detected", fg=GREEN)

    # Ensure config directory exists
    from src.constants import CONFIG_DIR, DATA_DIR
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    config_path = os.path.join(CONFIG_DIR, "config.yaml")

    # Create config if missing
    if not os.path.exists(config_path):
        click.secho(f"⚠ config.yaml not found at {config_path}", fg=YELLOW)
        click.secho("  Creating default configuration...", fg=CYAN)
        
        from utils.config_loader import DEFAULT_CONFIG
        # Update paths in default config to be absolute or relative to CONFIG_DIR correctly
        # Actually, DEFAULT_CONFIG uses relative paths like "data/instructions.md"
        # which will resolve relative to where the bot is run/configured.
        
        try:
            with open(config_path, "w") as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False)
            click.secho("  ✓ Created config.yaml", fg=GREEN)
        except Exception as e:
            click.secho(f"  ✗ Failed to create config.yaml: {e}", fg=RED)
            return

    # Check for .env
    env_path = os.path.join(CONFIG_DIR, ".env")
    if not os.path.exists(env_path):
        click.secho(f"⚠ .env not found at {env_path}", fg=YELLOW)
        click.secho("  Configuration required:", fg=CYAN)
        
        telegram_token = click.prompt("🤖 Telegram Bot Token", type=str)
        auth_users = click.prompt("👥 Authorized Users (comma-separated IDs)", type=str)
        notif_chat = click.prompt("📢 Notification Chat ID", default=auth_users.split(',')[0].strip(), show_default=True)
        
        click.echo("\n--- Optional Integrations (press Enter to skip) ---")
        brave_key = click.prompt("🔍 Brave Search API Key", default="", show_default=False)
        gmail_user = click.prompt("📧 Gmail User", default="", show_default=False)
        gmail_pass = ""
        if gmail_user:
            gmail_pass = click.prompt("🔑 Gmail App Password", default="", hide_input=True, show_default=False)
            
        try:
            with open(env_path, "w") as f:
                f.write(f"# Telegram\nTELEGRAM_TOKEN={telegram_token}\nAUTHORIZED_USERS={auth_users}\nNOTIFICATION_CHAT_ID={notif_chat}\n\n")
                if brave_key:
                    f.write(f"# Search\nBRAVE_API_KEY={brave_key}\n\n")
                if gmail_user:
                    f.write(f"# Email\nGMAIL_USER={gmail_user}\nGMAIL_APP_PASSWORD={gmail_pass}\n")
                    
            click.secho("  ✓ Created .env", fg=GREEN)
        except Exception as e:
            click.secho(f"  ✗ Failed to create .env: {e}", fg=RED)

    # Reload config now that it exists
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f) or {}

    # Ensure default data files exist
    try:
        # Instructions
        instr_file = cfg.get("INSTRUCTIONS_FILE", "data/instructions.md")
        instr_path = os.path.join(CONFIG_DIR, instr_file)
        # Ensure parent dir exists for instructions (e.g. data/)
        os.makedirs(os.path.dirname(instr_path), exist_ok=True)
        
        if not os.path.exists(instr_path):
            click.secho(f"  Creating default instructions at {instr_file}...", fg=CYAN)
            try:
                # Try to load from "data" package
                import importlib.resources
                content = importlib.resources.read_text("data", "instructions.md")
            except (ImportError, FileNotFoundError):
                # Fallback if package data not found (e.g. running from source without install)
                # In dev mode, data/instructions.md is at PROJECT_ROOT/data/instructions.md
                fallback_path = os.path.join(PROJECT_ROOT, "data", "instructions.md")
                if os.path.exists(fallback_path):
                     with open(fallback_path, "r", encoding="utf-8") as f:
                        content = f.read()
                else:
                    content = "Eres un asistente útil." # Minimal fallback

            with open(instr_path, "w", encoding="utf-8") as f:
                f.write(content.strip())
            click.secho(f"  ✓ Created {instr_file}", fg=GREEN)

        # Events
        events_file = cfg.get("EVENTS_FILE", "data/events.txt")
        events_path = os.path.join(CONFIG_DIR, events_file)
        os.makedirs(os.path.dirname(events_path), exist_ok=True)
        
        if not os.path.exists(events_path):
            with open(events_path, "w", encoding="utf-8") as f:
                f.write("") # Empty file
            click.secho(f"  ✓ Created empty {events_file}", fg=GREEN)

        # Memory (optional, but good to have)
        memory_file = cfg.get("MEMORY_FILE", "data/memory.md")
        if memory_file:
            memory_path = os.path.join(CONFIG_DIR, memory_file)
            os.makedirs(os.path.dirname(memory_path), exist_ok=True)
            if not os.path.exists(memory_path):
                with open(memory_path, "w", encoding="utf-8") as f:
                    f.write("# Memory Store\n")
                click.secho(f"  ✓ Created {memory_file}", fg=GREEN)

    except Exception as e:
        click.secho(f"  ⚠ Failed to ensure data files: {e}", fg=YELLOW)

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
        # Continue to setup models even if none found? No, return.
        return

    # Check Ollama
    if not _check_ollama():
        click.secho("✗ Ollama is not running.", fg=RED)
        click.secho("  Please start Ollama (e.g. 'ollama serve') and RUN 'femtobot setup' AGAIN to download models.", fg=YELLOW)
        return

    # Get already-downloaded models
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=5)
        existing = {m["name"] for m in r.json().get("models", [])}
    except Exception:
        existing = set()

    click.secho("=== FemtoBot Setup ===\n", fg=CYAN, bold=True)
    click.secho(f"Configuration directory: {CONFIG_DIR}", fg=CYAN)

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
    click.secho(f"IMPORTANT: Edit {os.path.join(CONFIG_DIR, '.env')} with your Telegram Token!", fg=YELLOW, bold=True)


# ─── UPDATE ───────────────────────────────────────────────────────────

@cli.command()
def update():
    """Update FemtoBot (git pull OR install latest release)."""
    click.secho("=== FemtoBot Update ===\n", fg=CYAN, bold=True)

    git_dir = os.path.join(PROJECT_ROOT, ".git")
    python = _get_python()

    if os.path.isdir(git_dir):
        # --- GIT UPDATE STRATEGY ---
        click.secho("  Pulling latest changes (git)...", fg=CYAN)
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

        # Re-install package editable
        result = subprocess.run(
            [python, "-m", "pip", "install", "-e", ".", "--quiet"],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            click.secho("  ✓ CLI re-installed", fg=GREEN)

    else:
        # --- GITHUB RELEASE STRATEGY ---
        click.secho("  Git not found. Checking latest release on GitHub...", fg=CYAN)
        try:
            import httpx
            resp = httpx.get("https://api.github.com/repos/rocopolas/FemtoBot/releases/latest", timeout=10.0)
            
            if resp.status_code == 404:
                click.secho("  ✗ No releases found on GitHub repo.", fg=RED)
                return
            
            if resp.status_code != 200:
                click.secho(f"  ✗ Failed to fetch releases: HTTP {resp.status_code}", fg=RED)
                return

            data = resp.json()
            tag_name = data.get("tag_name", "unknown")
            assets = data.get("assets", [])
            
            whl_url = None
            for asset in assets:
                if asset["name"].endswith(".whl"):
                    whl_url = asset["browser_download_url"]
                    break
            
            if not whl_url:
                click.secho(f"  ✗ No .whl file found in release {tag_name}", fg=RED)
                return

            click.secho(f"  Found release: {tag_name}", fg=GREEN)
            click.secho("  Upgrading package via pip...", fg=CYAN)
            
            # Install the wheel
            install_cmd = [python, "-m", "pip", "install", "--upgrade", whl_url]
            
            # Show output for transparency
            proc = subprocess.Popen(
                install_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = proc.communicate()
            
            if proc.returncode == 0:
                click.secho(f"  ✓ Successfully upgraded to {tag_name}", fg=GREEN)
            else:
                click.secho(f"  ✗ Upgrade failed:\n{stderr}", fg=RED)
                return

        except ImportError:
            click.secho("  ✗ 'httpx' library missing (required for updates).", fg=RED)
            return
        except Exception as e:
            click.secho(f"  ✗ Error during update: {e}", fg=RED)
            return

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

    data_dir = DATA_DIR
    config_file = os.path.join(CONFIG_DIR, "config.yaml")
    env_file = os.path.join(CONFIG_DIR, ".env")

    if not os.path.exists(data_dir):
        click.secho("✗ data/ directory not found", fg=RED)
        return

    _ensure_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = output or os.path.join(CONFIG_DIR, f"backup_{timestamp}.tar.gz")

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
        tar.extractall(path=CONFIG_DIR)

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
        
        # Auto-install offer
        if click.confirm("  Would you like to try installing Python 3.12 automatically? (Linux only)", default=True):
            try:
                import importlib.resources
                import subprocess
                import stat
                
                # Extract script to temp file
                try:
                    # Python 3.9+
                    import src.scripts
                    script_content = importlib.resources.read_text("src.scripts", "install_python.sh")
                except ImportError:
                    # Fallback for older python or dev mode
                    script_path = os.path.join(PROJECT_ROOT, "src", "scripts", "install_python.sh")
                    if os.path.exists(script_path):
                        with open(script_path, "r") as f:
                            script_content = f.read()
                    else:
                        raise FileNotFoundError("Scripts package not found")

                tmp_script = os.path.join(tempfile.gettempdir(), "femtobot_install_python.sh")
                with open(tmp_script, "w") as f:
                    f.write(script_content)
                
                # Make executable
                os.chmod(tmp_script, os.stat(tmp_script).st_mode | stat.S_IEXEC)
                
                click.secho("  Running installer... (requires sudo)", fg=CYAN)
                ret_code = subprocess.call([tmp_script])
                
                if ret_code == 0:
                    click.secho("  ✓ Python 3.12 installed & Environment created!", fg=GREEN)
                    click.secho("  ⚠ To switch to the new version, just run:", fg=YELLOW)
                    click.secho("    source venv_bot/bin/activate", fg=CYAN)
                    click.secho("    femtobot setup", fg=CYAN)
                    return # Exit to force user to switch
                else:
                    click.secho("  ✗ Installation failed.", fg=RED)
                
                # Cleanup
                if os.path.exists(tmp_script):
                    os.remove(tmp_script)
                    
            except Exception as e:
                click.secho(f"  ✗ Failed to run installer: {e}", fg=RED)


    # 2. Venv (Dev mode only)
    from src.constants import IS_DEV_MODE
    if IS_DEV_MODE:
        venv_path = os.path.join(PROJECT_ROOT, "venv_bot")
        if os.path.exists(venv_path):
            click.secho("  ✓ venv_bot exists", fg=GREEN)
        else:
            click.secho("  ✗ venv_bot not found (run ./run.sh first)", fg=RED)
            issues += 1
    else:
         if sys.prefix != sys.base_prefix:
            click.secho("  ✓ Running in venv (pip installed)", fg=GREEN)
         else:
            click.secho("  ⚠ Not running in a virtual environment (recommended)", fg=YELLOW)

    # 3. Config files
    config_path = os.path.join(CONFIG_DIR, "config.yaml")
    env_path = os.path.join(CONFIG_DIR, ".env")

    # 3.1 config.yaml
    if os.path.exists(config_path):
        click.secho("  ✓ config.yaml found", fg=GREEN)
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        click.secho("  ✗ config.yaml missing", fg=RED)
        issues += 1
        cfg = {} # Ensure cfg is defined even if file is missing

    # 3.2 .env
    if os.path.exists(env_path):
        click.secho("  ✓ .env found", fg=GREEN)
        
        # Check specific vars
        from dotenv import dotenv_values
        config = dotenv_values(env_path)
        
        if config.get("TELEGRAM_TOKEN"):
             click.secho("  ✓ TELEGRAM_TOKEN set", fg=GREEN)
        else:
             click.secho("  ✗ TELEGRAM_TOKEN missing", fg=RED)
             issues += 1
             
        if config.get("AUTHORIZED_USERS"):
             click.secho("  ✓ AUTHORIZED_USERS set", fg=GREEN)
        else:
             click.secho("  ✗ AUTHORIZED_USERS missing", fg=RED)
             issues += 1
             
        # Optional warnings
        if config.get("BRAVE_API_KEY"): click.secho("  ✓ BRAVE_API_KEY set", fg=GREEN)
        if config.get("GMAIL_USER"): click.secho("  ✓ GMAIL_USER set", fg=GREEN)
        if config.get("NOTIFICATION_CHAT_ID"): click.secho("  ✓ NOTIFICATION_CHAT_ID set", fg=GREEN)

    else:
        click.secho("  ✗ .env missing", fg=RED)
        issues += 1

    # 4. Data directory
    data_dir = DATA_DIR
    if os.path.exists(data_dir) and os.access(data_dir, os.W_OK):
        click.secho(f"  ✓ data/ writable ({data_dir})", fg=GREEN)
    else:
        click.secho(f"  ✗ data/ missing or not writable ({data_dir})", fg=RED)
        issues += 1

    # 5. Environment variables (This section is now redundant due to .env check above, removing it)
    # 6. Ollama
    if _check_ollama():
        click.secho("\n  ✓ Ollama running", fg=GREEN)
        
        # Check models
        models = [
            ("MODEL", cfg.get("MODEL")),
            ("VISION_MODEL", cfg.get("VISION_MODEL")),
            ("MATH_MODEL", cfg.get("MATH_MODEL")),
            ("OCR_MODEL", cfg.get("RAG", {}).get("OCR_MODEL", "glm-ocr:latest")),
            ("EMBEDDING", cfg.get("RAG", {}).get("EMBEDDING_MODEL"))
        ]
        
        available_models = []
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                available_models = [m["name"] for m in data.get("models", [])]
        except:
             pass
            
        for name, model_name in models:
            if not model_name: continue
            
            # Simple check if model string is in available tags
            found = False
            for avail in available_models:
                if model_name in avail:
                    found = True
                    break
            
            if found:
                click.secho(f"  ✓ {name}: {model_name} found", fg=GREEN)
            else:
                click.secho(f"  ✗ {name}: {model_name} (not downloaded — run 'femtobot setup')", fg=RED)
                issues += 1
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

