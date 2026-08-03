import logging
import os
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from typing import List, Dict
from models import Agent
from embeddings import get_embeddings

import config

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self, persist_directory=None, embedding_function=None):
        self.persist_directory = str(persist_directory or config.FAISS_DIR)
        self.embedding_function = embedding_function or get_embeddings()
        self.vector_store = None
        self.load_store()

    def load_store(self):
        try:
            if os.path.exists(self.persist_directory) and os.path.exists(os.path.join(self.persist_directory, "index.faiss")):
                self.vector_store = FAISS.load_local(
                    self.persist_directory,
                    self.embedding_function,
                    allow_dangerous_deserialization=True # Local execution, safe.
                )
            else:
                self.vector_store = None
        except Exception as e:
            logger.warning("Could not load vector store from %s: %s", self.persist_directory, e)
            self.vector_store = None

    def add_agents(self, agents: List[Agent]):
        """Adds a list of agents to the vector store"""
        documents = []
        for agent in agents:
            doc = Document(
                page_content=agent.page_content,
                metadata=agent.metadata
            )
            documents.append(doc)
        
        if self.vector_store:
            self.vector_store.add_documents(documents)
        else:
            self.vector_store = FAISS.from_documents(documents, self.embedding_function)
        
        # Save locally
        self.vector_store.save_local(self.persist_directory)
        logger.info("Added %d agents to vector store at %s", len(agents), self.persist_directory)

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Semantic search for agents"""
        if not self.vector_store:
            return []

        results = self.vector_store.similarity_search_with_score(query, k=limit)
        
        # Format results
        agents = []
        for doc, score in results:
            agents.append({
                "name": doc.metadata.get("name"),
                "description": doc.page_content, 
                "metadata": doc.metadata,
                "distance": float(score)
            })
        
        return agents

    def get_all_agents(self) -> List[Dict]:
        """Retrieve all agents (limit to 100 for now)"""
        if not self.vector_store:
            return []
        
        # FAISS doesn't support "get all" easily without iterating info.
        # We can reconstruct from docstore if needed, but for now validation,
        # let's rely on the backing docstore if simple, or just return empty/load from JSON if request.
        # However, to support the dashboard, let's try to fetch from docstore.
        
        agents = []
        # Accessing private docstore is hacky but common in FAISS wrapper usage for this.
        # Alternatively, we should use the JSON file for "get_all".
        try:
            for doc_id, doc in self.vector_store.docstore._dict.items():
                agents.append({
                    "name": doc.metadata.get("name"),
                    "metadata": doc.metadata
                })
        except:
             # Fallback if docstore access fails
             pass
             
        return agents

    def get_stats(self):
        count = 0
        if self.vector_store:
            count = self.vector_store.index.ntotal
        return {
            "count": count
        }
