"""Events checking background job."""
import os
from datetime import datetime
from telegram.ext import ContextTypes
import logging

from src.jobs.base import BackgroundJob
from src.constants import PROJECT_ROOT
from utils.config_loader import get_config

logger = logging.getLogger(__name__)


class EventsJob(BackgroundJob):
    """Job to check events file and send notifications."""
    
    def __init__(self, notification_chat_id: int = None, authorized_users: list = None):
        self.notification_chat_id = notification_chat_id
        self.authorized_users = authorized_users or []
        self.events_file = os.path.join(PROJECT_ROOT, get_config("EVENTS_FILE"))
    
    @property
    def name(self) -> str:
        return "events_checker"
    
    @property
    def interval_seconds(self) -> int:
        return 2  # Check every 2 seconds
    
    async def run(self, context: ContextTypes.DEFAULT_TYPE):
        """Check events file and send notifications."""
        # Determine target chats
        target_chats = []
        if self.notification_chat_id:
            target_chats.append(self.notification_chat_id)
        
        if not target_chats:
            return
        
        try:
            if os.path.exists(self.events_file) and os.path.getsize(self.events_file) > 0:
                with open(self.events_file, 'r+', encoding='utf-8') as f:
                    content = f.read()
                    if content.strip():
                        lines = content.strip().split('\n')
                        timestamp = datetime.now().strftime("%H:%M")
                        
                        sent_to = set()
                        for chat_id in target_chats:
                            if chat_id in sent_to:
                                continue
                            
                            try:
                                for line in lines:
                                    await context.bot.send_message(
                                        chat_id,
                                        f"🔔 *{timestamp}*\n{line}",
                                        parse_mode="Markdown"
                                    )
                                sent_to.add(chat_id)
                            except Exception as e:
                                logger.error(f"Error sending event to {chat_id}: {e}")
                        
                        # Clear events file
                        f.seek(0)
                        f.truncate()
                        
        except Exception as e:
            logger.error(f"Error in events job: {e}")
