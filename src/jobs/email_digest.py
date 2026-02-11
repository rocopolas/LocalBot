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
                    "⚠️ Gmail is not configured. Check the GMAIL_USER and GMAIL_APP_PASSWORD variables in the .env file"
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
                "📧 Fetching emails from the last day..."
            )
            
            # Fetch emails
            emails = await fetch_emails_last_24h()
            
            if not emails:
                await status_msg.edit_text("📭 No new emails in the last 24 hours.")
                self.email_digest_running = False
                return
            
            # Check for errors
            if "error" in emails[0]:
                await status_msg.edit_text(f"❌ {emails[0]['error']}")
                self.email_digest_running = False
                return
            
            await status_msg.edit_text(f"🧠 Analyzing {len(emails)} emails with AI...")
            
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
                    f"❌ Error generating email digest: {str(e)}"
                )
            except:
                pass
        finally:
            self.email_digest_running = False
    
    def _convert_to_telegram_markdown(self, text: str) -> str:
        """Convert standard Markdown to Telegram-compatible format."""
        # Convert headers (# ## ###) to bold
        text = re.sub(r'^#{3,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
        text = re.sub(r'^##\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
        text = re.sub(r'^#\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
        
        # Convert lists with - to emoji bullets
        text = re.sub(r'^-\s+', '• ', text, flags=re.MULTILINE)
        text = re.sub(r'^\*\s+', '• ', text, flags=re.MULTILINE)
        text = re.sub(r'^\+\s+', '• ', text, flags=re.MULTILINE)
        
        # Ensure ** is correctly formatted (no internal spaces)
        text = re.sub(r'\*\*\s+', '**', text)
        text = re.sub(r'\s+\*\*', '**', text)
        
        # Add space after emojis followed by text (but not standalone emojis)
        text = re.sub(r'([📁📧📅⏰⚠️❗✅🔗📌🛒💸🎵📢⚙️🔍📊📈])([a-zA-ZáéíóúÁÉÍÓÚñÑ])', r'\1 \2', text)
        
        # Ensure blank lines between sections (emoji + bold title)
        # Add blank line before lines starting with emoji + asterisk
        text = re.sub(r'([^\n])(\n)([📁📧📅⏰⚠️❗✅🔗📌🛒💸🎵📢⚙️🔍📊📈]\s*\*)', r'\1\n\n\3', text)
        
        # Add blank line after bold titles
        text = re.sub(r'(\*[^*]+\*)(\n)([^\n])', r'\1\n\n\3', text)
        
        return text
    
    async def _analyze_emails_with_llm(self, emails_text: str) -> str:
        """Analyze emails with LLM and return summary."""
        model = get_config("MODEL")
        client = OllamaClient()
        
        system_prompt = """You are an assistant specialized in analyzing emails and creating clean, structured digests.

        MANDATORY FORMAT RULES:
        1. Group emails by category using the 📁 emoji and a bold title (e.g., 📁 * Category Name *).
        2. Inside each category, list emails using the 📧 emoji, bold sender name, and a bullet point • with the summary.
        3. If there are multiple emails from the same sender in the same category, mention "(X emails)" in the summary.
        4. At the very end, add a "⚠️ * Actions Needed *" section with a bulleted list of items requiring user attention.
        5. DO NOT include a "Summary" or "Introduction" text. Start directly with the first category.
        6. Use the exact structure below.

        STRUCTURE EXAMPLE:
        📁 * Security *
        📧 * PayPal *
        • Suspicious login attempt detected

        📁 * Newsletters *
        📧 * The Verge *
        • New iPhone review and tech updates
        📧 * Morning Brew *
        • Market recap (2 emails)

        ⚠️ * Actions Needed *
        • Verify PayPal login
        • Cancel unused subscription

        CATEGORIES TO USE (adapt as needed):
        - Security
        - Service Updates
        - Product Updates
        - Promotions
        - Financial Updates
        - Service Reminders
        - Product Announcements
        - Personal Communications
        - News/Updates

        Your task:
        - Filter out spam/irrelevant emails if possible, but keep anything that might be useful.
        - Be concise.
        - Summarize the core message of each email in 1 line if possible.
        - If an email implies an action (reset password, pay bill), add it to "Actions Needed".

        Respond in English."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze these emails from the last day and create a summary:\n\n{emails_text}"}
        ]
        
        summary = ""
        async for chunk in client.stream_chat(model, messages):
            summary += chunk
        
        # Convert to Telegram format and apply bot formatting
        # summary = self._convert_to_telegram_markdown(summary) # Legacy
        summary = format_bot_response(summary)
        
        # Format the response
        header = f"📧 *Email Digest - {datetime.now().strftime('%d/%m/%Y')}*\n\n"
        
        if not summary.strip():
            return header + "No important emails found in the last 24 hours."
        
        return header + summary
