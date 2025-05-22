import logging
import yaml
import os
from typing import Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class ContextStorageSettings(BaseModel):
    """
    Settings for context storage configuration, supporting local and MinIO backends.
    """
    type: str = Field(default="local", description="Storage type: 'local' or 'minio'")
    options: Dict[str, Any] = Field(default_factory=dict, description="Storage backend options")
    
    @classmethod
    def from_yaml(cls, config_path: str = "./config/configuration.yaml") -> "ContextStorageSettings":
        """
        Load settings from YAML configuration file.
        """
        try:
            if not os.path.exists(config_path):
                logger.warning(f"Configuration file not found: {config_path}")
                return cls()
                
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
                
            if not config:
                logger.warning(f"Empty or invalid configuration file: {config_path}")
                return cls()
                
            context_storage_config = config.get("context_storage", {})
            if not context_storage_config:
                logger.warning(f"No 'context_storage' section found in {config_path}, using defaults")
                
            return cls(
                type=context_storage_config.get("type", "local"),
                options=context_storage_config.get("options", {})
            )
        except Exception as e:
            logger.warning(f"Error loading context_storage config from {config_path}: {str(e)}")
            logger.warning("Using default context storage settings")
            return cls()
            
    def get_storage_path(self) -> str:
        """
        Get the storage path for local storage, expanding user directory if needed.
        Always returns a valid path, even for MinIO storage (for fallback purposes).
        """
        # Default path if nothing is configured
        default_path = "~/.fred/context-store"
        
        # For local storage, use configured path or default
        if self.type.lower() == "local":
            path = self.options.get("path", default_path)
        else:
            # For non-local storage (minio), still provide default path for fallback
            path = self.options.get("fallback_path", default_path)
            
        # Ensure we always return an expanded path
        return os.path.expanduser(path)

# Default singleton instance
try:
    context_storage_settings = ContextStorageSettings.from_yaml()
except Exception as e:
    logger.error(f"Failed to load context storage settings: {e}")
    context_storage_settings = ContextStorageSettings()