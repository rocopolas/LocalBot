"""Email digest background job for FemtoBot."""
import os
import logging
from datetime import datetime
from telegram.ext import ContextTypes

from src.jobs.base import BackgroundJob
from src.client import OllamaClient
from utils.email_utils import fetch_emails_last_24h, format_emails_for_llm, is_gmail_configured
from utils.config_loader import get_config
from utils.telegram_utils import format_bot_response, split_message, telegramify_content, send_telegramify_results
import re

logger = logging.getLogger(__name__)


class EmailDigestJob(BackgroundJob):
    """Job to fetch and summarize emails daily."""
    
    def __init__(self, notification_chat_id: int = None):
        self.notification_chat_id = notification_chat_id
        self.email_digest_running = False
    
    @property
    def name(self) -> str:
        return "email_digest"
    
    @property
    def interval_seconds(self) -> int:
        return 60  # Check every minute if it's time to run
    
    async def run(self, context: ContextTypes.DEFAULT_TYPE):
        """Check if it's time to run the email digest (4:00 AM)."""
        if not is_gmail_configured():
            return
        
        if not self.notification_chat_id:
            return
        
        # Check if it's 4:00 AM and we haven't run today
        now = datetime.now()
        if now.hour == 4 and now.minute == 0 and not self.email_digest_running:
            await self._send_digest(context)
    
    async def run_manual(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int = None):
        """Run email digest manually."""
        if not is_gmail_configured():
            target_chat = chat_id or self.notification_chat_id
            if target_chat:
                await context.bot.send_message(
                    target_chat,
                    "⚠️ Gmail no está configurado. Verifica las variables GMAIL_USER y GMAIL_APP_PASSWORD en el archivo .env"
                )
            return
        
        await self._send_digest(context, chat_id)
    
    async def _send_digest(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int = None):
        """Fetch emails and send digest."""
        target_chat = chat_id or self.notification_chat_id
        if not target_chat:
            return
        
        self.email_digest_running = True
        
        try:
            # Send status message
            status_msg = await context.bot.send_message(
                target_chat,
                "📧 Obteniendo emails del último día..."
            )
            
            # Fetch emails
            emails = await fetch_emails_last_24h()
            
            if not emails:
                await status_msg.edit_text("📭 No hay emails nuevos en las últimas 24 horas.")
                self.email_digest_running = False
                return
            
            # Check for errors
            if "error" in emails[0]:
                await status_msg.edit_text(f"❌ {emails[0]['error']}")
                self.email_digest_running = False
                return
            
            await status_msg.edit_text(f"🧠 Analizando {len(emails)} emails con IA...")
            
            # Format emails for LLM
            emails_text = format_emails_for_llm(emails)
            
            # Analyze with LLM
            summary = await self._analyze_emails_with_llm(emails_text)
            
            # Send summary with proper formatting
            # Use telegramify to format and split
            chunks = await telegramify_content(summary)
            await send_telegramify_results(context, target_chat, chunks, status_msg)
            
            logger.info(f"Email digest sent to {target_chat} with {len(emails)} emails")
            
        except Exception as e:
            logger.error(f"Error sending email digest: {e}")
            try:
                await context.bot.send_message(
                    target_chat,
                    f"❌ Error al generar el resumen de emails: {str(e)}"
                )
            except:
                pass
        finally:
            self.email_digest_running = False
    
    def _convert_to_telegram_markdown(self, text: str) -> str:
        """Convierte Markdown estándar a formato compatible con Telegram."""
        # Convertir headers (# ## ###) a negrita
        text = re.sub(r'^#{3,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
        text = re.sub(r'^##\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
        text = re.sub(r'^#\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
        
        # Convertir listas con - a emojis
        text = re.sub(r'^-\s+', '• ', text, flags=re.MULTILINE)
        text = re.sub(r'^\*\s+', '• ', text, flags=re.MULTILINE)
        text = re.sub(r'^\+\s+', '• ', text, flags=re.MULTILINE)
        
        # Asegurar que ** esté correctamente formateado (sin espacios internos)
        text = re.sub(r'\*\*\s+', '**', text)
        text = re.sub(r'\s+\*\*', '**', text)
        
        # Agregar espacio después de emojis seguidos de texto (pero no emojis sueltos)
        text = re.sub(r'([📁📧📅⏰⚠️❗✅🔗📌🛒💸🎵📢⚙️🔍📊📈])([a-zA-ZáéíóúÁÉÍÓÚñÑ])', r'\1 \2', text)
        
        # Asegurar que haya líneas en blanco entre secciones (emoji + título en negrita)
        # Agregar línea en blanco antes de líneas que comienzan con emoji + asterisco
        text = re.sub(r'([^\n])(\n)([📁📧📅⏰⚠️❗✅🔗📌🛒💸🎵📢⚙️🔍📊📈]\s*\*)', r'\1\n\n\3', text)
        
        # Agregar línea en blanco después de títulos en negrita
        text = re.sub(r'(\*[^*]+\*)(\n)([^\n])', r'\1\n\n\3', text)
        
        return text
    
    async def _analyze_emails_with_llm(self, emails_text: str) -> str:
        """Analyze emails with LLM and return summary."""
        model = get_config("MODEL")
        client = OllamaClient()
        
        system_prompt = """Eres un asistente especializado en analizar emails y crear resúmenes concisos.

REGLAS DE FORMATO OBLIGATORIAS (sintaxis de Telegram):
- Usa *texto* para negrita (títulos y énfasis importantes)
- Usa _texto_ para cursiva (opcional)
- Usa `texto` para código o valores técnicos
- Usa emojis al inicio de secciones: 📁 📧 ⏰ ❗ ✅
- NO uses # ## ### para títulos (usa *título* en negrita)
- NO uses listas con guiones (usa • con emojis)
- Mantén el formato simple y compatible con Telegram

REGLAS DE ESPACIADO CRÍTICO:
- DEJA UNA LÍNEA EN BLANCO entre cada sección/email diferente
- DEJA UNA LÍNEA EN BLANCO después de cada título en negrita
- DEJA UNA LÍNEA EN BLANCO antes de las listas con •
- Agrega un ESPACIO después de cada emoji
- NUNCA juntes el emoji con el texto: ❌ *📁Carpeta* ✅ *📁 Carpeta*

Ejemplo correcto:
📁 * Trabajo *

• Email de jefe
• Reunión a las 3pm

📧 * Personal *

• Mensaje de familia

Tu tarea es:
1. Identificar emails importantes que requieran atención
2. Agrupar emails por categorías usando emojis
3. Destacar fechas límite, reuniones o acciones requeridas
4. Ser breve y directo

Responde en español."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analiza estos emails del último día y crea un resumen:\n\n{emails_text}"}
        ]
        
        summary = ""
        async for chunk in client.stream_chat(model, messages):
            summary += chunk
        
        # Convertir a formato Telegram y aplicar formato del bot
        # summary = self._convert_to_telegram_markdown(summary) # Legacy
        summary = format_bot_response(summary)
        
        # Format the response
        header = f"📧 *Resumen de Emails - {datetime.now().strftime('%d/%m/%Y')}*\n\n"
        
        if not summary.strip():
            return header + "No se encontraron emails importantes en las últimas 24 horas."
        
        return header + summary
