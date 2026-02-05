"""Document handler for LocalBot."""
import os
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
from utils.telegram_utils import format_bot_response, split_message, prune_history
from utils.document_utils import extract_text_from_document, is_supported_document

logger = logging.getLogger(__name__)


class DocumentHandler:
    """Handler for document messages (PDF, DOCX, TXT)."""
    
    def __init__(
        self,
        chat_manager: ChatManager,
        is_authorized_func,
        get_system_prompt_func,
        load_memory_func,
        command_patterns
    ):
        self.chat_manager = chat_manager
        self.is_authorized = is_authorized_func
        self.get_system_prompt = get_system_prompt_func
        self.load_memory = load_memory_func
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
            doc_text, doc_type = extract_text_from_document(tmp_path, file_name)
            
            # Clean up temp file
            with suppress(FileNotFoundError, PermissionError, OSError):
                os.unlink(tmp_path)
            
            # Check if extraction failed
            if doc_text.startswith("[Error"):
                await status_msg.edit_text(doc_text)
                return
            
            # Truncate if too long
            if len(doc_text) > 50000:
                doc_text = doc_text[:50000] + "\n\n[... documento truncado por longitud ...]"
            
            await status_msg.edit_text(f"💭 Procesando documento {doc_type}...")
            
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
            
            # Format response
            formatted_response = format_bot_response(full_response)
            
            # Split and send chunks
            chunks = split_message(formatted_response)
            for i, chunk in enumerate(chunks):
                try:
                    if i == 0:
                        await status_msg.edit_text(chunk, parse_mode="Markdown")
                    else:
                        await context.bot.send_message(chat_id, chunk, parse_mode="Markdown")
                except Exception:
                    if i == 0:
                        await status_msg.edit_text(chunk)
                    else:
                        await context.bot.send_message(chat_id, chunk)
            
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
                        self.load_memory()
                        await context.bot.send_message(chat_id, f"💾 Guardado en memoria: _{memory_content}_", parse_mode="Markdown")
                    except Exception as e:
                        await context.bot.send_message(chat_id, f"⚠️ Error guardando memoria: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Error processing document: {e}")
            await status_msg.edit_text(f"❌ Error: {str(e)}")
