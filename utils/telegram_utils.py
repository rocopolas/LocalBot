import re
from typing import List


async def telegramify_content(text: str, max_length: int = 4090):
    """
    Usa telegramify-markdown v1.0.0+ para convertir y dividir el mensaje.
    Retorna objetos de telegramify con diferentes tipos de contenido (TEXT, PHOTO, FILE).
    """
    try:
        from telegramify_markdown import telegramify
        
        results = await telegramify(text, max_message_length=max_length)
        return results
        
    except ImportError:
        print("Módulo telegramify_markdown no instalado. Usando fallback.")
        return split_message(text)
    except Exception as e:
        print(f"Error en telegramify: {e}")
        return split_message(text)


def escape_markdown(text: str) -> str:
    """Escapa caracteres especiales de Markdown para Telegram."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', lambda m: '\\' + m.group(1), text)


def escape_code(text: str) -> str:
    """Escapa solo backticks y backslashes para bloques de código."""
    return re.sub(r'([`\\])', lambda m: '\\' + m.group(1), text)


async def send_telegramify_results(context, chat_id, results, placeholder_msg=None):
    """
    Envía resultados de telegramify_markdown v1.0.0+ manejando diferentes tipos de contenido.
    Usa entities en lugar de parse_mode.
    
    Args:
        context: Contexto del bot de Telegram
        chat_id: ID del chat
        results: Lista de objetos de telegramify (Text, File, Photo)
        placeholder_msg: Mensaje placeholder opcional para editar
    
    Returns:
        Lista de mensajes enviados
    """
    from telegramify_markdown import ContentType
    import io
    
    sent_messages = []
    first_item_sent = False
    
    for item in results:
        try:
            # Verificar si es string (fallback de split_message)
            if isinstance(item, str):
                if not first_item_sent and placeholder_msg:
                    await placeholder_msg.edit_text(item)
                    sent_messages.append(placeholder_msg)
                    first_item_sent = True
                else:
                    msg = await context.bot.send_message(chat_id, item)
                    sent_messages.append(msg)
                continue
            
            # Manejar objetos de telegramify v1.0.0+
            if item.content_type == ContentType.TEXT:
                # Convertir entities a diccionarios
                entities = [e.to_dict() for e in item.entities] if item.entities else None
                
                if not first_item_sent and placeholder_msg:
                    await placeholder_msg.edit_text(item.text, entities=entities)
                    sent_messages.append(placeholder_msg)
                    first_item_sent = True
                else:
                    msg = await context.bot.send_message(
                        chat_id, 
                        item.text,
                        entities=entities
                    )
                    sent_messages.append(msg)
                    
            elif item.content_type == ContentType.PHOTO:
                photo_file = io.BytesIO(item.file_data)
                photo_file.name = item.file_name
                
                # Convertir caption entities si existen
                caption_entities = None
                if hasattr(item, 'caption_entities') and item.caption_entities:
                    caption_entities = [e.to_dict() for e in item.caption_entities]
                
                caption = item.caption_text if hasattr(item, 'caption_text') else None
                
                if not first_item_sent and placeholder_msg:
                    await placeholder_msg.delete()
                    msg = await context.bot.send_photo(
                        chat_id,
                        photo=photo_file,
                        caption=caption,
                        caption_entities=caption_entities
                    )
                    sent_messages.append(msg)
                    first_item_sent = True
                else:
                    msg = await context.bot.send_photo(
                        chat_id,
                        photo=photo_file,
                        caption=caption,
                        caption_entities=caption_entities
                    )
                    sent_messages.append(msg)
                    
            elif item.content_type == ContentType.FILE:
                doc_file = io.BytesIO(item.file_data)
                doc_file.name = item.file_name
                
                # Convertir caption entities si existen
                caption_entities = None
                if hasattr(item, 'caption_entities') and item.caption_entities:
                    caption_entities = [e.to_dict() for e in item.caption_entities]
                
                caption = item.caption_text if hasattr(item, 'caption_text') else None
                
                if not first_item_sent and placeholder_msg:
                    await placeholder_msg.delete()
                    msg = await context.bot.send_document(
                        chat_id,
                        document=doc_file,
                        caption=caption,
                        caption_entities=caption_entities
                    )
                    sent_messages.append(msg)
                    first_item_sent = True
                else:
                    msg = await context.bot.send_document(
                        chat_id,
                        document=doc_file,
                        caption=caption,
                        caption_entities=caption_entities
                    )
                    sent_messages.append(msg)
                    
        except Exception as e:
            print(f"Error enviando item de telegramify: {e}")
            # Fallback: intentar enviar como texto simple
            if hasattr(item, 'text'):
                msg = await context.bot.send_message(chat_id, item.text)
                sent_messages.append(msg)
            elif hasattr(item, 'content'):
                msg = await context.bot.send_message(chat_id, item.content)
                sent_messages.append(msg)
    
    return sent_messages


def split_message(text, limit=4096):
    """
    Splits a message into chunks that fit within the Telegram character limit.
    Tries to split at newlines to preserve readability.
    Handles code blocks to ensure they are closed in one chunk and reopened in the next.
    """
    if len(text) <= limit:
        return [text]

    parts = []
    while len(text) > limit:
        split_index = -1
        
        last_newline = text.rfind('\n', 0, limit)
        if last_newline != -1:
            split_index = last_newline
        else:
            split_index = limit

        chunk = text[:split_index]
        
        # Handle code blocks
        code_starts = chunk.count('```') % 2
        if code_starts:
            last_code = chunk.rfind('```')
            if last_code != -1:
                chunk = chunk[:last_code]
                text = text[last_code:]
            else:
                text = text[split_index:]
        else:
            text = text[split_index:]
            if text.startswith('\n'):
                text = text[1:]

        parts.append(chunk)

    if text:
        parts.append(text)

    return parts


def format_bot_response(response: str) -> str:
    """Format bot response for Telegram, handling various Markdown elements."""
    if not response:
        return ""
    
    formatted = response
    
    # Handle think tags - format as quotes or remove
    if "<think>" in formatted:
        formatted = formatted.replace("<think>", "> 🧠 **Pensando:**\n> ")
        formatted = formatted.replace("</think>", "\n\n")
        # Remove any remaining think content
        formatted = re.sub(r'<think>.*?</think>', '', formatted, flags=re.DOTALL)
    
    # Remove ANSI color codes
    formatted = re.sub(r'\x1b\[[0-9;]*m', '', formatted)
    
    # Handle memory commands - remove them from visible output
    formatted = re.sub(r':::memory(?::)?\s*.+?:::', '', formatted, flags=re.DOTALL)
    formatted = re.sub(r':::memory_delete(?::)?\s*.+?:::', '', formatted, flags=re.DOTALL)
    
    # Handle cron commands
    formatted = re.sub(r':::cron(?::)?\s*.+?:::', '', formatted)
    formatted = re.sub(r':::cron_delete(?::)?\s*.+?:::', '', formatted)
    
    # Handle search commands
    formatted = re.sub(r':::search(?::)?\s*.+?:::', '', formatted)
    formatted = re.sub(r':::foto(?::)?\s*.+?:::', '', formatted, flags=re.IGNORECASE)
    
    # Handle light/camera commands
    formatted = re.sub(r':::luz(?::)?\s*.+?:::', '', formatted, flags=re.IGNORECASE)
    formatted = re.sub(r':::camara(?::)?(?:\s+\S+)?:::', '', formatted)
    
    # LaTeX math is now handled automatically by telegramify-markdown
    
    return formatted.strip()


def prune_history(history: list, limit: int = 30000) -> list:
    """Prune chat history to fit within token limit while keeping system prompt."""
    if not history:
        return []
    
    # Always keep system prompt (first message if it's system)
    if history and history[0].get("role") == "system":
        system_msg = history[0]
        messages = history[1:]
    else:
        system_msg = None
        messages = history
    
    # Calculate total length
    total_length = sum(len(str(msg.get("content", ""))) for msg in history)
    
    # If under limit, return all
    if total_length <= limit:
        return history
    
    # Remove oldest messages until under limit
    while messages and total_length > limit:
        removed = messages.pop(0)
        total_length -= len(str(removed.get("content", "")))
    
    # Reconstruct history
    result = []
    if system_msg:
        result.append(system_msg)
    result.extend(messages)
    
    return result
