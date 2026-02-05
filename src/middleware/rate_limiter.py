"""Rate limiting middleware for Telegram bot."""
import time
import asyncio
from functools import wraps
from typing import Dict, List, Optional
from telegram import Update
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter for Telegram bot messages.
    
    Tracks message history per user and enforces limits.
    """
    
    def __init__(
        self,
        max_messages: int = 10,
        window_seconds: int = 60,
        burst_size: int = 3
    ):
        """
        Initialize rate limiter.
        
        Args:
            max_messages: Maximum messages allowed in window
            window_seconds: Time window in seconds
            burst_size: Initial burst allowance
        """
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.burst_size = burst_size
        self._user_history: Dict[int, List[float]] = {}
        self._lock = asyncio.Lock()
        logger.info(
            f"RateLimiter initialized ({max_messages} msgs/{window_seconds}s, "
            f"burst: {burst_size})"
        )
    
    async def check_rate_limit(self, user_id: int) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        async with self._lock:
            now = time.time()
            
            if user_id not in self._user_history:
                self._user_history[user_id] = []
            
            # Clean old messages outside window
            cutoff = now - self.window_seconds
            self._user_history[user_id] = [
                t for t in self._user_history[user_id]
                if t > cutoff
            ]
            
            # Check if under limit
            if len(self._user_history[user_id]) >= self.max_messages:
                oldest_msg = self._user_history[user_id][0]
                retry_after = int(self.window_seconds - (now - oldest_msg))
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return False, max(1, retry_after)
            
            # Record this message
            self._user_history[user_id].append(now)
            
            # Log remaining quota for debugging
            remaining = self.max_messages - len(self._user_history[user_id])
            logger.debug(f"User {user_id} has {remaining} messages remaining")
            
            return True, 0
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """
        Get rate limiting stats for a user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with stats
        """
        async with self._lock:
            now = time.time()
            history = self._user_history.get(user_id, [])
            
            # Count messages in current window
            cutoff = now - self.window_seconds
            recent_msgs = [t for t in history if t > cutoff]
            
            return {
                "messages_in_window": len(recent_msgs),
                "max_allowed": self.max_messages,
                "remaining": self.max_messages - len(recent_msgs),
                "window_seconds": self.window_seconds
            }
    
    async def reset_user(self, user_id: int) -> None:
        """
        Reset rate limit for a specific user.
        
        Args:
            user_id: Telegram user ID
        """
        async with self._lock:
            if user_id in self._user_history:
                del self._user_history[user_id]
                logger.info(f"Rate limit reset for user {user_id}")


def rate_limit(
    max_messages: int = 10,
    window_seconds: int = 60,
    exempt_users: Optional[List[int]] = None
):
    """
    Decorator to apply rate limiting to handlers.
    
    Args:
        max_messages: Maximum messages allowed in window
        window_seconds: Time window in seconds
        exempt_users: List of user IDs exempt from rate limiting
        
    Example:
        @rate_limit(max_messages=5, window_seconds=60)
        async def handle_message(update, context):
            # Handler code
            pass
    """
    limiter = RateLimiter(max_messages, window_seconds)
    exempt = set(exempt_users or [])
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Detect if this is a method (first arg is self) or a function
            # For methods: args = (self, update, context, ...)
            # For functions: args = (update, context, ...)
            
            if len(args) >= 1 and hasattr(args[0], 'effective_user'):
                # Function style: first arg is update
                update = args[0]
                actual_args = args
            elif len(args) >= 2 and hasattr(args[1], 'effective_user'):
                # Method style: second arg is update
                update = args[1]
                actual_args = args
            else:
                # Fallback: try to find update in args
                for arg in args:
                    if hasattr(arg, 'effective_user'):
                        update = arg
                        actual_args = args
                        break
                else:
                    # Can't find update, just call the function
                    return await func(*args, **kwargs)
            
            user_id = update.effective_user.id
            
            # Skip rate limiting for exempt users
            if user_id in exempt:
                return await func(*args, **kwargs)
            
            allowed, retry_after = await limiter.check_rate_limit(user_id)
            
            if not allowed:
                await update.message.reply_text(
                    f"⏳ *Rate limit excedido*\n\n"
                    f"Has enviado demasiados mensajes. "
                    f"Espera `{retry_after}` segundos antes de continuar.",
                    parse_mode="Markdown"
                )
                logger.warning(
                    f"Rate limit blocked user {user_id} "
                    f"(retry after {retry_after}s)"
                )
                return
            
            return await func(*args, **kwargs)
        
        # Attach limiter for external access
        wrapper._rate_limiter = limiter
        return wrapper
    
    return decorator
