"""Main Telegram bot for LocalBot - Refactored modular version."""
import os
import re
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters
)

# Add parent directory to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Import modular components
from src.constants import PROJECT_ROOT as CONSTANTS_ROOT
from src.state.chat_manager import ChatManager
from src.client import OllamaClient
from src.memory.vector_store import VectorManager
from src.handlers.commands import CommandHandlers
from src.handlers.voice import VoiceHandler
from src.handlers.audio import AudioHandler
from src.handlers.photo import PhotoHandler
from src.handlers.document import DocumentHandler
from src.jobs.events import EventsJob
from src.jobs.inactivity import InactivityJob
from src.jobs.cleanup import CleanupJob
from src.jobs.email_digest import EmailDigestJob
from src.middleware.rate_limiter import rate_limit

from utils.cron_utils import CronUtils
from utils.config_loader import get_config, get_all_config
from utils.telegram_utils import split_message, format_bot_response, escape_markdown, prune_history
from utils.youtube_utils import is_youtube_url, download_youtube_audio, get_video_title
from utils.twitter_utils import is_twitter_url, download_twitter_video, get_twitter_media_url
from utils.search_utils import BraveSearch

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Authorization
AUTHORIZED_USERS_RAW = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS = [int(uid.strip()) for uid in AUTHORIZED_USERS_RAW.split(",") if uid.strip().isdigit()]

NOTIFICATION_CHAT_ID_RAW = os.getenv("NOTIFICATION_CHAT_ID", "")
NOTIFICATION_CHAT_ID = int(NOTIFICATION_CHAT_ID_RAW) if NOTIFICATION_CHAT_ID_RAW.strip().isdigit() else None

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global instances
chat_manager = ChatManager(max_inactive_hours=24)
vector_manager = VectorManager(get_all_config(), OllamaClient())
message_queue = asyncio.Queue()
queue_worker_running = False
last_activity = datetime.now()

# Initialize email digest job
email_digest_job = EmailDigestJob(notification_chat_id=NOTIFICATION_CHAT_ID)

# Config values
MODEL = get_config("MODEL")
COMMAND_PATTERNS = {
    'memory': re.compile(r':::memory\s+(.+?):::', re.DOTALL),
    'memory_delete': re.compile(r':::memory_delete\s+(.+?):::', re.DOTALL),
    'cron': re.compile(r':::cron\s+(.+?)\s+(.+?):::'),
    'cron_delete': re.compile(r':::cron_delete\s+(.+?):::'),
    'search': re.compile(r':::search\s+(.+?):::'),
    'foto': re.compile(r':::foto\s+(.+?):::', re.IGNORECASE),
    'luz': re.compile(r':::luz\s+(\S+)\s+(\S+)(?:\s+(\S+))?:::'),
    'camara': re.compile(r':::camara(?:\s+\S+)?:::'),
}

# System instructions
system_instructions = ""


def is_authorized(user_id: int) -> bool:
    """Check if a user is authorized."""
    if not AUTHORIZED_USERS:
        return False
    return user_id in AUTHORIZED_USERS


def load_instructions():
    """Load system instructions from file."""
    global system_instructions
    try:
        from src.constants import PROJECT_ROOT
        instructions_path = os.path.join(PROJECT_ROOT, get_config("INSTRUCTIONS_FILE"))
        with open(instructions_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                system_instructions = content
                logger.info("Instructions loaded successfully")
    except FileNotFoundError:
        logger.warning("Instructions file not found")
    except Exception as e:
        logger.error(f"Error loading instructions: {e}")



# [DELETED] load_memory function


def get_system_prompt():
    """Get system instructions."""
    return system_instructions if system_instructions else ""


# Initialize handlers
command_handlers = CommandHandlers(
    chat_manager=chat_manager,
    is_authorized_func=is_authorized,
    get_system_prompt_func=get_system_prompt,
    email_digest_job=email_digest_job
)

voice_handler = VoiceHandler(
    is_authorized_func=is_authorized,
    message_queue=message_queue,
    queue_worker_func=None  # Will be set later
)

audio_handler = AudioHandler(is_authorized_func=is_authorized)

photo_handler = PhotoHandler(
    chat_manager=chat_manager,
    is_authorized_func=is_authorized,
    get_system_prompt_func=get_system_prompt,
    command_patterns=COMMAND_PATTERNS
)

document_handler = DocumentHandler(
    chat_manager=chat_manager,
    vector_manager=vector_manager,
    is_authorized_func=is_authorized,
    get_system_prompt_func=get_system_prompt,
    command_patterns=COMMAND_PATTERNS
)


async def queue_worker():
    """Process messages from queue."""
    global queue_worker_running, last_activity
    
    while True:
        try:
            item = await asyncio.wait_for(message_queue.get(), timeout=1.0)
            update, context, needs_reply = item[0], item[1], item[2]
            text_override = item[3] if len(item) > 3 else None
        except asyncio.TimeoutError:
            queue_worker_running = False
            return
        
        last_activity = datetime.now()
        await process_message_item(update, context, use_reply=needs_reply, text_override=text_override)
        message_queue.task_done()


# Set queue worker function for voice handler
voice_handler.queue_worker = queue_worker


@rate_limit(max_messages=10, window_seconds=60)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text(
            f"⛔ No tienes acceso. Tu ID: `{user_id}`",
            parse_mode="Markdown"
        )
        return
    
    needs_reply = not message_queue.empty()
    await message_queue.put((update, context, needs_reply, None))
    
    global queue_worker_running
    if not queue_worker_running:
        queue_worker_running = True
        asyncio.create_task(queue_worker())


async def process_message_item(update: Update, context: ContextTypes.DEFAULT_TYPE,
                               use_reply: bool = False, text_override: str = None):
    """Process a single message with LLM."""
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    user_text = text_override or update.message.text
    
    if not user_text or not user_text.strip():
        await context.bot.send_message(chat_id, "⚠️ No se detectó texto.")
        return
    
    # Initialize chat history
    history = await chat_manager.get_history(chat_id)
    if not history:
        system_prompt = get_system_prompt()
        await chat_manager.initialize_chat(chat_id, system_prompt)
        history = await chat_manager.get_history(chat_id)
    
    placeholder_msg = None
    
    # Check for Twitter URL
    twitter_url = is_twitter_url(user_text)
    if twitter_url:
        keywords = ["descarga", "baja", "video", "bajar", "download"]
        if any(k in user_text.lower() for k in keywords):
            status_msg = await context.bot.send_message(chat_id, "🐦 Analizando Twitter/X...")
            try:
                media_path = await download_twitter_video(twitter_url)
                await status_msg.edit_text("📤 Subiendo...")
                
                with open(media_path, 'rb') as f:
                    if media_path.endswith(('.jpg', '.png', '.jpeg')):
                        await context.bot.send_photo(chat_id, photo=f)
                    else:
                        await context.bot.send_video(chat_id, video=f)
                
                import os
                os.unlink(media_path)
                await status_msg.delete()
                return
            except Exception as e:
                await status_msg.edit_text(f"❌ Error: {str(e)}")
                return
    
    # Check for YouTube URL
    youtube_url = is_youtube_url(user_text)
    if youtube_url:
        keywords = ["descarga", "baja", "video", "bajar", "download"]
        if any(k in user_text.lower() for k in keywords):
            status_msg = await context.bot.send_message(chat_id, "🎥 Descargando...")
            try:
                from utils.youtube_utils import download_youtube_video
                video_path = await download_youtube_video(youtube_url)
                await status_msg.edit_text("📤 Subiendo...")
                
                with open(video_path, 'rb') as f:
                    await context.bot.send_video(chat_id, video=f)
                
                import os
                os.unlink(video_path)
                await status_msg.delete()
                return
            except Exception as e:
                await status_msg.edit_text(f"❌ Error: {str(e)}")
                return
        
        # Process for transcription
        try:
            status_msg = await context.bot.send_message(chat_id, "🎥 Descargando audio...")
            video_title = get_video_title(youtube_url)
            audio_path = await download_youtube_audio(youtube_url)
            
            from utils.audio_utils import transcribe_audio
            await status_msg.edit_text(f"🎙️ Transcribiendo: _{video_title}_...")
            transcription = await transcribe_audio(audio_path)
            
            import os
            os.unlink(audio_path)
            
            user_text = (
                f"Analiza esta transcripción de YouTube '{video_title}':\n\n"
                f"\"\"\"\n{transcription}\n\"\"\"\n\n"
                f"Haz un resumen detallado."
            )
            placeholder_msg = status_msg
        except Exception as e:
            await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")
            return
    
    # Generate response (Send "..." immediately)
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    if placeholder_msg is None:
        if use_reply:
            placeholder_msg = await context.bot.send_message(
                chat_id=chat_id, text="🧠 RAG...", reply_to_message_id=message_id
            )
        else:
            placeholder_msg = await update.message.reply_text("🧠 RAG...")

    # Prepare context
    current_time = datetime.now().strftime("%H:%M del %d/%m/%Y")
    crontab_lines = CronUtils.get_crontab()
    crontab_str = "\n".join(crontab_lines) if crontab_lines else "(vacío)"
    
    # RAG Context Retrieval
    rag_context = ""
    try:
        # Search both collections
        docs_results = await vector_manager.search(user_text, collection_type="documents", limit=3)
        mem_results = await vector_manager.search(user_text, collection_type="memory", limit=3)
        
        # Combine and sort by similarity
        all_results = docs_results + mem_results
        all_results.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Take top 3
        search_results = all_results[:3]
        
        if search_results:
             logger.info(f"🔍 RAG Results found: {len(search_results)}")
             rag_entries = [
                f"- {res['content']} (Sim: {res['similarity']:.2f})"
                for res in search_results
            ]
             rag_context = "\n\n# Contexto Recuperado (RAG)\n" + "\n".join(rag_entries)
             logger.info(f"📄 RAG Context injected: {rag_context}")
        else:
             logger.info("❌ No RAG results found.")
    except Exception as e:
        logger.error(f"RAG Error: {e}")

    context_message = f"{user_text} [Sistema: La hora actual es {current_time}. Agenda: {crontab_str}.{rag_context}]"
    await chat_manager.append_message(chat_id, {"role": "user", "content": context_message})
    
    try:
        # Update UI to show LLM generation started
        if placeholder_msg:
             await placeholder_msg.edit_text("🧠 LLM...")
             
        client = OllamaClient()
        history = await chat_manager.get_history(chat_id)
        pruned_history = prune_history(history, get_config("CONTEXT_LIMIT", 30000))
        
        full_response = ""
        async for chunk in client.stream_chat(MODEL, pruned_history):
            full_response += chunk
        
        # Handle search command
        search_match = COMMAND_PATTERNS['search'].search(full_response)
        if search_match:
            search_query = search_match.group(1).strip()
            await placeholder_msg.edit_text(f"🔍 Buscando: {search_query}...")
            
            search_results = await BraveSearch.search(search_query)
            await chat_manager.append_message(chat_id, {"role": "assistant", "content": full_response})
            await chat_manager.append_message(chat_id, {
                "role": "user",
                "content": f"[Resultados de búsqueda para '{search_query}']:\n{search_results}"
            })
            
            final_response = ""
            history = await chat_manager.get_history(chat_id)
            async for chunk in client.stream_chat(MODEL, prune_history(history, get_config("CONTEXT_LIMIT", 30000))):
                final_response += chunk
            
            full_response = final_response
            formatted = format_bot_response(full_response)
            
            chunks = split_message(formatted)
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await placeholder_msg.edit_text(chunk, parse_mode="Markdown")
                else:
                    await context.bot.send_message(chat_id, chunk, parse_mode="Markdown")
            
            await chat_manager.append_message(chat_id, {"role": "assistant", "content": full_response})
        else:
            formatted = format_bot_response(full_response)
            
            if not formatted:
                await placeholder_msg.delete()
            else:
                chunks = split_message(formatted)
                for i, chunk in enumerate(chunks):
                    try:
                        if i == 0:
                            await placeholder_msg.edit_text(chunk, parse_mode="Markdown")
                        else:
                            await context.bot.send_message(chat_id, chunk, parse_mode="Markdown")
                    except Exception:
                        if i == 0:
                            await placeholder_msg.edit_text(chunk)
                        else:
                            await context.bot.send_message(chat_id, chunk)
            
            await chat_manager.append_message(chat_id, {"role": "assistant", "content": full_response})
        
        # Process commands
        await _process_commands(full_response, chat_id, context)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await placeholder_msg.edit_text(f"❌ Error: {str(e)}")


async def _process_commands(full_response: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Process internal commands from LLM response."""
    from utils.wiz_utils import control_light
    from src.constants import PROJECT_ROOT
    
    # Cron delete
    for match in COMMAND_PATTERNS['cron_delete'].finditer(full_response):
        target = match.group(1).strip()
        target_esc = escape_markdown(target)
        await context.bot.send_message(
            chat_id,
            f"🗑️ Eliminando: `{target_esc}`",
            parse_mode="Markdown"
        )
        if CronUtils.delete_job(target):
            await context.bot.send_message(chat_id, "✅ Tarea eliminada.")
        else:
            await context.bot.send_message(chat_id, "⚠️ No se encontraron tareas.")
    
    # Cron add
    for match in COMMAND_PATTERNS['cron'].finditer(full_response):
        schedule = match.group(1).strip()
        command = match.group(2).strip()
        
        if command.endswith(":"):
            command = command[:-1].strip()
        
        if "echo" in command and ">>" not in command:
            events_file = os.path.join(PROJECT_ROOT, get_config("EVENTS_FILE"))
            command += f" >> {events_file}"
        
        sched_esc = escape_markdown(schedule)
        cmd_esc = escape_markdown(command)
        
        await context.bot.send_message(
            chat_id,
            f"⚠️ Agregando: `{sched_esc} {cmd_esc}`",
            parse_mode="Markdown"
        )
        
        if CronUtils.add_job(schedule, command):
            await context.bot.send_message(chat_id, "✅ Tarea agregada.")
        else:
            await context.bot.send_message(chat_id, "❌ Error al agregar.")
    
    # Memory delete
    for match in COMMAND_PATTERNS['memory_delete'].finditer(full_response):
        target = match.group(1).strip()
        if target:
            try:
                if await vector_manager.delete_memory(target):
                    await context.bot.send_message(
                        chat_id, 
                        f"🗑️ Memoria borrada: _{target}_",
                         parse_mode="Markdown"
                    )
                else:
                     await context.bot.send_message(chat_id, f"⚠️ No encontré recuerdos similares a: _{target}_", parse_mode="Markdown")
            except Exception as e:
                await context.bot.send_message(chat_id, f"⚠️ Error borrando memoria: {str(e)}")
    
    # Memory add
    # Memory add
    for match in COMMAND_PATTERNS['memory'].finditer(full_response):
        content = match.group(1).strip()
        if content:
            try:
                # Save ONLY to Vector DB
                if await vector_manager.add_memory(content):
                    await context.bot.send_message(
                        chat_id,
                        f"💾 Guardado (DB): _{content}_",
                        parse_mode="Markdown"
                    )
                else:
                     await context.bot.send_message(chat_id, "❌ Error al guardar en DB.")

            except Exception as e:
                await context.bot.send_message(chat_id, f"⚠️ Error: {str(e)}")
    
    # Light control
    for match in COMMAND_PATTERNS['luz'].finditer(full_response):
        name = match.group(1).strip()
        action = match.group(2).strip()
        value = match.group(3).strip() if match.group(3) else None
        
        result = await control_light(name, action, value)
        await context.bot.send_message(chat_id, result)


def main():
    """Main entry point."""
    # Load initial data
    # Load initial data
    load_instructions()
    # memory load removed
    
    # Build application
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", command_handlers.start))
    application.add_handler(CommandHandler("new", command_handlers.new_conversation))
    application.add_handler(CommandHandler("status", command_handlers.status))
    application.add_handler(CommandHandler("unload", command_handlers.unload_models))
    application.add_handler(CommandHandler("restart", command_handlers.restart_bot))
    application.add_handler(CommandHandler("digest", command_handlers.email_digest))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.VOICE, voice_handler.handle))
    application.add_handler(MessageHandler(filters.AUDIO, audio_handler.handle))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler.handle))
    application.add_handler(MessageHandler(filters.Document.ALL, document_handler.handle))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Background jobs
    if NOTIFICATION_CHAT_ID:
        events_job = EventsJob(
            notification_chat_id=NOTIFICATION_CHAT_ID,
            authorized_users=AUTHORIZED_USERS
        )
        application.job_queue.run_repeating(
            events_job.run,
            interval=events_job.interval_seconds,
            first=1
        )
    
    inactivity_job = InactivityJob(
        get_last_activity_func=lambda: last_activity,
        model=MODEL
    )
    application.job_queue.run_repeating(
        inactivity_job.run,
        interval=inactivity_job.interval_seconds,
        first=300
    )
    
    cleanup_job = CleanupJob(chat_manager=chat_manager)
    application.job_queue.run_repeating(
        cleanup_job.run,
        interval=cleanup_job.interval_seconds,
        first=3600
    )
    
    # Email digest job - checks every minute if it's 4:00 AM
    if NOTIFICATION_CHAT_ID:
        application.job_queue.run_repeating(
            email_digest_job.run,
            interval=email_digest_job.interval_seconds,
            first=60
        )
        logger.info("Email digest job scheduled (runs daily at 4:00 AM)")
    
    logger.info("LocalBot started successfully!")
    application.run_polling()


if __name__ == "__main__":
    main()
