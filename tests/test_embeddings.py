"""Tests for the real embeddings module.

conftest replaces `embeddings` in sys.modules with a stub so VectorStore
never builds a client, so the real module is loaded here under its own name.
"""

import importlib.util

import pytest

from conftest import BACKEND


@pytest.fixture
def embeddings_module():
    spec = importlib.util.spec_from_file_location("_real_embeddings", BACKEND / "embeddings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    module.EmbeddingService.reset()


def test_client_is_configured_from_config(embeddings_module):
    import config

    client = embeddings_module.get_embeddings()
    assert client.base_url == config.OLLAMA_BASE_URL
    assert client.model == config.MODEL_NAME


def test_client_is_a_singleton(embeddings_module):
    assert embeddings_module.get_embeddings() is embeddings_module.get_embeddings()


def test_reset_drops_the_cached_client(embeddings_module):
    first = embeddings_module.get_embeddings()
    embeddings_module.EmbeddingService.reset()
    assert embeddings_module.get_embeddings() is not first
