"""Email utilities for reading Gmail via IMAP."""
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import os


def get_gmail_credentials():
    """Gets Gmail credentials from environment. Returns (user, password) or (None, None)."""
    user = os.getenv("GMAIL_USER", "").strip()
    password = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    if user and password:
        return user, password
    return None, None


def is_gmail_configured() -> bool:
    """Check if Gmail is configured."""
    user, password = get_gmail_credentials()
    return user is not None and password is not None


def decode_mime_header(header_value):
    """Decodes MIME encoded header."""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)


def get_email_body(msg):
    """Extracts the text body from an email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    break
                except:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace')
        except:
            body = str(msg.get_payload())
    
    # Truncate very long bodies
    if len(body) > 2000:
        body = body[:2000] + "..."
    return body.strip()


async def fetch_emails_last_24h() -> list[dict]:
    """
    Fetches emails from the last 24 hours from Gmail.
    Returns a list of dicts with: from, subject, date, snippet
    """
    user, password = get_gmail_credentials()
    if not user or not password:
        return []
    
    emails = []
    
    try:
        # Connect to Gmail IMAP
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, password)
        mail.select("INBOX")
        
        # Search for emails from last 24 hours
        since_date = (datetime.now() - timedelta(hours=24)).strftime("%d-%b-%Y")
        _, message_numbers = mail.search(None, f'(SINCE "{since_date}")')
        
        if not message_numbers[0]:
            mail.logout()
            return []
        
        email_ids = message_numbers[0].split()
        
        # Limit to last 50 emails to avoid overload
        email_ids = email_ids[-50:]
        
        for email_id in email_ids:
            try:
                _, msg_data = mail.fetch(email_id, "(RFC822)")
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                # Extract info
                from_header = decode_mime_header(msg.get("From", ""))
                subject = decode_mime_header(msg.get("Subject", "(No subject)"))
                date_header = msg.get("Date", "")
                body_snippet = get_email_body(msg)
                
                emails.append({
                    "from": from_header,
                    "subject": subject,
                    "date": date_header,
                    "snippet": body_snippet[:500]  # First 500 chars of body
                })
            except Exception as e:
                continue
        
        mail.logout()
        
    except imaplib.IMAP4.error as e:
        return [{"error": f"IMAP authentication error: {str(e)}"}]
    except Exception as e:
        return [{"error": f"Error connecting to Gmail: {str(e)}"}]
    
    return emails


def format_emails_for_llm(emails: list[dict]) -> str:
    """Formats email list for LLM analysis."""
    if not emails:
        return "No new emails in the last 24 hours."
    
    if "error" in emails[0]:
        return emails[0]["error"]
    
    lines = [f"📬 **{len(emails)} emails received in the last 24 hours:**\n"]
    
    for i, email_data in enumerate(emails, 1):
        lines.append(f"---\n**Email {i}:**")
        lines.append(f"- From: {email_data['from']}")
        lines.append(f"- Subject: {email_data['subject']}")
        lines.append(f"- Date: {email_data['date']}")
        if email_data.get('snippet'):
            lines.append(f"- Excerpt: {email_data['snippet'][:200]}...")
        lines.append("")
    
    return "\n".join(lines)
