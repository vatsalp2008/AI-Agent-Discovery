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
    # Sidecar file recording which embedding model built the index.
    META_FILENAME = "index_meta.json"

    def __init__(self, persist_directory=None, embedding_function=None, embedding_model=None):
        self.persist_directory = str(persist_directory or config.FAISS_DIR)
        self.embedding_function = embedding_function or get_embeddings()
        self.embedding_model = embedding_model or config.EMBEDDING_MODEL
        self.vector_store = None
        # Set when an existing index was built by a different embedding model.
        self.stale_model = None
        self.load_store()

    @property
    def meta_path(self) -> str:
        return os.path.join(self.persist_directory, self.META_FILENAME)

    def _read_meta(self) -> Dict:
        try:
            with open(self.meta_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_meta(self, agent_count: int) -> None:
        try:
            os.makedirs(self.persist_directory, exist_ok=True)
            with open(self.meta_path, "w") as f:
                json.dump({"embedding_model": self.embedding_model, "agent_count": agent_count}, f, indent=2)
        except OSError as e:
            logger.warning("Could not write %s: %s", self.meta_path, e)

    def _is_stale(self) -> bool:
        """True when the index was built by a different embedding model.

        Vectors from one model are meaningless to another (and usually a
        different width), so loading such an index yields garbage rankings or
        a dimension error deep inside FAISS. Detect it up front instead.

        An index with no sidecar predates this check; assume it matches rather
        than forcing an unnecessary re-seed.
        """
        recorded = self._read_meta().get("embedding_model")
        if recorded is None:
            return False
        return recorded != self.embedding_model

    def load_store(self):
        try:
            if os.path.exists(self.persist_directory) and os.path.exists(os.path.join(self.persist_directory, "index.faiss")):
                if self._is_stale():
                    self.stale_model = self._read_meta().get("embedding_model")
                    logger.error(
                        "Index at %s was built with embedding model %r but the configured model is %r. "
                        "Re-run seed.py to rebuild it.",
                        self.persist_directory, self.stale_model, self.embedding_model,
                    )
                    self.vector_store = None
                    return
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

    def replace_agents(self, agents: List[Agent]):
        """Rebuild the index from scratch so re-seeding cannot duplicate entries."""
        self.vector_store = None
        self.add_agents(agents)

    def add_agents(self, agents: List[Agent]):
        """Adds a list of agents to the vector store"""
        if not agents:
            logger.warning("No agents to index; leaving the vector store unchanged.")
            return

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
        self._write_meta(self.vector_store.index.ntotal)
        logger.info("Added %d agents to vector store at %s", len(agents), self.persist_directory)

    # When filtering by category we over-fetch, since the nearest neighbours
    # overall may all belong to other categories.
    CATEGORY_OVERFETCH = 5

    def search(self, query: str, limit: int = None, category: str = None) -> List[Dict]:
        """Semantic search for agents, best match first.

        When `category` is given, only agents in that category are returned
        (case-insensitive).
        """
        if not self.vector_store:
            return []

        limit = limit or config.SEARCH_DEFAULT_LIMIT
        k = limit * self.CATEGORY_OVERFETCH if category else limit
        results = self.vector_store.similarity_search_with_score(query, k=k)

        wanted = category.strip().casefold() if category else None

        # Format results
        agents = []
        for doc, distance in results:
            if wanted and (doc.metadata.get("category") or "").casefold() != wanted:
                continue
            agents.append({
                "name": doc.metadata.get("name"),
                "description": doc.page_content,
                "metadata": doc.metadata,
                "distance": float(distance),
                "score": relevance_score(distance)
            })

        agents.sort(key=lambda agent: agent["score"], reverse=True)
        return agents[:limit]

    def get_categories(self) -> List[Dict]:
        """Return the indexed categories with agent counts, most common first."""
        counts = {}
        for agent in self.get_all_agents():
            category = agent["metadata"].get("category") or "Uncategorized"
            counts[category] = counts.get(category, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

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
