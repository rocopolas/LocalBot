# 🤖 LocalBot

A smart personal assistant that runs locally using [Ollama](https://ollama.ai). Available as a Telegram bot and TUI interface.

## ✨ Features

- 💬 **Local LLM chat** - No external API dependencies
- 📷 **Image analysis** - Describe and understand images with vision model
- 🎙️ **Audio transcription** - Convert voice messages to text with Whisper
- 🎥 **YouTube summaries** - Send a link and get a summary
- 🐦 **Twitter/X downloader** - Download videos/images directly
- 🔍 **Web search** - Brave Search integration
- 📄 **Document reading** - Analyze and chat with PDF or text files
- 📧 **Email digest** - Read and summarize emails from Gmail
- ⏰ **Reminders** - Schedule cron tasks that notify you in chat
- 🧠 **Persistent memory** - The bot remembers information about you
- 💡 **Smart lights** - Control WIZ lights via chat

## 🤔 Why LocalBot?

| | LocalBot | Cloud Bots (Claude, GPT) |
|---|---|---|
| 💰 **Cost** | **Free** | $20+/month or pay per use |
| 🔒 **Privacy** | Your data never leaves your PC | Your chats go to external servers |
| ⚡ **Speed** | Small models = instant responses | Depends on API and your plan |
| 🌐 **Internet** | Works offline | Requires constant connection |
| 🎛️ **Control** | You choose model, context, everything | Limited to what they offer |
| 🏠 **Smart Home** | Control your lights, all local | Not available |

**Ideal for:**
- Using small and fast models (7B-14B params)
- Keeping your privacy at 100%
- Not paying monthly subscriptions
- Having a personal assistant that runs on YOUR hardware

## 📁 Structure

```
LocalBot/
├── config.yaml          # Main configuration
├── .env                 # Environment variables (tokens)
├── requirements.txt     # Python dependencies
├── cargarentorno.sh     # Installation script
├── run.sh               # Run script
│
├── src/                 # Source code
│   ├── telegram_bot.py  # Telegram bot
│   ├── tui.py           # TUI interface
│   └── client.py        # Ollama client
│
├── utils/               # Utility modules
│   ├── audio_utils.py   # Whisper transcription
│   ├── youtube_utils.py # YouTube audio download
│   ├── search_utils.py  # Brave search
│   ├── cron_utils.py    # Crontab management
│   ├── document_utils.py # PDF/DOCX extraction
│   ├── email_utils.py   # Gmail integration
│   ├── wiz_utils.py     # WIZ smart lights
│   └── config_loader.py # YAML config loader
│
├── data/                # Data files
│   ├── instructions.md  # LLM instructions
│   ├── memory.md        # User memory
│   └── events.txt       # Notification queue
│
└── assets/              # Resources
    └── styles.tcss      # TUI styles
```

## 🚀 Installation

### Requirements
- Python 3.12+
- [Ollama](https://ollama.ai) installed and running
- FFmpeg (for audio transcription)

### Steps

1. **Clone the repository:**
```bash
git clone https://github.com/your-username/LocalBot.git
cd LocalBot
```

2. **Set up environment:**
```bash
chmod +x cargarentorno.sh
./cargarentorno.sh
```

3. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your tokens
```

4. **Download Ollama model:**
```bash
ollama pull llama3.1:latest
# Or your preferred model
```

## ⚙️ Configuration

### `.env`
```env
TELEGRAM_TOKEN=your_botfather_token
AUTHORIZED_USERS=123456789  # Your Telegram ID
NOTIFICATION_CHAT_ID=123456789
BRAVE_API_KEY=your_api_key  # Optional, for searches
GMAIL_USER=your_email@gmail.com  # Optional, for email digest
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### `config.yaml`
```yaml
MODEL: "llama3.1:latest"
VISION_MODEL: "qwen3-vl:2b"
CONTEXT_LIMIT: 200000
WHISPER_LANGUAGE: "es"
WHISPER_MODEL_VOICE: "base"
WHISPER_MODEL_EXTERNAL: "medium"
INACTIVITY_TIMEOUT_MINUTES: 5
```

## 🎮 Usage

### Telegram Bot
```bash
./run.sh
# or
source venv_bot/bin/activate
python src/telegram_bot.py
```

### TUI Interface
```bash
source venv_bot/bin/activate
python src/main.py
```

## 📱 Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Start conversation |
| `/new` | New conversation (clears history) |
| `/status` | View context and token usage |
| `/unload` | Unload all models from RAM |

## 🎤 Special Features

### Image Analysis
- Send a photo → Vision model describes it, text model responds
- Send photo + caption → Bot considers both for response

### Audio Transcription
- Send a voice message → Transcribed and answered
- Send an audio file → Transcription only (larger model)

### YouTube Summary
- Send a YouTube link → Bot downloads, transcribes and summarizes

### Twitter/X Media Download
- Send a Twitter/X link and ask to "download" or "bajar"
- The bot will download the video/image and send the file to you

### Document Reading
- Send a PDF, DOCX, or TXT file → Bot extracts text and responds
- Send document + caption → Bot considers both for response

### Reminders
Ask the bot things like:
- "Remind me to drink water every hour"
- "Notify me tomorrow at 9am about my meeting"

### Memory
The bot can remember information about you:
- Edit `data/memory.md` with your data
- Or just tell it things and it will remember automatically

### Email Digest (Optional)
If Gmail is configured, the bot will:
- Run at 4:00 AM daily
- Read emails from the last 24 hours
- Use LLM to identify important emails
- Send you a summary on Telegram

### Smart Lights (Optional)
Control WIZ lights via natural language:
- "Turn off the bedroom lights"
- "Set brightness to 50%"
- "Change color to red"

- "Change color to red"
- "Turn off all lights"

**Configuration** in `config.yaml`:
```yaml
WIZ_LIGHTS:
  bedroom:  # Single light
    - "192.168.0.121"
  living:   # Multiple lights (group)
    - "192.168.0.63"
    - "192.168.0.115"
```

**Requires**: `pip install pywizlight`

## 🔧 Development

### Adding new features
1. Create the module in `utils/`
2. Import it in `src/telegram_bot.py`
3. Add instructions in `data/instructions.md`

### Changing model
Edit `config.yaml`:
MODEL: "your-model:tag"

## 📄 License

MIT License 
Copyright 2026 Rocopolas

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

Hecho con 🧉 en Argentina
