import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

import config
from embeddings import get_embeddings
from models import Agent
from scoring import relevance_score

logger = logging.getLogger(__name__)

class VectorStore:
    # Sidecar file recording which embedding model built the index.
    META_FILENAME = "index_meta.json"

    # A seed writes the sidecar (from add_agents) before rewriting
    # agents.json, and built_at is stored to whole seconds, so the catalogue
    # is legitimately a shade newer than the index every time. Only a gap
    # larger than this means a human edited the file afterwards.
    FRESHNESS_GRACE_SECONDS = 5

    def __init__(self, persist_directory=None, embedding_function=None, embedding_model=None):
        self.persist_directory = str(persist_directory or config.FAISS_DIR)
        self.embedding_function = embedding_function or get_embeddings()
        self.embedding_model = embedding_model or config.EMBEDDING_MODEL
        self.vector_store = None
        # Set when an existing index was built by a different embedding model.
        self.stale_model = None
        self._search_cache = OrderedDict()
        # Memoized agent list and name index; both rebuilt when the index changes.
        self._agents = None
        self._agents_by_name = None
        self.load_store()

    @property
    def meta_path(self) -> str:
        return os.path.join(self.persist_directory, self.META_FILENAME)

    def _read_meta(self) -> dict:
        try:
            with open(self.meta_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_meta(self, agent_count: int) -> None:
        try:
            os.makedirs(self.persist_directory, exist_ok=True)
            with open(self.meta_path, "w") as f:
                json.dump({
                    "embedding_model": self.embedding_model,
                    "agent_count": agent_count,
                    # UTC ISO-8601, so an operator can tell at a glance whether
                    # the index predates the current agents.json.
                    "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }, f, indent=2)
        except OSError as e:
            logger.warning("Could not write %s: %s", self.meta_path, e)

    @property
    def built_at(self):
        """When the index was last rebuilt, or None for older indexes."""
        return self._read_meta().get("built_at")

    @property
    def catalogue_is_stale(self):
        """True when agents.json has been edited since the index was built.

        Editing the catalogue without re-seeding is easy to do and silent:
        searches keep working, they just return the previous contents. Compare
        file mtime against the recorded build time so it can be surfaced.

        None when it cannot be determined (no sidecar, or no catalogue file).
        """
        built = self.built_at
        if not built or not os.path.exists(config.AGENTS_JSON):
            return None
        try:
            built_ts = datetime.fromisoformat(built).timestamp()
        except ValueError:
            return None
        return os.path.getmtime(config.AGENTS_JSON) > built_ts + self.FRESHNESS_GRACE_SECONDS

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
            index_file = os.path.join(self.persist_directory, "index.faiss")
            if os.path.exists(self.persist_directory) and os.path.exists(index_file):
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

    def replace_agents(self, agents: list[Agent]):
        """Rebuild the index from scratch so re-seeding cannot duplicate entries."""
        self.vector_store = None
        self.add_agents(agents)

    def add_agents(self, agents: list[Agent]):
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
        self.clear_cache()  # cached results no longer reflect the index
        logger.info("Added %d agents to vector store at %s", len(agents), self.persist_directory)

    # When filtering by category we over-fetch, since the nearest neighbours
    # overall may all belong to other categories.
    CATEGORY_OVERFETCH = 5

    def search(self, query: str, limit: int = None, category: str = None,
               min_score: float = None) -> list[dict]:
        """Semantic search for agents, best match first.

        When `category` is given, only agents in that category are returned
        (case-insensitive). When `min_score` is given, weaker matches are
        dropped entirely; by default nothing is filtered and callers decide
        what to do with low scores.

        Results are cached per (query, limit, category): embedding the query
        means a round trip to Ollama, which dominates the cost of a repeat
        search. The cache is dropped whenever the index changes.
        """
        if not self.vector_store:
            return []

        limit = limit or config.SEARCH_DEFAULT_LIMIT
        cache_key = (query.casefold(), limit, (category or "").casefold(), min_score)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

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
                # The plain description, not the composite text that was
                # embedded; that is exposed separately as matched_text.
                "description": doc.metadata.get("description", ""),
                "matched_text": doc.page_content,
                "metadata": doc.metadata,
                "distance": float(distance),
                "score": relevance_score(distance)
            })

        agents.sort(key=lambda agent: agent["score"], reverse=True)
        if min_score is not None:
            agents = [a for a in agents if a["score"] >= min_score]
        agents = agents[:limit]
        self._cache_put(cache_key, agents)
        return agents

    def _cache_get(self, key):
        """Return a cached result list, refreshing its recency."""
        if key not in self._search_cache:
            return None
        self._search_cache.move_to_end(key)
        # Hand back copies so a caller mutating a result cannot poison the cache.
        return [dict(result) for result in self._search_cache[key]]

    def _cache_put(self, key, results):
        if config.SEARCH_CACHE_SIZE <= 0:
            return
        self._search_cache[key] = [dict(result) for result in results]
        self._search_cache.move_to_end(key)
        while len(self._search_cache) > config.SEARCH_CACHE_SIZE:
            self._search_cache.popitem(last=False)

    def clear_cache(self):
        """Drop every derived cache. Called whenever the index changes."""
        self._search_cache.clear()
        self._agents = None
        self._agents_by_name = None

    def get_categories(self) -> list[dict]:
        """Return the indexed categories with agent counts, most common first."""
        counts = {}
        for agent in self.get_all_agents():
            category = agent["metadata"].get("category") or "Uncategorized"
            counts[category] = counts.get(category, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def get_all_agents(self) -> list[dict]:
        """Retrieve every indexed agent, sorted by name.

        Memoized: walking the docstore, building dicts and sorting is pure
        work that only changes when the index does. /api/stats alone used to
        trigger it twice per request (once directly, once via get_categories).

        The list is copied on the way out so a caller cannot mutate the cache;
        the agent dicts themselves are shared, as they always have been.
        """
        if self._agents is None:
            self._agents = self._build_agents()
        return list(self._agents)

    def _build_agents(self) -> list[dict]:
        """Assemble the agent list from the docstore.

        FAISS has no public "list everything" API, so this walks the backing
        docstore. If that internal layout ever changes, fall back to the
        seeded JSON file rather than pretending the index is empty.

        An absent index is a different situation: an unseeded app must look
        empty everywhere rather than serving the raw JSON catalogue while
        reporting zero indexed vectors.
        """
        if not self.vector_store:
            return []

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

    def find_similar(self, name: str, limit: int = None) -> list[dict]:
        """Agents most like the named one, excluding itself.

        Over-fetches by one and drops the agent from its own results, so a
        request for N neighbours actually returns N rather than N-1.
        Returns None when the agent does not exist, to distinguish that from
        an agent that genuinely has no neighbours.
        """
        agent = self.get_agent(name)
        if agent is None:
            return None

        limit = limit or config.SEARCH_DEFAULT_LIMIT
        query = agent["metadata"].get("description") or agent["name"]
        results = self.search(query, limit=limit + 1)

        wanted = (agent["name"] or "").casefold()
        return [r for r in results if (r["name"] or "").casefold() != wanted][:limit]

    def get_tech_stacks(self) -> list[dict]:
        """Return the indexed technologies with agent counts, most common first.

        `stack` is stored as a comma-joined string (FAISS metadata values must
        be scalars), so it is split back apart here.
        """
        counts = {}
        for agent in self.get_all_agents():
            for tech in str(agent["metadata"].get("stack") or "").split(","):
                tech = tech.strip()
                if tech:
                    counts[tech] = counts.get(tech, 0) + 1
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def get_agent(self, name: str) -> dict:
        """Look up a single agent by name (case-insensitive), or None."""
        if not name:
            return None
        if self._agents_by_name is None:
            self._agents_by_name = {
                (agent["name"] or "").casefold(): agent
                for agent in self.get_all_agents()
            }
        return self._agents_by_name.get(name.strip().casefold())

    def _iter_documents(self):
        """Return the indexed documents, or None if the docstore is unreadable."""
        try:
            return list(self.vector_store.docstore._dict.values())
        except AttributeError as e:
            logger.warning("Could not read FAISS docstore (%s); falling back to %s", e, config.AGENTS_JSON)
            return None

    def _agents_from_json(self) -> list[dict]:
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

    def get_stats(self) -> dict:
        """Summarize the index.

        The dashboard used to download every agent to work these out in the
        browser; computing them here keeps that page to a small response.
        """
        count = 0
        if self.vector_store:
            count = self.vector_store.index.ntotal

        categories = self.get_categories()
        total_stars = sum(
            int(agent["metadata"].get("stars") or 0)
            for agent in self.get_all_agents()
        )

        return {
            "count": count,
            "categories": len(categories),
            "top_category": categories[0] if categories else None,
            "total_stars": total_stars,
            "average_stars": round(total_stars / count) if count else 0,
            "embedding_model": self.embedding_model,
            "built_at": self.built_at,
            "catalogue_stale": self.catalogue_is_stale,
        }
