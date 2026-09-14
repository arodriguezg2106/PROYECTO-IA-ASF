"""Genera los informes comparativos sin texto de CRF."""

import json
from collections import Counter

from audit_crf import OUT


def table(lines, headers, rows):
    lines.extend(["", "| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"])
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")


def main():
    before = json.loads((OUT / "antes.json").read_text(encoding="utf-8"))["documentos"]
    after = json.loads((OUT / "despues.json").read_text(encoding="utf-8"))["documentos"]
    baseline = {d["archivo"]: d for d in before}
    assert len(before) == len(after) == 14
    assert all(d["sha256_original"] == baseline[d["archivo"]]["sha256_original"] and d["original_sin_cambios"] for d in after)
    totals = {k: sum(d[k] for d in after) for k in ("total_xml", "con_texto", "extraidos", "no_extraidos", "con_texto_no_extraidos", "texto_parcial")}
    old_missing = [p for d in before for p in d["parrafos"] if not p["extraido"]]
    assert len(old_missing) == 157
    original = json.loads((OUT.parent / "reporte_crf" / "reporte.json").read_text(encoding="utf-8"))["documentos"]
    original_by_file = {d["archivo"]: d for d in original}
    for document in before:
        expected = {(e["parte"], e["xml_path"]) for e in original_by_file[document["archivo"]]["elementos_no_extraidos"] if e["tipo"] == "parrafos"}
        actual = {(p["parte"], p["ruta_xml"]) for p in document["parrafos"] if not p["extraido"]}
        assert expected == actual
    old_partial = sum(d["texto_parcial"] for d in before)
    total_text = totals["con_texto"]
    old_covered = sum(d["con_texto"] - d["con_texto_no_extraidos"] - d["texto_parcial"] for d in before)
    lines = ["# Auditoría de párrafos XML", "",
             f"Se contrastaron los mismos 14 DOCX y sus hashes SHA-256. Los 157 párrafos omitidos coinciden exactamente, por parte y XPath, con el reporte anterior.", "",
             f"De los 157 omitidos: {sum(p['con_texto'] for p in old_missing)} contienen texto y {sum(not p['con_texto'] for p in old_missing)} están vacíos o solo tienen formato/controles sin texto.", "",
             f"Además, {old_partial} párrafos ya representados tenían texto incompleto. La cobertura de texto completo pasó de {100 * old_covered / total_text:.4f}% a {100 * (total_text - totals['con_texto_no_extraidos'] - totals['texto_parcial']) / total_text:.4f}%.", "",
             "## Método", "",
             "- Inventario independiente de cada `w:p` en todas las partes `word/*.xml`; coincidencia por parte y XPath, no por contenido repetido.",
             "- Texto propio del párrafo: `w:t`, `w:delText`, tabulaciones de contenido, saltos y guiones especiales. Excluye propiedades de formato, instrucciones de campo y texto de párrafos descendientes.",
             "- Con texto significa que ese texto no está vacío después de quitar espacios. La longitud cuenta caracteres Unicode, no bytes; incluye espacios y saltos.",
             "- Cobertura estricta: párrafos con texto recuperado completo (igualdad SHA-256 del texto XML y el extraído) / párrafos XML con texto. También se mide presencia del párrafo.",
             "- Revisiones conservadas, sin aceptarlas ni rechazarlas; texto eliminado identificado mediante metadatos. No representa una vista final de Word.",
             "- Notas y comentarios en `supplementary_parts`; cuerpo y encabezados/pies mantienen sus ámbitos. El orden se verifica dentro de cada parte, porque no existe un orden lineal común entre partes del paquete.",
             "- Duplicados: misma parte y XPath o mismo identificador repetido. Textos iguales en ubicaciones diferentes y documentos diferentes no son duplicados de extracción.",
             "- Un encabezado/pie compartido se extrae una vez; las demás secciones usan `content_ref`.",
             "- Los controles, formas, cambios y tablas anidadas son etiquetas que pueden solaparse. Vacío/con texto es una dimensión separada.",
             "- No se evalúa contenido, cifras, gramática ni formato visual. Imágenes, instrucciones de campo, objetos y símbolos sin texto Unicode no forman parte del denominador; no se ejecutan ni se aplica OCR."]
    table(lines, ["Documento", "XML", "Con texto", "Extraídos antes", "Extraídos ahora", "Con texto omitidos antes", "Con texto omitidos ahora", "Texto parcial ahora", "Cobertura %", "Duplicados", "Errores"],
          [[d["archivo"], d["total_xml"], d["con_texto"], baseline[d["archivo"]]["extraidos"], d["extraidos"],
            baseline[d["archivo"]]["con_texto_no_extraidos"], d["con_texto_no_extraidos"], d["texto_parcial"],
            f"{d['cobertura_texto']:.4f}", len(d["duplicados_elementos"]) + len(d["ids_duplicados"]),
            len(d["errores"]) + len(d["errores_orden_origen"])] for d in after])
    lines.extend(["", f"Totales: `{json.dumps(totals, ensure_ascii=False)}`.", "", "## Contenedores de los 157 omitidos"])
    containers = Counter(p["contenedor"] for p in old_missing)
    table(lines, ["Contenedor", "Total", "Con texto", "Vacíos"],
          [[c, n, sum(p["con_texto"] for p in old_missing if p["contenedor"] == c), sum(not p["con_texto"] for p in old_missing if p["contenedor"] == c)] for c, n in containers.most_common()])
    table(lines, ["Categoría (puede solaparse)", "Omitidos antes"], [[c, sum(c in p["categorias"] for p in old_missing)] for c in
          ("control_contenido", "cuadro_texto_o_forma", "cambios_controlados", "tabla_anidada", "otros_contenedores")])
    for d in after:
        b = baseline[d["archivo"]]
        current = {(p["parte"], p["ruta_xml"]): p for p in d["parrafos"]}
        omitted = [p for p in b["parrafos"] if not p["extraido"]]
        lines.extend(["", f"## {d['archivo']}", "",
                      f"Original sin cambios: {d['original_sin_cambios']}. Párrafos pendientes: {d['no_extraidos']}. Duplicados de ubicación: {len(d['duplicados_elementos'])}; de ID: {len(d['ids_duplicados'])}. Errores técnicos: {len(d['errores'])}; errores de orden/origen: {len(d['errores_orden_origen'])}.",
                      f"Advertencias restantes (no son pérdida de párrafos): `{json.dumps(d['advertencias_lector'])}`.", "",
                      "Párrafos inicialmente omitidos (sin texto del documento):"])
        table(lines, ["Parte", "XPath", "Categorías", "Contenedor", "Con texto", "Longitud", "ID recuperado"],
              [[p["parte"], p["ruta_xml"], ", ".join(p["categorias"]), p["contenedor"], p["con_texto"], p["longitud_texto"],
                ", ".join(current[(p["parte"], p["ruta_xml"])]["ids_extraidos"])] for p in omitted])
        partial = [p for p in b["parrafos"] if p["con_texto"] and p["extraido"] and not p["texto_completo"]]
        if partial:
            lines.extend(["", "Párrafos previamente parciales, ahora contrastados completos:"])
            table(lines, ["Parte", "XPath", "Longitud XML", "Elementos internos", "Completo ahora"],
                  [[p["parte"], p["ruta_xml"], p["longitud_texto"],
                    json.dumps(current[(p["parte"], p["ruta_xml"])]["elementos_internos"]),
                    current[(p["parte"], p["ruta_xml"])]["texto_completo"]] for p in partial])
    (OUT / "reporte.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    format_lines = ["# Estilos y combinaciones de formato", "",
                    "Inventario de los 5,922 párrafos XML, incluidos vacíos, notas y comentarios. No contiene texto de las CRF.", "",
                    "## Ausencia de títulos por nivel de esquema", "",
                    "En los 5,922 párrafos no existe nivel de esquema directo ni heredado por la cadena de estilos o los valores predeterminados. El lector requiere niveles XML 0–8 para identificar títulos (niveles 1–9 en la salida). Los estilos de título que puedan estar definidos en styles.xml no están aplicados a estos párrafos mediante una cadena con nivel de esquema. Negritas, tamaño, alineación o nombres de estilo no establecen por sí mismos un nivel de esquema.", "",
                    "No se ha implementado un detector heurístico de títulos. Una prueba sintética verifica que un estilo personalizado basado en Heading 2 sí se identifica por herencia.", "",
                    "## Método de formato", "",
                    "Frecuencia = número de párrafos con esa combinación; cada párrafo cuenta una vez. Se recopilan los tamaños y estados de negrita de sus runs con texto; si no los hay, se inspecciona el formato de la marca de párrafo. Las listas de varios valores indican formato mixto, no promedios.", "",
                    "Se resuelven docDefaults, basedOn de estilos de párrafo, estilos de carácter y formato directo; se respeta la inversión de negrita en estilos. Tamaño = w:sz / 2 en puntos. Alineación = w:jc directo o heredado. No especificado significa que no se encontró un valor, no equivale automáticamente a falso o a alineación izquierda.", "",
                    "Son propiedades XML con herencia de estilos, no una simulación completa de Word: no se resuelven estilos condicionales de tabla, formatos de numeración, tamaños de escritura compleja w:szCs ni disposición visual. Las combinaciones se presentan con ese alcance.", "",
                    "## Frecuencias globales"]
    styles = Counter()
    combinations = Counter()
    for d in after:
        for s in d["formatos"]["estilos"]:
            styles[(s["id"], s["nombre"])] += s["frecuencia"]
        for c in d["formatos"]["combinaciones"]:
            key = (c["estilo_id"], c["nombre_estilo"], tuple(c["tamanos_pt"]), tuple(c["negritas"]), c["alineacion"])
            combinations[key] += c["frecuencia"]
    table(format_lines, ["ID estilo", "Nombre", "Frecuencia"], [[*key, n] for key, n in styles.most_common()])
    table(format_lines, ["ID estilo", "Nombre", "Tamaños pt", "Negritas", "Alineación", "Frecuencia"],
          [[*key, n] for key, n in combinations.most_common(30)])
    for d in after:
        f = d["formatos"]
        format_lines.extend(["", f"## {d['archivo']}", "",
                             f"Niveles directos: `{json.dumps(f['niveles_esquema_directos'])}`. Niveles resueltos: `{json.dumps(f['niveles_esquema_resueltos'])}`."])
        table(format_lines, ["ID estilo", "Nombre", "Frecuencia"], [[s["id"], s["nombre"], s["frecuencia"]] for s in f["estilos"]])
        table(format_lines, ["Nombre estilo", "Tamaños pt", "Negritas", "Alineación", "Frecuencia"],
              [[c["nombre_estilo"], c["tamanos_pt"], c["negritas"], c["alineacion"], c["frecuencia"]] for c in f["combinaciones"][:20]])
    format_lines.extend(["", "La lista completa de combinaciones por documento y los estilos con nivel de esquema definidos están en despues.json, campo formatos."])
    (OUT / "estilos_y_formatos.md").write_text("\n".join(format_lines) + "\n", encoding="utf-8")
    print(json.dumps({"documentos": len(after), **totals,
                      "duplicados": sum(len(d["duplicados_elementos"]) for d in after),
                      "errores": sum(len(d["errores"]) + len(d["errores_orden_origen"]) for d in after)}))


if __name__ == "__main__":
    main()
