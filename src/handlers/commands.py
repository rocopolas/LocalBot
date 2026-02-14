"""Command handlers for FemtoBot."""
import os
import sys
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
import logging


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
        email_digest_job=None,
        update_activity_func=None
    ):
        self.chat_manager = chat_manager
        self.is_authorized = is_authorized_func
        self.get_system_prompt = get_system_prompt_func
        self.email_digest_job = email_digest_job
        self.update_activity = update_activity_func
    
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
        """Handle /restart command - graceful shutdown, requires external restart."""
        user_id = update.effective_user.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return
        
        await update.message.reply_text("🔄 Stopping bot gracefully...\nUse 'femtobot start' to restart it.")
        logger.info(f"Bot shutdown initiated by user {user_id}")
        
        # Clean shutdown - stop the application
        try:
            # Get the application from context
            application = context.application
            
            # Schedule shutdown
            async def shutdown():
                await application.stop()
                await application.shutdown()
            
            # Run shutdown in the event loop
            asyncio.create_task(shutdown())
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            # Force exit if graceful shutdown fails
            os._exit(0)
    
    @rate_limit(max_messages=1, window_seconds=60)
    async def stop_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command - stop bot completely."""
        user_id = update.effective_user.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return
        
        await update.message.reply_text("🛑 Stopping bot completely...\nUse 'femtobot start' to start it again.")
        logger.info(f"Bot STOP initiated by user {user_id}")
        
        # Clean shutdown
        try:
            application = context.application
            
            async def shutdown():
                await application.stop()
                await application.shutdown()
            
            asyncio.create_task(shutdown())
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            os._exit(0)
    
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

    async def deep_research(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deep command - deep research mode."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso.",
                parse_mode="Markdown"
            )
            return

        # Get the prompt
        if not context.args:
            await update.message.reply_text("⚠️ Please provide a topic. Usage: `/deep <topic>`", parse_mode="Markdown")
            return
            
        topic = " ".join(context.args)
        
        status_msg = await update.message.reply_text(f"🧠 Starting deep research on: *{topic}*...\nThis may take a few minutes.", parse_mode="Markdown")
        
        from src.services.deep_research_service import DeepResearchService
        service = DeepResearchService()
        
        async def status_callback(msg):
            try:
                # Update activity to prevent model unloading
                if self.update_activity:
                    self.update_activity()
                    
                # Append to the existing message or send a new one if it's too long?
                # For now, just edit the message to show current status
                await status_msg.edit_text(f"🧠 Deep Research: *{topic}*\n\n{msg}", parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Failed to update status message: {e}")
        
        try:
            file_path = await service.research(topic, chat_id, status_callback)
            
            await status_msg.edit_text("✅ Research complete! Sending report...")
            
            await update.message.reply_document(
                document=open(file_path, 'rb'),
                filename=os.path.basename(file_path),
                caption=f"📊 Research Report: {topic}"
            )
            
            # Clean up: delete the file after sending
            try:
                os.remove(file_path)
                logger.info(f"Deleted research report: {file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to delete research report {file_path}: {cleanup_error}") 
            
        except Exception as e:
            logger.error(f"Deep research failed: {e}", exc_info=True)
            await status_msg.edit_text(f"❌ Research failed: {str(e)}")
