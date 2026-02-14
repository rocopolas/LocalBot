import logging
import sys
import re

class CustomFormatter(logging.Formatter):
    """
    Custom formatter with color support.
    """
    
    # ANSI colors
    GREY = "\x1b[38;5;240m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    BLUE = "\x1b[34;20m"
    RESET = "\x1b[0m"
    
    # Format strings
    # We use a simpler format for httpx to minimize noise
    HTTPX_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def __init__(self):
        super().__init__()
        self.formats = {
            logging.DEBUG: self.GREY + self.DEFAULT_FORMAT + self.RESET,
            logging.INFO: self.GREEN + self.DEFAULT_FORMAT + self.RESET,
            logging.WARNING: self.YELLOW + self.DEFAULT_FORMAT + self.RESET,
            logging.ERROR: self.RED + self.DEFAULT_FORMAT + self.RESET,
            logging.CRITICAL: self.BOLD_RED + self.DEFAULT_FORMAT + self.RESET
        }

    def format(self, record):
        log_fmt = self.formats.get(record.levelno)
        
        # Special handling for httpx/httpcore to make them grey regardless of level (mostly INFO)
        if "httpx" in record.name or "httpcore" in record.name:
            log_fmt = self.GREY + self.HTTPX_FORMAT + self.RESET
            
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

class TokenRedactFilter(logging.Filter):
    """Filter to redact sensitive tokens from log messages."""
    
    def __init__(self, token=None):
        super().__init__()
        self.token = token
        # Pattern to match bot tokens in URLs
        self.token_pattern = re.compile(r'bot\d+:[A-Za-z0-9_-]+')
    
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if hasattr(record, 'args') and record.args:
            record.args = tuple(
                self._redact(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True
    
    def _redact(self, text):
        """Redact token from text."""
        if self.token:
            text = text.replace(self.token, '***REDACTED***')
        # Also redact any bot token pattern
        text = self.token_pattern.sub('bot***REDACTED***', text)
        return text

def setup_logging(token=None):
    """
    Setup logging configuration with custom colors and filters.
    """
    # Create console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(CustomFormatter())
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.addHandler(console_handler)
    
    # Suppress overly verbose loggers
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    
    # Add token redaction filter to sensitive loggers
    token_filter = TokenRedactFilter(token)
    for logger_name in ['httpx', 'httpcore', 'telegram', 'root']:
        logging.getLogger(logger_name).addFilter(token_filter)
        
    return logging.getLogger("FemtoBot")
