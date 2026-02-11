"""TUI slash command handlers (/status, /new, etc)."""
import logging
from typing import List, Dict, Any, Callable

from src.client import OllamaClient
from utils.config_loader import get_config

logger = logging.getLogger(__name__)


class TUISlashCommands:
    """Handle slash commands in TUI."""
    
    def __init__(self, output_callback: Callable[[str, str], None], 
                 history_manager=None, chat_manager=None):
        self.output = output_callback
        self.history_manager = history_manager
        self.chat_manager = chat_manager
        self.model = get_config("MODEL")
    
    async def handle(self, command: str, args: str, chat_history: List[Dict]) -> bool:
        """
        Handle a slash command.
        
        Args:
            command: Command name (without /)
            args: Command arguments
            chat_history: Current chat history
            
        Returns:
            True if command was handled
        """
        handlers = {
            'status': self._cmd_status,
            'new': self._cmd_new,
            'clear': self._cmd_new,  # Alias
            'reset': self._cmd_new,  # Alias
            'unload': self._cmd_unload,
            'save': self._cmd_save,
            'load': self._cmd_load,
            'sessions': self._cmd_sessions,
            'export': self._cmd_export,
            'help': self._cmd_help,
        }
        
        handler = handlers.get(command.lower())
        if handler:
            await handler(args, chat_history)
            return True
        return False
    
    async def _cmd_status(self, args: str, chat_history: List[Dict]):
        """Show bot status."""
        try:
            import tiktoken
            encoder = tiktoken.get_encoding("cl100k_base")
            calculation_method = "Real (tiktoken)"
            
            total_tokens = 0
            for msg in chat_history:
                content = msg.get("content", "")
                total_tokens += 4  # message overhead
                total_tokens += len(encoder.encode(content))
            total_tokens += 3
            
        except ImportError:
            total_chars = sum(len(m.get("content", "")) for m in chat_history)
            total_tokens = total_chars // 4
            calculation_method = "Approximate"
        
        context_limit = int(get_config("CONTEXT_LIMIT", 200000))
        usage_percent = min(100, (total_tokens / context_limit) * 100)
        remaining = max(0, context_limit - total_tokens)
        
        # Progress bar
        bar_length = 20
        filled = int(bar_length * usage_percent / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        status_text = f"""📊 Bot Status ({calculation_method})
━━━━━━━━━━━━━━
🧠 Context Memory:
{bar} {usage_percent:.1f}%
🔢 {total_tokens:,} / {context_limit:,} tokens
📉 {remaining:,} remaining
💬 {len(chat_history)} messages

🔌 System:
✅ Model: {self.model}
✅ Audio: {get_config('WHISPER_MODEL_VOICE')}"""
        
        self.output(status_text, "info")
    
    async def _cmd_new(self, args: str, chat_history: List[Dict]):
        """Start new conversation."""
        # Keep only system messages
        system_msgs = [m for m in chat_history if m.get("role") == "system"]
        chat_history.clear()
        chat_history.extend(system_msgs)
        
        self.output("🔄 New conversation started. History cleared.", "success")
        
        # Save if history manager available
        if self.history_manager:
            self.history_manager.save_history(chat_history)
    
    async def _cmd_unload(self, args: str, chat_history: List[Dict]):
        """Unload models from RAM."""
        self.output("🔄 Unloading models...", "info")
        
        client = OllamaClient()
        await client.unload_model(self.model)
        
        vision_model = get_config("VISION_MODEL")
        if vision_model:
            await client.unload_model(vision_model)
        
        self.output("✅ Models unloaded from RAM.", "success")
    
    async def _cmd_save(self, args: str, chat_history: List[Dict]):
        """Save current session."""
        if not self.history_manager:
            self.output("❌ History not available", "error")
            return
        
        session_name = args.strip() if args.strip() else "default"
        
        if self.history_manager.save_history(chat_history, session_name):
            self.output(f"💾 Session saved: {session_name}", "success")
        else:
            self.output("❌ Error saving session", "error")
    
    async def _cmd_load(self, args: str, chat_history: List[Dict]):
        """Load a session."""
        if not self.history_manager:
            self.output("❌ History not available", "error")
            return
        
        session_name = args.strip() if args.strip() else "default"
        
        history = self.history_manager.load_history(session_name)
        if history:
            chat_history.clear()
            chat_history.extend(history)
            self.output(f"📂 Session loaded: {session_name} ({len(history)} messages)", "success")
        else:
            self.output(f"⚠️ Session not found: {session_name}", "warning")
    
    async def _cmd_sessions(self, args: str, chat_history: List[Dict]):
        """List all saved sessions."""
        if not self.history_manager:
            self.output("❌ History not available", "error")
            return
        
        sessions = self.history_manager.list_sessions()
        
        if not sessions:
            self.output("No saved sessions", "info")
            return
        
        output = "📁 Saved sessions:\n"
        for session in sessions[:10]:  # Show last 10
            output += f"  • {session['id']}: {session['message_count']} msgs ({session['last_saved'][:10]})\n"
        
        self.output(output, "info")
    
    async def _cmd_export(self, args: str, chat_history: List[Dict]):
        """Export current conversation."""
        if not self.history_manager:
            self.output("❌ Historial no disponible", "error")
            return
        
        from datetime import datetime
        
        filename = args.strip() if args.strip() else f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        if not filename.endswith('.md'):
            filename += '.md'
        
        if self.history_manager.export_session("default", filename):
            self.output(f"📄 Exported to: {filename}", "success")
        else:
            self.output("❌ Error exporting", "error")
    
    async def _cmd_help(self, args: str, chat_history: List[Dict]):
        """Show help."""
        help_text = """📚 Available commands:

/status    - View token usage and status
/new       - New conversation (clears history)
/clear     - Alias for /new
/unload    - Unload models from RAM
/save [name]     - Save session
/load [name]     - Load session
/sessions  - List saved sessions
/export [file]   - Export to markdown
/help      - Show this help

Bot commands:
• Type messages normally
• The bot responds with the LLM
• Supports :::memory:::, :::cron:::, etc."""
        
        self.output(help_text, "info")
