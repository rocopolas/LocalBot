"""TUI command handlers for processing :::xxx::: commands."""
import re
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Callable

from src.constants import PROJECT_ROOT
from src.client import OllamaClient
from utils.cron_utils import CronUtils
from utils.wiz_utils import control_light
from utils.config_loader import get_config
from utils.telegram_utils import escape_markdown

logger = logging.getLogger(__name__)


class TUICommandProcessor:
    """Process all :::xxx::: commands in TUI."""
    
    # Pre-compiled patterns
    PATTERNS = {
        'memory': re.compile(r':::memory(?!_delete)\s+(.+?):::', re.DOTALL),
        'memory_delete': re.compile(r':::memory_delete\s+(.+?):::', re.DOTALL),
        'cron': re.compile(r':::cron\s+(.+?):::', re.DOTALL),
        'cron_delete': re.compile(r':::cron_delete\s+(.+?):::'),
        'search': re.compile(r':::search\s+(.+?):::'),
        'foto': re.compile(r':::foto\s+(.+?):::', re.IGNORECASE),
        'luz': re.compile(r':::luz\s+(\S+)\s+(\S+)(?:\s+(\S+))?:::'),
    }
    
    def __init__(self, output_callback: Callable[[str, str], None]):
        """
        Initialize processor.
        
        Args:
            output_callback: Function to call with (message, style)
        """
        self.output = output_callback
    
    async def process_response(self, response: str, chat_history: List[Dict]) -> str:
        """
        Process all commands in a response.
        
        Args:
            response: LLM response text
            chat_history: Current chat history
            
        Returns:
            Cleaned response (commands removed)
        """
        # Handle search first (needs LLM follow-up)
        search_match = self.PATTERNS['search'].search(response)
        if search_match:
            return await self._handle_search(search_match, response, chat_history)
        
        # Process other commands
        await self._process_cron_commands(response)
        await self._process_memory_commands(response)
        await self._process_light_commands(response)
        
        # Remove all command patterns from response
        cleaned = self._clean_response(response)
        return cleaned
    
    async def _handle_search(self, match, response: str, chat_history: List[Dict]) -> str:
        """Handle search command."""
        from utils.search_utils import BraveSearch
        
        query = match.group(1).strip()
        self.output(f"🔍 Searching: {query}", "info")
        
        try:
            results = await BraveSearch.search(query)
            
            # Add to history
            chat_history.append({"role": "assistant", "content": response})
            chat_history.append({
                "role": "user",
                "content": f"[System: Search results for '{query}']:\n{results}\n\nNow respond to the user."
            })
            
            # Get follow-up response
            client = OllamaClient()
            model = get_config("MODEL")
            
            follow_up = ""
            async for chunk in client.stream_chat(model, chat_history):
                follow_up += chunk
            
            # Process any commands in follow-up
            await self._process_cron_commands(follow_up)
            await self._process_memory_commands(follow_up)
            
            cleaned = self._clean_response(follow_up)
            return cleaned
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            self.output(f"❌ Search error: {e}", "error")
            return self._clean_response(response)
    
    async def _process_cron_commands(self, response: str):
        """Process cron add/delete commands."""
        events_file = os.path.join(PROJECT_ROOT, get_config("EVENTS_FILE"))
        
        # Delete commands
        for match in self.PATTERNS['cron_delete'].finditer(response):
            target = match.group(1).strip()
            self.output(f"🗑️ Removing task: {target}", "info")
            
            if CronUtils.delete_job(target):
                self.output("✅ Task removed", "success")
            else:
                self.output("⚠️ No matching tasks found", "warning")
        
        # Add commands - new simplified format: tipo minuto hora dia mes nombre
        for match in self.PATTERNS['cron'].finditer(response):
            cron_content = match.group(1).strip()
            parts = cron_content.split(None, 5)
            
            if len(parts) < 6:
                self.output(f"❌ Invalid cron format: {cron_content}", "error")
                continue
            
            tipo = parts[0].lower()
            min_f, hour_f, day_f, month_f = parts[1:5]
            nombre = parts[5].strip().rstrip(":")
            
            if tipo not in ("unico", "recurrente"):
                self.output(f"❌ Invalid type: {tipo}", "error")
                continue
            
            schedule = f"{min_f} {hour_f} {day_f} {month_f} *"
            
            if tipo == "unico":
                year = datetime.now().year
                command = (
                    f'[ "$(date +\\%Y)" = "{year}" ] && '
                    f'notify-send "{nombre}"; echo "{nombre}" >> {events_file}'
                )
            else:
                command = f'notify-send "{nombre}"; echo "{nombre}" >> {events_file}'
            
            self.output(f"⚠️ Adding ({tipo}): {schedule} — {nombre}", "info")
            
            if CronUtils.add_job(schedule, command):
                self.output("✅ Task added", "success")
            else:
                self.output("❌ Error adding task", "error")
    
    async def _process_memory_commands(self, response: str):
        """Process memory add/delete commands."""
        memory_path = os.path.join(PROJECT_ROOT, get_config("MEMORY_FILE"))
        
        # Delete commands
        for match in self.PATTERNS['memory_delete'].finditer(response):
            target = match.group(1).strip()
            if not target:
                continue
            
            try:
                with open(memory_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                new_lines = [l for l in lines if target.lower() not in l.lower()]
                removed = len(lines) - len(new_lines)
                
                if removed > 0:
                    with open(memory_path, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                    self.output(f"🗑️ Removed from memory: {target}", "success")
                else:
                    self.output(f"⚠️ Not found: {target}", "warning")
                    
            except Exception as e:
                self.output(f"❌ Error: {e}", "error")
        
        # Add commands
        for match in self.PATTERNS['memory'].finditer(response):
            content = match.group(1).strip()
            if not content:
                continue
            
            try:
                with open(memory_path, "a", encoding="utf-8") as f:
                    f.write(f"\n- {content}")
                self.output(f"💾 Saved to memory: {content}", "success")
            except Exception as e:
                self.output(f"❌ Error: {e}", "error")
    
    async def _process_light_commands(self, response: str):
        """Process WIZ light commands."""
        for match in self.PATTERNS['luz'].finditer(response):
            name = match.group(1).strip()
            action = match.group(2).strip()
            value = match.group(3).strip() if match.group(3) else None
            
            try:
                result = await control_light(name, action, value)
                self.output(result, "info")
            except Exception as e:
                self.output(f"❌ Light error: {e}", "error")
    
    def _clean_response(self, response: str) -> str:
        """Remove all command patterns from response."""
        cleaned = response
        
        # Remove all command patterns
        cleaned = self.PATTERNS['memory'].sub('', cleaned)
        cleaned = self.PATTERNS['memory_delete'].sub('', cleaned)
        cleaned = self.PATTERNS['cron'].sub('', cleaned)
        cleaned = self.PATTERNS['cron_delete'].sub('', cleaned)
        cleaned = self.PATTERNS['search'].sub('', cleaned)
        cleaned = self.PATTERNS['foto'].sub('', cleaned)
        cleaned = self.PATTERNS['luz'].sub('', cleaned)
        
        # Clean up whitespace
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()
