import logging

import config

logger = logging.getLogger(__name__)


class EmbeddingService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            # Deferred: importing langchain_ollama costs ~70ms and is only
            # needed once something actually embeds text.
            # langchain_community.embeddings.OllamaEmbeddings is deprecated;
            # the Ollama integration lives in its own langchain-ollama package.
            from langchain_ollama import OllamaEmbeddings

            logger.info("Initializing embeddings with model=%s at %s", config.EMBEDDING_MODEL, config.OLLAMA_BASE_URL)
            client = OllamaEmbeddings(
                base_url=config.OLLAMA_BASE_URL,
                model=config.EMBEDDING_MODEL
            )
            # Serve repeat queries from disk; see embedding_cache for why the
            # embedding rather than the result set is what gets persisted.
            if config.EMBEDDING_CACHE_SIZE > 0:
                from embedding_cache import CachedEmbeddings

                client = CachedEmbeddings(client)
            cls._instance = client
        return cls._instance

    @classmethod
    def reset(cls):
        """Drop the cached client so config changes take effect. Used by tests."""
        cls._instance = None


def get_embeddings():
    return EmbeddingService.get_instance()


def save_cache():
    """Flush the embedding cache to disk. Safe to call when nothing is cached."""
    client = EmbeddingService._instance
    cache = getattr(client, "cache", None)
    if cache is not None:
        cache.save()
