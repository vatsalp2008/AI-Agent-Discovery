"""An index built by one embedding model must not be used by another."""

import json

from vectorstore import VectorStore


def _make_index_dir(tmp_path, embedding_model=None):
    """Fake a persisted index: FAISS files plus the optional sidecar."""
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    (index_dir / "index.faiss").write_bytes(b"stub")
    (index_dir / "index.pkl").write_bytes(b"stub")
    if embedding_model is not None:
        (index_dir / VectorStore.META_FILENAME).write_text(
            json.dumps({"embedding_model": embedding_model, "agent_count": 3})
        )
    return index_dir


def test_matching_model_is_not_treated_as_stale(tmp_path):
    index_dir = _make_index_dir(tmp_path, "nomic-embed-text")
    vs = VectorStore(persist_directory=index_dir, embedding_function=object(), embedding_model="nomic-embed-text")
    assert vs.stale_model is None


def test_mismatched_model_refuses_to_load(tmp_path):
    index_dir = _make_index_dir(tmp_path, "llama3.2")
    vs = VectorStore(persist_directory=index_dir, embedding_function=object(), embedding_model="nomic-embed-text")
    assert vs.stale_model == "llama3.2"
    assert vs.vector_store is None
    assert vs.search("anything") == []


def test_index_without_a_sidecar_is_assumed_compatible(tmp_path):
    """Indexes predating this check should not force a needless re-seed."""
    index_dir = _make_index_dir(tmp_path, embedding_model=None)
    vs = VectorStore(persist_directory=index_dir, embedding_function=object(), embedding_model="nomic-embed-text")
    assert vs.stale_model is None


def test_corrupt_sidecar_is_assumed_compatible(tmp_path):
    index_dir = _make_index_dir(tmp_path, "nomic-embed-text")
    (index_dir / VectorStore.META_FILENAME).write_text("{ not json")
    vs = VectorStore(persist_directory=index_dir, embedding_function=object(), embedding_model="nomic-embed-text")
    assert vs.stale_model is None


def test_sidecar_records_the_model_and_count(store, tmp_path):
    store._write_meta(7)
    meta = json.loads((tmp_path / "index" / VectorStore.META_FILENAME).read_text())
    assert meta["embedding_model"] == store.embedding_model
    assert meta["agent_count"] == 7


def test_health_explains_a_stale_index(client, store):
    store.vector_store = None
    store.stale_model = "llama3.2"
    response = client.get("/api/health")
    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "degraded"
    assert "llama3.2" in body["detail"]
    assert "seed.py" in body["detail"]


def test_sidecar_records_when_the_index_was_built(store, tmp_path):
    store._write_meta(3)
    meta = json.loads((tmp_path / "index" / VectorStore.META_FILENAME).read_text())
    assert "built_at" in meta
    # Parses as an aware UTC timestamp.
    from datetime import datetime, timezone
    parsed = datetime.fromisoformat(meta["built_at"])
    assert parsed.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 60


def test_built_at_is_none_for_an_index_without_a_sidecar(tmp_path):
    index_dir = _make_index_dir(tmp_path, embedding_model=None)
    vs = VectorStore(persist_directory=index_dir, embedding_function=object())
    assert vs.built_at is None


def test_stats_expose_the_build_time(store):
    store._write_meta(3)
    assert store.get_stats()["built_at"] is not None


def test_health_reports_the_build_time(client, store):
    store._write_meta(3)
    body = client.get("/api/health").get_json()
    assert body["index_built_at"] is not None
