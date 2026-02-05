"""Ollama API client for LocalBot with streaming support."""
import httpx
import json
import logging
from typing import AsyncGenerator, Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Type aliases for better readability
Message = Dict[str, Any]
Messages = List[Message]


class OllamaClient:
    """
    Client for interacting with Ollama API.
    
    Provides streaming chat, image description, and model management.
    """
    
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        """
        Initialize Ollama client.
        
        Args:
            base_url: Base URL for Ollama API (default: http://localhost:11434)
        """
        self.base_url = base_url
        logger.debug(f"OllamaClient initialized with base_url: {base_url}")

    async def stream_chat(
        self, 
        model: str, 
        messages: Messages
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat responses from Ollama.
        
        Args:
            model: Name of the model to use
            messages: List of message dictionaries with 'role' and 'content'
            
        Yields:
            Text chunks from the model response
            
        Example:
            ```python
            messages = [
                {"role": "user", "content": "Hello!"}
            ]
            async for chunk in client.stream_chat("llama3.1", messages):
                print(chunk, end="")
            ```
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True 
        }
        
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST", 
                    url, 
                    json=payload, 
                    timeout=None
                ) as response:
                    if response.status_code != 200:
                        error_detail = ""
                        try:
                            async for chunk in response.aiter_text():
                                error_detail += chunk
                        except Exception:
                            pass
                        error_msg = (
                            f"Error: Ollama returned status {response.status_code}. "
                            f"Details: {error_detail}"
                        )
                        logger.error(error_msg)
                        yield error_msg
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                content = data["message"].get("content", "")
                                if content:
                                    yield content
                            if data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse JSON line: {line[:100]}...")
                            continue
                            
            except httpx.ConnectError as e:
                error_msg = (
                    "Error: No se pudo conectar a Ollama. "
                    "Asegúrate de que 'ollama serve' esté corriendo."
                )
                logger.error(f"Connection error to Ollama: {e}")
                yield error_msg
                
            except httpx.RemoteProtocolError as e:
                error_msg = (
                    "Error: La conexión con Ollama se cerró inesperadamente. "
                    "(Posible crash del modelo o timeout)."
                )
                logger.error(f"Remote protocol error: {e}")
                yield error_msg
                
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                logger.error(f"Unexpected error in stream_chat: {e}", exc_info=True)
                yield error_msg

    async def unload_model(self, model: str) -> bool:
        """
        Unload a model from Ollama memory.
        
        Args:
            model: Name of the model to unload
            
        Returns:
            True if successful, False otherwise
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "keep_alive": 0
        }
        try:
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload)
                logger.info(f"Successfully unloaded model: {model}")
                return True
        except Exception as e:
            logger.warning(f"Failed to unload model {model}: {e}")
            return False

    async def describe_image(
        self, 
        model: str, 
        image_base64: str, 
        prompt: str = "Describe esta imagen en detalle."
    ) -> str:
        """
        Use a vision model to describe an image.
        
        Args:
            model: Name of the vision model to use
            image_base64: Base64-encoded image data
            prompt: Prompt to guide the image description
            
        Returns:
            Description of the image or error message
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_base64]
                }
            ],
            "stream": False
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=120.0)
                if response.status_code == 200:
                    data = response.json()
                    description = data.get("message", {}).get("content", "[Sin descripción]")
                    logger.debug(f"Image described successfully with model {model}")
                    return description
                else:
                    error_msg = f"[Error del modelo de visión: {response.status_code}]"
                    logger.error(f"Vision model error: {error_msg}")
                    return error_msg
                    
        except httpx.ConnectError as e:
            logger.error(f"Connection error in describe_image: {e}")
            return "[Error: No se pudo conectar a Ollama]"
            
        except httpx.TimeoutException as e:
            logger.error(f"Timeout in describe_image: {e}")
            return "[Error: Timeout al procesar la imagen]"
            
        except Exception as e:
            logger.error(f"Unexpected error in describe_image: {e}", exc_info=True)
            return f"[Error: {str(e)}]"
