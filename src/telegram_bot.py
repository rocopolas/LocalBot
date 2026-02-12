"""Main Telegram bot for FemtoBot - Refactored modular version."""
import os
import re
import sys
import asyncio
import logging
import signal
import atexit
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    CommandHandler, MessageHandler, filters
)
from telegram.error import BadRequest, Conflict

# Add parent directory to path
# Add parent directory to path
_ABS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ABS_ROOT)

# Absolute project root (works from any working directory)
PROJECT_ROOT = _ABS_ROOT
from src.constants import CONFIG_DIR

# Import modular components
from src.state.chat_manager import ChatManager
from src.client import OllamaClient
from src.memory.vector_store import VectorManager
from src.handlers.commands import CommandHandlers
from src.handlers.voice import VoiceHandler
from src.handlers.audio import AudioHandler
from src.handlers.photo import PhotoHandler
from src.handlers.video import VideoHandler
from src.handlers.document import DocumentHandler
from src.jobs.events import EventsJob
from src.jobs.inactivity import InactivityJob
from src.jobs.cleanup import CleanupJob
from src.jobs.email_digest import EmailDigestJob
from src.middleware.rate_limiter import rate_limit

# Import Services
from src.services.rag_service import RagService
from src.services.media_service import MediaService
from src.services.command_service import CommandService

from utils.cron_utils import CronUtils
from utils.config_loader import get_config, get_all_config
from utils.telegram_utils import split_message, format_bot_response, prune_history, telegramify_content, send_telegramify_results
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

# Initialize Services
rag_service = RagService(vector_manager)
media_service = MediaService()

# Initialize email digest job
email_digest_job = EmailDigestJob(notification_chat_id=NOTIFICATION_CHAT_ID)

# Config values
MODEL = get_config("MODEL")
MATH_MODEL = get_config("MATH_MODEL")
COMMAND_PATTERNS = {
    'memory': re.compile(r':::memory(?!_delete)(?::)?\s*(.+?):::', re.DOTALL),
    'memory_delete': re.compile(r':::memory_delete(?::)?\s*(.+?):::', re.DOTALL),
    'cron': re.compile(r':::cron(?::)?\s*(.+?):::', re.DOTALL),
    'cron_delete': re.compile(r':::cron_delete(?::)?\s*(.+?):::'),
    'search': re.compile(r':::search(?::)?\s*(.+?):::', re.DOTALL),
    'foto': re.compile(r':::foto(?::)?\s*(.+?):::', re.IGNORECASE),
    'luz': re.compile(r':::luz(?::)?\s+(\S+)\s+(\S+)(?:\s+(\S+))?:::'),
    'camara': re.compile(r':::camara(?::)?(?:\s+\S+)?:::'),
    'matematicas': re.compile(r':::matematicas:::'),
}

# Initialize Command Service
command_service = CommandService(vector_manager, COMMAND_PATTERNS, CONFIG_DIR)

# System instructions
system_instructions = ""

# PID file handling for single instance enforcement
PID_FILE = os.path.join(PROJECT_ROOT, ".bot.pid")

def cleanup_pid():
    """Remove PID file on exit."""
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
            logger.info("PID file cleaned up")
    except Exception as e:
        logger.error(f"Error cleaning up PID file: {e}")

def kill_existing_bot():
    """Kill existing bot instance if running."""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            try:
                os.kill(old_pid, signal.SIGTERM)
                logger.info(f"Killed existing bot process (PID: {old_pid})")
                # Wait a moment for the process to die
                import time
                time.sleep(2)
            except ProcessLookupError:
                logger.info(f"No process found with PID {old_pid}")
            except PermissionError:
                logger.warning(f"Permission denied to kill process {old_pid}")
    except (ValueError, FileNotFoundError):
        pass
    except Exception as e:
        logger.error(f"Error checking/killing existing bot: {e}")

def write_pid():
    """Write current PID to file."""
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        atexit.register(cleanup_pid)
        logger.info(f"PID file created: {os.getpid()}")
    except Exception as e:
        logger.error(f"Error writing PID file: {e}")


def is_authorized(user_id: int) -> bool:
    """Check if a user is authorized."""
    if not AUTHORIZED_USERS:
        return False
    return user_id in AUTHORIZED_USERS


def load_instructions():
    """Load system instructions from file."""
    global system_instructions
    try:
        from src.constants import CONFIG_DIR
        instructions_path = os.path.join(CONFIG_DIR, get_config("INSTRUCTIONS_FILE"))
        with open(instructions_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content:
                system_instructions = content
                logger.info("Instructions loaded successfully")
    except FileNotFoundError:
        logger.warning("Instructions file not found")
    except Exception as e:
        logger.error(f"Error loading instructions: {e}")


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
    start_worker_func=None  # Will be set later
)

audio_handler = AudioHandler(is_authorized_func=is_authorized)

photo_handler = PhotoHandler(
    chat_manager=chat_manager,
    is_authorized_func=is_authorized,
    get_system_prompt_func=get_system_prompt,
    command_patterns=COMMAND_PATTERNS
)

video_handler = VideoHandler(
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
    
    try:
        while True:
            try:
                item = await asyncio.wait_for(message_queue.get(), timeout=1.0)
                update, context, needs_reply = item[0], item[1], item[2]
                text_override = item[3] if len(item) > 3 else None
            except asyncio.TimeoutError:
                return
            
            last_activity = datetime.now()
            try:
                await process_message_item(update, context, use_reply=needs_reply, text_override=text_override)
            except Exception as e:
                logger.error(f"Error processing text message in queue: {e}", exc_info=True)
                # Notify user about the error
                try:
                    chat_id = update.effective_chat.id
                    await context.bot.send_message(chat_id, f"❌ Error processing message: {e}")
                except Exception:
                    pass
            
            message_queue.task_done()
    finally:
        queue_worker_running = False


# Set start_worker function for voice handler
def start_worker_if_needed():
    global queue_worker_running
    if not queue_worker_running:
        queue_worker_running = True
        asyncio.create_task(queue_worker())

voice_handler.start_worker = start_worker_if_needed


@rate_limit(max_messages=10, window_seconds=60)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text(
            f"⛔ Access denied. Your ID: `{user_id}`",
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
        await context.bot.send_message(chat_id, "⚠️ No text detected.")
        return
    
    # Initialize chat history
    history = await chat_manager.get_history(chat_id)
    if not history:
        system_prompt = get_system_prompt()
        await chat_manager.initialize_chat(chat_id, system_prompt)
        history = await chat_manager.get_history(chat_id)
    
    placeholder_msg = None
    
    # --- REPLY UPLOAD HANDLING ---
    # Check if this is a reply to a media message with upload intent
    if update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        from src.services.upload_service import UploadService
        uploader = UploadService()
        
        if uploader.is_upload_intent(user_text):
            media_file = None
            media_type = None
            
            if replied_msg.photo:
                media_file = await context.bot.get_file(replied_msg.photo[-1].file_id)
                media_type = "image"
                ext = ".jpg"
            elif replied_msg.video:
                media_file = await context.bot.get_file(replied_msg.video.file_id)
                media_type = "video"
                ext = ".mp4"
            elif replied_msg.document: # Maybe handle docs too?
                 media_file = await context.bot.get_file(replied_msg.document.file_id)
                 media_type = "document"
                 ext = os.path.splitext(replied_msg.document.file_name)[1] or ".tmp"

            if media_file:
                 status_msg = await update.message.reply_text(f"📤 Preparing {media_type} for upload...")
                 try:
                     import tempfile
                     with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        await media_file.download_to_drive(tmp.name)
                        tmp_path = tmp.name
                     
                     await status_msg.edit_text("📤 Uploading to Catbox.moe...")
                     url = await asyncio.to_thread(uploader.upload_to_catbox, tmp_path)
                     
                     if url:
                         await status_msg.edit_text(f"✅ Upload complete:\n{url}", disable_web_page_preview=True)
                     else:
                         await status_msg.edit_text("❌ Error uploading to Catbox.")
                         
                     import os
                     from contextlib import suppress
                     with suppress(FileNotFoundError, PermissionError, OSError):
                        os.unlink(tmp_path)
                     return # Stop processing
                 except Exception as e:
                     logger.error(f"Error handling reply upload: {e}")
                     await status_msg.edit_text(f"❌ Error: {str(e)}")
                     return
    
    # --- MEDIA SERVICE HANDLING ---
    media_action = media_service.identify_action(user_text)
    if media_action:
        platform, action_type, url = media_action
        
        if platform == 'twitter':
            status_msg = await context.bot.send_message(chat_id, "🐦 Processing Twitter...")
            try:
                await status_msg.edit_text("📤 Downloading...")
                media_path, media_type = await media_service.process_twitter(url)
                
                await status_msg.edit_text("📤 Uploading...")
                with open(media_path, 'rb') as f:
                    if media_type == 'photo':
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

        elif platform == 'youtube':
            if action_type == 'download_video':
                status_msg = await context.bot.send_message(chat_id, "🎥 Starting download...")
                try:
                    await status_msg.edit_text("⬇️ Downloading video...")
                    video_path = await media_service.download_youtube(url)
                    
                    await status_msg.edit_text("📤 Uploading...")
                    with open(video_path, 'rb') as f:
                        await context.bot.send_video(chat_id, video=f)
                    import os
                    os.unlink(video_path)
                    await status_msg.delete()
                    return
                except Exception as e:
                    await status_msg.edit_text(f"❌ Error: {str(e)}")
                    return
                    
            elif action_type == 'transcribe':
                status_msg = await context.bot.send_message(chat_id, "🎙️ Analyzing video for transcription...")
                try:
                    # Perform transcription
                    transcription, video_title = await media_service.transcribe_youtube(url)
                    
                    await status_msg.edit_text(f"✅ Transcription of '_{video_title}_' complete. Analyzing...")
                    
                    # Update user text with transcription request for the LLM
                    user_text = (
                        f"Analyze this YouTube transcription of '{video_title}':\n\n"
                        f"\"\"\"\n{transcription}\n\"\"\"\n\n"
                        f"Provide a detailed summary."
                    )
                    placeholder_msg = status_msg
                except Exception as e:
                    await status_msg.edit_text(f"❌ Error: {str(e)}")
                    return

    # --- LLM + RAG ---
    
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
    crontab_str = CronUtils.get_readable_agenda()
    
    # RAG Context Retrieval via Service
    rag_context = await rag_service.get_context(user_text)

    context_message = f"{user_text} [System: Current time is {current_time}. Schedule: {crontab_str}.{rag_context}]"
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
        
        # Handle math command - switch to math model
        if COMMAND_PATTERNS['matematicas'].search(full_response):
            await placeholder_msg.edit_text("🧮 Solving math...")
            logger.info(f"Math command detected, querying {MATH_MODEL}")
            
            # Build math messages from conversation history (no system prompt, no RAG)
            math_messages = [
                msg for msg in pruned_history
                if msg.get("role") != "system"
            ]
            # Replace last user message with raw text (without RAG context)
            if math_messages and math_messages[-1].get("role") == "user":
                math_messages[-1] = {"role": "user", "content": user_text}
            else:
                math_messages.append({"role": "user", "content": user_text})
            
            full_response = ""
            async for chunk in client.stream_chat(MATH_MODEL, math_messages):
                full_response += chunk
            
            # LaTeX math is handled automatically by telegramify-markdown
            
            # Unload math model after use
            await client.unload_model(MATH_MODEL)
            logger.info(f"Math model {MATH_MODEL} unloaded")
        
        # Handle search command
        search_match = COMMAND_PATTERNS['search'].search(full_response)
        if search_match:
            search_query = search_match.group(1).strip()
            await placeholder_msg.edit_text(f"🔍 Searching: {search_query}...")
            
            search_results = await BraveSearch.search(search_query)
            await chat_manager.append_message(chat_id, {"role": "assistant", "content": full_response})
            await chat_manager.append_message(chat_id, {
                "role": "user",
                "content": f"[Search results for '{search_query}']:\n{search_results}"
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
            # Clean text first (math, commands, etc.)
            cleaned_text = format_bot_response(full_response)
            
            if not cleaned_text:
                await placeholder_msg.delete()
            else:
                # Use telegramify to format and split (handles TEXT, PHOTO, FILE)
                chunks = await telegramify_content(cleaned_text)
                await send_telegramify_results(context, chat_id, chunks, placeholder_msg)
            
            await chat_manager.append_message(chat_id, {"role": "assistant", "content": full_response})
        
        # Process commands via Service
        commands_processed = await command_service.process_commands(full_response, chat_id, context)
        
        # Check if response is empty after formatting but commands were processed
        response_empty = not formatted if 'formatted' in locals() else not cleaned_text
        
        # If response is empty after formatting but commands were processed, show confirmation
        if response_empty and commands_processed:
            try:
                await placeholder_msg.edit_text("✅ Commands executed successfully.")
            except BadRequest:
                await context.bot.send_message(chat_id, "✅ Commands executed successfully.")
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        try:
            if placeholder_msg:
                await placeholder_msg.edit_text(f"❌ Error: {str(e)}")
            else:
                await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")
        except Exception:
            # If edit fails (e.g. message deleted), send new message
            await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for unhandled exceptions."""
    error = context.error
    
    # Handle Conflict errors (another bot instance running)
    if isinstance(error, Conflict):
        logger.warning("Conflict detected - another bot instance is running. Retrying...")
        # Don't propagate the error, let the bot retry
        return
    
    logger.error(f"Unhandled exception: {error}", exc_info=error)
    # Try to notify the user
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        try:
            await context.bot.send_message(
                update.effective_chat.id,
                f"❌ Unexpected error: {error}"
            )
        except Exception:
            pass


def main():
    """Main entry point."""
    # Kill any existing bot instance and write PID
    kill_existing_bot()
    write_pid()
    
    # Load initial data
    load_instructions()
    
    # Build application
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_error_handler(error_handler)
    
    # Command handlers
    application.add_handler(CommandHandler("start", command_handlers.start))
    application.add_handler(CommandHandler("new", command_handlers.new_conversation))
    application.add_handler(CommandHandler("status", command_handlers.status))
    application.add_handler(CommandHandler("unload", command_handlers.unload_models))
    application.add_handler(CommandHandler("restart", command_handlers.restart_bot))
    application.add_handler(CommandHandler("stop", command_handlers.stop_bot))
    application.add_handler(CommandHandler("digest", command_handlers.email_digest))
    application.add_handler(CommandHandler("deep", command_handlers.deep_research))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.VOICE, voice_handler.handle))
    application.add_handler(MessageHandler(filters.AUDIO, audio_handler.handle))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler.handle))
    application.add_handler(MessageHandler(filters.VIDEO, video_handler.handle))
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
            first=1,
            name=events_job.name
        )
    
    inactivity_job = InactivityJob(
        get_last_activity_func=lambda: last_activity,
        model=MODEL
    )
    application.job_queue.run_repeating(
        inactivity_job.run,
        interval=inactivity_job.interval_seconds,
        first=300,
        name=inactivity_job.name
    )
    
    cleanup_job = CleanupJob(chat_manager=chat_manager)
    application.job_queue.run_repeating(
        cleanup_job.run,
        interval=cleanup_job.interval_seconds,
        first=3600,
        name=cleanup_job.name
    )
    
    # Email digest job - runs daily at 4:00 AM
    if NOTIFICATION_CHAT_ID:
        application.job_queue.run_repeating(
            email_digest_job.run,
            interval=email_digest_job.interval_seconds,
            first=60,
            name=email_digest_job.name
        )
        logger.info("Email digest job scheduled (runs daily at 4:00 AM)")
    
    logger.info("FemtoBot started successfully!")
    
    # Run with conflict retry logic
    max_retries = 10
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            application.run_polling()
            break  # Normal exit
        except Conflict as e:
            if attempt < max_retries - 1:
                logger.warning(f"Conflict on attempt {attempt + 1}, retrying in {retry_delay}s...")
                import time
                time.sleep(retry_delay)
            else:
                logger.error("Max retries reached, could not start bot")
                raise


if __name__ == "__main__":
    main()
