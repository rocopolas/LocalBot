import re
from typing import Optional


def format_bot_response(
    response: str,
    include_thinking: bool = True,
    remove_commands: bool = True,
    escape_ansi: bool = True
) -> str:
    """
    Formatea la respuesta del bot eliminando comandos internos y procesando tags.
    
    Args:
        response: Respuesta cruda del LLM
        include_thinking: Si True, convierte <think> en formato markdown
        remove_commands: Si True, elimina comandos :::xxx:::
        escape_ansi: Si True, elimina códigos de color ANSI
    
    Returns:
        Texto formateado listo para enviar al usuario
    """
    formatted = response
    
    # Procesar tags de pensamiento
    if include_thinking:
        formatted = formatted.replace("<think>", "> 🧠 **Pensando:**\n> ")
        formatted = formatted.replace("</think>", "\n\n")
    else:
        # Eliminar completamente los bloques de pensamiento
        formatted = re.sub(r'<think>.*?</think>', '', formatted, flags=re.DOTALL)
    
    # Eliminar códigos ANSI
    if escape_ansi:
        formatted = re.sub(r'\x1b\[[0-9;]*m', '', formatted)
    
    # Eliminar comandos internos
    if remove_commands:
        # Comandos de memoria
        formatted = re.sub(r':::memory\s+.+?:::', '', formatted, flags=re.DOTALL)
        formatted = re.sub(r':::memory_delete\s+.+?:::', '', formatted, flags=re.DOTALL)
        
        # Comandos de cron
        formatted = re.sub(r':::cron\s+.+?:::', '', formatted)
        formatted = re.sub(r':::cron_delete\s+.+?:::', '', formatted)
        
        # Comandos de búsqueda
        formatted = re.sub(r':::search\s+.+?:::', '', formatted)
        formatted = re.sub(r':::foto\s+.+?:::', '', formatted, flags=re.IGNORECASE)
        
        # Comandos de dispositivos
        formatted = re.sub(r':::luz\s+.+?:::', '', formatted, flags=re.IGNORECASE)
        formatted = re.sub(r':::camara(?:\s+\S+)?:::', '', formatted)
    
    return formatted.strip()


def escape_markdown(text: str) -> str:
    """Escapa caracteres especiales de Markdown para Telegram."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


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
        # Find a suitable split point
        split_index = -1
        
        # Try to split at the last newline before the limit
        last_newline = text.rfind('\n', 0, limit)
        if last_newline != -1:
            split_index = last_newline
        else:
            # If no newline, force split at limit
            split_index = limit

        # Candidate chunk and remaining
        if split_index == last_newline:
             candidate_chunk = text[:last_newline+1]
             candidate_remaining = text[last_newline+1:]  
        else:
             candidate_chunk = text[:limit]
             candidate_remaining = text[limit:]

        # --- Code Block Logic (Preview) ---
        # We need to calculate the actual impact on length to ensure progress
        code_block_markers = candidate_chunk.count("```")
        overhead_added = 0
        
        if code_block_markers % 2 != 0:
            # We would add "\n```" to chunk (4 chars)
            # And "```\n" to remaining (4 chars)
            # But the loop condition depends on len(remaining_with_modification)
            overhead_remaining = 4 # len("```\n")
        else:
            overhead_remaining = 0
            
        # Check if we are making progress
        # Current length: len(text)
        # New length will be: len(candidate_remaining) + overhead_remaining
        if len(candidate_remaining) + overhead_remaining >= len(text):
            # We are not shrinking the text fast enough (or at all).
            # Force split at limit
            split_index = limit
            candidate_chunk = text[:limit]
            candidate_remaining = text[limit:]
            
            # Re-eval overhead for limit split
            if candidate_chunk.count("```") % 2 != 0:
                 overhead_remaining = 4
            else:
                 overhead_remaining = 0
            
            # If still stuck, we must break the loop to avoid hanging
            if len(candidate_remaining) + overhead_remaining >= len(text):
                 # Emergency break: just take the chunk as is, or ignore code block safety?
                 # If we ignore code block safety we break formatting, but avoid loop.
                 # Let's just output `candidate_chunk` without modification and remaining without modification?
                 # No, better to accept slightly larger chunk?
                 # Let's break, append remaining text as one last chunk (violating limit) to handle edge case
                 parts.append(text)
                 text = ""
                 break

        # Apply logic
        chunk = candidate_chunk
        remaining = candidate_remaining
        
        if chunk.count("```") % 2 != 0:
            chunk += "\n```"
            remaining = "```\n" + remaining

        parts.append(chunk)
        text = remaining

    if text:
        parts.append(text)

    return parts
