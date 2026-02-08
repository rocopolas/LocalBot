# TUI (Terminal User Interface) Documentation

## Overview

The TUI provides a terminal-based interface for FemtoBot with full feature parity to the Telegram bot.

## Features

### Core Features
- 💬 Real-time chat with streaming responses
- 💾 Automatic persistence of conversations
- 📂 Session management (save/load multiple sessions)
- 📄 Export to Markdown
- 🔔 Cron notification integration
- 🧠 Full support for all `:::xxx:::` commands
- 📊 Token usage monitoring

### Commands

#### Slash Commands
Type `/` followed by a command:

| Command | Description | Example |
|---------|-------------|---------|
| `/status` | Show token usage and model info | `/status` |
| `/new` | Start new conversation | `/new` |
| `/clear` | Alias for `/new` | `/clear` |
| `/save` | Save current session | `/save mysession` |
| `/load` | Load a saved session | `/load mysession` |
| `/sessions` | List all saved sessions | `/sessions` |
| `/export` | Export conversation to markdown | `/export chat.md` |
| `/unload` | Unload models from RAM | `/unload` |
| `/help` | Show help message | `/help` |

#### LLM Commands
All commands work exactly like in Telegram:

- `:::memory <text>:::` - Save to memory
- `:::memory_delete <text>:::` - Remove from memory
- `:::cron <schedule> <command>:::` - Add cron job
- `:::cron_delete <text>:::` - Remove cron job
- `:::search <query>:::` - Web search
- `:::luz <name> <action> [value]:::` - Control WIZ lights

### Session Management

Sessions are automatically saved to `data/tui_history/`.

**Default session**: Your conversation is automatically saved as "default" and restored on restart.

**Named sessions**: Use `/save <name>` to create named snapshots.

**Export**: Use `/export filename.md` to export current conversation.

### Keyboard Shortcuts

- `Enter` - Send message
- `Ctrl+C` - Exit application
- `Up/Down` - Navigate input history (coming soon)

## Architecture

```
src/
├── tui.py                          # Main TUI application
├── tui_handlers/
│   ├── command_processor.py        # Process :::xxx::: commands
│   └── slash_commands.py          # Handle /commands
└── tui_utils/
    └── history_manager.py         # Persistence layer
```

### Components

**TUIHistoryManager**: Handles saving/loading conversations to JSON files.

**TUICommandProcessor**: Processes all `:::xxx:::` commands exactly like Telegram bot.

**TUISlashCommands**: Handles slash commands for TUI-specific features.

**FemtoBotApp**: Main Textual application integrating all components.

## Data Storage

Conversations are stored in:
```
data/tui_history/
├── default.json           # Auto-saved session
├── session1.json         # Named sessions
└── session2.json
```

Format:
```json
{
  "version": 1,
  "last_saved": "2026-02-05T14:30:00",
  "message_count": 42,
  "history": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

## Styling

The TUI uses Textual CSS for styling. Customize in `assets/styles.tcss`:

```css
.user-message {
    background: $primary;
    color: $text-primary;
}

.bot-message {
    background: $surface;
    color: $text;
}
```

## Differences from Telegram Bot

| Feature | Telegram | TUI |
|---------|----------|-----|
| Media (photos) | ✅ Yes | ❌ No (terminal limitation) |
| Voice messages | ✅ Yes | ❌ No (terminal limitation) |
| Documents | ✅ Yes | ❌ No (terminal limitation) |
| Session persistence | ❌ No | ✅ Yes |
| Slash commands | Limited | Extensive |
| Export | ❌ No | ✅ Yes |
| Notifications | ✅ Yes | ✅ Yes |

## Troubleshooting

### TUI won't start
```bash
# Check dependencies
pip install textual

# Verify Python version (3.11+ required)
python --version
```

### History not saving
```bash
# Check permissions
ls -la data/tui_history/

# Create directory manually
mkdir -p data/tui_history
```

### Display issues
- Ensure terminal supports Unicode
- Try different terminal emulator
- Check terminal size (minimum 80x24)

## Future Enhancements

Planned features:
- [ ] Input history (arrow keys)
- [ ] Tab completion
- [ ] Split-screen mode
- [ ] Themes (light/dark)
- [ ] Vim/emacs keybindings
- [ ] Image preview (using kitty/sixel)
