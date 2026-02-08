"""Configuration loader for FemtoBot with validation and caching."""
import yaml
import os
import logging
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

_config: Optional[Dict[str, Any]] = None
_config_path: Optional[str] = None

# Default configuration values
DEFAULT_CONFIG = {
    "MODEL": "llama3.1:8b",
    "CONTEXT_LIMIT": 32000,
    "VISION_MODEL": None,
    "WHISPER_MODEL_VOICE": "base",
    "WHISPER_MODEL_AUDIO": "large",
    "INSTRUCTIONS_FILE": "data/instructions.md",
    "MEMORY_FILE": "data/memory.md",
    "EVENTS_FILE": "data/events.txt",
}


class ConfigError(Exception):
    """Raised when there's an error loading or validating configuration."""
    pass


def get_config_path() -> str:
    """Gets the absolute path to config.yaml."""
    # config.yaml is in the project root (parent of utils/)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Loads configuration from config.yaml with validation.
    
    Args:
        force_reload: If True, reloads config from disk even if already loaded
        
    Returns:
        Dictionary with configuration values
        
    Raises:
        ConfigError: If config file cannot be loaded or is invalid
    """
    global _config, _config_path
    
    if _config is not None and not force_reload:
        return _config
    
    config_path = get_config_path()
    
    # Check if file exists
    if not os.path.exists(config_path):
        logger.warning(f"Config file not found at {config_path}. Using defaults.")
        _config = DEFAULT_CONFIG.copy()
        _config_path = config_path
        return _config
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)
        
        if loaded_config is None:
            logger.warning(f"Config file is empty. Using defaults.")
            _config = DEFAULT_CONFIG.copy()
            _config_path = config_path
            return _config
        
        if not isinstance(loaded_config, dict):
            raise ConfigError(f"Config file must contain a YAML dictionary, got {type(loaded_config).__name__}")
        
        # Merge with defaults
        _config = DEFAULT_CONFIG.copy()
        _config.update(loaded_config)
        _config_path = config_path
        
        # Validate required fields
        _validate_config(_config)
        
        logger.info(f"Configuration loaded successfully from {config_path}")
        return _config
        
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")
    except PermissionError:
        raise ConfigError(f"Permission denied reading config file: {config_path}")
    except Exception as e:
        raise ConfigError(f"Error loading config: {e}")


def _validate_config(config: Dict[str, Any]) -> None:
    """
    Validates configuration values.
    
    Args:
        config: Configuration dictionary to validate
        
    Raises:
        ConfigError: If validation fails
    """
    # Validate numeric fields
    context_limit = config.get("CONTEXT_LIMIT")
    if context_limit is not None and not isinstance(context_limit, int):
        raise ConfigError(f"CONTEXT_LIMIT must be an integer, got {type(context_limit).__name__}")
    if context_limit is not None and context_limit < 1000:
        logger.warning(f"CONTEXT_LIMIT is very low ({context_limit}). This may cause issues.")
    
    # Validate string fields
    string_fields = ["MODEL", "WHISPER_MODEL_VOICE", "WHISPER_MODEL_AUDIO"]
    for field in string_fields:
        value = config.get(field)
        if value is not None and not isinstance(value, str):
            raise ConfigError(f"{field} must be a string, got {type(value).__name__}")
    
    # Validate file paths
    path_fields = ["INSTRUCTIONS_FILE", "MEMORY_FILE", "EVENTS_FILE"]
    for field in path_fields:
        value = config.get(field)
        if value is not None and not isinstance(value, str):
            raise ConfigError(f"{field} must be a string path, got {type(value).__name__}")


def get_config(key: str, default: Any = None) -> Any:
    """
    Gets a config value by key with lazy loading.
    
    Args:
        key: Configuration key to retrieve
        default: Default value if key is not found
        
    Returns:
        Configuration value or default
    """
    global _config
    if _config is None:
        try:
            load_config()
        except ConfigError as e:
            logger.error(f"Failed to load config: {e}. Using defaults.")
            _config = DEFAULT_CONFIG.copy()
    
    return _config.get(key, default)


def reload_config() -> Dict[str, Any]:
    """
    Forces reload of configuration from disk.
    
    Returns:
        Updated configuration dictionary
    """
    return load_config(force_reload=True)


def get_all_config() -> Dict[str, Any]:
    """
    Gets the entire configuration dictionary.
    
    Returns:
        Complete configuration dictionary
    """
    if _config is None:
        load_config()
    return _config.copy()
