"""Vistas de revisiones sin descartar la evidencia XML."""

MODES = {"final", "original", "all"}
ALLOWED = {
    "final": {"normal", "inserted", "moved_to"},
    "original": {"normal", "deleted", "moved_from"},
    "all": {"normal", "inserted", "deleted", "moved_from", "moved_to", "unknown"},
}
STATUS = {"ins": "inserted", "del": "deleted", "moveFrom": "moved_from", "moveTo": "moved_to",
          "cellIns": "inserted", "cellDel": "deleted"}


def revision_status(revisions):
    states = {STATUS.get(r["type"], "unknown") for r in revisions}
    return next(iter(states)) if len(states) == 1 else "unknown" if states else "normal"


def included(status, mode):
    return status in ALLOWED[mode]


def text_views(paragraph, mode):
    """Text plus source-character mapping; all never joins alternative revisions.

    The all inventory uses the final and original projections, deduplicating
    occurrences by XML fragment spans downstream. Unknown fragments stay isolated.
    """
    if mode not in MODES:
        raise ValueError(f"Modo de lectura inválido: {mode}")
    content = paragraph.get("content", [])
    if not content:
        text = paragraph.get("text", "")
        return [(text, [(i, "normal") for i in range(len(text))], mode)]
    views = []
    for view in ("final", "original") if mode == "all" else (mode,):
        chars, mapping = [], []
        for fragment in content:
            if fragment["type"] != "text":
                continue
            if included(fragment["revision_status"], view):
                chars.append(fragment["text"])
                mapping.extend((i, fragment["revision_status"]) for i in range(fragment["source_start"], fragment["source_end"]))
        views.append(("".join(chars), mapping, view))
    if mode == "all":
        for fragment in content:
            if fragment["type"] == "text" and fragment["revision_status"] == "unknown":
                views.append((fragment["text"], [(i, "unknown") for i in range(fragment["source_start"], fragment["source_end"])], "unknown"))
    return views
