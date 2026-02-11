"""Audio file handler for FemtoBot."""
import os
import tempfile
from contextlib import suppress
from telegram import Update
from telegram.ext import ContextTypes
import logging

from src.middleware.rate_limiter import rate_limit
from utils.audio_utils import transcribe_audio_large, is_whisper_available
from utils.telegram_utils import split_message, telegramify_content, send_telegramify_results

logger = logging.getLogger(__name__)


class AudioHandler:
    """Handler for external audio files."""
    
    def __init__(self, is_authorized_func):
        self.is_authorized = is_authorized_func
    
    @rate_limit(max_messages=3, window_seconds=120)
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle external audio files - transcribe only with large model, no LLM."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Authorization check
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`",
                parse_mode="Markdown"
            )
            return
        
        # Check if whisper is available
        if not is_whisper_available():
            await update.message.reply_text(
                "⚠️ Whisper no configurado. Instala: `pip install faster-whisper`",
                parse_mode="Markdown"
            )
            return
        
        # Show transcribing status
        audio = update.message.audio
        file_name = audio.file_name or "audio"
        status_msg = await update.message.reply_text(
            f"🎧 Transcribiendo *{file_name}* con modelo grande...\n"
            f"_(Esto puede tomar tiempo)_",
            parse_mode="Markdown"
        )
        
        try:
            # Download audio file
            audio_file = await context.bot.get_file(audio.file_id)
            
            # Determine extension
            ext = ".mp3" if file_name.endswith(".mp3") else ".ogg"
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                await audio_file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            
            # Transcribe with LARGE model
            transcription = await transcribe_audio_large(tmp_path)
            
            # Clean up temp file
            with suppress(FileNotFoundError, PermissionError, OSError):
                os.unlink(tmp_path)
            
            # Show transcription only (no LLM processing)
            text = f"📝 *Transcription of* `{file_name}`:\n\n{transcription}"
            
            # Split and send chunks using telegramify
            chunks = await telegramify_content(text)
            await send_telegramify_results(context, chat_id, chunks, status_msg)
                    
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            await status_msg.edit_text(f"❌ Error: {str(e)}")
