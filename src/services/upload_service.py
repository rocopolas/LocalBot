"""
Upload Service for handling file uploads to external services like Catbox.moe.
Includes fallback to Litterbox when Catbox is unavailable.
"""
import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CATBOX_API = 'https://catbox.moe/user/api.php'
LITTERBOX_API = 'https://litterbox.catbox.moe/resources/internals/api.php'


class UploadService:
    def __init__(self, userhash: Optional[str] = None):
        self.userhash = userhash

    def _upload_to_catbox_direct(self, file_path: str) -> tuple[Optional[str], Optional[str]]:
        """
        Direct upload to Catbox.moe API.
        Returns (url, error_message) tuple.
        """
        data = {'reqtype': 'fileupload'}
        if self.userhash:
            data['userhash'] = self.userhash
            
        with open(file_path, 'rb') as f:
            files = {'fileToUpload': (os.path.basename(file_path), f)}
            response = httpx.post(CATBOX_API, data=data, files=files, timeout=120)
        
        if response.status_code == 200:
            url = response.text.strip()
            if url and url.startswith('https://'):
                return url, None
            else:
                return None, f"Invalid response: {response.text[:100]}"
        elif response.status_code == 412:
            return None, "Catbox uploads paused"
        else:
            return None, f"HTTP {response.status_code}: {response.text[:100]}"

    def _upload_to_litterbox(self, file_path: str, expire_time: str = "72h") -> tuple[Optional[str], Optional[str]]:
        """
        Upload to Litterbox (temporary file hosting).
        expire_time options: "1h", "12h", "24h", "72h"
        Returns (url, error_message) tuple.
        """
        data = {
            'reqtype': 'fileupload',
            'time': expire_time
        }
        
        with open(file_path, 'rb') as f:
            files = {'fileToUpload': (os.path.basename(file_path), f)}
            response = httpx.post(LITTERBOX_API, data=data, files=files, timeout=120)
        
        if response.status_code == 200:
            url = response.text.strip()
            if url and url.startswith('https://'):
                return url, None
            else:
                return None, f"Invalid response: {response.text[:100]}"
        else:
            return None, f"HTTP {response.status_code}: {response.text[:100]}"

    def upload_to_catbox(self, file_path: str, use_fallback: bool = True) -> Optional[str]:
        """
        Uploads a file to Catbox.moe and returns the URL.
        Falls back to Litterbox if Catbox is unavailable.
        
        Args:
            file_path: Path to the file to upload
            use_fallback: If True, try Litterbox when Catbox fails
            
        Returns:
            URL string on success, None on failure
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None

        # Try Catbox first
        logger.info(f"Uploading to Catbox: {file_path}")
        url, error = self._upload_to_catbox_direct(file_path)
        
        if url:
            logger.info(f"Catbox upload successful: {url}")
            return url
        
        logger.warning(f"Catbox upload failed: {error}")
        
        # Fallback to Litterbox
        if use_fallback:
            logger.info(f"Trying Litterbox fallback for: {file_path}")
            url, error = self._upload_to_litterbox(file_path)
            
            if url:
                logger.info(f"Litterbox upload successful (expires in 72h): {url}")
                return url
            else:
                logger.error(f"Litterbox upload also failed: {error}")
        
        return None

    def upload_to_litterbox(self, file_path: str, expire_time: str = "72h") -> Optional[str]:
        """
        Uploads a file directly to Litterbox (temporary hosting).
        
        Args:
            file_path: Path to the file to upload
            expire_time: Expiration time ("1h", "12h", "24h", "72h")
            
        Returns:
            URL string on success, None on failure
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None
            
        url, error = self._upload_to_litterbox(file_path, expire_time)
        
        if url:
            logger.info(f"Litterbox upload successful: {url}")
            return url
        else:
            logger.error(f"Litterbox upload failed: {error}")
            return None

    def is_upload_intent(self, text: str) -> bool:
        """Check if text indicates an intent to upload."""
        if not text:
            return False
        
        text_lower = text.lower()
        triggers = ["catbox", "sube", "upload", "carga", "link", "url", "litterbox"]
        
        return any(t in text_lower for t in triggers)
