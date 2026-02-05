"""Command handlers for LocalBot."""
import os
import sys
from telegram import Update
from telegram.ext import ContextTypes
import logging

from src.constants import PROJECT_ROOT
from src.state.chat_manager import ChatManager
from src.middleware.rate_limiter import rate_limit
from src.client import OllamaClient
from utils.config_loader import get_config

logger = logging.getLogger(__name__)


class CommandHandlers:
    """Handlers for bot commands."""
    
    def __init__(
        self,
        chat_manager: ChatManager,
        is_authorized_func,
        get_system_prompt_func
    ):
        self.chat_manager = chat_manager
        self.is_authorized = is_authorized_func
        self.get_system_prompt = get_system_prompt_func
    
    @rate_limit(max_messages=5, window_seconds=60)
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`",
                parse_mode="Markdown"
            )
            return
        
        # Initialize chat with system prompt
        system_prompt = self.get_system_prompt()
        await self.chat_manager.initialize_chat(chat_id, system_prompt)
        
        await update.message.reply_text(
            "¡Hola! Soy LocalBot en Telegram. Háblame y te responderé."
        )
        logger.info(f"Chat {chat_id} started by user {user_id}")
    
    @rate_limit(max_messages=3, window_seconds=60)
    async def new_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /new command - clear history."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return
        
        # Clear and reinitialize
        system_prompt = self.get_system_prompt()
        await self.chat_manager.initialize_chat(chat_id, system_prompt)
        
        await update.message.reply_text(
            "🔄 Nueva conversación iniciada. El historial anterior fue borrado."
        )
        logger.info(f"New conversation started for chat {chat_id}")
    
    @rate_limit(max_messages=3, window_seconds=60)
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show token usage."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return
        
        try:
            context_limit = int(get_config("CONTEXT_LIMIT", 200000))
            history = await self.chat_manager.get_history(chat_id)
            
            total_tokens = 0
            calculation_method = "Aproximado (caracteres)"
            
            try:
                import tiktoken
                encoder = tiktoken.get_encoding("cl100k_base")
                calculation_method = "Real (tiktoken)"
                
                for msg in history:
                    content = msg.get("content", "")
                    total_tokens += 4  # message overhead
                    total_tokens += len(encoder.encode(content))
                
                total_tokens += 3  # reply overhead
                
            except ImportError:
                # Fallback: 1 token ~= 4 chars
                total_chars = sum(len(msg.get("content", "")) for msg in history)
                total_tokens = total_chars // 4
            
            # Calculate stats
            usage_percent = min(100, (total_tokens / context_limit) * 100)
            remaining_tokens = max(0, context_limit - total_tokens)
            
            # Progress bar
            bar_length = 20
            filled_length = min(int(bar_length * usage_percent / 100), bar_length)
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            
            status_text = (
                f"📊 *Estado del Bot* ({calculation_method})\n"
                f"━━━━━━━━━━━━━━\n"
                f"🧠 **Memoria Contextual:**\n"
                f"`{bar}` {usage_percent:.1f}%\n"
                f"🔢 {total_tokens:,} / {context_limit:,} tokens usados\n"
                f"📉 {remaining_tokens:,} tokens restantes\n"
                f"💬 {len(history)} mensajes en historial\n\n"
                f"🔌 **Sistema:**\n"
                f"✅ Modelo: `{get_config('MODEL')}`\n"
                f"✅ Audio: `{get_config('WHISPER_MODEL_VOICE')}`"
            )
            
        except Exception as e:
            logger.error(f"Error calculating status: {e}")
            status_text = f"⚠️ Error calculando estado: {str(e)}"
        
        try:
            await update.message.reply_text(status_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Markdown error in status: {e}")
            await update.message.reply_text(status_text)
    
    @rate_limit(max_messages=2, window_seconds=300)
    async def unload_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unload command - unload models from RAM."""
        user_id = update.effective_user.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return
        
        status_msg = await update.message.reply_text("🔄 Descargando modelos...")
        
        client = OllamaClient()
        model = get_config("MODEL")
        
        # Unload text model
        await client.unload_model(model)
        
        # Unload vision model if configured
        vision_model = get_config("VISION_MODEL")
        if vision_model:
            await client.unload_model(vision_model)
        
        await status_msg.edit_text("✅ Modelos descargados de RAM.")
        logger.info(f"Models unloaded by user {user_id}")
    
    @rate_limit(max_messages=1, window_seconds=60)
    async def restart_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /restart command - restart bot process."""
        user_id = update.effective_user.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return
        
        await update.message.reply_text("🔄 Reiniciando bot...")
        logger.info(f"Bot restart initiated by user {user_id}")
        
        # Restart the process
        os.execl(sys.executable, sys.executable, *sys.argv)
