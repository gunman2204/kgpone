import logging
from qdrant_client import QdrantClient
from src.config.settings import Settings

logger = logging.getLogger("qdrant_config")

_cloud_client = None
_local_client = None

def get_qdrant_client():
    """Initializes and returns the Cloud Qdrant client singleton."""
    global _cloud_client
    if _cloud_client is None:
        try:
            _cloud_client = QdrantClient(
                url=Settings.QDRANT_URL,
                api_key=Settings.QDRANT_API_KEY or None,
                timeout=5.0
            )
            # Test connection
            _cloud_client.get_collections()
            logger.info(f"Successfully connected to Cloud Qdrant at {Settings.QDRANT_URL}")
        except Exception as e:
            logger.warning(f"Failed to connect to Cloud Qdrant: {e}. Vector search will fail if online.")
            _cloud_client = None
    return _cloud_client

def get_local_qdrant_client():
    """Initializes and returns the Local Qdrant client singleton (for offline/dropzone usage)."""
    global _local_client
    if _local_client is None:
        try:
            import os
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            local_qdrant_dir = os.path.join(backend_dir, "qdrant_local_data")
            os.makedirs(local_qdrant_dir, exist_ok=True)
            _local_client = QdrantClient(path=local_qdrant_dir)
            logger.info(f"Successfully initialized Local Qdrant with local disk storage at {local_qdrant_dir}.")
        except Exception as e:
            logger.error(f"Failed to initialize Local Qdrant: {e}")
            _local_client = None
    return _local_client
