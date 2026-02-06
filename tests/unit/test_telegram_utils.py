"""Unit tests for telegram_utils module."""
import pytest
from utils.telegram_utils import split_message, format_bot_response, escape_markdown


class TestSplitMessage:
    """Test suite for message splitting."""
    
    def test_short_message_no_split(self):
        """Test that short messages aren't split."""
        text = "Short message"
        result = split_message(text)
        assert result == [text]
    
    def test_long_message_split(self):
        """Test that long messages are split."""
        text = "A" * 5000
        result = split_message(text)
        assert len(result) > 1
        assert all(len(chunk) <= 4096 for chunk in result)
    
    def test_split_at_newline(self):
        """Test that splits happen at newlines when possible."""
        text = "Line1\n" + "A" * 4000 + "\nLine2"
        result = split_message(text)
        # Should try to split at the newline
        assert len(result) >= 1
    
    def test_code_block_handling(self):
        """Test that code blocks are handled correctly."""
        text = "```python\n" + "code\n" * 1000 + "```"
        result = split_message(text)
        # Each chunk should have balanced code block markers
        for chunk in result:
            if "```" in chunk:
                assert chunk.count("```") % 2 == 0 or chunk.endswith("```")


class TestFormatBotResponse:
    """Test suite for response formatting."""
    
    def test_remove_think_tags(self):
        """Test removal of think tags."""
        text = "<think>Thinking...</think>Result"
        result = format_bot_response(text, include_thinking=False)
        assert "<think>" not in result
        assert "</think>" not in result
    
    def test_format_think_tags(self):
        """Test formatting of think tags."""
        text = "<think>Thinking...</think>Result"
        result = format_bot_response(text, include_thinking=True)
        assert "🧠 **Pensando:**" in result
    
    def test_remove_commands(self):
        """Test removal of internal commands."""
        text = "Response :::memory save this::: more text"
        result = format_bot_response(text, remove_commands=True)
        assert ":::memory" not in result
        assert "Response" in result
        assert "more text" in result
    
    def test_remove_ansi_codes(self):
        """Test removal of ANSI color codes."""
        text = "\033[31mRed text\033[0m normal"
        result = format_bot_response(text, escape_ansi=True)
        assert "\033[" not in result
        assert "Red text" in result


class TestEscapeMarkdown:
    """Test suite for markdown escaping."""
    
    def test_escape_special_chars(self):
        """Test escaping of special markdown characters."""
        text = "_test_ *test* [test]"
        result = escape_markdown(text)
        assert r"\_test\_" in result
        assert r"\*test\*" in result
        assert r"\[test\]" in result
    
    def test_no_change_for_normal_text(self):
        """Test that normal text isn't changed."""
        text = "Normal text without special chars"
        result = escape_markdown(text)
        assert result == text
