import logging

from langchain_community.embeddings import OllamaEmbeddings

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


def get_embeddings():
    return EmbeddingService.get_instance()
