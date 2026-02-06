"""Pytest configuration and fixtures for LocalBot tests."""
import sys
import os

# Add project root to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime

# Set event loop policy for tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_update():
    """Mock Telegram update object."""
    update = Mock()
    update.effective_user.id = 123456
    update.effective_user.username = "testuser"
    update.effective_chat.id = 123456
    update.message.message_id = 1
    update.message.text = "Test message"
    update.message.caption = None
    update.message.voice = None
    update.message.audio = None
    update.message.photo = None
    update.message.document = None
    return update


@pytest.fixture
def mock_context():
    """Mock Telegram context object."""
    context = Mock()
    context.bot.send_message = AsyncMock()
    context.bot.get_file = AsyncMock()
    context.bot.send_chat_action = AsyncMock()
    return context


@pytest.fixture
def mock_chat_manager():
    """Mock chat manager."""
    from src.state.chat_manager import ChatManager
    
    manager = ChatManager()
    # Pre-populate with test data
    asyncio.run(manager.initialize_chat(123456, "System prompt"))
    return manager


@pytest.fixture
def sample_config():
    """Sample configuration for tests."""
    return {
        "MODEL": "llama3.1:8b",
        "CONTEXT_LIMIT": 32000,
        "VISION_MODEL": "llava",
        "WHISPER_MODEL_VOICE": "base",
        "WHISPER_MODEL_EXTERNAL": "large",
        "INSTRUCTIONS_FILE": "data/instructions.md",
        "MEMORY_FILE": "data/memory.md",
        "EVENTS_FILE": "data/events.txt",
    }


@pytest.fixture
def sample_authorized_users():
    """Sample authorized users list."""
    return [123456, 789012]
