# Troubleshooting Guide

## Common Issues and Solutions

### Ollama Connection Errors

#### Error: "No se pudo conectar a Ollama"

**Symptoms:**
- Bot responds with connection errors
- Model doesn't load

**Solutions:**
1. **Check if Ollama is running:**
   ```bash
   ollama serve
   ```
   Or if using systemd:
   ```bash
   sudo systemctl status ollama
   ```

2. **Verify Ollama is accessible:**
   ```bash
   curl http://localhost:11434/api/tags
   ```

3. **Check if model is downloaded:**
   ```bash
   ollama list
   # If model missing:
   ollama pull llama3.1:8b
   ```

4. **Check firewall/network:**
   - Ensure port 11434 is accessible
   - Check if localhost resolves correctly

---

### Whisper/Audio Issues

#### Error: "faster-whisper no instalado"

**Solution:**
```bash
pip install faster-whisper
```

#### Error: "Error de transcripción"

**Possible causes:**
1. **Corrupted audio file**
   - Check if audio file plays correctly
   - Try downloading again

2. **Memory issues**
   - Large audio files require significant RAM
   - Try with shorter audio clips

3. **Model loading error**
   - Delete cached model: `rm -rf ~/.cache/whisper/`
   - Re-download model

---

### Telegram Bot Issues

#### Bot not responding

**Checklist:**
1. **Verify token:**
   ```bash
   # Check .env file
   cat .env | grep TELEGRAM_TOKEN
   ```

2. **Check bot is running:**
   ```bash
   ps aux | grep telegram_bot
   ```

3. **Check logs:**
   ```bash
   tail -f logs/bot.log
   ```

4. **Verify authorization:**
   - Check your user ID is in AUTHORIZED_USERS
   - Use `/start` command to see your ID

#### Rate limit exceeded

**Symptoms:**
- "Rate limit excedido" message
- Can't send messages

**Solution:**
- Wait for the time window to reset (default: 60 seconds)
- If legitimate high usage, add your user ID to exemptions

---

### YouTube Download Issues

#### Error: "No se pudo descargar"

**Solutions:**
1. **Update yt-dlp:**
   ```bash
   pip install -U yt-dlp
   ```

2. **Check URL format:**
   - Supported: `youtube.com/watch?v=...`, `youtu.be/...`
   - Not supported: playlists, live streams

3. **Age-restricted videos:**
   - Some videos require authentication
   - Consider using cookies from browser

4. **Region-blocked videos:**
   - Video may not be available in your region
   - Try different video

---

### Document Processing Issues

#### PDF extraction fails

**Solutions:**
1. **Install PyMuPDF:**
   ```bash
   pip install pymupdf
   ```

2. **Check PDF is not corrupted:**
   - Try opening with PDF viewer
   - Re-download if necessary

3. **Scanned PDFs:**
   - PyMuPDF can't extract text from scanned images
   - Use OCR tools first

#### DOCX extraction fails

**Solution:**
```bash
pip install python-docx
```

---

### Cron Job Issues

#### Jobs not executing

**Checklist:**
1. **Check crontab:**
   ```bash
   crontab -l
   ```

2. **Verify command syntax:**
   - Use valid cron syntax
   - Test command manually first

3. **Check logs:**
   ```bash
   grep CRON /var/log/syslog
   ```

4. **Path issues:**
   - Cron uses limited PATH
   - Use absolute paths in commands

#### "Error al agregar tarea"

**Causes:**
- Command contains dangerous patterns
- Invalid cron schedule format
- Permission denied

**Solution:**
- Check command doesn't contain `;`, `|`, `$()`, etc.
- Verify schedule format: `min hour day month dow`
- Ensure you have crontab access

---

### Memory/Persistence Issues

#### Memory not persisting

**Checklist:**
1. **Check file permissions:**
   ```bash
   ls -la data/memory.md
   ```

2. **Verify file exists:**
   ```bash
   touch data/memory.md
   ```

3. **Check disk space:**
   ```bash
   df -h
   ```

#### Memory commands not working

**Format must be:**
```
:::memory This is what I want to save:::
```

Common mistakes:
- Missing colons
- Extra spaces in command name
- Missing closing :::

---

### Smart Light (WIZ) Issues

#### Can't control lights

**Solutions:**
1. **Check light is on network:**
   ```bash
   # Find WIZ lights on network
   python -c "import pywizlight; ..."
   ```

2. **Verify IP address:**
   - Check config.yaml has correct IP
   - Light must be on same network

3. **Check light is powered:**
   - Physical power switch
   - Not in "off" state

---

### Context/History Issues

#### "Context limit exceeded"

**Solutions:**
1. **Start new conversation:**
   - Use `/new` command
   - Clears history

2. **Reduce context size:**
   - Edit config.yaml to lower CONTEXT_LIMIT

3. **Pruning not working:**
   - Check system prompt isn't too large
   - Verify tiktoken is installed for accurate counting

#### Lost conversation history

**Note:** Chat histories are stored in memory only (not persistent).
- Lost on bot restart
- This is by design for privacy

---

### Performance Issues

#### Bot is slow to respond

**Optimizations:**
1. **Model already loaded:**
   - First request loads model (slow)
   - Subsequent requests are faster

2. **Context too large:**
   - Reduce CONTEXT_LIMIT in config
   - Use `/new` to clear history

3. **System resources:**
   - Check CPU/RAM usage
   - Close other applications

4. **Use smaller model:**
   - Switch to smaller model in config.yaml
   - 8B models are faster than 70B

---

### Installation Issues

#### Import errors

**Solution:**
```bash
# Reinstall in correct environment
pip install -r requirements.txt

# Check Python version (3.11+ required)
python --version

# Install missing specific package
pip install <package-name>
```

#### Permission denied

**Solutions:**
```bash
# Fix permissions
chmod +x run.sh

# Use virtual environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Getting Help

If issue persists:

1. **Check logs:**
   ```bash
   tail -100 logs/bot.log
   ```

2. **Enable debug logging:**
   Edit logging level in telegram_bot.py:
   ```python
   level=logging.DEBUG
   ```

3. **Create issue:**
   - Include error message
   - Describe steps to reproduce
   - Attach relevant logs

4. **Check documentation:**
   - README.md
   - docs/architecture.md
   - Code comments
