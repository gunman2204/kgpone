import logging
from qdrant_client import QdrantClient
from src.config.settings import Settings

logger = logging.getLogger("qdrant_config")

_client = None

def get_qdrant_client():
    """Initializes and returns the Qdrant client singleton."""
    global _client
    if _client is None:
        try:
            if Settings.OFFLINE_MODE:
                logger.info("OFFLINE_MODE: Initializing Qdrant with local disk storage.")
                import os
                os.makedirs("./qdrant_local_data", exist_ok=True)
                _client = QdrantClient(path="./qdrant_local_data")
            else:
                _client = QdrantClient(
                    url=Settings.QDRANT_URL,
                    api_key=Settings.QDRANT_API_KEY or None,
                    timeout=3.0
                )
                # Test connection
                _client.get_collections()
                logger.info(f"Successfully connected to Qdrant at {Settings.QDRANT_URL}")
        except Exception as e:
            logger.warning(f"Failed to connect to Qdrant: {e}. Repo will fall back to in-memory mock mode.")
            _client = None
    return _client
