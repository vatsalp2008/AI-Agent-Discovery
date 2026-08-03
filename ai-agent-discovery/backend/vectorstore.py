import json
import logging
import os
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from typing import List, Dict
from models import Agent
from embeddings import get_embeddings
from scoring import relevance_score

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

    def search(self, query: str, limit: int = None) -> List[Dict]:
        """Semantic search for agents, best match first."""
        if not self.vector_store:
            return []

        limit = limit or config.SEARCH_DEFAULT_LIMIT
        results = self.vector_store.similarity_search_with_score(query, k=limit)

        # Format results
        agents = []
        for doc, distance in results:
            agents.append({
                "name": doc.metadata.get("name"),
                "description": doc.page_content,
                "metadata": doc.metadata,
                "distance": float(distance),
                "score": relevance_score(distance)
            })

        agents.sort(key=lambda agent: agent["score"], reverse=True)
        return agents

    def get_all_agents(self) -> List[Dict]:
        """Retrieve every indexed agent, sorted by name.

        FAISS has no public "list everything" API, so this walks the backing
        docstore. If that internal layout ever changes, fall back to the
        seeded JSON file rather than pretending the index is empty.
        """
        documents = self._iter_documents()
        if documents is None:
            return self._agents_from_json()

        agents = [
            {
                "name": doc.metadata.get("name"),
                "description": doc.metadata.get("description", ""),
                "metadata": doc.metadata,
            }
            for doc in documents
        ]
        agents.sort(key=lambda agent: (agent["name"] or "").lower())
        return agents

    def _iter_documents(self):
        """Return the indexed documents, or None if the docstore is unreadable."""
        if not self.vector_store:
            return None
        try:
            return list(self.vector_store.docstore._dict.values())
        except AttributeError as e:
            logger.warning("Could not read FAISS docstore (%s); falling back to %s", e, config.AGENTS_JSON)
            return None

    def _agents_from_json(self) -> List[Dict]:
        """Load agents straight from the seeded JSON file."""
        if not os.path.exists(config.AGENTS_JSON):
            return []
        try:
            with open(config.AGENTS_JSON) as f:
                records = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Could not read %s: %s", config.AGENTS_JSON, e)
            return []

        agents = [
            {
                "name": record.get("name"),
                "description": record.get("description", ""),
                "metadata": Agent.from_dict(record).metadata,
            }
            for record in records
        ]
        agents.sort(key=lambda agent: (agent["name"] or "").lower())
        return agents

    def get_stats(self):
        count = 0
        if self.vector_store:
            count = self.vector_store.index.ntotal
        return {
            "count": count
        }
