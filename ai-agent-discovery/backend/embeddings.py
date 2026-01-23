import os
from langchain_community.embeddings import OllamaEmbeddings
from dotenv import load_dotenv

load_dotenv()

class EmbeddingService:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            model = os.getenv("MODEL_NAME", "llama3.2")
            print(f"Initializing Embeddings with model={model} at {base_url}")
            cls._instance = OllamaEmbeddings(
                base_url=base_url,
                model=model
            )
        return cls._instance

def get_embeddings():
    return EmbeddingService.get_instance()
