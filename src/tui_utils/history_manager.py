"""TUI persistence manager for chat history."""
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TUIHistoryManager:
    """
    Manages persistent storage of TUI chat history.
    
    Stores conversations in JSON format with metadata.
    """
    
    def __init__(self, history_dir: str = None):
        """
        Initialize history manager.
        
        Args:
            history_dir: Directory to store history files (default: data/tui_history/)
        """
        if history_dir is None:
            from src.constants import PROJECT_ROOT
            history_dir = os.path.join(PROJECT_ROOT, "data", "tui_history")
        
        self.history_dir = history_dir
        os.makedirs(history_dir, exist_ok=True)
        logger.info(f"TUIHistoryManager initialized: {history_dir}")
    
    def _get_history_file(self, session_id: str = "default") -> str:
        """Get path to history file for a session."""
        return os.path.join(self.history_dir, f"{session_id}.json")
    
    def save_history(self, history: List[Dict[str, Any]], session_id: str = "default") -> bool:
        """
        Save chat history to disk.
        
        Args:
            history: List of message dictionaries
            session_id: Session identifier
            
        Returns:
            True if successful
        """
        try:
            history_file = self._get_history_file(session_id)
            
            data = {
                "version": 1,
                "last_saved": datetime.now().isoformat(),
                "message_count": len(history),
                "history": history
            }
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"History saved: {len(history)} messages to {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving history: {e}")
            return False
    
    def load_history(self, session_id: str = "default") -> List[Dict[str, Any]]:
        """
        Load chat history from disk.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of message dictionaries (empty if not found)
        """
        try:
            history_file = self._get_history_file(session_id)
            
            if not os.path.exists(history_file):
                logger.info(f"No history found for session: {session_id}")
                return []
            
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            history = data.get("history", [])
            logger.info(f"History loaded: {len(history)} messages from {session_id}")
            return history
            
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted history file: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            return []
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all available sessions.
        
        Returns:
            List of session metadata
        """
        sessions = []
        
        try:
            for filename in os.listdir(self.history_dir):
                if filename.endswith('.json'):
                    session_id = filename[:-5]  # Remove .json
                    filepath = os.path.join(self.history_dir, filename)
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        sessions.append({
                            "id": session_id,
                            "last_saved": data.get("last_saved", "Unknown"),
                            "message_count": data.get("message_count", 0)
                        })
                    except:
                        pass
            
            # Sort by last_saved descending
            sessions.sort(key=lambda x: x.get("last_saved", ""), reverse=True)
            
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
        
        return sessions
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session history.
        
        Args:
            session_id: Session to delete
            
        Returns:
            True if deleted
        """
        try:
            history_file = self._get_history_file(session_id)
            if os.path.exists(history_file):
                os.remove(history_file)
                logger.info(f"Session deleted: {session_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False
    
    def export_session(self, session_id: str, export_path: str) -> bool:
        """
        Export session to a file (markdown format).
        
        Args:
            session_id: Session to export
            export_path: Path for export file
            
        Returns:
            True if successful
        """
        try:
            history = self.load_history(session_id)
            if not history:
                return False
            
            with open(export_path, 'w', encoding='utf-8') as f:
                f.write(f"# LocalBot TUI Conversation Export\n\n")
                f.write(f"**Session:** {session_id}\n")
                f.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write("---\n\n")
                
                for msg in history:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        f.write(f"**User:** {content}\n\n")
                    elif role == "assistant":
                        f.write(f"**Bot:** {content}\n\n")
                    elif role == "system":
                        f.write(f"*{content}*\n\n")
            
            logger.info(f"Session exported: {session_id} -> {export_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting session: {e}")
            return False
