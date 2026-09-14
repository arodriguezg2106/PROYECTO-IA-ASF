"""Reconstruye la vista final histórica conservada en all y registra diferencias."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results" / "auditoria_inventario"


def key(number):
    return (number["origen"]["part"], number["origen"]["xml_path"], tuple(number["offsets_text_all"]))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    snapshot = OUTPUT / "snapshot_4681"
    if snapshot.exists():
        raise ValueError("El snapshot histórico ya existe; no se sobrescribe.")
    snapshot.mkdir()
    old_count = new_count = 0
    changes, documents = [], []
    for path in sorted((ROOT / "results/inventario_cifras/final").glob("*.json")):
        current = json.loads(path.read_text(encoding="utf-8"))
        if "cifras" not in current:
            continue
        (snapshot / path.name).write_bytes(path.read_bytes())
        old_path = ROOT / "results/inventario_cifras/all" / path.name
        historical = json.loads(old_path.read_text(encoding="utf-8"))
        previous = [n for n in historical["cifras"] if "final" in n["vistas"]]
        old, new = {key(n): n for n in previous}, {key(n): n for n in current["cifras"]}
        assert len(old) == len(previous) and len(new) == len(current["cifras"])
        old_count += len(old)
        new_count += len(new)
        added, removed, modified = new.keys() - old.keys(), old.keys() - new.keys(), {k for k in old.keys() & new.keys() if old[k]["tipo"] != new[k]["tipo"] or old[k].get("subtipo") != new[k].get("subtipo")}
        for category, keys in (("añadido", added), ("eliminado", removed), ("clasificacion_cambiada", modified)):
            for k in sorted(keys):
                a, b = old.get(k), new.get(k)
                n = b or a
                changes.append({"documento_id": current["source"]["file"], "cambio": category,
                                "elemento_id": n["elemento_id"], "registro_id_anterior_all": a["id"] if a else None,
                                "registro_id_actual": b["id"] if b else None,
                                "tipo_anterior": a["tipo"] if a else None, "tipo_actual": b["tipo"] if b else None,
                                "origen": n["origen"], "offsets_text_all": n["offsets_text_all"],
                                "fragmento_numerico": n["texto_original"],
                                "motivo": "Nueva detección de fracción normativa con numeral romano." if category == "añadido" and b["tipo"] == "fracción" else "Cambio de extracción o clasificación."})
        documents.append({"documento": current["source"]["file"], "anteriores": len(old), "actuales": len(new),
                          "añadidos": len(added), "eliminados": len(removed), "reclasificados": len(modified),
                          "duplicados_de_ocurrencia": len(current["cifras"]) - len(new),
                          "hash_snapshot_4681": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "hash_archivo_all_historico": hashlib.sha256(old_path.read_bytes()).hexdigest()})
    assert old_count == 4579 and new_count == 4681
    report = {"metodo": "El final de 4579 fue sobrescrito. Se reconstruye filtrando vistas que contienen final en el inventario all histórico numbers-1.0. Se comparan parte, XPath y offsets de origen; no IDs secuenciales ni importes.",
              "clasificacion": "Comparación de tipo/subtipo léxico. El campo posterior classification=ambiguous es una política de confianza, no una reclasificación léxica histórica.",
              "anterior": old_count, "actual": new_count, "documentos": documents, "diferencias": changes}
    (OUTPUT / "diferencias_4579_4681.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Diferencias del inventario 4579 → 4681", "", report["metodo"], "", report["clasificacion"], "",
             "| Documento | Anterior | Actual | Añadidos | Eliminados | Reclasificados | Duplicados de ocurrencia |", "|---|---|---|---|---|---|---|"]
    for d in documents:
        lines.append("| " + " | ".join(str(d[k]) for k in ("documento", "anteriores", "actuales", "añadidos", "eliminados", "reclasificados", "duplicados_de_ocurrencia")) + " |")
    lines.extend(["", "| Documento | Cambio | elemento_id | Tipo anterior | Tipo actual | Motivo |", "|---|---|---|---|---|---|"])
    for c in changes:
        lines.append("| " + " | ".join(str(c[k] or "—") for k in ("documento_id", "cambio", "elemento_id", "tipo_anterior", "tipo_actual", "motivo")) + " |")
    (OUTPUT / "diferencias_4579_4681.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print({"anteriores": old_count, "actuales": new_count, "añadidos": sum(d["añadidos"] for d in documents),
           "eliminados": sum(d["eliminados"] for d in documents), "reclasificados": sum(d["reclasificados"] for d in documents),
           "adiciones_solo_fracciones": all(c["tipo_actual"] == "fracción" for c in changes)})


if __name__ == "__main__":
    main()
