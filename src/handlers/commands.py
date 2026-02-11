"""Command handlers for FemtoBot."""
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
        get_system_prompt_func,
        email_digest_job=None
    ):
        self.chat_manager = chat_manager
        self.is_authorized = is_authorized_func
        self.get_system_prompt = get_system_prompt_func
        self.email_digest_job = email_digest_job
    
    @rate_limit(max_messages=5, window_seconds=60)
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ Access denied.\nYour ID is: `{user_id}`",
                parse_mode="Markdown"
            )
            return
        
        # Initialize chat with system prompt
        system_prompt = self.get_system_prompt()
        await self.chat_manager.initialize_chat(chat_id, system_prompt)
        
        await update.message.reply_text(
            "Hi! I'm FemtoBot on Telegram. Talk to me and I'll respond."
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
            "🔄 New conversation started. Previous history cleared."
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
            calculation_method = "Approximate (characters)"
            
            try:
                import tiktoken
                encoder = tiktoken.get_encoding("cl100k_base")
                calculation_method = "Exact (tiktoken)"
                
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
                f"📊 *Bot Status* ({calculation_method})\n"
                f"━━━━━━━━━━━━━━\n"
                f"🧠 **Context Memory:**\n"
                f"`{bar}` {usage_percent:.1f}%\n"
                f"🔢 {total_tokens:,} / {context_limit:,} tokens used\n"
                f"📉 {remaining_tokens:,} tokens remaining\n"
                f"💬 {len(history)} messages in history\n\n"
                f"🔌 **System:**\n"
                f"✅ Model: `{get_config('MODEL')}`\n"
                f"✅ Audio: `{get_config('WHISPER_MODEL_VOICE')}`"
            )
            
        except Exception as e:
            logger.error(f"Error calculating status: {e}")
            status_text = f"⚠️ Error calculating status: {str(e)}"
        
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
        
        status_msg = await update.message.reply_text("🔄 Unloading models...")
        
        client = OllamaClient()
        model = get_config("MODEL")
        
        # Unload text model
        await client.unload_model(model)
        
        # Unload vision model if configured
        vision_model = get_config("VISION_MODEL")
        if vision_model:
            await client.unload_model(vision_model)
        
        await status_msg.edit_text("✅ Models unloaded from RAM.")
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
        
        await update.message.reply_text("🔄 Restarting bot...")
        logger.info(f"Bot restart initiated by user {user_id}")
        
        # Restart the process
        os.execl(sys.executable, sys.executable, *sys.argv)
    
    @rate_limit(max_messages=1, window_seconds=60)
    async def email_digest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /digest command - manually trigger email digest."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return
        
        if not self.email_digest_job:
            await update.message.reply_text(
                "⚠️ Email digest system is not available.",
                parse_mode="Markdown"
            )
            return
        
        logger.info(f"Manual email digest triggered by user {user_id}")
        await self.email_digest_job.run_manual(context, chat_id)
