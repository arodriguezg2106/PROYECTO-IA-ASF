from collections import Counter
from human_validation_small import select_sample, QUOTAS


def test_small_sample_is_reproducible_and_disjoint():
    records = []
    for i in range(90):
        kind = i % 3
        records.append({"documento_id": f"sintetico-{i % 14}", "id": str(i), "tabla": "T" if i % 2 else None,
                        "confidence": "high" if kind == 0 else "low",
                        "classification": "importe" if kind == 0 else "ambiguous", "no_clasificada": kind == 2})
    sample = select_sample(records)
    assert sample == select_sample(list(reversed(records)))
    assert len(sample) == len({r["id"] for r in sample}) == 30
    assert Counter(r["estrato"] for r in sample) == QUOTAS
    assert all(r["tabla"] for r in sample if r["estrato"] == "tablas")
    assert all(r["confidence"] == "high" for r in sample if r["estrato"] == "high")
