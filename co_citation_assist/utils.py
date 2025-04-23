import os
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

def load_env_file(env_path: Optional[Path] = None) -> Dict[str, str]:
    """
    Load environment variables from a .env file.
    
    Args:
        env_path: Path to the .env file. If None, looks for .env in the project root.
    
    Returns:
        Dictionary of environment variables loaded from the file.
    """
    if env_path is None:
        # Look for .env in various locations (project root, parent dirs)
        possible_locations = [
            Path.cwd() / ".env",  # Current working directory
            Path(__file__).parent.parent / ".env",  # Project root
            Path.home() / ".co-citation-assist.env",  # User's home directory
        ]
        
        for loc in possible_locations:
            if loc.exists():
                env_path = loc
                logger.debug(f"Found .env file at {env_path}")
                break
    
    env_vars = {}
    if env_path and env_path.exists():
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse KEY=VALUE format
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Remove quotes if present
                        if value and value[0] == value[-1] and value[0] in ('"', "'"):
                            value = value[1:-1]
                        
                        env_vars[key] = value
                        # Don't set in os.environ by default - let caller decide
        
            logger.info(f"Loaded {len(env_vars)} environment variables from {env_path}")
        except Exception as e:
            logger.warning(f"Error loading .env file at {env_path}: {e}")
    else:
        logger.debug("No .env file found")
    
    return env_vars

def get_openalex_email() -> str:
    """
    Get the email address to use for OpenAlex API requests.
    
    Checks:
    1. OPENALEX_EMAIL environment variable
    2. .env file
    3. Falls back to anonymous email
    
    Returns:
        Email address to use for API requests
    """
    # First check actual environment variable
    email = os.environ.get("OPENALEX_EMAIL")
    
    if not email:
        # Try loading from .env file
        env_vars = load_env_file()
        email = env_vars.get("OPENALEX_EMAIL")
    
    # Fallback to anonymous
    if not email or not isinstance(email, str) or '@' not in email:
        email = "anonymous@example.com"
        logger.debug("Using anonymous email for OpenAlex API")
    else:
        logger.debug(f"Using email {email} for OpenAlex API")
    
    return email 