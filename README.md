# 🤖 LocalBot

Asistente personal inteligente que corre localmente usando [Ollama](https://ollama.ai). Disponible como bot de Telegram y como interface TUI.

## ✨ Características

- 💬 **Chat con LLM local** - Sin dependencias de APIs externas
- 🎙️ **Transcripción de audio** - Convierte mensajes de voz a texto con Whisper
- 🎥 **Resúmenes de YouTube** - Envía un link y recibe un resumen
- 🔍 **Búsqueda web** - Integración con Brave Search
- ⏰ **Recordatorios** - Programa tareas con cron que te notifican en el chat
- 🧠 **Memoria persistente** - El bot recuerda información sobre vos

## 📁 Estructura

```
LocalBot/
├── config.yaml          # Configuración principal
├── .env                 # Variables de entorno (tokens)
├── requirements.txt     # Dependencias Python
├── cargarentorno.sh     # Script de instalación
├── run.sh               # Script para ejecutar
│
├── src/                 # Código fuente
│   ├── telegram_bot.py  # Bot de Telegram
│   ├── tui.py           # Interface TUI
│   └── client.py        # Cliente Ollama
│
├── utils/               # Módulos utilitarios
│   ├── audio_utils.py   # Transcripción Whisper
│   ├── youtube_utils.py # Descargar audio de YT
│   ├── search_utils.py  # Búsqueda Brave
│   └── cron_utils.py    # Gestión de crontab
│
├── data/                # Archivos de datos
│   ├── instructions.md  # Instrucciones del LLM
│   ├── memory.md        # Memoria del usuario
│   └── events.txt       # Cola de notificaciones
│
└── assets/              # Recursos
    └── styles.tcss      # Estilos TUI
```

## 🚀 Instalación

### Requisitos
- Python 3.12+
- [Ollama](https://ollama.ai) instalado y corriendo
- FFmpeg (para transcripción de audio)

### Pasos

1. **Clonar el repositorio:**
```bash
git clone https://github.com/tu-usuario/LocalBot.git
cd LocalBot
```

2. **Configurar entorno:**
```bash
chmod +x cargarentorno.sh
./cargarentorno.sh
```

3. **Configurar variables de entorno:**
```bash
cp .env.example .env
# Editar .env con tus tokens
```

4. **Descargar modelo de Ollama:**
```bash
ollama pull glm-4.7-flash:q8_0
# O el modelo que prefieras
```

## ⚙️ Configuración

### `.env`
```env
TELEGRAM_TOKEN=tu_token_de_botfather
AUTHORIZED_USERS=123456789  # Tu ID de Telegram
NOTIFICATION_CHAT_ID=123456789
BRAVE_API_KEY=tu_api_key  # Opcional, para búsquedas
```

### `config.yaml`
```yaml
MODEL: "glm-4.7-flash:q8_0"
CONTEXT_LIMIT: 200000
WHISPER_LANGUAGE: "es"
WHISPER_MODEL_VOICE: "base"
WHISPER_MODEL_EXTERNAL: "medium"
INACTIVITY_TIMEOUT_MINUTES: 5
```

## 🎮 Uso

### Bot de Telegram
```bash
./run.sh
# o
source venv_bot/bin/activate
python src/telegram_bot.py
```

### Interface TUI
```bash
source venv_bot/bin/activate
python src/main.py
```

## 📱 Comandos de Telegram

| Comando | Descripción |
|---------|-------------|
| `/start` | Iniciar conversación |
| `/new` | Nueva conversación (limpia historial) |
| `/status` | Ver uso de contexto y tokens |

## 🎤 Funciones Especiales

### Transcripción de Audio
- Envía un mensaje de voz → Se transcribe y responde
- Envía un archivo de audio → Solo transcripción (modelo más grande)

### Resumen de YouTube
- Envía un link de YouTube → El bot descarga, transcribe y resume

### Recordatorios
Pedile al bot cosas como:
- "Recordame tomar agua cada hora"
- "Avisame mañana a las 9am que tengo reunión"

### Memoria
El bot puede recordar información sobre vos:
- Edita `data/memory.md` con tus datos
- O simplemente contale cosas y las recordará automáticamente

## 🔧 Desarrollo

### Agregar nuevas funcionalidades
1. Crea el módulo en `utils/`
2. Importalo en `src/telegram_bot.py`
3. Agrega instrucciones en `data/instructions.md`

### Cambiar modelo
Edita `config.yaml`:
```yaml
MODEL: "tu-modelo:tag"
```

## 📄 Licencia

MIT License - Usa, modifica y comparte libremente.

---

Hecho con 🧉 en Argentina
