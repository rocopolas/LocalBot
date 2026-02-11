"""Audio transcription utilities using faster-whisper."""
import os
import asyncio
from pathlib import Path
from utils.config_loader import get_config
import gc
import logging

logger = logging.getLogger(__name__)

# Lazy load whisper to avoid import errors if not installed
_model = None
_model_large = None


def get_whisper_model():
    """Lazy load faster-whisper model for voice messages."""
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
            model_name = get_config("WHISPER_MODEL_VOICE")
            _model = WhisperModel(model_name, device="cpu", compute_type="int8")
            logger.info(f"Loaded whisper model: {model_name}")
        except ImportError:
            logger.error("faster-whisper not installed")
            return None
    return _model


def get_whisper_model_large():
    """Lazy load faster-whisper model for external audio."""
    global _model_large
    if _model_large is None:
        try:
            from faster_whisper import WhisperModel
            model_name = get_config("WHISPER_MODEL_EXTERNAL")
            _model_large = WhisperModel(model_name, device="cpu", compute_type="int8")
            logger.info(f"Loaded large whisper model: {model_name}")
        except ImportError:
            logger.error("faster-whisper not installed")
            return None
    return _model_large


def unload_whisper_model():
    """Unload the voice whisper model from memory."""
    global _model
    if _model is not None:
        del _model
        _model = None
        gc.collect()
        logger.debug("Unloaded whisper model")


def unload_whisper_model_large():
    """Unload the large whisper model from memory."""
    global _model_large
    if _model_large is not None:
        del _model_large
        _model_large = None
        gc.collect()
        logger.debug("Unloaded large whisper model")


def _transcribe_sync(model, audio_path: str, language: str):
    """Synchronous transcription helper."""
    segments, info = model.transcribe(
        audio_path, 
        language=language,
        beam_size=1,
        best_of=1,
        temperature=0,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    
    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())
    
    return " ".join(text_parts).strip()


async def transcribe_audio(audio_path: str) -> str:
    """
    Transcribes an audio file using faster-whisper.
    Runs the blocking transcription in a thread.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Transcription text or error message
    """
    model = get_whisper_model()
    
    if model is None:
        return "[Error: faster-whisper not installed. Run: pip install faster-whisper]"
    
    try:
        language = get_config("WHISPER_LANGUAGE")
        
        # Run blocking operation in thread
        transcription = await asyncio.to_thread(
            _transcribe_sync, model, audio_path, language
        )
        
        transcription = " ".join(transcription.split())
        
        if transcription:
            logger.info(f"Transcription completed ({len(transcription)} chars)")
            return transcription
        else:
            return "[No audio content detected]"
        
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return f"[Transcription error: {str(e)}]"
    finally:
        unload_whisper_model()


async def transcribe_audio_large(audio_path: str) -> str:
    """
    Transcribes an audio file using the larger whisper model.
    Runs the blocking transcription in a thread.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Transcription text or error message
    """
    model = get_whisper_model_large()
    
    if model is None:
        return "[Error: faster-whisper not installed]"
    
    try:
        language = get_config("WHISPER_LANGUAGE")
        
        # Run blocking operation in thread
        transcription = await asyncio.to_thread(
            _transcribe_sync, model, audio_path, language
        )
        
        transcription = " ".join(transcription.split())
        
        if transcription:
            logger.info(f"Large model transcription completed ({len(transcription)} chars)")
            return transcription
        else:
            return "[No audio content detected]"
        
    except Exception as e:
        logger.error(f"Large transcription error: {e}")
        return f"[Transcription error: {str(e)}]"
    finally:
        unload_whisper_model_large()


def is_whisper_available() -> bool:
    """Check if faster-whisper is available."""
    try:
        from faster_whisper import WhisperModel
        return True
    except ImportError:
        return False
