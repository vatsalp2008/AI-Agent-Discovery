"""Turn raw FAISS distances into a relevance score.

``similarity_search_with_score`` returns an L2 distance: lower is better and
the value is unbounded, which is awkward to display or threshold on. We map
it to ``1 / (1 + distance)``, which is strictly decreasing and lands in
[0, 1] — an exact match scores 1.0 and relevance decays smoothly from there.
Results are rounded to four places, so distances beyond ~10000 bottom out at
0.0, the same value reported for an unusable distance. Both mean "no useful
relevance", so the collision is harmless.

Kept dependency-free so it can be unit tested without Ollama or FAISS.
"""


def relevance_score(distance: float) -> float:
    """Convert an L2 distance to a relevance score in [0, 1]."""
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    if value < 0:
        value = 0.0
    return round(1.0 / (1.0 + value), 4)
