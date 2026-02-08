"""Document handler for LocalBot."""
import os
import asyncio
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
from utils.document_utils import extract_text_from_document, is_supported_document, convert_pdf_to_images

logger = logging.getLogger(__name__)


class DocumentHandler:
    """Handler for document messages (PDF, DOCX, TXT)."""
    
    def __init__(
        self,
        chat_manager: ChatManager,
        vector_manager,
        is_authorized_func,
        get_system_prompt_func,
        command_patterns
    ):
        self.chat_manager = chat_manager
        self.vector_manager = vector_manager
        self.is_authorized = is_authorized_func
        self.get_system_prompt = get_system_prompt_func
        self.command_patterns = command_patterns
        self.model = get_config("MODEL")
    
    @rate_limit(max_messages=3, window_seconds=120)
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle documents by extracting text and processing with LLM."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        # Authorization check
        if not self.is_authorized(user_id):
            await update.message.reply_text(
                f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`",
                parse_mode="Markdown"
            )
            return
        
        document = update.message.document
        file_name = document.file_name or "documento"
        
        # Check if it's a supported document type
        if not is_supported_document(file_name):
            return
        
        status_msg = await update.message.reply_text(
            f"📄 Leyendo *{file_name}*...",
            parse_mode="Markdown"
        )
        
        try:
            # Download document
            doc_file = await context.bot.get_file(document.file_id)
            
            # Determine extension for temp file
            ext = os.path.splitext(file_name)[1] or ".tmp"
            
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                await doc_file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            
            # Extract text
            doc_text, doc_type, needs_ocr = await extract_text_from_document(tmp_path, file_name)
            
            # OCR Fallback
            if needs_ocr and doc_type == "PDF":
                ocr_model = get_config("OCR_MODEL", "glm-4v")
                await status_msg.edit_text(f"👁️ Documento escaneado detectado. Iniciando OCR con {ocr_model}...")
                try:
                    images_b64 = await asyncio.to_thread(convert_pdf_to_images, tmp_path)
                    if images_b64:
                         client = OllamaClient()
                         ocr_texts = []
                         for i, img_b64 in enumerate(images_b64):
                             await status_msg.edit_text(f"👁️ OCR: Procesando página {i+1}/{len(images_b64)}...")
                             # Prompt for OCR
                             page_text = await client.describe_image(
                                 model=ocr_model,
                                 image_base64=img_b64,
                                 prompt="Transcribe all text from this image exactly as it appears. Do not add commentary. Output only the text."
                             )
                             ocr_texts.append(page_text)
                         
                         doc_text = "\n\n".join(ocr_texts)
                         doc_type += " (OCR)"
                    else:
                         doc_text += "\n[Advertencia: Documento escaneado pero no se pudieron extraer imágenes]"
                except Exception as e:
                    logger.error(f"OCR Error: {e}")
                    doc_text += f"\n[Error OCR: {str(e)}]"
            
            # Clean up temp file
            with suppress(FileNotFoundError, PermissionError, OSError):
                os.unlink(tmp_path)
            
            # Check if extraction and OCR failed
            if doc_text.startswith("[Error") and not needs_ocr:
                await status_msg.edit_text(doc_text)
                return
            
            # LaTeX math is handled automatically by telegramify-markdown
            
            # Truncate if too long
            if len(doc_text) > 100000:
                doc_text = doc_text[:100000] + "\n\n[... documento truncado por longitud ...]"
            
            # Index to Vector Store
            from datetime import datetime
            metadata = {
                "source": file_name,
                "type": doc_type,
                "timestamp": str(datetime.now())
            }
            await self.vector_manager.add_document(doc_text, metadata)
            
            await status_msg.edit_text(f"🧠 Procesando e indexando documento {doc_type}...")
            
            # Initialize chat history if needed
            history = await self.chat_manager.get_history(chat_id)
            if not history:
                system_prompt = self.get_system_prompt()
                await self.chat_manager.initialize_chat(chat_id, system_prompt)
                history = await self.chat_manager.get_history(chat_id)
            
            # Build context message
            caption = update.message.caption
            if caption:
                context_message = f"[El usuario envió un documento {doc_type} llamado '{file_name}' con el mensaje: '{caption}']\n\nContenido del documento:\n{doc_text}\n\nResponde considerando el documento y el mensaje del usuario."
            else:
                context_message = f"[El usuario envió un documento {doc_type} llamado '{file_name}']\n\nContenido del documento:\n{doc_text}\n\nResume o comenta sobre el contenido del documento."
            
            # Add to history
            await self.chat_manager.append_message(chat_id, {"role": "user", "content": context_message})
            history = await self.chat_manager.get_history(chat_id)
            
            # Generate response
            client = OllamaClient()
            full_response = ""
            async for chunk in client.stream_chat(self.model, prune_history(history, get_config("CONTEXT_LIMIT", 30000))):
                full_response += chunk
            
            # Format response (clean text)
            cleaned_text = format_bot_response(full_response)
            
            # Split and send chunks using telegramify
            chunks = await telegramify_content(cleaned_text)
            await send_telegramify_results(context, chat_id, chunks, status_msg)
            
            # Add to history
            await self.chat_manager.append_message(chat_id, {"role": "assistant", "content": full_response})
            
            # Parse memory commands
            for memory_match in self.command_patterns['memory'].finditer(full_response):
                memory_content = memory_match.group(1).strip()
                if memory_content:
                    try:
                        memory_path = os.path.join(PROJECT_ROOT, get_config("MEMORY_FILE"))
                        with open(memory_path, "a", encoding="utf-8") as f:
                            f.write(f"\n- {memory_content}")
                        # Legacy load memory memory
                        # self.load_memory() 
                        
                        # Save to Vector DB
                        await self.vector_manager.add_memory(memory_content)
                        await context.bot.send_message(chat_id, f"💾 Guardado en memoria: _{memory_content}_", parse_mode="Markdown")
                    except Exception as e:
                        await context.bot.send_message(chat_id, f"⚠️ Error guardando memoria: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            await status_msg.edit_text(f"❌ Error: {str(e)}")
