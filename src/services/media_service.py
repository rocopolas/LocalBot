"""
Media Service for handling Twitter and YouTube downloads.
"""
import os
import logging
from typing import Optional, Tuple, Union

# Import utils
from utils.youtube_utils import is_youtube_url, download_youtube_video, download_youtube_audio, get_video_title
from utils.twitter_utils import is_twitter_url, download_twitter_video
from utils.audio_utils import transcribe_audio

logger = logging.getLogger(__name__)

class MediaService:
    def __init__(self):
        pass

    def identify_action(self, text: str) -> Optional[Tuple[str, str, str]]:
        """
        Identify if text contains a supported media URL and what action to take.
        Returns: (platform, action_type, url)
        platform: 'twitter' or 'youtube'
        action_type: 'download', 'download_video', 'transcribe'
        url: The extracted URL
        """
        # Twitter
        twitter_url = is_twitter_url(text)
        if twitter_url:
            keywords = ["descarga", "baja", "video", "bajar", "download"]
            if any(k in text.lower() for k in keywords):
                return 'twitter', 'download', twitter_url
        
        # YouTube
        youtube_url = is_youtube_url(text)
        if youtube_url:
            keywords = ["descarga", "baja", "video", "bajar", "download"]
            if any(k in text.lower() for k in keywords):
                return 'youtube', 'download_video', youtube_url
            else:
                return 'youtube', 'transcribe', youtube_url
                
        return None

    # ... (process_twitter, download_youtube, transcribe_youtube methods)
    
    async def process_twitter(self, url: str) -> Tuple[str, str]:
        """Process Twitter URL. Returns (media_path, media_type)"""
        try:
            logger.info(f"Processing Twitter URL: {url}")
            media_path = await download_twitter_video(url)
            if media_path.endswith(('.jpg', '.png', '.jpeg')):
                return media_path, 'photo'
            else:
                return media_path, 'video'
        except Exception as e:
            logger.error(f"Error processing Twitter URL: {e}")
            raise e

    async def download_youtube(self, url: str) -> str:
        """Download YouTube video. Returns video_path."""
        try:
            logger.info(f"Downloading YouTube video: {url}")
            video_path = await download_youtube_video(url)
            return video_path
        except Exception as e:
            logger.error(f"Error downloading YouTube video: {e}")
            raise e

    async def transcribe_youtube(self, url: str) -> Tuple[str, str]:
        """Transcribe YouTube video. Returns (transcription_text, video_title)"""
        try:
            logger.info(f"Transcribing YouTube video: {url}")
            video_title = get_video_title(url)
            audio_path = await download_youtube_audio(url)
            
            transcription = await transcribe_audio(audio_path)
            
            if os.path.exists(audio_path):
                os.unlink(audio_path)
                
            return transcription, video_title
        except Exception as e:
            logger.error(f"Error transcribing YouTube video: {e}")
            raise e

    def is_media_url(self, text: str) -> bool:
        return bool(is_twitter_url(text) or is_youtube_url(text))
