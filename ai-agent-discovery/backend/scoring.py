"""Turn raw FAISS distances into a relevance score.

``similarity_search_with_score`` returns an L2 distance: lower is better, and
the value is awkward to display or threshold on directly.

Embedding models used for retrieval (nomic-embed-text among them) emit
unit-length vectors, and for unit vectors the L2 distance and the cosine
similarity are related exactly:

    cosine = 1 - d² / 2

So rather than inventing a mapping, we recover the cosine similarity the model
was actually trained to produce. Measured against this catalogue:

    verbatim description of an agent   d≈0.42  ->  0.91
    good semantic match                d≈0.77  ->  0.70
    unrelated query ("banana bread")   d≈1.15  ->  0.34

An earlier version used ``1 / (1 + d)``, which squeezed that entire range into
0.46–0.70 — a perfect match displayed as "70% match" and nonsense as "47%",
which told the user almost nothing.

If a model emits non-unit vectors the identity no longer holds and the numbers
lose their cosine interpretation, but the mapping stays monotonically
decreasing in distance, so ranking is unaffected.
"""


def relevance_score(distance: float) -> float:
    """Convert an L2 distance between unit vectors to cosine similarity in [0, 1]."""
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    if value < 0:
        value = 0.0

    # Negative cosine means "points the other way", which is no more useful
    # than orthogonal for ranking, so the floor is 0.
    return round(max(0.0, 1.0 - (value * value) / 2.0), 4)
