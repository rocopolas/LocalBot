"""Unit tests for config_loader module."""
import pytest
import os
import yaml
from unittest.mock import patch, mock_open

from utils.config_loader import load_config, get_config, ConfigError


class TestConfigLoader:
    """Test suite for configuration loader."""
    
    def test_load_config_success(self, tmp_path, sample_config):
        """Test loading valid config file."""
        # Create temp config file
        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            yaml.dump(sample_config, f)
        
        with patch("utils.config_loader.get_config_path") as mock_path:
            mock_path.return_value = str(config_file)
            config = load_config(force_reload=True)
        
        assert config["MODEL"] == "llama3.1:8b"
        assert config["CONTEXT_LIMIT"] == 32000
    
    def test_load_config_file_not_found(self):
        """Test loading when file doesn't exist."""
        with patch("os.path.exists", return_value=False):
            config = load_config(force_reload=True)
        
        # Should return defaults
        assert "MODEL" in config
    
    def test_get_config_with_default(self):
        """Test get_config with default value."""
        with patch("utils.config_loader._config", {"MODEL": "test"}):
            result = get_config("NONEXISTENT", "default")
            assert result == "default"
    
    def test_load_config_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            f.write("invalid: yaml: content: [")
        
        with patch("utils.config_loader.get_config_path") as mock_path:
            mock_path.return_value = str(config_file)
            with pytest.raises(ConfigError):
                load_config(force_reload=True)
    
    def test_validate_config_invalid_context_limit(self):
        """Test validation of invalid context limit."""
        from utils.config_loader import _validate_config
        
        config = {"CONTEXT_LIMIT": "invalid"}
        with pytest.raises(ConfigError):
            _validate_config(config)


class TestConfigDefaults:
    """Test default configuration values."""
    
    def test_default_model(self):
        """Test default model value."""
        from utils.config_loader import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["MODEL"] == "qwen3:8b"
    
    def test_default_context_limit(self):
        """Test default context limit."""
        from utils.config_loader import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["CONTEXT_LIMIT"] == 30000
