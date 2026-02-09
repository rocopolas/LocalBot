"""Photo/image handler for FemtoBot."""
import asyncio
import os
import re
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

# Minimum length for OCR text to be considered meaningful
_MIN_OCR_LENGTH = 10

# Math detection patterns
_MATH_SYMBOLS = set('=+×÷^∫√∑∏∞πθ∂∇≠≤≥≈∈∉⊂⊃∪∩±')
_MATH_KEYWORDS_RE = re.compile(
    r'\\(?:frac|int|sum|prod|sqrt|lim|log|sin|cos|tan|begin\{|end\{)'
    r'|\d+\s*[+\-*/^=]\s*\d+'
    r'|\bx\s*[+\-*/^=]'
    r'|[a-z]\s*\^\s*\d'
    r'|\d+\s*/\s*\d+'
    r'|\b(?:solve|calculate|compute|evaluate|simplify|derive|integrate|differentiate)\b'
    r'|\b(?:resolver|calcular|evaluar|simplificar|derivar|integrar|factorizar)\b',
    re.IGNORECASE
)


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
            # Note: We keep the file if we need to upload it, otherwise unlink
            
            # Check for upload intent
            caption = update.message.caption or ""
            from src.services.upload_service import UploadService
            uploader = UploadService()
            
            if uploader.is_upload_intent(caption):
                 await self._handle_upload(update, context, tmp_path, status_msg)
                 # Clean up and return
                 with suppress(FileNotFoundError, PermissionError, OSError):
                    os.unlink(tmp_path)
                 return

            # If not uploading, we can unlink now locally if we had processed it in memory (base64)
            # But wait! We already read it into base64 above at line 68.
            # So we can unlink it now if we are not uploading.
            with suppress(FileNotFoundError, PermissionError, OSError):
                os.unlink(tmp_path)

            
            client = OllamaClient()
            caption = update.message.caption or ""
            
            # --- Step 1: OCR extraction ---
            ocr_model = get_config("OCR_MODEL")
            if ocr_model:
                await status_msg.edit_text(f"👁️ Extrayendo texto con OCR ({ocr_model})...")
                ocr_text = await client.describe_image(
                    ocr_model,
                    image_base64,
                    "Transcribe ALL text visible in this image exactly as it appears. "
                    "Output ONLY the raw text, no commentary or descriptions. "
                    "If there is no text, respond with: NO_TEXT"
                )
                
                # Unload OCR model if different from main
                if ocr_model != self.model:
                    await client.unload_model(ocr_model)
                
                ocr_text = ocr_text.strip()
                has_text = (
                    len(ocr_text) >= _MIN_OCR_LENGTH
                    and "NO_TEXT" not in ocr_text.upper()
                    and not ocr_text.startswith("[Error")
                )
            else:
                ocr_text = ""
                has_text = False
            
            # --- Step 2: Math detection ---
            if has_text and self._contains_math(ocr_text):
                # Route to math model
                math_model = get_config("MATH_MODEL")
                await status_msg.edit_text(f"🧮 Matemáticas detectadas, resolviendo con {math_model}...")
                logger.info(f"Math detected in OCR text, routing to {math_model}")
                
                math_prompt = ocr_text
                if caption:
                    math_prompt = f"{caption}\n\n{ocr_text}"
                
                # Build math messages from conversation history (no system prompt, no RAG)
                history = await self.chat_manager.get_history(chat_id)
                math_messages = [
                    msg for msg in (history or [])
                    if msg.get("role") != "system"
                ]
                math_messages.append({"role": "user", "content": math_prompt})
                
                full_response = ""
                async for chunk in client.stream_chat(math_model, math_messages):
                    full_response += chunk
                
                # Unload math model
                if math_model != self.model:
                    await client.unload_model(math_model)
                    logger.info(f"Math model {math_model} unloaded")
                
                # Format and send
                formatted = format_bot_response(full_response)
                chunks = await telegramify_content(formatted)
                await send_telegramify_results(context, chat_id, chunks, status_msg)
                
                # Save to history
                history = await self.chat_manager.get_history(chat_id)
                if not history:
                    system_prompt = self.get_system_prompt()
                    await self.chat_manager.initialize_chat(chat_id, system_prompt)
                
                await self.chat_manager.append_message(chat_id, {
                    "role": "user",
                    "content": f"[Imagen con matemáticas - OCR: {ocr_text}]"
                })
                await self.chat_manager.append_message(chat_id, {
                    "role": "assistant", "content": full_response
                })
                return
            
            # --- Step 3: Vision description (normal flow or with OCR context) ---
            await status_msg.edit_text(f"🔍 Analizando imagen con {vision_model}...")
            
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
            
            # Build context message (include OCR text if available)
            if has_text:
                ocr_block = f"\n\n[Texto extraído por OCR: {ocr_text}]"
            else:
                ocr_block = ""
            
            if caption:
                context_message = (
                    f"[El usuario envió una imagen con el mensaje: '{caption}']"
                    f"\n\n[Descripción de la imagen: {image_description}]"
                    f"{ocr_block}"
                    f"\n\nResponde al usuario considerando la imagen y su mensaje."
                )
            else:
                context_message = (
                    f"[El usuario envió una imagen]"
                    f"\n\n[Descripción de la imagen: {image_description}]"
                    f"{ocr_block}"
                    f"\n\nComenta sobre la imagen de manera útil."
                )
            
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
                        
        except Exception as e:
            logger.error(f"Error processing photo: {e}")
            await status_msg.edit_text(f"❌ Error: {str(e)}")

    @staticmethod
    def _contains_math(text: str) -> bool:
        """Detect if OCR text contains mathematical expressions."""
        if not text:
            return False
        
        # Count math symbols
        symbol_count = sum(1 for ch in text if ch in _MATH_SYMBOLS)
        if symbol_count >= 3:
            return True
        
        # Check regex patterns (operators, LaTeX, keywords)
        matches = _MATH_KEYWORDS_RE.findall(text)
        if len(matches) >= 2:
            return True
        
        return False

    async def _handle_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, status_msg):
        """Helper to handle Catbox upload."""
        try:
            from src.services.upload_service import UploadService
            uploader = UploadService()
            
            await status_msg.edit_text("📤 Subiendo a Catbox.moe...")
            url = await asyncio.to_thread(uploader.upload_to_catbox, file_path)
            
            if url:
                 await status_msg.edit_text(f"✅ Subida completada:\n{url}", disable_web_page_preview=True)
            else:
                 await status_msg.edit_text("❌ Error al subir a Catbox.")
                 
        except Exception as e:
            logger.error(f"Error in upload handler: {e}")
            await status_msg.edit_text(f"❌ Error interno: {str(e)}")
