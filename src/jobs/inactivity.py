"""Inactivity checking background job."""
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
import logging

from src.jobs.base import BackgroundJob
from src.client import OllamaClient
from utils.config_loader import get_config

logger = logging.getLogger(__name__)


class InactivityJob(BackgroundJob):
    """Job to check for inactivity and unload models."""
    
    def __init__(self, get_last_activity_func, model: str = None):
        self.get_last_activity = get_last_activity_func
        self.model = model or get_config("MODEL")
        self.inactivity_threshold_minutes = 30
    
    @property
    def name(self) -> str:
        return "inactivity_checker"
    
    @property
    def interval_seconds(self) -> int:
        return 300  # Check every 5 minutes
    
    async def run(self, context: ContextTypes.DEFAULT_TYPE):
        """Check inactivity and unload models if inactive."""
        try:
            last_activity = self.get_last_activity()
            inactive_time = datetime.now() - last_activity
            
            if inactive_time > timedelta(minutes=self.inactivity_threshold_minutes):
                client = OllamaClient()
                await client.unload_model(self.model)
                
                vision_model = get_config("VISION_MODEL")
                if vision_model:
                    await client.unload_model(vision_model)
                
                logger.info(f"Models unloaded after {inactive_time} of inactivity")
                
        except Exception as e:
            logger.error(f"Error in inactivity job: {e}")
