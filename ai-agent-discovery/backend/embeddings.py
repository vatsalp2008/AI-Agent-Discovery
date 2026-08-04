import logging

# langchain_community.embeddings.OllamaEmbeddings is deprecated; the Ollama
# integration now lives in its own langchain-ollama package.
from langchain_ollama import OllamaEmbeddings

import config

logger = logging.getLogger(__name__)


class EmbeddingService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            logger.info("Initializing embeddings with model=%s at %s", config.MODEL_NAME, config.OLLAMA_BASE_URL)
            cls._instance = OllamaEmbeddings(
                base_url=config.OLLAMA_BASE_URL,
                model=config.MODEL_NAME
            )
        return cls._instance

    @classmethod
    def reset(cls):
        """Drop the cached client so config changes take effect. Used by tests."""
        cls._instance = None


def get_embeddings():
    return EmbeddingService.get_instance()
