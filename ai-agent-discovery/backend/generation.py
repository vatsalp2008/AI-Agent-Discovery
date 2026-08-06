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
    "You help developers choose an AI agent or tool.\n"
    "You will be given a user's need and a list of candidate tools. Each tool is a "
    "block starting with [n] Name, followed by its own indented fields.\n"
    "\n"
    "Rules:\n"
    "1. Write 1-3 short sentences recommending which tool best suits the need.\n"
    "2. Refer to tools by their exact names as given.\n"
    "3. Every claim about a tool must come from that tool's own block. Never "
    "describe one tool using another tool's fields.\n"
    "4. Do not mention any tool that is not in the list, and do not invent "
    "features, numbers, or comparisons the blocks do not support.\n"
    "5. If the blocks lack the detail needed to choose, say so plainly.\n"
    "\n"
    "Reply with plain prose only: no markdown, no bullet points, no preamble."
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
    """Render the retrieved agents into a grounded prompt.

    One indented block per tool rather than a single delimited line: it makes
    the binding between a tool and its attributes unambiguous, which is what
    stops a small model attributing one tool's capabilities to another.
    """
    blocks = []
    for i, result in enumerate(results, start=1):
        meta = result.get("metadata", {})
        name = meta.get("name") or result.get("name") or "Unknown"
        lines = [f"[{i}] {name}"]
        if meta.get("category"):
            lines.append(f"    Category: {meta['category']}")
        if meta.get("stack"):
            lines.append(f"    Tech: {meta['stack']}")
        description = meta.get("description") or result.get("description") or ""
        if description:
            lines.append(f"    Description: {description}")
        blocks.append("\n".join(lines))

    return (
        f"User need: {query}\n\n"
        f"Candidate tools ({len(blocks)}):\n\n" + "\n\n".join(blocks)
    )


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
