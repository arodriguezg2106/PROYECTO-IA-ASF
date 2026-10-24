"""Revisión editorial ASF local, trazable y sin modificación del DOCX."""
from __future__ import annotations

import hashlib
import json
import re
import time
import tomllib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH

CATALOG_PATH = Path(__file__).with_name("editorial_catalog.json")
ABBREVIATIONS_PATH = Path(__file__).with_name("editorial_abbreviations.json")
EDITORIAL_PROMPT_VERSION = "editorial-context-2.1"
WORDING = {
    "aperturar": "abrir", "accesar": "acceder", "apegarse": "ajustarse o cumplir",
    "generar": "causar, originar o provocar", "estipular": "establecer",
    "requisitar": "llenar o cumplimentar", "eficientar": "mejorar u optimizar",
    "normatividad": "normativa", "problemática": "problema", "problemáticas": "problemas",
    "impacto": "repercusión", "posicionar": "situar o ubicar", "tendiente": "tendente",
    "coadyuvar": "contribuir o cooperar",
}
PROTECTED_PATTERNS = {
    "percentage": r"(?<!\w)[+-]?\d[\d,]*(?:\.\d+)?\s*%",
    "date": r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b",
    "folio": r"\b(?:folio|oficio|auditor[ií]a|acci[oó]n|art[ií]culo|art\.)\s*(?:n[uú]m\.?)?\s*[A-Z0-9][A-Z0-9./-]*",
    "number": r"(?<!\w)\$?[+-]?\d[\d,' ]*(?:\.\d+)?(?!\w)",
    "acronym": r"\b[A-ZÁÉÍÓÚÑ]{2,}(?:['’]s|s)?\b",
    "proper_name": r"\b(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+|$)){2,}",
}

@dataclass(frozen=True)
class EditorialConfig:
    enabled: bool = True
    ollama_enabled: bool = False
    model: str = "qwen3.5:4b"
    base_url: str = "http://localhost:11434/api"
    temperature: float = 0.0
    timeout_seconds: float = 120.0
    expected_model_digest: str | None = None
    max_fragment_chars: int = 4000
    confidence_threshold: float = 0.8
    categories: tuple[str, ...] = ()
    min_paragraph_words: int = 8
    max_paragraph_words: int = 180
    excluded_style_patterns: tuple[str, ...] = ("title", "heading", "título", "subtítulo", "caption")
    check_format: bool = True
    experimental_model: bool = False
    ollama_prompt_mode: str = "approved"
    ollama_max_suggestions: int = 200
    language_tool_enabled: bool = False
    language_tool_experimental: bool = False
    language_tool_url: str = "http://127.0.0.1:8081/v2"
    language_tool_language: str = "es"
    language_tool_timeout_seconds: float = 10.0
    language_tool_profile_path: str | None = None
    language_tool_rule_ids: tuple[str, ...] = ()
    language_tool_categories: tuple[str, ...] = ()
    language_tool_excluded_categories: tuple[str, ...] = ()
    language_tool_accepted_terms: tuple[str, ...] = ()
    language_tool_cache_path: str | None = "results/cache/languagetool.sqlite3"
    language_tool_cache_namespace: str = "LanguageTool-6.6"
    autofix: bool = False

    @classmethod
    def load(cls, path=None):
        values = {}
        if path:
            source = Path(path)
            try:
                values = tomllib.loads(source.read_text("utf-8")) if source.suffix.lower() == ".toml" else json.loads(source.read_text("utf-8"))
                values = values.get("editorial", values)
            except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
                raise ValueError(f"No se pudo leer la configuración editorial: {source}") from exc
        unknown = set(values) - set(cls.__dataclass_fields__)
        if unknown: raise ValueError("Campos editoriales desconocidos: " + ", ".join(sorted(unknown)))
        for key in ("categories", "excluded_style_patterns", "language_tool_rule_ids", "language_tool_categories", "language_tool_excluded_categories", "language_tool_accepted_terms"):
            if isinstance(values.get(key), list): values[key] = tuple(values[key])
        if path and values.get("language_tool_profile_path"):
            profile_path = Path(values["language_tool_profile_path"])
            if not profile_path.is_absolute():
                values["language_tool_profile_path"] = str((Path(path).parent / profile_path).resolve())
        result = cls(**values)
        if result.autofix: raise ValueError("autofix no está disponible en esta versión.")
        _invalid_config = (
            not 0 <= result.temperature <= 1
            or not 0 <= result.confidence_threshold <= 1
            or result.timeout_seconds <= 0
            or result.language_tool_timeout_seconds <= 0
            or result.max_fragment_chars < 100
            or result.min_paragraph_words < 1
            or result.max_paragraph_words <= result.min_paragraph_words
            or result.ollama_max_suggestions < 1
            or result.ollama_prompt_mode not in {"approved", "research_high_recall"}
        )
        if _invalid_config:
            raise ValueError("Configuración editorial fuera de rango.")
        return result

class EditorialProvider(Protocol):
    @property
    def descriptor(self) -> object: ...
    def review(self, request: dict, schema: dict) -> object: ...

class OllamaEditorialProvider:
    """Adaptador del transporte Ollama ya existente; sólo admite loopback."""
    def __init__(self, config: EditorialConfig):
        from .semantic import OllamaProvider, SemanticConfig
        from .editorial_models import authorize_model
        self.descriptor = authorize_model(config.model, experimental=config.experimental_model)
        semantic = SemanticConfig(base_url=config.base_url, model=config.model,
            timeout_seconds=config.timeout_seconds, confidence_threshold=max(.5, config.confidence_threshold),
            expected_model_digest=config.expected_model_digest)
        semantic.validate(); self.client = OllamaProvider(semantic); self.config = config
        if config.expected_model_digest:
            observed = self.client.metadata().get("digest")
            if observed != config.expected_model_digest:
                raise RuntimeError("ollama_model_digest_mismatch")
    def review(self, request, schema):
        prompt = SYSTEM_PROMPT
        if self.config.ollama_prompt_mode == "research_high_recall":
            from .ollama_research import SYSTEM_PROMPT as RESEARCH_SYSTEM_PROMPT
            prompt = RESEARCH_SYSTEM_PROMPT
        payload = {"model": self.config.model, "messages":[{"role":"system","content":prompt},{"role":"user","content":json.dumps(request, ensure_ascii=False)}],
            "stream":False,"think":False,"format":schema,"options":{"temperature":self.config.temperature,"seed":20260923}}
        response = self.client._request("chat", payload)
        return (response.get("message") or {}).get("content")

    def metadata(self):
        return self.client.metadata()

SYSTEM_PROMPT = (
    "Actúas como un detector conservador de infracciones editoriales en documentos de "
    "fiscalización de la Auditoría Superior de la Federación. Evalúa únicamente la regla "
    "incluida en la solicitud; no hagas una revisión general ni inventes reglas, hechos o "
    "necesidades de información. La salida preferida ante cualquier duda es "
    "{\"findings\": []}. Sólo genera un hallazgo cuando el fragmento contiene una "
    "infracción concreta y demostrable de esa regla. Nunca devuelvas felicitaciones, "
    "explicaciones de que el texto está correcto ni sugerencias meramente estilísticas como "
    "hallazgos. No pidas precisar quién actuó, agregar detalles o cambiar voz activa/pasiva "
    "si el sentido ya es claro. Los correct_examples de la regla son contraejemplos que "
    "deben producir findings vacío; los incorrect_examples muestran el tipo de problema, "
    "pero no autorizan inferencias fuera del fragmento. Ejemplos obligatorios: "
    "'La auditoría identificó deficiencias en los controles.' => findings vacío; "
    "'Después de recibir la solicitud, la entidad emitió la respuesta correspondiente.' "
    "=> findings vacío; 'Se concluyó que la entidad incumplió la normativa.' => findings "
    "vacío. No infieras el mismo defecto a partir de una palabra o construcción superficial. "
    "Un gerundio no es un error por sí mismo: es válido cuando expresa una acción simultánea "
    "o el modo de la acción principal. Ejemplo sintético válido: 'El equipo recorrió el "
    "archivo verificando los registros.' => findings vacío. Sólo señala posterioridad cuando "
    "el propio fragmento demuestra que la acción del gerundio sucede después; ejemplo "
    "sintético: 'La unidad cerró el expediente, notificándolo al día siguiente.' => hallazgo. "
    "No cambies el sentido técnico, jurídico o fiscalizador, "
    "cifras, importes, porcentajes, fechas, folios, nombres, siglas ni referencias normativas. "
    "problem_span debe ser el substring literal mínimo que demuestra el problema. Si no "
    "puedes citarlo literalmente, devuelve findings vacío. suggested_text debe ser null "
    "cuando la corrección dependa de información no presente. Devuelve exclusivamente JSON "
    "válido conforme al esquema. Toda propuesta requiere revisión humana."
)
EDITORIAL_PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()

def load_editorial_catalog(path=None):
    source = Path(path) if path else CATALOG_PATH
    try: data = json.loads(source.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ValueError(f"Catálogo editorial inválido: {source}") from exc
    required = {"rule_id","title","category","description","source_section","source_page","document_code","document_version","detection_type","severity","autofix_allowed","requires_context","enabled"}
    ids=set()
    for rule in data.get("rules", []):
        if required-set(rule) or rule["rule_id"] in ids: raise ValueError("Regla editorial incompleta o duplicada.")
        ids.add(rule["rule_id"])
    return data

def protected_elements(text):
    found=[]
    for kind, pattern in PROTECTED_PATTERNS.items():
        for match in re.finditer(pattern, text): found.append({"type":kind,"value":match.group(0),"start":match.start(),"end":match.end()})
    return found

def verify_protected(original, suggestion):
    before=Counter((x["type"],x["value"]) for x in protected_elements(original)); after=Counter((x["type"],x["value"]) for x in protected_elements(suggestion))
    return {"safe":before==after,"removed":[{"type":k[0],"value":k[1],"count":n} for k,n in (before-after).items()],"added":[{"type":k[0],"value":k[1],"count":n} for k,n in (after-before).items()]}

def _blocks(blocks, table=None, cell=None):
    for block in blocks:
        if block["type"]=="paragraph":
            yield block, table, cell
            yield from _blocks(block.get("blocks",[]),table,cell)
        else:
            for row in block.get("rows",[]):
                for c in row.get("cells",[]): yield from _blocks(c.get("blocks",[]),block,c)

def _finding(rule, p, span, message, suggestion=None, *, status="confirmed", method="deterministic"):
    start=p["text"].find(span); raw=f'{rule["rule_id"]}|{p["id"]}|{start}|{span}'
    return {"id":"ED-"+hashlib.sha256(raw.encode()).hexdigest()[:16],"rule_id":rule["rule_id"],"category":rule["category"],"severity":rule["severity"],"detection_method":method,
      "location":{"section":" > ".join(h["text"] for h in p.get("headings",[])) or None,"paragraph_id":p["id"],"table_id":None,"cell_reference":None},
      "original_text":p["text"],"problem_span":span,"message":message,"suggested_text":suggestion,"source_section":rule["source_section"],"source_page":rule["source_page"],
      "confidence":"high" if not rule["requires_context"] else "medium","validation_status":status,"evaluation_status":status,
      "effective_value":None,"value_source":None,"structural_evidence":[],
      "requires_human_review":rule["requires_context"],"autofix_allowed":False,"rejection_reason":None}

def _deterministic(document, rules):
    by={r["rule_id"]:r for r in rules}; out=[]; acronym_order=[]
    for p,table,cell in _blocks(document["blocks"]):
        text=p.get("text",""); local=[]
        checks=[("ASF-ED-II-07-10",r"\d(?:[.,]\d+)?\s+%","El signo % debe ir unido a la cifra.",lambda s:re.sub(r"\s+%$","%",s)),
          ("ASF-ED-II-07-09",r"\b\d+(?:\.\d+)?\s+por\s+ciento\b","En el texto ordinario debe emplearse el signo %.",None),
          ("ASF-ED-II-07-12",r"\b\d+%","El porcentaje ordinario debe expresarse con un decimal.",None),
          ("ASF-ED-II-07-05",r"\d['’]\d","Se detectó un apóstrofo como separador numérico.",None),
          ("ASF-ED-II-07-06",r"\b\d+\s+(?:mil|millones?)\s+\d+\b","La cantidad mezcla números y palabras.",None),
          ("ASF-ED-II-07-07",r"\b\d+(?:\.\d+)?\s+mil\s+\d+\s+millones?\s+de\s+pesos\b","No deben mezclarse cantidades y múltiplos monetarios.",None),
          ("ASF-ED-II-07-08",r"\b\d+\s*/\s*\d+\b","La fracción podría expresarse como decimal.",None),
          ("ASF-ED-II-08-04C",r"\b[A-ZÁÉÍÓÚÑ]{2,}(?:['’]s|s)\b","Las siglas no se pluralizan con s ni apóstrofo.",None),
          ("ASF-ED-II-08-04A",r"\b(?:[A-ZÁÉÍÓÚÑ]\.){2,}[A-ZÁÉÍÓÚÑ]?\.?","Las siglas se escriben con mayúsculas y sin puntos.",lambda s:s.replace(".","")),
          ("ASF-ED-I-05-YO",r"\by/o\b","Debe elegirse ‘y’ u ‘o’ de acuerdo con el sentido.",None),
          ("ASF-ED-I-05-MISMO",r"\b(?:mismo|misma|mismos|mismas)\s+que\b","Se recomienda un pronombre relativo.",None),
          ("ASF-ED-II-08-03",r"\b\d+(?:\.\d+)?\s*(?:kgs?|mts?|kms?|cms?)\.","La unidad de medida no lleva plural ni punto.",None)]
        for rid,pat,msg,fix in checks:
            if rid not in by: continue
            if rid=="ASF-ED-II-07-09" and table is not None:
                continue
            flags=re.I if rid in {"ASF-ED-I-05-YO","ASF-ED-I-05-MISMO","ASF-ED-II-08-03","ASF-ED-II-07-09"} else 0
            for m in re.finditer(pat,text,flags): local.append(_finding(by[rid],p,m.group(),msg,fix(m.group()) if fix else None))
        if "ASF-ED-I-06-06" in by:
            for bad,good in WORDING.items():
                for m in re.finditer(rf"\b{re.escape(bad)}\b",text,re.I): local.append(_finding(by["ASF-ED-I-06-06"],p,m.group(),f"‘{m.group()}’ figura como forma no recomendada.",good))
        for m in re.finditer(r"\b[A-ZÁÉÍÓÚÑ]{2,}\b",text): acronym_order.append({"acronym":m.group(),"paragraph_id":p["id"]})
        for item in local:
            if table: item["location"].update(table_id=table["id"],cell_reference=cell["id"] if cell else None)
        out.extend(local)
    return out, acronym_order


_CONTENT_STOPWORDS={"a","al","ante","bajo","con","contra","de","del","desde","durante","e","el","en","entre","es","esta","fue","la","las","lo","los","o","para","por","que","se","sin","su","sus","un","una","y"}

def _safe_context_findings(document, rules):
    """Detectores cerrados: señalan evidencia, pero nunca dictan una corrección."""
    by={r["rule_id"]:r for r in rules}; findings=[]; previous_by_scope={}
    patterns=(
      ("ASF-ED-I-04-GER",r",\s*(?:provocando|generando|ocasionando|causando|determinando)\b[^.;]*", "El gerundio separado por coma puede expresar consecuencia o posterioridad."),
      ("ASF-ED-I-04-QUE",r"\b(?:se\s+)?(?:informó|comunicó|notificó|indicó)\s+a\s+la\s+(?:entidad|unidad|dirección|dependencia)\s+(?:debía|debería|podía|podría|presentara|entregara)\b", "La construcción controlada puede omitir la conjunción ‘que’."),
      ("ASF-ED-I-04-RED",r"\b(?:volvió\s+a\s+repetir|repetir\s+nuevamente|por\s+segunda\s+vez\s+de\s+nuevo)\b", "La expresión contiene una redundancia léxica verificable."),
      ("ASF-ED-I-04-TENSE",r"\b(?:estaría|estarían)\s+\w+(?:ando|iendo)\b|\b(?:podría|podrían)\s+(?:estar\s+)?\w+(?:ar|er|ir|ando|iendo)\b", "La perífrasis puede debilitar una conclusión que debe sustentarse en evidencia."),
      ("ASF-ED-I-04-SUBJ",r"\b(?:se\s+)?(?:concluyó|determinó|acreditó)\s+que\b[^.;]{0,80}\b(?:pudiera|pudieran|debiera|debieran|hubiera|hubieran)\b", "La conclusión expresa contiene una forma subjuntiva que debe revisarse."),
      ("ASF-ED-I-04-SE",r"\bEn\s+(?:el|la|los|las)\s+(?:expediente|muestra|revisión|auditoría|documentación)\s+(?:identificaron|detectaron|localizaron|encontraron)\b", "La construcción locativa puede omitir ‘se’ impersonal."),
    )
    for p,table,cell in _blocks(document["blocks"]):
        text=p.get("text",""); local=[]
        for rid,pattern,message in patterns:
            if rid in by:
                for match in re.finditer(pattern,text,re.I):
                    local.append(_finding(by[rid],p,match.group(),message,status="possible",method="deterministic_context"))
        rid="ASF-ED-I-04-REP"
        if rid in by:
            for sentence in re.split(r"(?<=[.!?;])\s+",text):
                words=[w.lower() for w in re.findall(r"\b[a-záéíóúñ]{5,}\b",sentence,re.I)]
                repeated=next((word for word,count in Counter(words).items() if count>=3 and word not in _CONTENT_STOPWORDS),None)
                if repeated:
                    span=next(m.group() for m in re.finditer(rf"\b{re.escape(repeated)}\b",text,re.I))
                    local.append(_finding(by[rid],p,span,f"La palabra ‘{repeated}’ aparece tres o más veces en la misma oración.",status="possible",method="deterministic_context"))
        scope=(p.get("part"),p.get("section_id"),table["id"] if table else None)
        rid="ASF-ED-I-04-REF"
        vague=re.match(r"\s*(?:Lo anterior|Esto|Esta situación|Dicha situación)\b",text,re.I)
        if rid in by and vague and not previous_by_scope.get(scope):
            local.append(_finding(by[rid],p,vague.group().strip(),"La referencia vaga no tiene un antecedente estructural disponible.",status="possible",method="deterministic_context"))
        if text.strip():previous_by_scope[scope]=text
        for item in local:
            item["structural_evidence"]=[{"pattern":"closed","paragraph_id":p["id"]}]
            if table:item["location"].update(table_id=table["id"],cell_reference=cell["id"] if cell else None)
        findings.extend(local)
    return findings

def _effective(style, attr, group=None):
    seen=set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id); owner=getattr(style,group) if group else style; value=getattr(owner,attr,None)
        if value is not None:return value
        style=style.base_style
    return None

def _format_findings(path, rules):
    by={r["rule_id"]:r for r in rules}; doc=Document(path); out=[]; not_eval=[]
    page=by.get("ASF-ED-III-03-01")
    if page:
        for i,s in enumerate(doc.sections,1):
            if s.orientation!=WD_ORIENT.PORTRAIT or abs(s.page_width.inches-8.5)>.06 or abs(s.page_height.inches-11)>.06:
                p={"id":f"section-{i:04d}","text":"Configuración de sección","headings":[]}; out.append(_finding(page,p,"Configuración de sección","La sección no usa tamaño carta vertical o requiere validar una excepción.",status="possible",method="format"))
    font_rule=by.get("ASF-ED-III-03-02"); align_rule=by.get("ASF-ED-III-03-04")
    for i,p in enumerate(doc.paragraphs,1):
        if not p.text.strip():continue
        proxy={"id":f"body/word-p{i:04d}","text":p.text,"headings":[]}; name=_effective(p.style,"name","font") if p.style else None; size=_effective(p.style,"size","font") if p.style else None
        if font_rule and ((name and name.lower()!="calibri") or (size and abs(size.pt-11)>.05)): out.append(_finding(font_rule,proxy,p.text,"La fuente efectiva del párrafo no es Calibri de 11 puntos.",status="confirmed",method="format"))
        alignment=p.alignment if p.alignment is not None else _effective(p.style,"alignment","paragraph_format") if p.style else None
        if align_rule and alignment is not None and alignment!=WD_ALIGN_PARAGRAPH.JUSTIFY: out.append(_finding(align_rule,proxy,p.text,"La alineación efectiva no es justificada.",status="confirmed",method="format"))
    for rid,reason in (("ASF-ED-II-09-02","La apariencia efectiva de bordes requiere interpretación completa de estilos de tabla."),("ASF-ED-III-04-01","La alineación visual por punto decimal no es evaluable desde el XML lógico.")):
        if rid in by:not_eval.append({"rule_id":rid,"reason":reason,"source_section":by[rid]["source_section"],"source_page":by[rid]["source_page"]})
    return out,not_eval

def _with_effective(item, values, evidence):
    item["effective_value"] = values
    sources = {v.get("source") for v in values.values() if isinstance(v, dict) and v.get("source")}
    item["value_source"] = next(iter(sources)) if len(sources) == 1 else "mixed" if sources else None
    item["structural_evidence"] = evidence
    return item


def _format_findings_v2(path, rules, config):
    from .editorial_format import inspect_format
    by = {r["rule_id"]: r for r in rules}; data = inspect_format(path)
    out, not_eval, excluded = [], [], []
    page = by.get("ASF-ED-III-03-01")
    if page:
        expected = {"orientation":"PORTRAIT","width_inches":8.5,"height_inches":11.0,
                    "margins_cm":{"top":2.0,"bottom":3.0,"inside":4.0,"outside":3.0,"gutter":0.0},
                    "header_cm":0.5,"footer_cm":2.0}
        for section in data["sections"]:
            size_bad = abs(section["width_inches"]-8.5)>.06 or abs(section["height_inches"]-11)>.06
            margins_bad = any(abs(section["margins_cm"][k]-v)>.08 for k,v in expected["margins_cm"].items())
            distances_bad = abs(section["header_cm"]-.5)>.08 or abs(section["footer_cm"]-2)>.08
            if section["orientation"]!="PORTRAIT" or size_bad or margins_bad or distances_bad:
                p={"id":f"section-{section['index']:04d}","text":"Configuración de sección","headings":[]}
                item=_finding(page,p,p["text"],"La página difiere de carta vertical o de los márgenes institucionales; valide si existe una excepción autorizada.",status="possible",method="format")
                out.append(_with_effective(item,section,[{"expected":expected,"actual":section}]))
    for p in data["paragraphs"]:
        proxy={"id":f"ooxml:{p['xml_path']}","text":p["text"],"headings":[]}; fmt=p["format"]
        style=(p["style_id"] or "").lower(); is_excluded=any(x.lower() in style for x in config.excluded_style_patterns)
        rule=by.get("ASF-ED-III-04-01" if p["in_table"] else "ASF-ED-III-03-02"); target=8 if p["in_table"] else 11
        if is_excluded:
            for candidate in {x["rule_id"]:x for x in (rule,by.get("ASF-ED-III-03-04"),by.get("ASF-ED-III-03-04B")) if x}.values():
                excluded.append({"rule_id":candidate["rule_id"],"location":proxy["id"],"reason":f"Estilo excluido: {p['style_id']}"})
        name=fmt["font_name"]["value"]; size=fmt["font_size"]["value"]
        if rule and not is_excluded and ((name and str(name).lower()!="calibri") or (size is not None and abs(float(size)-target)>.05)):
            item=_finding(rule,proxy,p["text"],f"La fuente efectiva no es Calibri de {target} puntos.",method="format")
            out.append(_with_effective(item,{"font_name":fmt["font_name"],"font_size":fmt["font_size"]},[{"xml_path":p["xml_path"],"style_id":p["style_id"]}]))
        elif rule and name is None and size is None:
            excluded.append({"rule_id":rule["rule_id"],"location":proxy["id"],"reason":"Fuente efectiva no resoluble."})
        align_rule=by.get("ASF-ED-III-03-04"); alignment=fmt["alignment"]["value"]
        if align_rule and not p["in_table"] and not is_excluded and alignment is not None and alignment!="JUSTIFY":
            item=_finding(align_rule,proxy,p["text"],"La alineación efectiva no es justificada.",method="format")
            out.append(_with_effective(item,{"alignment":fmt["alignment"]},[{"xml_path":p["xml_path"]}]))
        spacing_rule=by.get("ASF-ED-III-04-01" if p["in_table"] else "ASF-ED-III-03-04")
        expected_spacing={"line_spacing":1.0 if p["in_table"] else 1.5,"space_before":3.0,"space_after":0.0 if p["in_table"] else 3.0}
        actual_spacing={key:fmt[key] for key in expected_spacing}
        deviations={key:{"actual":actual_spacing[key]["value"],"expected":expected} for key,expected in expected_spacing.items() if actual_spacing[key]["value"] is not None and abs(float(actual_spacing[key]["value"])-expected)>.05}
        if spacing_rule and not is_excluded and deviations:
            item=_finding(spacing_rule,proxy,p["text"],"El interlineado o espaciado efectivo difiere del formato institucional de revisión.",status="possible",method="format")
            out.append(_with_effective(item,actual_spacing,[{"xml_path":p["xml_path"],"deviations":deviations}]))
        length_rule=by.get("ASF-ED-III-03-04B"); words=len(re.findall(r"\b\w+\b",p["text"]))
        if length_rule and not p["in_table"] and not is_excluded and (words<config.min_paragraph_words or words>config.max_paragraph_words):
            item=_finding(length_rule,proxy,p["text"],f"El párrafo contiene {words} palabras; revise su unidad y extensión.",status="possible",method="structure")
            out.append(_with_effective(item,{"word_count":words,"minimum":config.min_paragraph_words,"maximum":config.max_paragraph_words},[{"xml_path":p["xml_path"]}]))
        if p["in_table"] and re.search(r"\d",p["text"]) and rule and not p["has_decimal_tab"]:
            item=_finding(rule,proxy,p["text"],"La celda contiene cifras sin tabulador decimal explícito; valide su alineación visual.",status="possible",method="format")
            out.append(_with_effective(item,{"decimal_tab":{"value":False,"source":p.get("decimal_tab_source","unknown")},"alignment":fmt["alignment"]},[{"xml_path":p["xml_path"]}]))
    border_rule=by.get("ASF-ED-II-09-02")
    if border_rule:
        for table in data["tables"]:
            if table["vertical_borders"]:
                p={"id":f"table-{table['index']:04d}","text":"Bordes de cuadro","headings":[]}
                item=_finding(border_rule,p,p["text"],"El cuadro contiene bordes verticales explícitos.",method="format")
                out.append(_with_effective(item,{"vertical_borders":table["vertical_borders"],"suppressed":table.get("suppressed_vertical_borders",[])},[{"table_index":table["index"]}]))
    note=by.get("ASF-ED-III-03-03")
    if note:
        for p in data.get("supplementary",[]):
            fmt=p["format"]; name=fmt["font_name"]["value"]; size=fmt["font_size"]["value"]; alignment=fmt["alignment"]["value"]
            deviations=[]
            if name and str(name).lower()!="calibri":deviations.append("font_name")
            if size is not None and abs(float(size)-8)>.05:deviations.append("font_size")
            if alignment is not None and alignment!="JUSTIFY":deviations.append("alignment")
            if deviations:
                proxy={"id":f"{p['part']}:{p['xml_path']}","text":p["text"],"headings":[]}
                item=_finding(note,proxy,p["text"],"El formato efectivo de la nota no cumple Calibri 8 y alineación justificada.",method="format")
                out.append(_with_effective(item,{key:fmt[key] for key in ("font_name","font_size","alignment","line_spacing","space_before","space_after","first_line_indent")},[{"part":p["part"],"xml_path":p["xml_path"],"deviations":deviations}]))
    return out, not_eval, excluded


_UNIT_SYMBOLS={"MW","MVA","GWH","GW","MB","MBD","MBPD","MMB","MMBD","MMBPD","MMPC","MMPCD","MMT","MTA"}
_ACRONYM_STOP={"FUENTE","NOTA","TOTAL","CUADRO","CAPÍTULO","RESULTADO","DICTAMEN"}
_KNOWN_INSTITUTIONAL_ACRONYMS={"ASF","CFDI","FAISMUN","FORTAMUN","FORTAMUNDF","AGEB","AGEBS","FAIS","PFM","DOP","CONEVAL","FISM","ZAP","SISGE","ISR","IVA","SPEI","DIF","MIDS"}
_ACRONYM_WORD_STOP={"DE","DEL","LA","LAS","LO","LOS","EL","EN","Y","O","NO","CON","PARA","POR","QUE","AL","SU","SÍ","SI","NÚM","OBRA","OBRAS","GASTO","CUENTA","TIPO","PAGO","NUEVO","GENERAL","URB"}

def _acronym_candidate(token, definitions):
    if token in definitions or token in _KNOWN_INSTITUTIONAL_ACRONYMS:return True
    if token in _ACRONYM_WORD_STOP or re.fullmatch(r"[IVXLCDM]+",token):return False
    letters=re.sub(r"[^A-Z]","",token)
    vowels=sum(ch in "AEIOU" for ch in letters)
    return 2<=len(letters)<=5 and vowels<=1

def load_abbreviations(path=None):
    source=Path(path) if path else ABBREVIATIONS_PATH
    try:data=json.loads(source.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc:raise ValueError(f"Catálogo de abreviaturas inválido: {source}") from exc
    if not isinstance(data.get("general"),dict) or not isinstance(data.get("units"),dict):
        raise ValueError("Catálogo de abreviaturas incompleto.")
    return data

def _acronym_and_abbreviation_findings(document, rules):
    by={r["rule_id"]:r for r in rules}; findings=[]; glossary={}; seen=set()
    abbreviations=load_abbreviations(); known=abbreviations["general"]
    definition=re.compile(r"([A-ZÁÉÍÓÚÑ][\wáéíóúñ.-]+(?:\s+(?:de|del|la|las|los|y|[A-ZÁÉÍÓÚÑ][\wáéíóúñ.-]+)){1,12})\s*\(([A-ZÁÉÍÓÚÑ]{2,})\)")
    acronym=re.compile(r"\b[A-ZÁÉÍÓÚÑ]{2,}\b")
    for p,table,cell in _blocks(document["blocks"]):
        text=p.get("text",""); definitions={m.group(2):m.group(1).strip() for m in definition.finditer(text)}
        heading=" ".join(x.get("text","") for x in p.get("headings",[])).lower()
        scope="special:"+heading if any(x in heading for x in ("acciones y recomendaciones","dictamen")) else "document"
        for sigla,name in definitions.items():
            glossary.setdefault(sigla,{"acronym":sigla,"denomination":name,"first_location":p["id"],"status":"defined"})
        for m in acronym.finditer(text):
            sigla=m.group();
            if sigla.upper() in _UNIT_SYMBOLS or sigla in _ACRONYM_STOP or not _acronym_candidate(sigla,definitions):continue
            if sigla not in glossary:glossary[sigla]={"acronym":sigla,"denomination":None,"first_location":p["id"],"status":"unknown"}
            key=(scope,sigla)
            malformed_plural=bool(re.match(r"(?:['’]s|s)\b",text[m.end():]))
            if key not in seen and sigla not in definitions and not malformed_plural and "ASF-ED-II-08-04B" in by:
                item=_finding(by["ASF-ED-II-08-04B"],p,sigla,"La primera mención detectable de la sigla no incluye una denominación completa inmediata.",status="possible")
                if table:item["location"].update(table_id=table["id"],cell_reference=cell["id"] if cell else None)
                findings.append(item)
            seen.add(key)
        if "ASF-ED-II-08-01" in by:
            for raw,correct in known.items():
                for m in re.finditer(rf"\b{re.escape(raw)}\b(?!\.)",text,re.I):
                    findings.append(_finding(by["ASF-ED-II-08-01"],p,m.group(),f"La abreviatura debe terminar en punto: {correct}",correct,status="possible"))
    return findings,sorted(glossary.values(),key=lambda x:(x["first_location"],x["acronym"]))

def _decimal_places(raw):
    match=re.search(r"\.([0-9]+)",str(raw)); return len(match.group(1)) if match else 0

def _numeric_editorial_findings(document, inventory, rules):
    by={r["rule_id"]:r for r in rules}; result=[]
    paragraphs={p["id"]:p for p,_,_ in _blocks(document["blocks"])}; groups={}
    for number in (inventory or {}).get("cifras",[]):
        unit=number.get("unidad_canonica") or number.get("unidad_original")
        multiplier=str(number.get("multiplicador") or "")
        if not unit:continue
        key=(number.get("elemento_id"),unit,multiplier,number.get("encabezado_columna"))
        groups.setdefault(key,[]).append(number)
    rule=by.get("ASF-ED-II-07-14")
    if rule:
        for (pid,unit,multiplier,column),numbers in groups.items():
            decimals={_decimal_places(n.get("valor_original")) for n in numbers}
            if len(numbers)>1 and len(decimals)>1 and pid in paragraphs:
                p=paragraphs[pid]; span=", ".join(str(n.get("valor_original")) for n in numbers[:5])
                item=_finding(rule,p,span,"Cantidades comparables del mismo orden utilizan distinta cantidad de decimales.",status="possible")
                item["effective_value"]={"decimal_places":sorted(decimals),"unit":unit,"multiplier":multiplier,"column":column}
                item["value_source"]="numbers-1.3"; item["structural_evidence"]=[{"number_id":n["id"],"raw":n.get("valor_original")} for n in numbers]
                result.append(item)
    percentage_rule=by.get("ASF-ED-II-07-15")
    scale_rule=by.get("ASF-ED-II-07-16")
    broad_groups={}
    for number in (inventory or {}).get("cifras",[]):
        unit=number.get("unidad_canonica") or number.get("unidad_original")
        row=number.get("encabezado_fila") or number.get("elemento_id")
        column=number.get("encabezado_columna")
        broad_groups.setdefault((row,column,unit),[]).append(number)
    for (row,column,unit),numbers in broad_groups.items():
        pid=numbers[0].get("elemento_id") if numbers else None
        if len(numbers)<2 or pid not in paragraphs:continue
        p=paragraphs[pid]; decimals={_decimal_places(n.get("valor_original")) for n in numbers}
        is_percentage=any(n.get("tipo")=="porcentaje" or str(unit).lower() in {"%","porcentaje"} for n in numbers)
        if percentage_rule and is_percentage and len(decimals)>1:
            item=_finding(percentage_rule,p,", ".join(str(n.get("valor_original")) for n in numbers[:5]),"Los porcentajes comparables utilizan distinta precisión decimal.",status="possible")
            result.append(_with_effective(item,{"decimal_places":sorted(decimals),"row":row,"column":column},[{"number_id":n["id"]} for n in numbers]))
        multipliers={str(n.get("multiplicador")) for n in numbers if n.get("multiplicador") is not None}
        monetary=any(n.get("tipo")=="importe" for n in numbers)
        if scale_rule and monetary and len(multipliers)>1:
            item=_finding(scale_rule,p,", ".join(str(n.get("texto_original") or n.get("valor_original")) for n in numbers[:5]),"Las cantidades comparables utilizan escalas monetarias diferentes.",status="possible")
            result.append(_with_effective(item,{"multipliers":sorted(multipliers),"unit":unit,"row":row,"column":column},[{"number_id":n["id"],"multiplier":str(n.get("multiplicador"))} for n in numbers]))
    return result

def retrieve_rules(text, rules):
    lowered=text.lower(); selected=[]
    signals={"percentages":("%","por ciento"),"numbers":("peso","miles","millones","/"),"acronyms":("(",),
             "abbreviations":("núm","art.","kg","km"),"grammar":("ando","iendo","que","se "),"wording":tuple(WORDING)+("y/o","mismo que")}
    for rule in rules:
        tokens=signals.get(rule["category"],())
        if rule["category"] in {"grammar","wording"} or any(token in lowered for token in tokens):selected.append(rule)
    return selected


def ollama_schema(rule_ids):
    item={"type":"object","additionalProperties":False,"properties":{"rule_id":{"type":"string","enum":rule_ids},"category":{"type":"string"},"severity":{"type":"string","enum":["error","warning","suggestion","info"]},"problem_span":{"type":"string"},"message":{"type":"string"},"suggested_text":{"type":["string","null"]},"confidence":{"type":"number","minimum":0,"maximum":1}},"required":["rule_id","category","severity","problem_span","message","suggested_text","confidence"]}
    return {"type":"object","additionalProperties":False,"properties":{"findings":{"type":"array","items":item}},"required":["findings"]}

def _parse_response(raw, allowed):
    if isinstance(raw,str):
        try:data=json.loads(raw)
        except json.JSONDecodeError:
            m=re.search(r"\{.*\}",raw,re.S)
            if not m:raise ValueError("editorial_invalid_json")
            try:data=json.loads(m.group())
            except json.JSONDecodeError as exc:raise ValueError("editorial_invalid_json") from exc
    elif isinstance(raw,dict):data=raw
    else:raise ValueError("editorial_invalid_json")
    if set(data)!={"findings"} or not isinstance(data["findings"],list):raise ValueError("editorial_invalid_schema")
    required={"rule_id","category","severity","problem_span","message","suggested_text","confidence"}
    for x in data["findings"]:
        if not isinstance(x,dict) or set(x)!=required or x["rule_id"] not in allowed or x["severity"] not in {"error","warning","suggestion","info"} or not isinstance(x["confidence"],(int,float)):raise ValueError("editorial_invalid_schema")
    return data["findings"]

def _language_tool_finding(paragraph, match):
    rule_data = match.get("rule") or {}
    external_id = str(rule_data.get("id") or "UNKNOWN")
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", external_id)
    offset = max(0, int(match.get("offset") or 0))
    length = max(0, int(match.get("length") or 0))
    span = paragraph.get("text", "")[offset:offset + length]
    replacements = match.get("replacements") or []
    replacement = replacements[0].get("value") if replacements and isinstance(replacements[0], dict) else None
    raw = f"LT-{safe_id}|{paragraph['id']}|{offset}|{span}"
    category = rule_data.get("category") or {}
    return {
        "id": "ED-" + hashlib.sha256(raw.encode()).hexdigest()[:16],
        "rule_id": f"LT-{safe_id}", "external_rule_id": external_id,
        "category": str(category.get("id") or "language"), "severity": "suggestion",
        "detection_method": "language_tool",
        "location": {"section": " > ".join(h["text"] for h in paragraph.get("headings", [])) or None,
                     "paragraph_id": paragraph["id"], "table_id": None, "cell_reference": None},
        "original_text": paragraph.get("text", ""), "problem_span": span,
        "message": str(match.get("message") or rule_data.get("description") or "Sugerencia de LanguageTool."),
        "suggested_text": replacement,
        "source_section": f"LanguageTool: {external_id}", "source_page": None,
        "confidence": "experimental", "validation_status": "possible", "evaluation_status": "possible",
        "effective_value": None, "value_source": "language_tool_local",
        "structural_evidence": [{"offset": offset, "length": length,
                                 "context": (match.get("context") or {}).get("text")}],
        "requires_human_review": True, "autofix_allowed": False, "rejection_reason": None,
    }


def _editorial_focus(item):
    """Clasifica sin alterar el hallazgo: contenido primero, formato aparte."""
    method = str(item.get("detection_method") or "").lower()
    category = str(item.get("category") or "").lower()
    external_rule = str(item.get("external_rule_id") or "").upper()
    if method == "format" or external_rule in {
        "WHITESPACE_RULE", "COMMA_PARENTHESIS_WHITESPACE", "SPACE_UNITIES"
    }:
        return "format"
    if category in {"numbers", "percentages", "tables"}:
        return "data"
    if method == "language_tool" or category in {"grammar", "wording", "acronyms", "abbreviations"}:
        return "language"
    return "structure"


def _ignore_spelling_match(match, text, accepted_terms=(), known_acronyms=()):
    """Elimina ruido ortográfico demostrable sin ocultar palabras comunes dudosas."""
    rule = match.get("rule") or {}
    category = str((rule.get("category") or {}).get("id") or "").upper()
    if category != "TYPOS":
        return False
    offset = max(0, int(match.get("offset") or 0))
    length = max(0, int(match.get("length") or 0))
    span = text[offset:offset + length].strip("  \t\r\n.,;:()[]{}\"'«»")
    if not span or not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", span):
        return True
    normalized = span.casefold()
    accepted = {str(value).casefold() for value in accepted_terms}
    acronyms = {str(value).casefold() for value in known_acronyms}
    if normalized in accepted or normalized in acronyms:
        return True
    letters = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", span)
    if len(letters) < 3:
        return True
    if letters.isupper() and len(letters) <= 12:
        return True
    return False


def review_editorial(path, document, config=None, catalog_path=None, provider=None, inventory=None,
                     visual_verifier=None, language_tool_provider=None):
    started=time.perf_counter(); config=config or EditorialConfig(); catalog=load_editorial_catalog(catalog_path)
    if config.ollama_enabled and config.language_tool_enabled:
        raise ValueError("Sólo puede activarse un proveedor lingüístico a la vez.")
    lt_profile = None
    if config.language_tool_enabled and not config.language_tool_experimental:
        if not config.language_tool_profile_path:
            raise ValueError("LanguageTool requiere un perfil aprobado.")
        from .language_tool_profile import load_language_tool_profile
        lt_profile = load_language_tool_profile(config.language_tool_profile_path)
    rules=[r for r in catalog["rules"] if r["enabled"] and (not config.categories or r["category"] in config.categories)]
    phase_started=time.perf_counter(); findings,_legacy_glossary=_deterministic(document,rules)
    findings+=_safe_context_findings(document,rules)
    method_durations={"deterministic":round(time.perf_counter()-phase_started,6)}
    phase_started=time.perf_counter()
    acronym_findings,glossary=_acronym_and_abbreviation_findings(document,rules); findings+=acronym_findings
    findings+=_numeric_editorial_findings(document,inventory,rules)
    method_durations["linguistic_and_numeric"]=round(time.perf_counter()-phase_started,6)
    not_eval=[]; excluded=[]
    if config.check_format:
        phase_started=time.perf_counter()
        fmt,not_eval,excluded=_format_findings_v2(path,rules,config); findings+=fmt
        method_durations["format"]=round(time.perf_counter()-phase_started,6)
    else:
        excluded.extend({"rule_id":r["rule_id"],"reason":"Comprobaciones de formato desactivadas."} for r in rules if r["detection_type"]=="format")
    contextual=[r for r in rules if r["requires_context"] and r["detection_type"]=="contextual"]; errors=[]; rejected=[]; calls=0; ollama_suggestions=0
    model_info=None; ollama_started=time.perf_counter()
    if config.ollama_enabled:
        from .editorial_models import authorize_model
        descriptor=authorize_model(config.model,experimental=config.experimental_model)
        model_info=asdict(descriptor)
        try:
            client=provider or OllamaEditorialProvider(config)
        except (RuntimeError, ValueError, OSError) as exc:
            client=None
            errors.append({"paragraph_id":None,"rule_id":None,"code":str(exc)})
        for p,table,cell in (_blocks(document["blocks"]) if client is not None else ()):
            if ollama_suggestions >= config.ollama_max_suggestions:break
            text=p.get("text","")[:config.max_fragment_chars]
            relevant=retrieve_rules(text,contextual); allowed={r["rule_id"]:r for r in relevant}
            if not text.strip() or not allowed:continue
            for rule_id, rule in allowed.items():
                if ollama_suggestions >= config.ollama_max_suggestions:break
                request={"fragment":text,"location":{"paragraph_id":p["id"],"headings":p.get("headings",[])},"rules":[rule],"protected_elements":protected_elements(text)}
                try:
                    calls+=1; rows=_parse_response(client.review(request,ollama_schema([rule_id])),{rule_id})
                    for row in rows:
                        if row["confidence"]<config.confidence_threshold:continue
                        if not row["problem_span"] or row["problem_span"] not in text:
                            errors.append({"paragraph_id":p["id"],"rule_id":rule_id,"code":"editorial_problem_span_not_literal"}); continue
                        item=_finding(rule,p,row["problem_span"],row["message"],row["suggested_text"],status="possible",method="ollama"); item["confidence"]=row["confidence"]
                        item["requires_human_review"]=True
                        if row["suggested_text"]:
                            safety=verify_protected(text,row["suggested_text"])
                            if not safety["safe"]: item["validation_status"]="rejected"; item["rejection_reason"]="La propuesta altera elementos protegidos."; item["protection_check"]=safety; rejected.append(item); continue
                        findings.append(item); ollama_suggestions+=1
                except (RuntimeError,ValueError) as exc: errors.append({"paragraph_id":p["id"],"rule_id":rule_id,"code":str(exc)})
        method_durations["ollama"]=round(time.perf_counter()-ollama_started,6)
    language_tool_errors=[]; language_tool_calls=0
    language_tool_started=time.perf_counter()
    lt_client = None  # inicialización defensiva: se asigna solo si language_tool_enabled
    if config.language_tool_enabled:
        from .language_tool import LanguageToolProvider
        if language_tool_provider is not None:
            lt_client=language_tool_provider
        else:
            lt_client=LanguageToolProvider(config.language_tool_url,config.language_tool_language,
                                           config.language_tool_timeout_seconds)
            if config.language_tool_cache_path:
                from .language_tool import CachedLanguageToolProvider
                lt_client=CachedLanguageToolProvider(lt_client,config.language_tool_cache_path,
                                                     namespace=config.language_tool_cache_namespace)
        profile_rules = tuple(lt_profile.approved_rule_ids) if lt_profile else ()
        if lt_profile and config.language_tool_rule_ids and not set(config.language_tool_rule_ids) <= set(profile_rules):
            raise ValueError("La configuración solicita reglas fuera del perfil aprobado de LanguageTool.")
        active_rule_ids = profile_rules or config.language_tool_rule_ids
        allowed_categories = {value.upper() for value in config.language_tool_categories}
        excluded_categories = {value.upper() for value in config.language_tool_excluded_categories}
        if lt_profile:
            excluded_categories.update(value.upper() for value in lt_profile.excluded_categories)
        accepted_terms = tuple(config.language_tool_accepted_terms) + (
            tuple(lt_profile.accepted_terms) if lt_profile else ()
        )
        known_acronyms = {item.get("acronym") for item in glossary if item.get("acronym")}
        for p,table,cell in _blocks(document["blocks"]):
            text=p.get("text", "")[:config.max_fragment_chars]
            style = str((p.get("style") or {}).get("name") or "").casefold()
            words = len(re.findall(r"\b\w+\b", text, re.UNICODE))
            if (not text.strip() or table is not None or p.get("heading_level") is not None
                    or any(pattern.casefold() in style for pattern in config.excluded_style_patterns)
                    or words < config.min_paragraph_words or words > config.max_paragraph_words):
                continue
            try:
                language_tool_calls += 1
                matches = lt_client.check(text, rule_ids=active_rule_ids)
                for match in matches:
                    category = str(((match.get("rule") or {}).get("category") or {}).get("id") or "").upper()
                    if allowed_categories and category not in allowed_categories:
                        continue
                    if category in excluded_categories:
                        continue
                    if _ignore_spelling_match(match, text, accepted_terms, known_acronyms):
                        continue
                    item = _language_tool_finding(p, match)
                    if table:
                        item["location"].update(table_id=table["id"], cell_reference=cell["id"] if cell else None)
                    if item["suggested_text"]:
                        start=item["structural_evidence"][0]["offset"]
                        end=start+item["structural_evidence"][0]["length"]
                        proposed=text[:start]+item["suggested_text"]+text[end:]
                        safety=verify_protected(text, proposed)
                        if not safety["safe"]:
                            item["suggested_text"]=None
                            item["rejection_reason"]="La propuesta de LanguageTool altera elementos protegidos."
                            item["protection_check"]=safety
                            rejected.append(item.copy())
                    findings.append(item)
            except RuntimeError as exc:
                language_tool_errors.append({"paragraph_id":p["id"],"code":str(exc)})
                break
        method_durations["language_tool"]=round(time.perf_counter()-language_tool_started,6)
    from .visual import NullVisualVerifier
    visual=(visual_verifier or NullVisualVerifier()).verify(path,document)
    findings.extend(visual.get("findings",[]))
    findings.sort(key=lambda x:(x["rule_id"],x["location"]["paragraph_id"],x["id"]))
    for item in findings:
        item["review_focus"]=_editorial_focus(item)
    for rule in rules:
        if rule["detection_type"]=="contextual" and not config.ollama_enabled:
            excluded.append({"rule_id":rule["rule_id"],"reason":"Ollama contextual desactivado."})
    not_evaluable_ids={x["rule_id"] for x in not_eval}; excluded_ids={x["rule_id"] for x in excluded}
    coverage={}
    for r in rules:
        count=sum(x["rule_id"]==r["rule_id"] for x in findings)
        status="not_evaluable" if r["rule_id"] in not_evaluable_ids else "excluded" if r["rule_id"] in excluded_ids and count==0 else "evaluated"
        coverage[r["rule_id"]]={"status":status,"findings":count,"source_section":r["source_section"],"source_page":r["source_page"]}
    by_focus=Counter(item["review_focus"] for item in findings)
    groups_by_focus=Counter()
    for focus in by_focus:
        groups_by_focus[focus]=len({(x["rule_id"],x["message"],x["evaluation_status"])
                                    for x in findings if x["review_focus"]==focus})
    _ollama_status = {
        "enabled": config.ollama_enabled,
        "experimental": config.experimental_model,
        "research_mode": config.ollama_prompt_mode == "research_high_recall",
        "suggestions": ollama_suggestions,
        "max_suggestions": config.ollama_max_suggestions,
        "model": model_info,
        "calls": calls,
        "errors": errors,
        "status": "complete" if not errors else "partial",
        "duration_seconds": method_durations.get("ollama", 0.0),
    }
    if config.ollama_prompt_mode == "research_high_recall":
        from .ollama_research import (
            EVALUATION_SHA256, METRICS, MODEL_DIGEST, PROMPT_SHA256,
            PROMPT_VERSION, SOURCE_COMMIT,
        )
        _ollama_status["research_evidence"] = {
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256,
            "evaluation_sha256": EVALUATION_SHA256,
            "source_commit": SOURCE_COMMIT,
            "model_digest": MODEL_DIGEST,
            "metrics": METRICS,
        }
    _lt_status = {
        "enabled": config.language_tool_enabled,
        "experimental": config.language_tool_experimental,
        "provider": "language_tool",
        "language": config.language_tool_language,
        "calls": language_tool_calls,
        "errors": language_tool_errors,
        "status": (
            "disabled" if not config.language_tool_enabled
            else "complete" if not language_tool_errors
            else "partial"
        ),
        "duration_seconds": method_durations.get("language_tool", 0.0),
        "cache": getattr(lt_client, "stats", {}) if config.language_tool_enabled else {},
        "profile": None if lt_profile is None else {
            "profile_version": lt_profile.profile_version,
            "status": lt_profile.status,
            "sha256": lt_profile.sha256,
            "approved_rule_count": len(lt_profile.approved_rule_ids),
        },
    }
    _summary = {
        "findings": len(findings),
        "substantive_findings": len(findings) - by_focus.get("format", 0),
        "format_occurrences": by_focus.get("format", 0),
        "distinct_rules": len({x["rule_id"] for x in findings}),
        "distinct_groups": len({(x["rule_id"], x["message"], x["evaluation_status"]) for x in findings}),
        "by_focus": dict(by_focus),
        "groups_by_focus": dict(groups_by_focus),
        "by_severity": dict(Counter(x["severity"] for x in findings)),
        "by_category": dict(Counter(x["category"] for x in findings)),
        "by_method": dict(Counter(x["detection_method"] for x in findings)),
        "by_evaluation_status": dict(Counter(x["evaluation_status"] for x in findings)),
        "rejected_suggestions": len(rejected),
        "duration_by_method": method_durations,
    }
    _config_out = {
        "autofix": False,
        "confidence_threshold": config.confidence_threshold,
        "min_paragraph_words": config.min_paragraph_words,
        "max_paragraph_words": config.max_paragraph_words,
        "check_format": config.check_format,
        "experimental_model": config.experimental_model,
        "ollama_prompt_mode": config.ollama_prompt_mode,
        "ollama_max_suggestions": config.ollama_max_suggestions,
        "language_tool_experimental": config.language_tool_experimental,
    }
    return {
        "schema_version": "editorial-asf-1.0",
        "enabled": config.enabled,
        "catalog_version": catalog["catalog_version"],
        "document_code": catalog["document_code"],
        "document_version": catalog["document_version"],
        "model": config.model if config.ollama_enabled else None,
        "ollama": _ollama_status,
        "language_tool": _lt_status,
        "visual_verification": visual,
        "coverage": coverage,
        "rules_evaluated": [rid for rid, item in coverage.items() if item["status"] == "evaluated"],
        "rules_not_evaluable": not_eval,
        "rules_excluded": excluded,
        "findings": findings,
        "rejected_suggestions": rejected,
        "acronym_glossary": glossary,
        "summary": _summary,
        "duration_seconds": round(time.perf_counter() - started, 6),
        "config": _config_out,
    }
