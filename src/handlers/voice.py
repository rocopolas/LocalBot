"""Voice message handler for FemtoBot."""
import os
import tempfile
from contextlib import suppress
from telegram import Update
from telegram.ext import ContextTypes
import logging
import asyncio

from src.middleware.rate_limiter import rate_limit
from utils.audio_utils import transcribe_audio, transcribe_audio_large, is_whisper_available
from utils.telegram_utils import split_message, telegramify_content, send_telegramify_results

logger = logging.getLogger(__name__)


class VoiceHandler:
    """Handler for voice messages."""
    
    def __init__(self, is_authorized_func, message_queue, start_worker_func=None):
        self.is_authorized = is_authorized_func
        self.message_queue = message_queue
        self.start_worker = start_worker_func
    
    @rate_limit(max_messages=5, window_seconds=60)
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages by transcribing and processing them."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        logger.debug(f"handle_voice called - user_id={user_id}, chat_id={chat_id}")
        
        # Authorization check
        if not self.is_authorized(user_id):
            logger.debug(f"User {user_id} not authorized")
            await update.message.reply_text(
                f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`",
                parse_mode="Markdown"
            )
            return
        
        logger.debug("User authorized, checking whisper...")
        
        # Check if whisper is available
        if not is_whisper_available():
            logger.debug("Whisper not available")
            await update.message.reply_text(
                "⚠️ Whisper no configurado. Instala: `pip install faster-whisper`",
                parse_mode="Markdown"
            )
            return
        
        # Detection: if voice has caption = external (WhatsApp, etc), no caption = Telegram native
        has_caption = update.message.caption is not None and len(update.message.caption.strip()) > 0
        is_external = has_caption
        
        if is_external:
            status_msg = await update.message.reply_text(
                "🎧 External audio detected. Transcribing with large model...\n"
                "_(This may take a while)_",
                parse_mode="Markdown"
            )
        else:
            status_msg = await update.message.reply_text("🎙️ Transcribiendo audio...")
        
        try:
            # Download voice file
            voice = update.message.voice
            voice_file = await context.bot.get_file(voice.file_id)
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
                await voice_file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            
            # Transcribe with appropriate model
            if is_external:
                transcription = await transcribe_audio_large(tmp_path)
            else:
                transcription = await transcribe_audio(tmp_path)
            
            # Clean up temp file
            with suppress(FileNotFoundError, PermissionError, OSError):
                os.unlink(tmp_path)
            
            if is_external:
                # External: just show transcription, don't process with LLM
                text = f"📝 *Transcription (external audio):*\n\n{transcription}"
                
                # Split and send chunks using telegramify
                chunks = await telegramify_content(text)
                await send_telegramify_results(context, chat_id, chunks, status_msg)
            else:
                # Direct voice: show transcription and process with LLM
                text = f"🎙️ *Transcription:*\n_{transcription}_"
                
                # Split and send chunks using telegramify
                chunks = await telegramify_content(text)
                await send_telegramify_results(context, chat_id, chunks, status_msg)
                
                # Add to queue with transcription text
                needs_reply = not self.message_queue.empty()
                await self.message_queue.put((update, context, needs_reply, transcription))
                
                if self.start_worker:
                    self.start_worker()
                    
        except Exception as e:
            logger.error(f"Error processing voice: {e}")
            await status_msg.edit_text(f"❌ Error: {str(e)}")
