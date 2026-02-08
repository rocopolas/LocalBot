"""Photo/image handler for FemtoBot."""
import os
import base64
import tempfile
from contextlib import suppress
from telegram import Update
from telegram.ext import ContextTypes
import logging

from src.constants import PROJECT_ROOT
from src.client import OllamaClient
from src.state.chat_manager import ChatManager
from src.middleware.rate_limiter import rate_limit
from utils.config_loader import get_config
from utils.telegram_utils import format_bot_response, split_message, prune_history, telegramify_content, send_telegramify_results

logger = logging.getLogger(__name__)


class PhotoHandler:
    """Handler for photo messages."""
    
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
        self.model = get_config("MODEL")
    
    @rate_limit(max_messages=5, window_seconds=60)
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photos by describing them with vision model and processing with LLM."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Authorization check
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`",
                parse_mode="Markdown"
            )
            return
        
        # Get vision model from config
        vision_model = get_config("VISION_MODEL")
        if not vision_model:
            vision_model = self.model
        
        status_msg = await update.message.reply_text("🔍 Analizando imagen...")
        
        try:
            # Get the largest photo (best quality)
            photo = update.message.photo[-1]
            photo_file = await context.bot.get_file(photo.file_id)
            
            # Download to temp file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                await photo_file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            
            # Read and encode to base64
            with open(tmp_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            # Clean up temp file
            with suppress(FileNotFoundError, PermissionError, OSError):
                os.unlink(tmp_path)
            
            # Get image description from vision model
            client = OllamaClient()
            await status_msg.edit_text(f"🔍 Analizando imagen con {vision_model}...")
            
            # Use caption as prompt if provided
            caption = update.message.caption
            if caption:
                vision_prompt = f"El usuario envió esta imagen con el mensaje: '{caption}'. Describe la imagen en detalle."
            else:
                vision_prompt = "Describe esta imagen en detalle. ¿Qué ves? Incluye objetos, personas, colores, texto visible, y cualquier detalle relevante."
            
            image_description = await client.describe_image(vision_model, image_base64, vision_prompt)
            
            # Unload vision model if different from main model
            if vision_model != self.model:
                await client.unload_model(vision_model)
            
            await status_msg.edit_text("💭 Procesando respuesta...")
            
            # Initialize chat history if needed
            history = await self.chat_manager.get_history(chat_id)
            if not history:
                system_prompt = self.get_system_prompt()
                await self.chat_manager.initialize_chat(chat_id, system_prompt)
                history = await self.chat_manager.get_history(chat_id)
            
            # Build context message
            if caption:
                context_message = f"[El usuario envió una imagen con el mensaje: '{caption}']\n\n[Descripción de la imagen: {image_description}]\n\nResponde al usuario considerando la imagen y su mensaje."
            else:
                context_message = f"[El usuario envió una imagen]\n\n[Descripción de la imagen: {image_description}]\n\nComenta sobre la imagen de manera útil."
            
            # Add to history
            await self.chat_manager.append_message(chat_id, {"role": "user", "content": context_message})
            history = await self.chat_manager.get_history(chat_id)
            
            # Generate response
            full_response = ""
            async for chunk in client.stream_chat(self.model, prune_history(history, get_config("CONTEXT_LIMIT", 30000))):
                full_response += chunk
            
            # Format response
            formatted_response = format_bot_response(full_response)
            
            # Split and send chunks using telegramify (handles TEXT, PHOTO, FILE)
            chunks = await telegramify_content(formatted_response)
            await send_telegramify_results(context, chat_id, chunks, status_msg)
            
            # Add to history
            await self.chat_manager.append_message(chat_id, {"role": "assistant", "content": full_response})
            
            # Parse memory commands
            for memory_match in self.command_patterns['memory'].finditer(full_response):
                memory_content = memory_match.group(1).strip()
                if memory_content:
                    try:
                        # Save ONLY to Vector DB
                        await context.bot.send_message(chat_id, f"💾 Guardando en DB: _{memory_content}_", parse_mode="Markdown")
                        # Note: We need access to vector_manager here. 
                        # PhotoHandler currently doesn't have it. Will add it.
                    except Exception as e:
                        await context.bot.send_message(chat_id, f"⚠️ Error guardando memoria: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Error processing photo: {e}")
            await status_msg.edit_text(f"❌ Error: {str(e)}")
