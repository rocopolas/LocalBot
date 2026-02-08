"""Main TUI application for FemtoBot - Refactored version."""
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Input, Header, Footer, Static, Markdown
import re
import os
import sys
import logging
from datetime import datetime

# Add parent directory to path
# Add parent directory to path
import os
import sys
_ABS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ABS_ROOT)

from src.constants import PROJECT_ROOT
from src.state.chat_manager import ChatManager
from src.client import OllamaClient
from src.tui_utils.history_manager import TUIHistoryManager
from src.tui_handlers.command_processor import TUICommandProcessor
from src.tui_handlers.slash_commands import TUISlashCommands
from utils.config_loader import get_config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class MessageWidget(Markdown):
    """Widget for displaying chat messages."""
    
    def __init__(self, content, is_user=False, timestamp=None, extra_classes=None):
        if is_user and timestamp is None:
            self.timestamp = datetime.now().strftime("%H:%M")
        else:
            self.timestamp = timestamp
            
        super().__init__(content)
        self.is_user = is_user
        self.add_class("message")
        
        if is_user:
            self.add_class("user-message")
        else:
            self.add_class("bot-message")
            
        if extra_classes:
            self.add_class(extra_classes)
            
    def format_content(self, content):
        """Format message content."""
        # Strip ANSI codes
        content = re.sub(r'\x1b\[[0-9;]*m', '', content)
        
        # Format think blocks
        content = content.replace("<think>", "> 🧠 **Pensando:**\n> ")
        content = content.replace("</think>", "\n\n")
        
        # Add timestamp
        if self.timestamp:
            content += f"  \n_{self.timestamp}_"
        
        return content

    async def update(self, content):
        await super().update(self.format_content(content))


class FemtoBotApp(App):
    """Main TUI application."""
    
    CSS_PATH = os.path.join(PROJECT_ROOT, "assets", "styles.tcss")
    TITLE = "FemtoBot TUI"
    SUB_TITLE = "Powered by Ollama"
    
    def __init__(self):
        super().__init__()
        self.client = OllamaClient()
        self.model = get_config("MODEL")
        self.vision_model = get_config("VISION_MODEL")
        
        # Initialize managers
        self.chat_manager = ChatManager(max_inactive_hours=24)
        self.history_manager = TUIHistoryManager()
        
        # Initialize handlers
        self.command_processor = TUICommandProcessor(self._output_message)
        self.slash_commands = TUISlashCommands(
            self._output_message,
            history_manager=self.history_manager,
            chat_manager=self.chat_manager
        )
        
        # Chat ID for TUI (using -1 for local)
        self.chat_id = -1
        
        # File watcher
        self.events_file = os.path.join(PROJECT_ROOT, get_config("EVENTS_FILE"))
        if not os.path.exists(self.events_file):
            open(self.events_file, 'w').close()
        
        # Load system instructions (synchronously)
        self._system_instructions = ""
        try:
            instructions_path = os.path.join(PROJECT_ROOT, get_config("INSTRUCTIONS_FILE"))
            with open(instructions_path, "r", encoding="utf-8") as f:
                self._system_instructions = f.read().strip()
        except FileNotFoundError:
            pass
        
        # Load persisted history (synchronously)
        self._pending_history = self.history_manager.load_history("default")
    
    def _output_message(self, message: str, style: str = "info"):
        """Output a system message to the chat."""
        # Schedule in event loop
        asyncio.create_task(self._add_system_message(message, style))
    
    async def _add_system_message(self, message: str, style: str = "info"):
        """Add a system message to the chat display."""
        container = self.query_one("#chat-container")
        msg_container = Vertical(classes=f"message-container bot-container {style}-container")
        await container.mount(msg_container)
        
        timestamp = datetime.now().strftime("%H:%M")
        await msg_container.mount(MessageWidget(message, is_user=False, timestamp=timestamp))
        container.scroll_end(animate=True)

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        yield ScrollableContainer(id="chat-container")
        yield Input(
            placeholder="Escribe tu mensaje... (Escribe 'salir' o /quit para cerrar)",
            id="chat-input"
        )
        yield Footer()

    async def on_mount(self):
        """Called when app mounts."""
        # Initialize chat with system instructions
        if self._system_instructions:
            await self.chat_manager.initialize_chat(self.chat_id, self._system_instructions)
            logger.info("Instructions loaded")
        
        # Load persisted history if exists
        if self._pending_history:
            await self.chat_manager.set_history(self.chat_id, self._pending_history)
            logger.info(f"Loaded {len(self._pending_history)} messages from history")
            self._pending_history = None
        
        # Start event checker
        self.set_interval(2.0, self.check_events)
        
        # Show welcome message
        self._output_message(
            "🤖 FemtoBot TUI iniciado\n"
            "Escribe /help para ver comandos disponibles",
            "info"
        )

    async def check_events(self):
        """Check for events from cron jobs."""
        try:
            if os.path.getsize(self.events_file) > 0:
                with open(self.events_file, 'r+', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        for line in content.strip().split('\n'):
                            if line.strip():
                                await self._add_system_message(f"🔔 {line.strip()}", "notification")
                        
                        # Clear file
                        f.seek(0)
                        f.truncate()
        except Exception as e:
            logger.error(f"Error checking events: {e}")

    async def on_unmount(self):
        """Called when app exits."""
        # Save history
        history = await self.chat_manager.get_history(self.chat_id)
        self.history_manager.save_history(history, "default")
        
        # Unload models
        if self.model:
            await self.client.unload_model(self.model)
        if self.vision_model:
            await self.client.unload_model(self.vision_model)
        
        logger.info("FemtoBot TUI shutdown complete")

    async def on_input_submitted(self, event: Input.Submitted):
        """Handle user input."""
        message = event.value.strip()
        if not message:
            return

        # Clear input
        event.input.value = ""
        
        # Check for exit
        if message.lower() in ["salir", "exit", "quit", "/quit"]:
            self.exit()
            return
        
        container = self.query_one("#chat-container")
        
        # Check for slash commands
        if message.startswith('/'):
            await self._handle_slash_command(message, container)
            return
        
        # Regular message
        await self._handle_user_message(message, container)
    
    async def _handle_slash_command(self, message: str, container):
        """Handle slash commands."""
        parts = message[1:].split(' ', 1)  # Remove / and split
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        
        history = await self.chat_manager.get_history(self.chat_id)
        handled = await self.slash_commands.handle(command, args, history)
        
        if not handled:
            await self._add_system_message(f"❌ Comando desconocido: /{command}", "error")
    
    async def _handle_user_message(self, message: str, container):
        """Handle regular user message."""
        # Show user message
        user_container = Vertical(classes="message-container user-container")
        await container.mount(user_container)
        await user_container.mount(MessageWidget(message, is_user=True))
        
        # Prepare context
        current_time = datetime.now().strftime("%H:%M del %d/%m/%Y")
        from utils.cron_utils import CronUtils
        crontab = "\n".join(CronUtils.get_crontab()) or "(vacío)"
        
        context_message = f"{message} [Sistema: La hora actual es {current_time}. Agenda:\n{crontab}]"
        
        # Add to history
        await self.chat_manager.append_message(
            self.chat_id,
            {"role": "user", "content": context_message}
        )
        
        # Show bot placeholder
        bot_container = Vertical(classes="message-container bot-container")
        await container.mount(bot_container)
        bot_widget = MessageWidget("...", is_user=False)
        await bot_container.mount(bot_widget)
        container.scroll_end(animate=True)
        
        # Stream response
        await self._stream_response(bot_widget)
    
    async def _stream_response(self, widget):
        """Stream LLM response."""
        history = await self.chat_manager.get_history(self.chat_id)
        
        # Prune if needed
        from utils.telegram_utils import prune_history
        pruned = prune_history(history, get_config("CONTEXT_LIMIT", 30000))
        
        full_response = ""
        first_chunk = True
        
        async for chunk in self.client.stream_chat(self.model, pruned):
            if first_chunk:
                full_response = ""
                first_chunk = False
            full_response += chunk
            await widget.update(full_response)
            self.query_one("#chat-container").scroll_end(animate=False)
        
        # Set timestamp and final update
        widget.timestamp = datetime.now().strftime("%H:%M")
        await widget.update(full_response)
        
        # Process commands in response
        cleaned_response = await self.command_processor.process_response(
            full_response, history
        )
        
        # If response was modified (e.g., search), update display
        if cleaned_response != full_response:
            await widget.update(cleaned_response)
        
        # Add to history
        await self.chat_manager.append_message(
            self.chat_id,
            {"role": "assistant", "content": full_response}
        )
        
        # Save history
        history = await self.chat_manager.get_history(self.chat_id)
        self.history_manager.save_history(history, "default")
        
        self.query_one("#chat-container").scroll_end(animate=True)


# Import needed here for on_mount
import asyncio


if __name__ == "__main__":
    app = FemtoBotApp()
    app.run()
