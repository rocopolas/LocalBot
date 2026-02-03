"""Twitter/X media download utilities using yt-dlp."""
import re
import os
import tempfile
import asyncio

def is_twitter_url(text: str) -> str | None:
    """Check if text contains a Twitter/X URL."""
    patterns = [
        r'(https?://(www\.)?twitter\.com/\w+/status/\d+)',
        r'(https?://(www\.)?x\.com/\w+/status/\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None

async def download_twitter_video(url: str) -> str:
    """
    Downloads video from a Twitter/X URL using yt-dlp.
    Returns path to downloaded file.
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp no instalado.")

    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best', # Download best quality
        'outtmpl': os.path.join(temp_dir, 'twitter_media.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        # Twitter might need cookies or user-agent
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }
    
    # Run in executor to avoid blocking asyncio loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _download_sync(url, ydl_opts))
    
    # Find file
    for f in os.listdir(temp_dir):
        if f.endswith(('.mp4', '.jpg', '.png', '.gif')):
            return os.path.join(temp_dir, f)
            
    raise RuntimeError("No se pudo descargar multimedia de Twitter.")

def _download_sync(url, opts):
    import yt_dlp
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

async def get_twitter_media_url(url: str) -> str:
    """Gets direct URL to media without downloading."""
    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: _extract_info_sync(url, ydl_opts))
        return info.get('url') or info.get('entries', [{}])[0].get('url')
        
    except Exception as e:
        return f"Error extrayendo link: {e}"

def _extract_info_sync(url, opts):
    import yt_dlp
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)
