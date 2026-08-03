from langchain_community.embeddings import OllamaEmbeddings

import config


class EmbeddingService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            print(f"Initializing Embeddings with model={config.MODEL_NAME} at {config.OLLAMA_BASE_URL}")
            cls._instance = OllamaEmbeddings(
                base_url=config.OLLAMA_BASE_URL,
                model=config.MODEL_NAME
            )
        return cls._instance


def get_embeddings():
    return EmbeddingService.get_instance()
