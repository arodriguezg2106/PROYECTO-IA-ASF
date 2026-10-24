"""Configuración fija del asistente experimental de alta cobertura para la demo."""

import hashlib


MODEL_ID = "gemma3:12b"
MODEL_DIGEST = "b92b218582c521ba287f38f1d6057dcd3c6cbff036f13cac97b5d861f5e58ec3"
PROMPT_VERSION = "editorial-context-research-recall-1.0"
EVALUATION_SHA256 = "43662d3e6d19ab91f4eb7a2273489ea5306611f14bf5f4e97e0d930bfed8fb7a"
SOURCE_COMMIT = "cf04c763037fc38ffb43006188a10c27ff8c33b9"
MAX_SUGGESTIONS = 5
CONFIDENCE_THRESHOLD = 0.7
METRICS = {
    "cases": 10,
    "repetitions": 3,
    "precision": 0.375,
    "recall": 0.75,
    "accuracy": 0.4,
    "prediction_agreement": 1.0,
    "invalid_responses": 0,
    "unsafe_suggestions": 0,
}

SYSTEM_PROMPT = (
    "Actúas como revisor editorial de documentos de fiscalización de la Auditoría "
    "Superior de la Federación. Revisa exclusivamente el fragmento conforme a las "
    "reglas incluidas. No inventes reglas ni hechos; no cambies el sentido técnico, "
    "jurídico o fiscalizador, cifras, importes, porcentajes, fechas, folios, nombres, "
    "siglas ni referencias normativas. Si no hay evidencia suficiente, no generes "
    "hallazgo. No señales una oración sólo por usar voz pasiva, ser breve, técnica o "
    "concluyente: explica un problema concreto sustentado por una regla. El problem_span "
    "debe ser un substring literal exacto del fragmento. Devuelve exclusivamente JSON "
    "válido. Una propuesta dependiente del contexto requiere revisión humana."
)
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()
