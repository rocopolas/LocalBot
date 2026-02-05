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
        return OllamaClient(base_url="http://localhost:11434")
    
    @pytest.mark.asyncio
    async def test_stream_chat_success(self, client):
        """Test successful streaming chat."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.aiter_lines = MagicMock(return_value=[
            json.dumps({"message": {"content": "Hello"}, "done": False}),
            json.dumps({"message": {"content": " world"}, "done": True}),
        ])
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.stream.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            
            chunks = []
            async for chunk in client.stream_chat("test-model", [{"role": "user", "content": "Hi"}]):
                chunks.append(chunk)
            
            assert "Hello" in "".join(chunks)
    
    @pytest.mark.asyncio
    async def test_stream_chat_connection_error(self, client):
        """Test handling of connection error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.stream.side_effect = Exception("Connection refused")
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            
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
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            
            result = await client.describe_image("vision-model", "base64data", "Describe this")
            assert result == "A cat"
    
    @pytest.mark.asyncio
    async def test_unload_model(self, client):
        """Test model unloading."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = MagicMock()
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            
            result = await client.unload_model("test-model")
            assert result == True
