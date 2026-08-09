"""On-disk cache of query embeddings.

Profiling puts ~91% of an uncached search in the round trip to Ollama to embed
the query. The in-memory result cache already removes that for repeats within
one process, but it starts empty after every restart.

Query embeddings are the right thing to persist. A result set depends on the
index and goes stale the moment the catalogue is re-seeded; an embedding
depends only on the model and the text, so it stays valid indefinitely. The
model name is part of the cache key, so changing models cannot serve vectors
of the wrong shape.
"""

import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict

from langchain_core.embeddings import Embeddings

import config

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """A bounded LRU of query -> vector, backed by a JSON file."""

    def __init__(self, path=None, model=None, max_entries=None):
        self.path = str(path or config.EMBEDDING_CACHE_PATH)
        self.model = model or config.EMBEDDING_MODEL
        self.max_entries = max_entries if max_entries is not None else config.EMBEDDING_CACHE_SIZE
        # embed_documents can be called from a worker thread during seeding.
        self._lock = threading.Lock()
        self._entries = OrderedDict()
        self._dirty = False
        self.load()

    def _key(self, text: str) -> str:
        """Hash the text so the file cannot grow unbounded in key length.

        The key is the digest alone; the model is recorded once for the whole
        file. Embedding it in the key and matching by prefix was wrong —
        "nomic-embed-text" is a prefix of "nomic-embed-text:latest", so
        entries from one tag loaded under the other and then never matched,
        quietly consuming the cache budget.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def load(self):
        if self.max_entries <= 0 or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                stored = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Ignoring unreadable embedding cache at %s: %s", self.path, e)
            return

        if not isinstance(stored, dict):
            return

        # Vectors from another model are the wrong shape; discard the file
        # rather than loading entries that can never be served.
        if stored.get("model") != self.model:
            logger.debug("Embedding cache at %s was written by %r, not %r; ignoring.",
                         self.path, stored.get("model"), self.model)
            return

        for key, vector in stored.get("entries", {}).items():
            if isinstance(vector, list):
                self._entries[key] = vector
        logger.debug("Loaded %d cached embeddings from %s", len(self._entries), self.path)

    def save(self):
        """Write the cache out. Cheap enough to call on shutdown."""
        if self.max_entries <= 0:
            return

        # Snapshot and clear the flag together, so an entry added while the
        # file is being written is not both excluded from it and marked clean.
        with self._lock:
            if not self._dirty:
                return
            snapshot = dict(self._entries)
            self._dirty = False

        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w") as f:
                json.dump({"model": self.model, "entries": snapshot}, f)
            # Atomic replace, so a crash mid-write cannot corrupt the cache.
            os.replace(tmp, self.path)
        except OSError as e:
            # Put the flag back; the entries are still only in memory.
            with self._lock:
                self._dirty = True
            logger.warning("Could not write embedding cache to %s: %s", self.path, e)

    def get(self, text: str):
        if self.max_entries <= 0:
            return None
        key = self._key(text)
        with self._lock:
            if key not in self._entries:
                return None
            self._entries.move_to_end(key)
            return list(self._entries[key])

    def put(self, text: str, vector):
        if self.max_entries <= 0:
            return
        key = self._key(text)
        with self._lock:
            self._entries[key] = list(vector)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            self._dirty = True

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._dirty = True

    def __len__(self):
        return len(self._entries)


class CachedEmbeddings(Embeddings):
    """Wraps an embeddings client, serving repeat queries from disk.

    Subclasses Embeddings rather than merely quacking like one: langchain's
    FAISS checks the type and silently falls back to calling a non-Embeddings
    object as a bare function, which fails at query time rather than at setup.

    Only `embed_query` is cached. `embed_documents` runs during seeding, where
    every text is different and the results are about to be written into the
    index anyway, so caching them would just duplicate the index on disk.
    """

    def __init__(self, inner, cache=None):
        self._inner = inner
        # `cache or EmbeddingCache()` would be wrong: __len__ makes an empty
        # cache falsy, so a freshly-loaded one would be silently replaced.
        self.cache = EmbeddingCache() if cache is None else cache

    def embed_query(self, text: str):
        hit = self.cache.get(text)
        if hit is not None:
            return hit

        vector = self._inner.embed_query(text)
        self.cache.put(text, vector)
        return vector

    def embed_documents(self, texts):
        return self._inner.embed_documents(texts)

    def __getattr__(self, name):
        # Anything else (model, base_url, ...) comes from the wrapped client.
        return getattr(self._inner, name)
