"""Persisted query-embedding cache."""

import json

import pytest

from embedding_cache import CachedEmbeddings, EmbeddingCache


class FakeClient:
    """Counts calls so cache hits are observable."""

    def __init__(self):
        self.query_calls = 0
        self.document_calls = 0
        self.model = "fake-model"

    def embed_query(self, text):
        self.query_calls += 1
        return [float(len(text)), 0.5, 0.25]

    def embed_documents(self, texts):
        self.document_calls += 1
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
def cache_path(tmp_path):
    return tmp_path / "embeddings.json"


@pytest.fixture
def cache(cache_path):
    return EmbeddingCache(path=cache_path, model="test-model", max_entries=5)


class TestCache:
    def test_starts_empty(self, cache):
        assert cache.get("anything") is None
        assert len(cache) == 0

    def test_round_trips_a_vector(self, cache):
        cache.put("hello", [1.0, 2.0])
        assert cache.get("hello") == [1.0, 2.0]

    def test_returns_a_copy_so_callers_cannot_corrupt_it(self, cache):
        cache.put("hello", [1.0])
        cache.get("hello").append(99.0)
        assert cache.get("hello") == [1.0]

    def test_evicts_least_recently_used(self, cache):
        for i in range(5):
            cache.put(f"q{i}", [float(i)])
        cache.get("q0")           # refresh q0
        cache.put("q5", [5.0])    # should evict q1
        assert cache.get("q0") is not None
        assert cache.get("q1") is None

    def test_persists_across_instances(self, cache, cache_path):
        cache.put("remembered", [1.0, 2.0])
        cache.save()

        reopened = EmbeddingCache(path=cache_path, model="test-model", max_entries=5)
        assert reopened.get("remembered") == [1.0, 2.0]

    def test_a_different_model_does_not_see_the_entries(self, cache, cache_path):
        """Vectors from one model are the wrong shape for another."""
        cache.put("shared text", [1.0, 2.0])
        cache.save()

        other = EmbeddingCache(path=cache_path, model="other-model", max_entries=5)
        assert other.get("shared text") is None

    def test_save_is_atomic(self, cache, cache_path):
        cache.put("x", [1.0])
        cache.save()
        assert not (cache_path.parent / f"{cache_path.name}.tmp").exists()
        assert json.loads(cache_path.read_text())["entries"]

    def test_save_is_a_no_op_when_nothing_changed(self, cache, cache_path):
        cache.save()
        assert not cache_path.exists()

    def test_corrupt_file_is_ignored(self, cache_path):
        cache_path.write_text("{ not json")
        assert len(EmbeddingCache(path=cache_path, model="m", max_entries=5)) == 0

    def test_unexpected_file_shape_is_ignored(self, cache_path):
        cache_path.write_text('["not", "a", "dict"]')
        assert len(EmbeddingCache(path=cache_path, model="m", max_entries=5)) == 0

    def test_disabled_cache_stores_nothing(self, cache_path):
        disabled = EmbeddingCache(path=cache_path, model="m", max_entries=0)
        disabled.put("x", [1.0])
        assert disabled.get("x") is None
        disabled.save()
        assert not cache_path.exists()

    def test_unwritable_path_does_not_raise(self, tmp_path):
        cache = EmbeddingCache(path=tmp_path / "nope" / "x.json", model="m", max_entries=5)
        cache.put("x", [1.0])
        cache.save()  # logs a warning, does not raise


class TestCachedEmbeddings:
    def test_first_query_reaches_the_client(self, cache):
        client = FakeClient()
        wrapper = CachedEmbeddings(client, cache=cache)
        assert wrapper.embed_query("hello") == [5.0, 0.5, 0.25]
        assert client.query_calls == 1

    def test_repeat_query_is_served_from_cache(self, cache):
        client = FakeClient()
        wrapper = CachedEmbeddings(client, cache=cache)
        wrapper.embed_query("hello")
        wrapper.embed_query("hello")
        assert client.query_calls == 1

    def test_different_queries_each_reach_the_client(self, cache):
        client = FakeClient()
        wrapper = CachedEmbeddings(client, cache=cache)
        wrapper.embed_query("one")
        wrapper.embed_query("two")
        assert client.query_calls == 2

    def test_documents_are_not_cached(self, cache):
        """Seeding embeds each text once; caching would duplicate the index."""
        client = FakeClient()
        wrapper = CachedEmbeddings(client, cache=cache)
        wrapper.embed_documents(["a", "b"])
        wrapper.embed_documents(["a", "b"])
        assert client.document_calls == 2

    def test_other_attributes_come_from_the_wrapped_client(self, cache):
        wrapper = CachedEmbeddings(FakeClient(), cache=cache)
        assert wrapper.model == "fake-model"

    def test_survives_a_restart(self, cache, cache_path):
        client = FakeClient()
        CachedEmbeddings(client, cache=cache).embed_query("persisted")
        cache.save()

        fresh_client = FakeClient()
        reopened = EmbeddingCache(path=cache_path, model="test-model", max_entries=5)
        CachedEmbeddings(fresh_client, cache=reopened).embed_query("persisted")
        assert fresh_client.query_calls == 0


def test_an_empty_cache_is_not_silently_replaced(cache_path):
    """__len__ makes an empty cache falsy; `cache or ...` would discard it."""
    empty = EmbeddingCache(path=cache_path, model="m", max_entries=5)
    assert not empty, "precondition: an empty cache is falsy"

    wrapper = CachedEmbeddings(FakeClient(), cache=empty)
    assert wrapper.cache is empty


class TestModelIsolation:
    """Vectors from one model are the wrong shape for another."""

    def test_a_similar_model_tag_does_not_leak_entries(self, cache_path):
        """'nomic-embed-text' is a prefix of 'nomic-embed-text:latest'."""
        written = EmbeddingCache(path=cache_path, model="nomic-embed-text:latest", max_entries=5)
        written.put("hello", [1.0, 2.0])
        written.save()

        other = EmbeddingCache(path=cache_path, model="nomic-embed-text", max_entries=5)
        assert len(other) == 0, "entries from another model tag were loaded"
        assert other.get("hello") is None

    def test_the_same_model_still_loads(self, cache_path):
        written = EmbeddingCache(path=cache_path, model="nomic-embed-text", max_entries=5)
        written.put("hello", [1.0, 2.0])
        written.save()

        reopened = EmbeddingCache(path=cache_path, model="nomic-embed-text", max_entries=5)
        assert reopened.get("hello") == [1.0, 2.0]

    def test_the_file_records_which_model_wrote_it(self, cache, cache_path):
        cache.put("x", [1.0])
        cache.save()
        assert json.loads(cache_path.read_text())["model"] == "test-model"


def test_save_does_not_lose_an_entry_added_during_the_write(cache, cache_path):
    """The dirty flag must not be cleared for an entry that was not written."""
    cache.put("first", [1.0])
    cache.save()

    cache.put("second", [2.0])
    cache.save()

    reopened = EmbeddingCache(path=cache_path, model="test-model", max_entries=5)
    assert reopened.get("first") == [1.0]
    assert reopened.get("second") == [2.0]


def test_a_failed_save_keeps_the_cache_dirty(cache, monkeypatch):
    """Otherwise the entries are dropped on the next successful save."""
    cache.put("x", [1.0])

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", explode)
    cache.save()
    assert cache._dirty is True
