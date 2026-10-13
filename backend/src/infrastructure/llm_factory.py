import logging
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from src.utils.interfaces import ILLMFactory
from src.config.settings import Settings

logger = logging.getLogger("llm_factory")

_embeddings_cache = {}

class LLMFactory(ILLMFactory):
    def get_llm(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        provider = Settings.AI_PROVIDER
        api_key = Settings.AI_API_KEY
        model = model_name or Settings.AI_MODEL

        if not api_key and provider != "ollama":
            logger.error(f"AI_API_KEY is missing for provider: {provider}")
            raise ValueError(f"AI_API_KEY is not set for AI_PROVIDER={provider}")

        return self._build_llm(provider, api_key, model, **kwargs)

    def get_llm_for_request(
        self,
        byok_provider: str | None = None,
        byok_api_key: str | None = None,
        byok_model: str | None = None,
        **kwargs,
    ) -> BaseChatModel:
        """
        Returns an LLM using BYOK credentials if provided, otherwise falls back
        to environment-configured settings. Keys are NEVER stored — used per-request only.
        """
        if byok_provider and byok_api_key:
            logger.info(f"Using BYOK LLM: provider={byok_provider}, model={byok_model or '(default)'}")
            return self._build_llm(byok_provider, byok_api_key, byok_model, **kwargs)
        return self.get_llm(**kwargs)

    def _build_llm(self, provider: str, api_key: str, model: str | None, **kwargs) -> BaseChatModel:
        """Internal: constructs the LLM for the given provider / key / model."""
        if provider == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model or "gpt-4o-mini", api_key=api_key, **kwargs)

        elif provider == "groq":
            from langchain_groq import ChatGroq
            return ChatGroq(model=model or "llama-3.3-70b-versatile", api_key=api_key, **kwargs)

        elif provider == "huggingface":
            from langchain_huggingface import HuggingFaceEndpoint
            from langchain_community.chat_models.huggingface import ChatHuggingFace
            llm = HuggingFaceEndpoint(repo_id=model or "meta-llama/Meta-Llama-3-8B-Instruct", huggingfacehub_api_token=api_key, **kwargs)
            return ChatHuggingFace(llm=llm)

        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model or "gemini-3.5-flash-lite", google_api_key=api_key, **kwargs)

        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model or "claude-3-5-sonnet-20241022", api_key=api_key, **kwargs)

        elif provider == "ollama":
            try:
                from langchain_ollama import ChatOllama
                return ChatOllama(model=model or "phi3:mini", base_url="http://127.0.0.1:11434", timeout=15.0, **kwargs)
            except ImportError:
                from langchain_community.chat_models import ChatOllama
                return ChatOllama(model=model or "phi3:mini", base_url="http://127.0.0.1:11434", timeout=15.0, **kwargs)

        else:
            logger.error(f"Unsupported AI provider: {provider}")
            raise ValueError(f"Unsupported AI provider: {provider}")

    def get_offline_llm(self, model_name: str | None = None, **kwargs) -> BaseChatModel:
        """Returns local Ollama LLM optimized for fast CPU inference."""
        model = model_name or "phi3:mini"
        params = {"num_predict": 350, "temperature": 0.2}
        params.update(kwargs)
        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(model=model, base_url="http://127.0.0.1:11434", timeout=30.0, **params)
        except ImportError:
            from langchain_community.chat_models import ChatOllama
            return ChatOllama(model=model, base_url="http://127.0.0.1:11434", timeout=30.0, **params)



    def get_embeddings(self, model_name: str | None = None, **kwargs) -> Embeddings:
        provider = Settings.EMBEDDING_PROVIDER
        api_key = Settings.EMBEDDING_API_KEY
        model = model_name or Settings.EMBEDDING_MODEL
        cache_key = f"{provider}:{model}"

        if cache_key in _embeddings_cache:
            return _embeddings_cache[cache_key]
        
        embedder = None
        if provider == "local":
            from langchain_huggingface import HuggingFaceEmbeddings
            embedder = HuggingFaceEmbeddings(model_name=model or "BAAI/bge-small-en-v1.5", **kwargs)
            
        elif provider == "infinity":
            from langchain_openai import OpenAIEmbeddings
            base_url = Settings.INFINITY_URL
            
            # Infinity provides an OpenAI compatible API at the root
            embedder = OpenAIEmbeddings(
                model=model or "BAAI/bge-small-en-v1.5",
                base_url=base_url,
                api_key="infinity", # API key is required by library but ignored by server
                check_embedding_ctx_length=False,
                **kwargs
            )
            
        elif provider == "openai":
            if not api_key:
                logger.error(f"EMBEDDING_API_KEY is missing for provider: {provider}")
                raise ValueError(f"EMBEDDING_API_KEY is not set for EMBEDDING_PROVIDER={provider}")
            from langchain_openai import OpenAIEmbeddings
            # Force 768 dimensions for OpenAI (only works on text-embedding-3 models) to match Qdrant
            embedder = OpenAIEmbeddings(model=model or "text-embedding-3-small", api_key=api_key, dimensions=768, **kwargs)
            
        elif provider == "huggingface":
            if not api_key:
                logger.error(f"EMBEDDING_API_KEY is missing for provider: {provider}")
                raise ValueError(f"EMBEDDING_API_KEY is not set for EMBEDDING_PROVIDER={provider}")
            from langchain_huggingface import HuggingFaceEndpointEmbeddings
            embedder = HuggingFaceEndpointEmbeddings(model=model or "sentence-transformers/all-MiniLM-L6-v2", huggingfacehub_api_token=api_key, **kwargs)
            
        elif provider == "gemini":
            if not api_key:
                logger.error(f"EMBEDDING_API_KEY is missing for provider: {provider}")
                raise ValueError(f"EMBEDDING_API_KEY is not set for EMBEDDING_PROVIDER={provider}")
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            embedder = GoogleGenerativeAIEmbeddings(model=model or "models/gemini-embedding-2", google_api_key=api_key, **kwargs)
            
        else:
            logger.error(f"Unsupported EMBEDDING_PROVIDER: {provider}")
            raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")

        _embeddings_cache[cache_key] = embedder
        return embedder
