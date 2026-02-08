# LocalBot Architecture

## Overview

LocalBot is a privacy-focused AI assistant that runs locally using Ollama LLM. It provides two interfaces:
- **Telegram Bot**: Primary interface for mobile/desktop messaging
- **TUI (Terminal User Interface)**: Desktop terminal interface using Textual

## System Architecture

```
┌─────────────────────────────────────────────┐
│         User Interfaces                     │
│  ┌──────────────┐    ┌─────────────────┐   │
│  │   Telegram   │    │   TUI (Textual) │   │
│  │    Bot       │    │   (Terminal)    │   │
│  └──────┬───────┘    └────────┬────────┘   │
└─────────┼─────────────────────┼─────────────┘
          │                     │
          └──────────┬──────────┘
                     │
┌────────────────────┴────────────────────────┐
│          Message Processing Layer           │
│  - Queue-based sequential processing        │
│  - Command parsing (:::command:::)          │
│  - Media handling (voice, photo, docs)      │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────┴────────────────────────┐
│          LLM Integration (Ollama)           │
│  - Streaming chat API                       │
│  - Vision model for image analysis          │
│  - Context management with pruning          │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────┴────────────────────────┐
│           Utility Services                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐   │
│  │ Whisper │ │  Brave  │ │  YouTube    │   │
│  │(Speech) │ │ Search  │ │  Download   │   │
│  └─────────┘ └─────────┘ └─────────────┘   │
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐   │
│  │  WIZ    │ │  Cron   │ │  Gmail      │   │
│  │ Lights  │ │ Jobs    │ │  IMAP       │   │
│  └─────────┘ └─────────┘ └─────────────┘   │
└─────────────────────────────────────────────┘
```

## Project Structure

```
LocalBot/
├── src/                        # Main source code
│   ├── __init__.py
│   ├── constants.py           # Global constants
│   ├── telegram_bot.py        # Main bot entry point
│   ├── client.py              # Ollama API client
│   ├── tui.py                 # Terminal UI
│   ├── main.py                # TUI entry point
│   ├── services/              # Business Logic Services
│   │   ├── rag_service.py     # RAG & Context Management
│   │   ├── media_service.py   # Twitter/YouTube handling
│   │   └── command_service.py # Internal bot commands
│   ├── handlers/              # Telegram handlers
│   │   ├── base.py
│   │   ├── commands.py
│   │   ├── voice.py
│   │   ├── audio.py
│   │   ├── photo.py
│   │   └── document.py
│   ├── jobs/                  # Background jobs
│   │   ├── base.py
│   │   ├── events.py
│   │   ├── inactivity.py
│   │   ├── cleanup.py
│   │   └── email_digest.py
│   ├── middleware/            # Middleware
│   │   └── rate_limiter.py
│   ├── state/                 # State management
│   │   └── chat_manager.py
│   └── memory/                # Long-term Memory
│       └── vector_store.py
├── utils/                      # Utility modules
│   ├── config_loader.py
│   ├── cron_utils.py
│   ├── telegram_utils.py
│   ├── audio_utils.py
│   ├── youtube_utils.py
│   ├── document_utils.py
│   ├── search_utils.py
│   ├── wiz_utils.py
│   ├── twitter_utils.py
│   └── email_utils.py
├── tests/                      # Test suite
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── docs/                       # Documentation
│   ├── architecture.md
│   └── troubleshooting.md
├── data/                       # Data files
│   ├── instructions.md
│   ├── memory.md
│   └── events.txt
├── config.yaml                # Configuration
├── requirements.txt
└── README.md
```

## Component Details

### Chat Manager (`src/state/chat_manager.py`)

Thread-safe state management for chat histories:
- Async lock per chat ID
- Automatic cleanup of inactive chats
- Stats tracking

### Handlers (`src/handlers/`)

Modular handlers for different message types:
- **commands.py**: Bot commands (/start, /status, etc.)
- **voice.py**: Voice message processing with Whisper
- **audio.py**: External audio file processing
- **photo.py**: Image analysis with vision models
- **document.py**: PDF/DOCX text extraction

### Jobs (`src/jobs/`)

Background tasks:
- **events.py**: Check events.txt for notifications
- **inactivity.py**: Unload models after inactivity
- **cleanup.py**: Remove old crons and chat histories

### Rate Limiter (`src/middleware/rate_limiter.py`)

Prevents spam by limiting messages per user:
- Configurable messages per time window
- Per-user tracking
- Configurable exemptions

## Data Flow

### Text Message Flow

1. User sends message
2. `MessageHandler` receives update
3. Rate limiter checks quota
4. Message added to async queue
5. `process_message_item()` processes sequentially
6. URL detection (YouTube/Twitter)
7. LLM generates response
8. Command parsing (:::memory:::, etc.)
9. Response sent to user

### Voice Message Flow

1. User sends voice message
2. `VoiceHandler` receives update
3. File downloaded to temp
4. Whisper transcribes audio (async thread)
5. Transcription shown to user
6. Text added to queue for LLM processing

### Photo Flow

1. User sends photo
2. `PhotoHandler` receives update
3. Image downloaded and encoded to base64
4. Vision model generates description
5. Description added to context
6. LLM generates response
7. Vision model unloaded

## Security Considerations

- **Authorization**: Only configured user IDs can use the bot
- **Rate Limiting**: Prevents spam and abuse
- **Command Sanitization**: Cron commands validated before execution
- **Path Validation**: File operations restricted to project directory
- **Input Validation**: Memory content sanitized before storage

## Performance Optimizations

- **Pre-compiled Regex**: Command patterns compiled once
- **Thread Pool**: Blocking operations (Whisper, PDF) run in threads
- **Connection Reuse**: HTTP client reuse for Ollama
- **Model Caching**: Whisper models loaded lazily
- **Context Pruning**: Automatically limit context size

## Configuration

Key settings in `config.yaml`:

```yaml
MODEL: llama3.1:8b              # Main LLM model
VISION_MODEL: llava:latest      # Vision model for images
CONTEXT_LIMIT: 32000            # Max tokens in context
WHISPER_MODEL_VOICE: base       # Whisper model for voice
WHISPER_MODEL_EXTERNAL: large   # Whisper for external audio
```

## Dependencies

Core dependencies:
- `python-telegram-bot`: Telegram Bot API
- `httpx`: Async HTTP client
- `ollama`: Local LLM inference
- `faster-whisper`: Speech-to-text
- `pywizlight`: Smart light control
- `yt-dlp`: YouTube downloads

See `requirements.txt` for complete list.
