import os
from dotenv import load_dotenv

# Ensure environment variables are loaded from the backend directory
load_dotenv()

class Settings:
    # Offline Mode Toggle
    OFFLINE_MODE = os.getenv("OFFLINE_MODE", "False").lower() == "true"

    # Database Settings
    _default_db = "sqlite:///./kgpone_offline.db" if OFFLINE_MODE else "postgresql://user:password@localhost:5432/kgpone"
    DATABASE_URL = _default_db if OFFLINE_MODE else os.getenv("DATABASE_URL", _default_db)

    # Qdrant Settings
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

    # Neo4j Settings
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

    # S3 / AWS Settings
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "kgpone-assets")
    EXTERNAL_S3_ENDPOINT_URL = os.getenv("EXTERNAL_S3_ENDPOINT_URL", "")

    # Celery / Redis Settings
    if OFFLINE_MODE:
        CELERY_BROKER_URL = "sqla+sqlite:///./celery_offline.sqlite"
        CELERY_RESULT_BACKEND = "db+sqlite:///./celery_offline.sqlite"
    else:
        CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    # AI Providers Configuration
    if OFFLINE_MODE:
        AI_PROVIDER = "ollama"
        AI_MODEL = "phi3:mini"
        EMBEDDING_PROVIDER = "infinity"
    else:
        AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
        AI_MODEL = os.getenv("AI_MODEL", "")
        EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini").lower()
        
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))
    EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")

    # Auth Settings
    SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-for-development")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # HuggingFace Inference API (for cross-encoder reranking)
    HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
    RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")

    # Local Infinity URL
    INFINITY_URL = os.getenv("INFINITY_URL", "http://host.docker.internal:7997")

    # Semantic Cache Settings
    REDIS_CACHE_URL = os.getenv("REDIS_CACHE_URL", "redis://localhost:6379/1")
    SEMANTIC_CACHE_TTL = int(os.getenv("SEMANTIC_CACHE_TTL", "3600"))

