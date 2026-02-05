"""Base handler class for Telegram bot handlers."""
from abc import ABC, abstractmethod
from telegram import Update
from telegram.ext import ContextTypes


class Handler(ABC):
    """Abstract base class for all Telegram handlers."""
    
    @abstractmethod
    async def can_handle(self, update: Update) -> bool:
        """
        Check if this handler can process the update.
        
        Args:
            update: Telegram update object
            
        Returns:
            True if handler can process this update
        """
        pass
    
    @abstractmethod
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Process the update.
        
        Args:
            update: Telegram update object
            context: Telegram context object
        """
        pass
