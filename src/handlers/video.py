"""Video handler for FemtoBot."""
import os
import tempfile
from contextlib import suppress
from telegram import Update
from telegram.ext import ContextTypes
import logging

from src.state.chat_manager import ChatManager
from src.middleware.rate_limiter import rate_limit

logger = logging.getLogger(__name__)


class VideoHandler:
    """Handler for video messages."""
    
    def __init__(
        self,
        chat_manager: ChatManager,
        is_authorized_func,
        get_system_prompt_func,
        command_patterns
    ):
        self.chat_manager = chat_manager
        self.is_authorized = is_authorized_func
        self.get_system_prompt = get_system_prompt_func
        self.command_patterns = command_patterns
    
    @rate_limit(max_messages=3, window_seconds=60)
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video messages."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Authorization check
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ Access denied.\nYour ID is: `{user_id}`",
                parse_mode="Markdown"
            )
            return
        
        caption = update.message.caption or ""
        
        from src.services.upload_service import UploadService
        uploader = UploadService()
        
        # Only process if upload intent is detected (for now)
        if uploader.is_upload_intent(caption):
            status_msg = await update.message.reply_text("🎬 Processing video...")
            
            try:
                video = update.message.video
                video_file = await context.bot.get_file(video.file_id)
                
                # Download to temp file
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                    await video_file.download_to_drive(tmp.name)
                    tmp_path = tmp.name
                
                await self._handle_upload(update, context, tmp_path, status_msg)
                
                # Clean up
                with suppress(FileNotFoundError, PermissionError, OSError):
                    os.unlink(tmp_path)
                    
            except Exception as e:
                logger.error(f"Error processing video: {e}")
                await status_msg.edit_text(f"❌ Error: {str(e)}")
        else:
            # Optional: Add logic for generic video handling if needed
            # For now, just ignore or acknowledge
            pass

    async def _handle_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, status_msg):
        """Helper to handle Catbox upload."""
        try:
            from src.services.upload_service import UploadService
            uploader = UploadService()
            
            await status_msg.edit_text("📤 Uploading to Catbox.moe...")
            # Run blocking upload in thread
            import asyncio
            url = await asyncio.to_thread(uploader.upload_to_catbox, file_path)
            
            if url:
                 await status_msg.edit_text(f"✅ Upload complete:\n{url}", disable_web_page_preview=True)
            else:
                 await status_msg.edit_text("❌ Error uploading to Catbox.")
                 
        except Exception as e:
            logger.error(f"Error in upload handler: {e}")
            await status_msg.edit_text(f"❌ Internal error: {str(e)}")
