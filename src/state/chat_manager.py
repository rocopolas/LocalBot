"""Thread-safe chat state manager for FemtoBot."""
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ChatManager:
    """
    Manages chat histories with thread-safe operations.
    
    Features:
    - Thread-safe read/write operations per chat
    - Automatic cleanup of inactive chats
    - Lock management per chat ID
    """
    
    def __init__(self, max_inactive_hours: int = 24):
        """
        Initialize ChatManager.
        
        Args:
            max_inactive_hours: Hours before considering a chat inactive
        """
        self._histories: Dict[int, List[Dict[str, Any]]] = {}
        self._locks: Dict[int, asyncio.Lock] = {}
        self._last_activity: Dict[int, datetime] = {}
        self._max_inactive_hours = max_inactive_hours
        self._global_lock = asyncio.Lock()
        logger.info(f"ChatManager initialized (cleanup after {max_inactive_hours}h)")
    
    async def get_history(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get chat history for a specific chat.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            Copy of chat history list
        """
        async with self._get_lock(chat_id):
            return self._histories.get(chat_id, []).copy()
    
    async def set_history(self, chat_id: int, history: List[Dict[str, Any]]) -> None:
        """
        Set chat history for a specific chat.
        
        Args:
            chat_id: Telegram chat ID
            history: List of message dictionaries
        """
        async with self._get_lock(chat_id):
            self._histories[chat_id] = history
            self._last_activity[chat_id] = datetime.now()
            logger.debug(f"History set for chat {chat_id} ({len(history)} messages)")
    
    async def append_message(self, chat_id: int, message: Dict[str, Any]) -> None:
        """
        Append a message to chat history.
        
        Args:
            chat_id: Telegram chat ID
            message: Message dictionary with 'role' and 'content'
        """
        async with self._get_lock(chat_id):
            if chat_id not in self._histories:
                self._histories[chat_id] = []
            self._histories[chat_id].append(message)
            self._last_activity[chat_id] = datetime.now()
            logger.debug(f"Message appended to chat {chat_id}")
    
    async def clear_history(self, chat_id: int) -> None:
        """
        Clear chat history for a specific chat.
        
        Args:
            chat_id: Telegram chat ID
        """
        async with self._get_lock(chat_id):
            self._histories[chat_id] = []
            self._last_activity[chat_id] = datetime.now()
            logger.info(f"History cleared for chat {chat_id}")
    
    async def initialize_chat(self, chat_id: int, system_prompt: str = "") -> None:
        """
        Initialize a new chat with optional system prompt.
        
        Args:
            chat_id: Telegram chat ID
            system_prompt: Optional system prompt to add
        """
        async with self._get_lock(chat_id):
            self._histories[chat_id] = []
            if system_prompt:
                self._histories[chat_id].append({
                    "role": "system",
                    "content": system_prompt
                })
            self._last_activity[chat_id] = datetime.now()
            logger.info(f"Chat {chat_id} initialized")
    
    async def cleanup_old_histories(self) -> int:
        """
        Remove histories for inactive chats.
        
        Returns:
            Number of chats removed
        """
        cutoff = datetime.now() - timedelta(hours=self._max_inactive_hours)
        removed_count = 0
        
        async with self._global_lock:
            to_remove = [
                chat_id for chat_id, last_time in self._last_activity.items()
                if last_time < cutoff
            ]
            
            for chat_id in to_remove:
                if chat_id in self._histories:
                    del self._histories[chat_id]
                if chat_id in self._last_activity:
                    del self._last_activity[chat_id]
                if chat_id in self._locks:
                    del self._locks[chat_id]
                removed_count += 1
                logger.info(f"Cleaned up inactive chat {chat_id}")
        
        if removed_count > 0:
            logger.info(f"Total chats cleaned up: {removed_count}")
        
        return removed_count
    
    async def get_active_chats(self) -> List[int]:
        """
        Get list of all active chat IDs.
        
        Returns:
            List of chat IDs
        """
        async with self._global_lock:
            return list(self._histories.keys())
    
    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        """Get or create lock for specific chat."""
        if chat_id not in self._locks:
            self._locks[chat_id] = asyncio.Lock()
        return self._locks[chat_id]
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about managed chats.
        
        Returns:
            Dictionary with statistics
        """
        async with self._global_lock:
            total_chats = len(self._histories)
            total_messages = sum(len(h) for h in self._histories.values())
            
            return {
                "total_chats": total_chats,
                "total_messages": total_messages,
                "avg_messages_per_chat": total_messages / total_chats if total_chats > 0 else 0,
                "max_inactive_hours": self._max_inactive_hours
            }
