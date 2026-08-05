"""Optional LLM step that explains why search results match a query.

This is the "generation" half of retrieval-augmented generation: the vector
store retrieves candidate agents, and this module asks the local chat model
(``MODEL_NAME``) to summarize them in the context of what the user asked.

Design notes:

- **Strictly optional.** Search must keep working when Ollama has no chat
  model pulled, is slow, or is down. Every failure here returns None and is
  logged; it never propagates to the caller.
- **Grounded.** The prompt contains only the retrieved agents, and the model
  is told to use nothing else. This is a summarization task over supplied
  context, not open-ended generation, which is what keeps a small local model
  useful and reduces invention.
- **Bounded.** Only the top few results are sent, and a timeout applies, so a
  slow model cannot hang a request indefinitely.
"""

import logging

import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You help developers choose an AI agent or tool. "
    "You will be given a user's need and a numbered list of candidate tools. "
    "Write 1-3 short sentences comparing the most relevant options and saying which "
    "suits the stated need. Use ONLY the information in the list; if it does not "
    "contain enough detail, say so plainly. Do not invent tools, features, or numbers. "
    "Plain prose, no markdown, no preamble."
)


class GenerationService:
    """Lazily-built chat client, mirroring EmbeddingService."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            from langchain_ollama import ChatOllama

            logger.info("Initializing chat model=%s at %s", config.MODEL_NAME, config.OLLAMA_BASE_URL)
            cls._instance = ChatOllama(
                base_url=config.OLLAMA_BASE_URL,
                model=config.MODEL_NAME,
                temperature=config.SUMMARY_TEMPERATURE,
                num_predict=config.SUMMARY_MAX_TOKENS,
                client_kwargs={"timeout": config.SUMMARY_TIMEOUT},
            )
        return cls._instance

    @classmethod
    def reset(cls):
        """Drop the cached client so config changes take effect. Used by tests."""
        cls._instance = None


def build_prompt(query, results):
    """Render the retrieved agents into a grounded prompt."""
    lines = []
    for i, result in enumerate(results, start=1):
        meta = result.get("metadata", {})
        parts = [f"{i}. {meta.get('name') or result.get('name') or 'Unknown'}"]
        if meta.get("category"):
            parts.append(f"category: {meta['category']}")
        if meta.get("stack"):
            parts.append(f"tech: {meta['stack']}")
        description = meta.get("description") or result.get("description") or ""
        if description:
            parts.append(description)
        lines.append(" — ".join(parts))

    return f"User need: {query}\n\nCandidate tools:\n" + "\n".join(lines)


def summarize(query, results, client=None):
    """Return a short natural-language summary of `results`, or None.

    Returns None rather than raising whenever generation is unavailable or
    fails, so a search never breaks because the chat model is missing.
    """
    if not config.ENABLE_SUMMARY:
        logger.debug("Summary requested but ENABLE_SUMMARY is off")
        return None
    if not results:
        return None

    top = results[: config.SUMMARY_MAX_RESULTS]

    try:
        client = client or GenerationService.get_instance()
        response = client.invoke([
            ("system", SYSTEM_PROMPT),
            ("human", build_prompt(query, top)),
        ])
    except Exception as e:
        # Includes Ollama being down, the model not being pulled, and timeouts.
        logger.warning("Could not generate summary: %s", e)
        return None

    text = getattr(response, "content", response)
    if not isinstance(text, str):
        logger.warning("Chat model returned %s, expected text", type(text).__name__)
        return None

    text = text.strip()
    return text or None
