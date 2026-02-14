"""Unit tests for client module (Ollama client)."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from src.client import OllamaClient


class TestOllamaClient:
    """Test suite for Ollama client."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        # Reset shared client to ensure mocks work
        OllamaClient._shared_client = None
        return OllamaClient(base_url="http://localhost:11434")
    
    @pytest.mark.asyncio
    async def test_stream_chat_success(self, client):
        """Test successful streaming chat."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        class AsyncIterator:
            def __init__(self, data):
                self.data = iter(data)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self.data)
                except StopIteration:
                    raise StopAsyncIteration

        mock_response.aiter_lines = MagicMock(return_value=AsyncIterator([
            json.dumps({"message": {"content": "Hello"}, "done": False}),
            json.dumps({"message": {"content": " world"}, "done": True}),
        ]))
        
        # Create async context manager mock for stream
        stream_context = AsyncMock()
        stream_context.__aenter__ = AsyncMock(return_value=mock_response)
        stream_context.__aexit__ = AsyncMock(return_value=None)
        
        with patch("httpx.AsyncClient") as mock_client_cls:
            # Configure the client instance directly
            mock_instance = mock_client_cls.return_value
            mock_instance.stream = MagicMock(return_value=stream_context)
            
            chunks = []
            async for chunk in client.stream_chat("test-model", [{"role": "user", "content": "Hi"}]):
                chunks.append(chunk)
            
            assert "Hello" in "".join(chunks)
    
    @pytest.mark.asyncio
    async def test_stream_chat_connection_error(self, client):
        """Test handling of connection error."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            # Configure stream to raise exception
            mock_instance.stream = MagicMock(side_effect=Exception("Connection refused"))
            
            chunks = []
            async for chunk in client.stream_chat("test-model", []):
                chunks.append(chunk)
            
            assert any("Error" in chunk for chunk in chunks)
    
    @pytest.mark.asyncio
    async def test_describe_image(self, client):
        """Test image description."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": {"content": "A cat"}}
        
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            # Configure post as an async method
            mock_instance.post = AsyncMock(return_value=mock_response)
            
            result = await client.describe_image("vision-model", "base64data", "Describe this")
            assert result == "A cat"
    
    @pytest.mark.asyncio
    async def test_unload_model(self, client):
        """Test model unloading."""
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            # Configure post as an async method
            mock_instance.post = AsyncMock(return_value=MagicMock())
            
            result = await client.unload_model("test-model")
            assert result == True
