"""Cleanup background job."""
from telegram.ext import ContextTypes
import logging

from src.jobs.base import BackgroundJob
from utils.cron_utils import CronUtils
from src.state.chat_manager import ChatManager

logger = logging.getLogger(__name__)


class CleanupJob(BackgroundJob):
    """Job to cleanup old crons and chat histories."""
    
    def __init__(self, chat_manager: ChatManager = None):
        self.chat_manager = chat_manager
    
    @property
    def name(self) -> str:
        return "cleanup"
    
    @property
    def interval_seconds(self) -> int:
        return 3600  # Run every hour
    
    async def run(self, context: ContextTypes.DEFAULT_TYPE):
        """Cleanup old crons and inactive chats."""
        try:
            # Cleanup old cron jobs
            removed = CronUtils.cleanup_old_jobs()
            if removed > 0:
                logger.info(f"Cleaned up {removed} old cron jobs")
            
            # Cleanup old chat histories if chat_manager available
            if self.chat_manager:
                removed_chats = await self.chat_manager.cleanup_old_histories()
                if removed_chats > 0:
                    logger.info(f"Cleaned up {removed_chats} inactive chats")
                    
        except Exception as e:
            logger.error(f"Error in cleanup job: {e}")
