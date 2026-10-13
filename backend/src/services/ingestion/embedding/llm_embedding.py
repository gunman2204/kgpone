import asyncio
import logging
import time
from src.services.ingestion.embedding.base import BaseEmbedder
from src.infrastructure.llm_factory import LLMFactory

logger = logging.getLogger("llm_embedding")

class LLMEmbedder(BaseEmbedder):
    def __init__(self):
        self.factory = LLMFactory()
        try:
            self.embedder = self.factory.get_embeddings()
        except Exception as e:
            logger.error(f"Failed to initialize embeddings from LLMFactory: {e}. Falling back to offline text hashing.")
            self.embedder = None
            self.use_fallback = True
        else:
            self.use_fallback = False

    async def embed(self, chunks: list[str]) -> list[list[float]]:
        if self.use_fallback or not self.embedder:
            import hashlib
            from src.config.settings import Settings
            vectors = []
            for chunk in chunks:
                h = hashlib.sha256(chunk.encode("utf-8")).digest()
                dim = Settings.EMBEDDING_DIMENSION
                # Create a float vector deterministically from the hash matching the required dimension
                vec = []
                for i in range(dim):
                    val = h[i % len(h)] / 255.0
                    vec.append(val)
                vectors.append(vec)
            return vectors

        # Batching and Retry Logic for strict Rate Limits (e.g. Gemini 100 RPM free tier)
        # We process chunks in batches of 50 to avoid hitting limits instantly.
        batch_size = 50
        all_embeddings = []
        
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            max_retries = 5
            retry_delay = 65  # Google's limit is per minute, so waiting 65s guarantees a reset
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"Embedding batch {i//batch_size + 1}/{(len(chunks) - 1)//batch_size + 1} ({len(batch)} chunks)...")
                    batch_embeddings = await self.embedder.aembed_documents(batch)
                    all_embeddings.extend(batch_embeddings)
                    break  # Success, move to next batch
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "Quota exceeded" in error_msg:
                        if attempt < max_retries - 1:
                            logger.warning(f"Rate limit hit during embedding. Sleeping for {retry_delay}s to let quota reset... (Attempt {attempt + 1}/{max_retries})")
                            await asyncio.sleep(retry_delay)
                            retry_delay += 10  # Add a little more padding each retry
                        else:
                            logger.error(f"Failed to embed batch after {max_retries} attempts due to rate limit.")
                            raise
                    else:
                        logger.warning(f"Unexpected embedding error ({error_msg}). Falling back to local offline embeddings.")
                        self.use_fallback = True
                        return await self.embed(chunks)
                        
            # Add a small delay between successful batches to prevent bursting
            if i + batch_size < len(chunks):
                await asyncio.sleep(2)
                
        return all_embeddings

    async def embed_query(self, query: str) -> list[float]:
        if self.use_fallback or not self.embedder:
            vectors = await self.embed([query])
            return vectors[0]

        try:
            query_embedding = await self.embedder.aembed_query(query)
            return query_embedding
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                logger.warning(f"Rate limit hit during query embedding ({error_msg}). Falling back to local offline embeddings.")
            else:
                logger.warning(f"Query embedding failed ({error_msg}). Falling back to local offline embeddings.")
            self.use_fallback = True
            vectors = await self.embed([query])
            return vectors[0]
