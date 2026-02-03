import os
import re
import sys
import asyncio
import logging
import base64
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
import tempfile


from src.client import OllamaClient
from utils.cron_utils import CronUtils
from utils.search_utils import BraveSearch
from utils.audio_utils import transcribe_audio, transcribe_audio_large, is_whisper_available
from utils.youtube_utils import is_youtube_url, download_youtube_audio, get_video_title
from utils.document_utils import extract_text_from_document, is_supported_document
from utils.email_utils import is_gmail_configured, fetch_emails_last_24h, format_emails_for_llm
from utils.wiz_utils import control_light, is_wiz_available
from utils.config_loader import get_config

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
EVENTS_FILE = get_config("EVENTS_FILE")

# Authorization: Comma-separated user IDs allowed to use the bot
# If empty, NO ONE is authorized (secure by default)
AUTHORIZED_USERS_RAW = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(uid.strip()) for uid in AUTHORIZED_USERS_RAW.split(",") if uid.strip().isdigit()]

# Chat ID to send notifications to (reminders, etc.)
NOTIFICATION_CHAT_ID_RAW = os.getenv("NOTIFICATION_CHAT_ID", "")
NOTIFICATION_CHAT_ID = int(NOTIFICATION_CHAT_ID_RAW) if NOTIFICATION_CHAT_ID_RAW.strip().isdigit() else None

def is_authorized(user_id: int) -> bool:
    """Check if a user is in the authorized list."""
    if not AUTHORIZED_USERS:
        return False  # No one authorized if list is empty
    return user_id in AUTHORIZED_USERS

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Global constants from config
MODEL = get_config("MODEL")
MODEL_CONTEXT_SIZE = get_config("CONTEXT_LIMIT")

# Store chat history in memory (simple dict for single-process bot)
# chat_id -> list of messages
chat_histories = {}
system_instructions = ""
user_memory = ""

# Message queue for sequential processing
message_queue = asyncio.Queue()
queue_worker_running = False
last_activity = datetime.now()
email_digest_running = False

# Project root directory (parent of src/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_instructions():
    global system_instructions
    try:
        instructions_path = os.path.join(PROJECT_ROOT, get_config("INSTRUCTIONS_FILE"))
        with open(instructions_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                system_instructions = content
    except FileNotFoundError:
        pass

def load_memory():
    global user_memory
    try:
        memory_path = os.path.join(PROJECT_ROOT, get_config("MEMORY_FILE"))
        with open(memory_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                user_memory = content
    except FileNotFoundError:
        pass

def get_system_prompt():
    """Combines instructions and memory into a single system prompt."""
    parts = []
    if system_instructions:
        parts.append(system_instructions)
    if user_memory:
        parts.append(f"\n\n---\n\n# Memoria del Usuario\n\n{user_memory}")
    return "\n".join(parts) if parts else ""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Authorization check
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`", parse_mode="Markdown")
        return
    
    chat_histories[chat_id] = []
    system_prompt = get_system_prompt()
    if system_prompt:
        chat_histories[chat_id].append({"role": "system", "content": system_prompt})
    await update.message.reply_text("¡Hola! Soy LocalBot en Telegram. Háblame y te responderé.")

async def new_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears chat history and starts a new conversation."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso.", parse_mode="Markdown")
        return
    
    chat_histories[chat_id] = []
    # Reload memory in case it was updated
    load_memory()
    system_prompt = get_system_prompt()
    if system_prompt:
        chat_histories[chat_id].append({"role": "system", "content": system_prompt})
    await update.message.reply_text("🔄 Nueva conversación iniciada. El historial anterior fue borrado.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows bot status including token usage."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso.", parse_mode="Markdown")
        return
    
    # Calculate tokens using tiktoken (fallback to approximation)
    context_limit = int(get_config("CONTEXT_LIMIT", 200000))
    history = chat_histories.get(chat_id, [])
    
    total_tokens = 0
    calculation_method = "Aproximado (caracteres)"
    
    try:
        import tiktoken
        # cl100k_base is used by gpt-4, llama3, etc. Good enough approximation for all modern LLMs
        encoder = tiktoken.get_encoding("cl100k_base")
        calculation_method = "Real (tiktoken)"
        
        for msg in history:
            content = msg.get("content", "")
            # Add message overhead (approx 4 tokens for role/structure)
            total_tokens += 4
            total_tokens += len(encoder.encode(content))
        
        # Add reply overhead
        total_tokens += 3
        
    except ImportError:
        # Fallback: 1 token ~= 4 chars
        total_chars = sum(len(msg.get("content", "")) for msg in history)
        total_tokens = total_chars // 4
    
    # Calculate stats
    usage_percent = (total_tokens / context_limit) * 100
    if usage_percent > 100: usage_percent = 100
    
    remaining_tokens = max(0, context_limit - total_tokens)
    
    # Progress bar
    bar_length = 20
    filled_length = int(bar_length * usage_percent / 100)
    filled_length = min(filled_length, bar_length)
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

    await update.message.reply_text(status_text, parse_mode="Markdown")
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def unload_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unloads all models from RAM."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso.", parse_mode="Markdown")
        return
    
    status_msg = await update.message.reply_text("🔄 Descargando modelos...")
    
    client = OllamaClient()
    
    # Unload text model
    await client.unload_model(MODEL)
    
    # Unload vision model if configured
    vision_model = get_config("VISION_MODEL")
    if vision_model:
        await client.unload_model(vision_model)
    
    await status_msg.edit_text("✅ Modelos descargados de RAM.")


def escape_markdown(text: str) -> str:
    """Helper to escape Markdown special characters for Telegram."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles voice messages by transcribing and processing them."""
    print(f"[DEBUG] handle_voice called")
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    print(f"[DEBUG] user_id={user_id}, chat_id={chat_id}")
    
    # Authorization check
    if not is_authorized(user_id):
        print(f"[DEBUG] User not authorized")
        await update.message.reply_text(f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`", parse_mode="Markdown")
        return
    
    print(f"[DEBUG] User authorized, checking whisper...")
    
    # Check if whisper is available
    if not is_whisper_available():
        print(f"[DEBUG] Whisper not available")
        await update.message.reply_text("⚠️ Whisper no configurado. Instala: `pip install faster-whisper`", parse_mode="Markdown")
        return
    
    # Detection: if voice has caption = external (WhatsApp, etc), no caption = Telegram native
    has_caption = update.message.caption is not None and len(update.message.caption.strip()) > 0
    is_external = has_caption
    
    if is_external:
        # External audio: use large model, transcribe only
        status_msg = await update.message.reply_text("🎧 Audio externo detectado. Transcribiendo con modelo grande...\n_(Esto puede tomar tiempo)_", parse_mode="Markdown")
    else:
        # Direct voice: use base model + LLM
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
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        if is_external:
            # External: just show transcription, don't process with LLM
            await status_msg.edit_text(f"📝 *Transcripción (audio externo):*\n\n{transcription}", parse_mode="Markdown")
        else:
            # Direct voice: show transcription and process with LLM
            await status_msg.edit_text(f"🎙️ *Transcripción:*\n_{transcription}_", parse_mode="Markdown")
            
            # Add to queue with transcription text (4th element)
            needs_reply = not message_queue.empty()
            await message_queue.put((update, context, needs_reply, transcription))
            
            global queue_worker_running
            if not queue_worker_running:
                queue_worker_running = True
                asyncio.create_task(queue_worker())
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles external audio files - transcribe only with large model, no LLM."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Authorization check
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`", parse_mode="Markdown")
        return
    
    # Check if whisper is available
    if not is_whisper_available():
        await update.message.reply_text("⚠️ Whisper no configurado. Instala: `pip install faster-whisper`", parse_mode="Markdown")
        return
    
    # Show transcribing status
    audio = update.message.audio
    file_name = audio.file_name or "audio"
    status_msg = await update.message.reply_text(f"🎧 Transcribiendo *{file_name}* con modelo grande...\n_(Esto puede tomar tiempo)_", parse_mode="Markdown")
    
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
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        # Show transcription only (no LLM processing)
        await status_msg.edit_text(f"📝 *Transcripción de* `{file_name}`:\n\n{transcription}", parse_mode="Markdown")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles photos by describing them with vision model and processing with LLM."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Authorization check
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`", parse_mode="Markdown")
        return
    
    # Get vision model from config
    vision_model = get_config("VISION_MODEL")
    if not vision_model:
        await update.message.reply_text("⚠️ Modelo de visión no configurado en config.yaml")
        return
    
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
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        # Get image description from vision model
        client = OllamaClient()
        await status_msg.edit_text(f"🔍 Analizando imagen con {vision_model}...")
        
        # Use caption as prompt if provided, otherwise default
        caption = update.message.caption
        if caption:
            vision_prompt = f"El usuario envió esta imagen con el mensaje: '{caption}'. Describe la imagen en detalle."
        else:
            vision_prompt = "Describe esta imagen en detalle. ¿Qué ves? Incluye objetos, personas, colores, texto visible, y cualquier detalle relevante."
        
        image_description = await client.describe_image(vision_model, image_base64, vision_prompt)
        
        # Unload vision model to free RAM
        await client.unload_model(vision_model)
        
        await status_msg.edit_text("💭 Procesando respuesta...")
        
        # Initialize chat history if needed
        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
            system_prompt = get_system_prompt()
            if system_prompt:
                chat_histories[chat_id].append({"role": "system", "content": system_prompt})
        
        # Build context message for text model
        if caption:
            context_message = f"[El usuario envió una imagen con el mensaje: '{caption}']\n\n[Descripción de la imagen: {image_description}]\n\nResponde al usuario considerando la imagen y su mensaje."
        else:
            context_message = f"[El usuario envió una imagen]\n\n[Descripción de la imagen: {image_description}]\n\nComenta sobre la imagen de manera útil."
        
        # Add to history
        chat_histories[chat_id].append({"role": "user", "content": context_message})
        
        # Generate response with text model
        full_response = ""
        async for chunk in client.stream_chat(MODEL, chat_histories[chat_id]):
            full_response += chunk
        
        # Format response and strip commands
        formatted_response = full_response.replace("<think>", "> 🧠 **Pensando:**\n> ").replace("</think>", "\n\n")
        formatted_response = re.sub(r'\x1b\[[0-9;]*m', '', formatted_response)
        formatted_response = re.sub(r':::memory\s+.+?:::', '', formatted_response, flags=re.DOTALL)
        formatted_response = re.sub(r':::memory_delete\s+.+?:::', '', formatted_response, flags=re.DOTALL)
        formatted_response = formatted_response.strip()
        
        try:
            await status_msg.edit_text(formatted_response, parse_mode="Markdown")
        except Exception:
            await status_msg.edit_text(formatted_response)
        
        # Add to history
        chat_histories[chat_id].append({"role": "assistant", "content": full_response})
        
        # Parse memory commands
        for memory_match in re.finditer(r":::memory\s+(.+?):::", full_response, re.DOTALL):
            memory_content = memory_match.group(1).strip()
            if memory_content:
                try:
                    memory_path = os.path.join(PROJECT_ROOT, get_config("MEMORY_FILE"))
                    with open(memory_path, "a", encoding="utf-8") as f:
                        f.write(f"\n- {memory_content}")
                    load_memory()
                    await context.bot.send_message(chat_id, f"💾 Guardado en memoria: _{memory_content}_", parse_mode="Markdown")
                except Exception as e:
                    await context.bot.send_message(chat_id, f"⚠️ Error guardando memoria: {str(e)}")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles documents (PDF, DOCX, TXT) by extracting text and processing with LLM."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Authorization check
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`", parse_mode="Markdown")
        return
    
    document = update.message.document
    file_name = document.file_name or "documento"
    
    # Check if it's a supported document type
    if not is_supported_document(file_name):
        # Ignore unsupported files silently (could be stickers, etc)
        return
    
    status_msg = await update.message.reply_text(f"📄 Leyendo *{file_name}*...", parse_mode="Markdown")
    
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
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        # Check if extraction failed
        if doc_text.startswith("[Error"):
            await status_msg.edit_text(doc_text)
            return
        
        # Truncate if too long (keep first ~50k chars)
        if len(doc_text) > 50000:
            doc_text = doc_text[:50000] + "\n\n[... documento truncado por longitud ...]"
        
        await status_msg.edit_text(f"💭 Procesando documento {doc_type}...")
        
        # Initialize chat history if needed
        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
            system_prompt = get_system_prompt()
            if system_prompt:
                chat_histories[chat_id].append({"role": "system", "content": system_prompt})
        
        # Build context message
        caption = update.message.caption
        if caption:
            context_message = f"[El usuario envió un documento {doc_type} llamado '{file_name}' con el mensaje: '{caption}']\n\nContenido del documento:\n{doc_text}\n\nResponde considerando el documento y el mensaje del usuario."
        else:
            context_message = f"[El usuario envió un documento {doc_type} llamado '{file_name}']\n\nContenido del documento:\n{doc_text}\n\nResume o comenta sobre el contenido del documento."
        
        # Add to history
        chat_histories[chat_id].append({"role": "user", "content": context_message})
        
        # Generate response
        client = OllamaClient()
        full_response = ""
        async for chunk in client.stream_chat(MODEL, chat_histories[chat_id]):
            full_response += chunk
        
        # Format response and strip commands
        formatted_response = full_response.replace("<think>", "> 🧠 **Pensando:**\n> ").replace("</think>", "\n\n")
        formatted_response = re.sub(r'\x1b\[[0-9;]*m', '', formatted_response)
        formatted_response = re.sub(r':::memory\s+.+?:::', '', formatted_response, flags=re.DOTALL)
        formatted_response = re.sub(r':::memory_delete\s+.+?:::', '', formatted_response, flags=re.DOTALL)
        formatted_response = formatted_response.strip()
        
        try:
            await status_msg.edit_text(formatted_response, parse_mode="Markdown")
        except Exception:
            await status_msg.edit_text(formatted_response)
        
        # Add to history
        chat_histories[chat_id].append({"role": "assistant", "content": full_response})
        
        # Parse memory commands
        for memory_match in re.finditer(r":::memory\s+(.+?):::", full_response, re.DOTALL):
            memory_content = memory_match.group(1).strip()
            if memory_content:
                try:
                    memory_path = os.path.join(PROJECT_ROOT, get_config("MEMORY_FILE"))
                    with open(memory_path, "a", encoding="utf-8") as f:
                        f.write(f"\n- {memory_content}")
                    load_memory()
                    await context.bot.send_message(chat_id, f"💾 Guardado en memoria: _{memory_content}_", parse_mode="Markdown")
                except Exception as e:
                    await context.bot.send_message(chat_id, f"⚠️ Error guardando memoria: {str(e)}")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queues incoming messages for sequential processing."""
    user_id = update.effective_user.id
    
    # Authorization check
    # Authorization check
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso a este bot.\nTu ID es: `{user_id}`", parse_mode="Markdown")
        return
    
    # Check if queue already has items (means there's a backlog)
    needs_reply = not message_queue.empty()
    
    # Add to queue with flag (None for text_override since this is a text message)
    await message_queue.put((update, context, needs_reply, None))
    
    # Start worker if not running
    global queue_worker_running
    if not queue_worker_running:
        queue_worker_running = True
        asyncio.create_task(queue_worker())

async def queue_worker():
    """Processes messages from the queue one by one."""
    global queue_worker_running
    global last_activity
    
    while True:
        try:
            # Get next message (4 elements: update, context, needs_reply, text_override)
            item = await asyncio.wait_for(message_queue.get(), timeout=1.0)
            update, context, needs_reply = item[0], item[1], item[2]
            text_override = item[3] if len(item) > 3 else None
        except asyncio.TimeoutError:
            # No more messages, stop worker
            queue_worker_running = False
            return
        
        # Update activity timestamp
        last_activity = datetime.now()
        
        # Process this message
        await process_message_item(update, context, use_reply=needs_reply, text_override=text_override)
        
        message_queue.task_done()

async def process_message_item(update: Update, context: ContextTypes.DEFAULT_TYPE, use_reply: bool = False, text_override: str = None):
    """Processes a single message (the actual LLM logic)."""
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    user_text = text_override if text_override else update.message.text
    
    # Validate user_text
    if not user_text or not user_text.strip():
        await context.bot.send_message(chat_id, "⚠️ No se detectó texto en el mensaje.")
        return

    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
        system_prompt = get_system_prompt()
        if system_prompt:
            chat_histories[chat_id].append({"role": "system", "content": system_prompt})

    placeholder_msg = None # Initialize placeholder to reuse for YouTube status

    # Check for YouTube URL
    youtube_url = is_youtube_url(user_text)
    if youtube_url:
        try:
            # Send status
            status_msg = await context.bot.send_message(chat_id, "🎥 Descargando audio del video...")
            
            # Get video title
            video_title = get_video_title(youtube_url)
            
            # Download audio
            audio_path = await download_youtube_audio(youtube_url)
            
            await status_msg.edit_text(f"🎙️ Transcribiendo: _{video_title}_...", parse_mode="Markdown")
            
            # Transcribe with base model
            transcription = await transcribe_audio(audio_path)
            
            # Clean up audio file
            try:
                os.unlink(audio_path)
                os.rmdir(os.path.dirname(audio_path))
            except:
                pass
            
            # Replace user_text with STRONG summarization request
            user_text = (
                f"Analiza la siguiente transcripción del video de YouTube '{video_title}':\n\n"
                f"\"\"\"\n{transcription}\n\"\"\"\n\n"
                f"INSTRUCCIÓN: Haz un resumen detallado y estructurado del contenido del video anterior."
            )
            
            await status_msg.edit_text(f"📝 Resumiendo: _{video_title}_...", parse_mode="Markdown")
            
            # Keep this message to be updated with the response
            placeholder_msg = status_msg
                
        except Exception as e:
            await context.bot.send_message(chat_id, f"❌ Error procesando video: {str(e)}")
            return

    # Prepare context with time and schedule
    current_time_str = datetime.now().strftime("%H:%M del %d/%m/%Y")
    crontab_lines = CronUtils.get_crontab()
    crontab_str = "\n".join(crontab_lines) if crontab_lines else "(vacío)"
    context_message = f"{user_text} [Sistema: La hora actual es {current_time_str}. Agenda actual (crontab):\n{crontab_str}]"
    
    # Add to history
    chat_histories[chat_id].append({"role": "user", "content": context_message})

    # Send typing action
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Generate response
    client = OllamaClient()
    full_response = ""
    
    # Use reply_to if there are pending messages in queue
    if placeholder_msg is None:
        if use_reply:
            placeholder_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="...",
                reply_to_message_id=message_id
            )
        else:
            placeholder_msg = await update.message.reply_text("...")
    
    try:
        async for chunk in client.stream_chat(MODEL, chat_histories[chat_id]):
            full_response += chunk
            pass
            
        # --- Check for Search Command BEFORE displaying ---
        search_match = re.search(r":::search\s+(.+?):::", full_response)
        if search_match:
            search_query = search_match.group(1).strip()
            
            # Update placeholder to show we're searching
            await placeholder_msg.edit_text(f"🔍 Buscando: {search_query}...")
            
            # Execute search
            search_results = await BraveSearch.search(search_query)
            
            # Inject results into history (add the initial response and search results)
            chat_histories[chat_id].append({"role": "assistant", "content": full_response})
            chat_histories[chat_id].append({"role": "user", "content": f"[Sistema: Resultados de búsqueda para '{search_query}']:\n{search_results}\n\nAhora responde al usuario con esta información. NO repitas el comando de búsqueda."})
            
            # Get final response from LLM
            final_response = ""
            async for chunk in client.stream_chat(MODEL, chat_histories[chat_id]):
                final_response += chunk
            
            # CRITICAL: Update full_response so command parsers see the new text
            full_response = final_response
            
            # Format the final response (no search command visible)
            final_formatted = final_response.replace("<think>", "> 🧠 **Pensando:**\n> ").replace("</think>", "\n\n")
            final_formatted = re.sub(r'\x1b\[[0-9;]*m', '', final_formatted)
            # Remove all command patterns from output
            final_formatted = re.sub(r':::search\s+.+?:::', '', final_formatted)
            final_formatted = re.sub(r':::memory\s+.+?:::', '', final_formatted, flags=re.DOTALL)
            final_formatted = re.sub(r':::memory_delete\s+.+?:::', '', final_formatted, flags=re.DOTALL)
            final_formatted = re.sub(r':::cron_delete\s+.+?:::', '', final_formatted)
            final_formatted = re.sub(r':::cron\s+.+?:::', '', final_formatted)
            final_formatted = re.sub(r':::luz\s+.+?:::', '', final_formatted)
            final_formatted = re.sub(r':::camara(?:\s+\S+)?:::', '', final_formatted)
            final_formatted = final_formatted.strip()
            
            try:
                await placeholder_msg.edit_text(final_formatted, parse_mode="Markdown")
            except Exception:
                await placeholder_msg.edit_text(final_formatted)
            
            chat_histories[chat_id].append({"role": "assistant", "content": final_response})
            # Skip to cron parsing (search already handled)
        else:
            formatted_response = full_response
            formatted_response = formatted_response.replace("<think>", "> 🧠 **Pensando:**\n> ")
            formatted_response = formatted_response.replace("</think>", "\n\n")
            formatted_response = re.sub(r'\x1b\[[0-9;]*m', '', formatted_response)
            # Remove all command patterns from output
            formatted_response = re.sub(r':::memory\s+.+?:::', '', formatted_response, flags=re.DOTALL)
            formatted_response = re.sub(r':::memory_delete\s+.+?:::', '', formatted_response, flags=re.DOTALL)
            formatted_response = re.sub(r':::cron_delete\s+.+?:::', '', formatted_response)
            formatted_response = re.sub(r':::cron\s+.+?:::', '', formatted_response)
            formatted_response = re.sub(r':::luz\s+.+?:::', '', formatted_response)
            formatted_response = re.sub(r':::camara(?:\s+\S+)?:::', '', formatted_response)
            
            final_text = formatted_response.strip()
            
            # If after stripping commands the message is empty, delete placeholder
            if not final_text:
                try:
                    await placeholder_msg.delete()
                except:
                    pass
            else:
                try:
                    await placeholder_msg.edit_text(final_text, parse_mode="Markdown")
                except Exception:
                    await placeholder_msg.edit_text(final_text)
            
            # Append to history
            chat_histories[chat_id].append({"role": "assistant", "content": full_response})
        
        # --- Command Parsing ---
        # 1. Delete commands
        for delete_match in re.finditer(r":::cron_delete\s+(.+?):::", full_response):
            target = delete_match.group(1).strip()
            # Escape target for markdown display
            target_esc = target.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`") 
            await context.bot.send_message(chat_id, f"🗑️  Eliminando tarea que contenga: `{target_esc}`", parse_mode="Markdown")
            
            if CronUtils.delete_job(target):
                await context.bot.send_message(chat_id, f"✅ Tarea eliminada con éxito.")
            else:
                 await context.bot.send_message(chat_id, f"⚠️ No se encontraron tareas coincidentes.")

        # 2. Add commands
        for cron_match in re.finditer(r":::cron\s+(.+?)\s+(.+?):::", full_response):
            schedule = cron_match.group(1).strip()
            command = cron_match.group(2).strip()
            
            if command.endswith(":"):
               command = command[:-1].strip()
            
            # Escape for display
            sched_esc = schedule.replace("_", "\\_").replace("*", "\\*")
            cmd_esc = command.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
            
            await context.bot.send_message(chat_id, f"⚠️  Agregando tarea Cron: `{sched_esc} {cmd_esc}`", parse_mode="Markdown")
            
            if CronUtils.add_job(schedule, command):
                 await context.bot.send_message(chat_id, f"✅ Tarea agregada con éxito.")
            else:
                 await context.bot.send_message(chat_id, f"❌ Error al agregar tarea.")
        
        # 3. Memory delete commands - remove from memory.md
        for memory_del_match in re.finditer(r":::memory_delete\s+(.+?):::", full_response, re.DOTALL):
            target = memory_del_match.group(1).strip()
            if target:
                try:
                    memory_path = os.path.join(PROJECT_ROOT, get_config("MEMORY_FILE"))
                    with open(memory_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    
                    # Filter out lines containing the target
                    new_lines = [line for line in lines if target.lower() not in line.lower()]
                    removed = len(lines) - len(new_lines)
                    
                    if removed > 0:
                        with open(memory_path, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                        load_memory()
                        await context.bot.send_message(chat_id, f"🗑️ Eliminado de memoria: _{target}_", parse_mode="Markdown")
                    else:
                        await context.bot.send_message(chat_id, f"⚠️ No se encontró en memoria: _{target}_", parse_mode="Markdown")
                except Exception as e:
                    await context.bot.send_message(chat_id, f"⚠️ Error eliminando memoria: {str(e)}")
        
        # 4. Memory add commands - append to memory.md
        for memory_match in re.finditer(r":::memory\s+(.+?):::", full_response, re.DOTALL):
            memory_content = memory_match.group(1).strip()
            if memory_content:
                try:
                    memory_path = os.path.join(PROJECT_ROOT, get_config("MEMORY_FILE"))
                    with open(memory_path, "a", encoding="utf-8") as f:
                        f.write(f"\n- {memory_content}")
                    # Reload memory for future conversations
                    load_memory()
                    await context.bot.send_message(chat_id, f"💾 Guardado en memoria: _{memory_content}_", parse_mode="Markdown")
                except Exception as e:
                    await context.bot.send_message(chat_id, f"⚠️ Error guardando memoria: {str(e)}")
        
        # 5. Light control commands - :::luz nombre accion valor:::
        for luz_match in re.finditer(r":::luz\s+(\S+)\s+(\S+)(?:\s+(\S+))?:::", full_response):
            luz_name = luz_match.group(1).strip()
            luz_action = luz_match.group(2).strip()
            luz_value = luz_match.group(3).strip() if luz_match.group(3) else None
            
            result = await control_light(luz_name, luz_action, luz_value)
            await context.bot.send_message(chat_id, result)
                 
    except Exception as e:
        # Fallback for main loop errors
        try:
            await placeholder_msg.edit_text(f"Error: {str(e)}")
        except:
            pass

async def check_events(context: ContextTypes.DEFAULT_TYPE):
    """Background task to watch events.txt and send to Telegram."""
    # Use configured chat ID, or fall back to active chats
    target_chats = []
    if NOTIFICATION_CHAT_ID:
        target_chats.append(NOTIFICATION_CHAT_ID)
    else:
        # Only use active chats if no fixed ID is set
        # This is volatile (lost on restart) but acceptable if user opted out of .env
        target_chats.extend(chat_histories.keys())
    
    if not target_chats:
        return  # No one to notify

    try:
        if os.path.exists(EVENTS_FILE) and os.path.getsize(EVENTS_FILE) > 0:
            with open(EVENTS_FILE, 'r+', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    lines = content.strip().split('\n')
                    timestamp = datetime.now().strftime("%H:%M")
                    
                    sent_to = set()  # Avoid duplicate sends
                    for chat_id in target_chats:
                        if chat_id in sent_to:
                            continue
                        sent_to.add(chat_id)
                        for line in lines:
                            if line.strip():
                                # Escape the line content to prevent broken markdown
                                line_esc = line.strip().replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
                                try:
                                    await context.bot.send_message(
                                        chat_id=chat_id, 
                                        text=f"🔔 {line_esc}",
                                        parse_mode="Markdown"
                                    )
                                except Exception:
                                    # Fallback without markdown
                                    await context.bot.send_message(
                                        chat_id=chat_id, 
                                        text=f"🔔 {line.strip()}"
                                    )
                    
                    # Clear file
                    f.seek(0)
                    f.truncate()
    except Exception as e:
        print(f"Error checking events: {e}")


async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    """Unloads model if no activity for configured timeout."""
    global last_activity
    # Don't unload if email digest is running
    if email_digest_running:
        print("[INACTIVITY] Skipping unload - email digest in progress")
        return
    timeout_seconds = get_config("INACTIVITY_TIMEOUT_MINUTES") * 60
    if (datetime.now() - last_activity).total_seconds() > timeout_seconds:
        print("[INACTIVITY] Unloading model due to timeout")
        client = OllamaClient()
        await client.unload_model(MODEL)

async def cleanup_old_crons(context: ContextTypes.DEFAULT_TYPE):
    """Removes one-time cron jobs that have already passed."""
    removed = CronUtils.cleanup_old_jobs()
    if removed > 0:
        print(f"[CLEANUP] Removed {removed} old cron job(s)")

async def daily_email_digest(context: ContextTypes.DEFAULT_TYPE):
    """Fetches emails from last 24h and sends a summary of important ones."""
    global email_digest_running
    
    # Only run if Gmail is configured
    if not is_gmail_configured():
        return
    
    notification_chat_id = os.getenv("NOTIFICATION_CHAT_ID")
    if not notification_chat_id:
        return
    
    # Set flag to prevent model unload during digest
    email_digest_running = True
    print("[EMAIL DIGEST] Flag set, starting digest...")
    
    try:
        print("[EMAIL DIGEST] Fetching emails from last 24 hours...")
        emails = await fetch_emails_last_24h()
        print(f"[EMAIL DIGEST] Fetched {len(emails)} emails")
        
        if not emails:
            print("[EMAIL DIGEST] No new emails")
            return
        
        if "error" in emails[0]:
            await context.bot.send_message(
                notification_chat_id,
                f"⚠️ Error al revisar emails: {emails[0]['error']}"
            )
            return
        
        # Format emails for LLM
        email_summary = format_emails_for_llm(emails)
        print(f"[EMAIL DIGEST] Formatted summary ({len(email_summary)} chars)")
        
        # Use LLM to identify important emails
        client = OllamaClient()
        analysis_prompt = f"""Analiza estos emails recibidos en las últimas 24 horas. 
Identifica los más IMPORTANTES (urgentes, de personas conocidas, acciones requeridas).
Ignora spam, newsletters y promociones.
Responde en español con un resumen breve de los emails importantes.
Si no hay nada importante, dilo brevemente.

{email_summary}"""
        
        messages = [{"role": "user", "content": analysis_prompt}]
        
        print("[EMAIL DIGEST] Starting LLM analysis...")
        full_response = ""
        chunk_count = 0
        async for chunk in client.stream_chat(MODEL, messages):
            full_response += chunk
            chunk_count += 1
            if chunk_count % 10 == 0:
                print(f"[EMAIL DIGEST] Received {chunk_count} chunks...")
        
        print(f"[EMAIL DIGEST] LLM done. Response length: {len(full_response)} chars")
        
        # Remove thinking tags
        formatted = full_response.replace("<think>", "").replace("</think>", "")
        formatted = formatted.strip()
        
        # Send digest
        print("[EMAIL DIGEST] Sending message to Telegram...")
        await context.bot.send_message(
            notification_chat_id,
            f"📬 **Resumen de emails (últimas 24h)**\n\n{formatted}",
            parse_mode="Markdown"
        )
        
        # Unload model after use
        await client.unload_model(MODEL)
        
        print(f"[EMAIL DIGEST] Sent summary of {len(emails)} emails")
        
    except Exception as e:
        import traceback
        print(f"[EMAIL DIGEST] Error: {str(e)}")
        print(f"[EMAIL DIGEST] Traceback: {traceback.format_exc()}")
    finally:
        email_digest_running = False
        print("[EMAIL DIGEST] Flag cleared, digest complete.")

async def digest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual trigger for email digest - for testing."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text(f"⛔ No tienes acceso.", parse_mode="Markdown")
        return
    
    await update.message.reply_text("📬 Ejecutando digest de emails...")
    await daily_email_digest(context)

if __name__ == '__main__':
    if not TOKEN or TOKEN == "your_telegram_token_here":
        print("Error: TELEGRAM_TOKEN not set in .env")
        exit(1)
        
    load_instructions()
    load_memory()
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    new_handler = CommandHandler('new', new_conversation)
    status_handler = CommandHandler('status', status)
    unload_handler = CommandHandler('unload', unload_models)
    digest_handler = CommandHandler('digest', digest_command)
    msg_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message)
    voice_handler = MessageHandler(filters.VOICE, handle_voice)
    audio_handler = MessageHandler(filters.AUDIO, handle_audio)
    photo_handler = MessageHandler(filters.PHOTO, handle_photo)
    document_handler = MessageHandler(filters.Document.ALL, handle_document)
    
    application.add_handler(start_handler)
    application.add_handler(new_handler)
    application.add_handler(status_handler)
    application.add_handler(unload_handler)
    application.add_handler(digest_handler)
    application.add_handler(msg_handler)
    application.add_handler(voice_handler)
    application.add_handler(audio_handler)
    application.add_handler(photo_handler)
    application.add_handler(document_handler)
    
    # Check events every 2 seconds
    if application.job_queue:
        application.job_queue.run_repeating(check_events, interval=2)
        # Check inactivity every minute
        application.job_queue.run_repeating(check_inactivity, interval=60)
        # Cleanup old crons periodically
        cleanup_interval = get_config("CRON_CLEANUP_INTERVAL_MINUTES") * 60
        application.job_queue.run_repeating(cleanup_old_crons, interval=cleanup_interval)
        # Daily email digest at 4:00 AM (only runs if Gmail is configured)
        if is_gmail_configured():
            from datetime import time as dt_time
            # Use configured timezone
            tz_offset = get_config("TIMEZONE_OFFSET_HOURS")
            local_tz = timezone(timedelta(hours=tz_offset))
            application.job_queue.run_daily(daily_email_digest, time=dt_time(hour=4, minute=0, tzinfo=local_tz))
            print(f"[EMAIL DIGEST] Job programado para las 4:00 AM (UTC{tz_offset:+d})")
    
    print("Bot is polling...")
    application.run_polling()
