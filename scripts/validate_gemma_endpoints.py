"""Comparación independiente de transporte Gemma, sólo biblioteca estándar.

No importa la aplicación, cambia proveedores aprobados ni modifica consistency-v1.
Las claves se leen del entorno y nunca forman parte del diario.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import http.client
import json
import os
import re
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS = {
    'ollama': 'https://ollama.com/api/chat',
    'gemini': 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent',
}
MODELS = {'ollama': 'gemma4:31b', 'gemini': 'gemma-4-31b-it'}
KEY_NAMES = {'ollama': 'OLLAMA_API_KEY', 'gemini': 'GEMINI_API_KEY'}
GEMINI_STREAM_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:streamGenerateContent?alt=sse'
CDMX = timezone(timedelta(hours=-6))
REDACTED = '[CLAVE_OMITIDA]'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def scrub(value, secrets):
    """Preserva errores completos salvo credenciales, aun si el servidor las refleja."""
    if isinstance(value, dict):
        return {scrub(str(k), secrets): scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secrets) for v in value]
    if not isinstance(value, str):
        return value
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        variants = {secret, urllib.parse.quote(secret, safe=''),
                    json.dumps(secret, ensure_ascii=True)[1:-1]}
        for variant in variants:
            value = value.replace(variant, REDACTED)
    return re.sub(r'AIza[\w-]{20,}', REDACTED, value)


def save(path, value, secrets=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as handle:
        json.dump(scrub(value, secrets), handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def source_symbol(relative, name, namespace=None):
    """Extrae sólo el símbolo indicado del código local, sin importar sus módulos."""
    source = (ROOT / relative).read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if namespace is None:
                return ast.literal_eval(node.value)
            return eval(compile(ast.Expression(node.value), relative, 'eval'),
                        {'__builtins__': {}, **namespace})
        if isinstance(node, ast.FunctionDef) and node.name == name:
            scope = {'__builtins__': {}}
            exec(compile(ast.Module(body=[node], type_ignores=[]), relative, 'exec'), scope)
            return scope[name]
    raise ValueError('Símbolo de configuración no encontrado: ' + name)


def red_png():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    pixels = (b'\0' + b'\xff\0\0' * 64) * 64
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 64, 64, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')


def load_cases(include_image=False):
    base = source_symbol('src/revisor_crf/editorial.py', 'SYSTEM_PROMPT')
    schema = source_symbol('src/revisor_crf/editorial.py', 'ollama_schema')(['ASF-ED-I-CONTEXT'])
    prompt = source_symbol('scripts/evaluate_ollama_cloud.py', 'CLOUD_PROMPT',
                           {'SYSTEM_PROMPT': base, 'SCHEMA': schema, 'json': json})
    bank = json.loads((ROOT / 'src/revisor_crf/editorial_consistency_bank.json').read_text(encoding='utf-8'))
    if bank.get('synthetic') is not True:
        raise ValueError('El banco debe estar declarado sintético.')
    catalog = json.loads((ROOT / 'src/revisor_crf/editorial_catalog.json').read_text(encoding='utf-8'))
    rule = next(row for row in catalog['rules'] if row['rule_id'] == 'ASF-ED-I-CONTEXT')
    cases = [{'id': 'saludo', 'system': '', 'text': 'Hola, responde con una sola palabra: ¿funcionas?',
              'source': 'Solicitud del usuario', 'max_tokens': 64}]
    for case_id in ('C01', 'C14', 'C26'):
        case = next(row for row in bank['cases'] if row['case_id'] == case_id)
        request = {'fragment': case['fragment'], 'location': {'case_id': case_id},
                   'rules': [rule], 'criteria': bank['evaluation_criteria'], 'protected_elements': []}
        cases.append({'id': case_id, 'system': prompt, 'text': json.dumps(request, ensure_ascii=False),
            'source': 'src/revisor_crf/editorial_consistency_bank.json#' + case_id,
            'expected_finding': case['expected_finding'], 'max_tokens': 2048})
    if include_image:
        cases.append({'id': 'imagen_sintetica', 'system': '', 'text': '¿Qué color predomina en esta imagen? Responde con una sola palabra.',
                      'source': 'PNG rojo sintético de 64×64 generado en memoria', 'max_tokens': 64,
                      'image_base64': base64.b64encode(red_png()).decode('ascii')})
    return cases, schema


def payload(provider, case):
    if provider == 'ollama':
        messages = []
        if case['system']:
            messages.append({'role': 'system', 'content': case['system']})
        user = {'role': 'user', 'content': case['text']}
        if 'image_base64' in case:
            user['images'] = [case['image_base64']]
        messages.append(user)
        return {'model': MODELS[provider], 'messages': messages, 'stream': False, 'think': False,
                'options': {'temperature': 0, 'seed': 20260923, 'num_predict': case['max_tokens']}}
    parts = [{'text': case['text']}]
    if 'image_base64' in case:
        parts.append({'inlineData': {'mimeType': 'image/png', 'data': case['image_base64']}})
    if case.get('gemini_minimal'):
        return {'contents': [{'role': 'user', 'parts': parts}]}
    if case.get('gemini_stream_high'):
        return {'contents': [{'role': 'user', 'parts': parts}],
                'generationConfig': {'thinkingConfig': {'thinkingLevel': 'HIGH'}, 'maxOutputTokens': 2048}}
    result = {'contents': [{'role': 'user', 'parts': parts}],
              'generationConfig': {'temperature': 0, 'seed': 20260923, 'maxOutputTokens': case['max_tokens'],
                                   'thinkingConfig': {'thinkingLevel': 'minimal'}}}
    if case['system']:
        result['systemInstruction'] = {'role': 'system', 'parts': [{'text': case['system']}]}
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def endpoint(provider, case):
    return GEMINI_STREAM_ENDPOINT if provider == 'gemini' and case.get('gemini_streaming') else ENDPOINTS[provider]


def merge_sse(raw):
    """Une texto visible y toma los últimos conteos acumulados, sin sumarlos."""
    events, lines = [], []
    for line in raw.splitlines() + ['']:
        if not line:
            if lines:
                value = '\n'.join(lines)
                if value != '[DONE]':
                    event = json.loads(value)
                    if not isinstance(event, dict):
                        raise ValueError('Evento SSE no es un objeto JSON.')
                    events.append(event)
                lines = []
        elif line.startswith('data:'):
            lines.append(line[5:].lstrip(' '))
    if not events:
        raise ValueError('No llegaron eventos SSE interpretables.')
    visible, usage, model, finish, stream_error = [], {}, None, None, None
    for event in events:
        if event.get('error'):
            stream_error = event['error']
            break
        usage.update(event.get('usageMetadata') or {})
        model = event.get('modelVersion', model)
        for candidate in event.get('candidates') or []:
            if candidate.get('index', 0) != 0:
                continue
            finish = candidate.get('finishReason', finish)
            visible.extend(part['text'] for part in candidate.get('content', {}).get('parts', [])
                           if isinstance(part.get('text'), str) and not part.get('thought'))
    if not finish and not stream_error:
        raise ValueError('El stream terminó sin finishReason; no se presume una respuesta completa.')
    result = {'candidates': [{'content': {'parts': [{'text': ''.join(visible)}]}, 'finishReason': finish}],
              'usageMetadata': usage, 'modelVersion': model, 'stream_events': len(events)}
    if stream_error:
        result['error'] = stream_error
    return result


def diagnostic(code, body):
    if code in (401, 403):
        return 'Revisar clave, permisos, restricciones de clave, región y habilitación de API; no habilitar facturación.'
    if code == 429:
        return 'Límite/cuota del proyecto; no reintentar automáticamente ni asumir que cambiar de llave lo resuelve.'
    if code == 400:
        return 'Revisar cuerpo y mensaje completo: argumentos, parámetros, imágenes o clave inválida.'
    if code == 402 or any(word in body.lower() for word in ('insufficient credit', 'payment required', 'purchase credits')):
        return 'Posible falta de créditos o requisito de pago; detener este proveedor, sin comprar créditos.'
    if code == 404:
        return 'Modelo o ruta no disponible para este proyecto; no sustituir silenciosamente el modelo.'
    if code and code >= 500:
        return 'Error del servicio; conservar evidencia sin reintentos automáticos.'
    return 'Consultar el error completo; un fallo de transporte no tiene código HTTP ni prueba una clave inválida.'


def token_usage(provider, body):
    usage = body if provider == 'ollama' else (body.get('usageMetadata') or {})
    names = ({'input': 'prompt_eval_count', 'cached_input': 'prompt_eval_cached_count', 'output': 'eval_count'}
             if provider == 'ollama' else {'input': 'promptTokenCount', 'cached_input': 'cachedContentTokenCount',
                 'output': 'candidatesTokenCount', 'total': 'totalTokenCount', 'thinking': 'thoughtsTokenCount'})
    return {name: usage.get(field) if type(usage.get(field)) is int and usage[field] >= 0 else None
            for name, field in names.items()}


def strict_json(text):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Clave JSON repetida: ' + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique_pairs)


def analysis_check(text, case, schema):
    if 'expected_finding' not in case:
        return None
    try:
        data = strict_json(text)
        if not (isinstance(data, dict) and set(data) == {'findings'} and isinstance(data['findings'], list)):
            raise ValueError('invalid_findings')
        fields = set(schema['properties']['findings']['items']['required'])
        for finding in data['findings']:
            if not (isinstance(finding, dict) and set(finding) == fields
                    and all(isinstance(finding[k], str) for k in fields - {'confidence', 'suggested_text'})
                    and finding['rule_id'] == 'ASF-ED-I-CONTEXT'
                    and finding['severity'] in ('error', 'warning', 'suggestion', 'info')
                    and finding['problem_span'].strip()
                    and (finding['suggested_text'] is None or isinstance(finding['suggested_text'], str))
                    and type(finding['confidence']) in (int, float) and 0 <= finding['confidence'] <= 1):
                raise ValueError('invalid_finding')
        return {'json_schema_valid': True, 'finding_count': len(data['findings']),
                'expected_decision_matches': bool(data['findings']) == case['expected_finding'],
                'editorial_quality_approved': False}
    except (ValueError, TypeError, KeyError):
        return {'json_schema_valid': False, 'editorial_quality_approved': False}


def call(provider, case, key, secrets, schema, timeout=60, opener=None):
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    streaming = provider == 'gemini' and case.get('gemini_streaming')
    if streaming:
        headers['Accept'] = 'text/event-stream'
    headers['Authorization' if provider == 'ollama' else 'x-goog-api-key'] = ('Bearer ' if provider == 'ollama' else '') + key
    request = urllib.request.Request(endpoint(provider, case), data=json.dumps(payload(provider, case), ensure_ascii=False).encode('utf-8'),
                                     headers=headers, method='POST')
    result = {'status': 'error', 'http_status': None, 'latency_seconds': None,
              'response_text': None, 'response_body': None, 'tokens': None, 'error': None}
    start = time.perf_counter()
    try:
        with (opener or urllib.request.build_opener(NoRedirect())).open(request, timeout=timeout) as response:
            result['http_status'] = response.status
            result['response_body'] = response.read().decode('utf-8', errors='replace')
        body = merge_sse(result['response_body']) if streaming else json.loads(result['response_body'])
        if not isinstance(body, dict):
            raise ValueError('La envoltura de respuesta no es un objeto JSON.')
        result['tokens'] = token_usage(provider, body)
        result['stream_events'] = body.get('stream_events')
        result['returned_model'] = body.get('model', body.get('modelVersion'))
        if body.get('error'):
            result['service_error_code'] = (body['error'].get('code')
                                            if isinstance(body['error'], dict) else None)
            raise ValueError('El servicio devolvió error dentro de una respuesta HTTP exitosa.')
        if provider == 'ollama':
            text = body.get('message', {}).get('content')
        else:
            candidates = body.get('candidates') or []
            parts = candidates[0].get('content', {}).get('parts', []) if candidates else []
            text = ''.join(p['text'] for p in parts if isinstance(p.get('text'), str) and not p.get('thought'))
        if not isinstance(text, str) or not text.strip():
            raise ValueError('No llegó texto visible; revisar bloqueos, finishReason y respuesta completa.')
        result.update(status='received', response_text=text, analysis=analysis_check(text, case, schema),
                      returned_model=body.get('model', body.get('modelVersion')),
                      stream_events=body.get('stream_events'))
    except urllib.error.HTTPError as exc:
        result['http_status'] = exc.code
        try:
            result['response_body'] = exc.read().decode('utf-8', errors='replace')
        except (OSError, ValueError) as read_error:
            result['body_read_error'] = str(read_error)
        finally:
            exc.close()
        result['error'] = {'type': type(exc).__name__, 'message': str(exc), 'reason': str(exc.reason),
                           'body': result['response_body'], 'diagnostic': diagnostic(exc.code, result['response_body'] or '')}
    except (urllib.error.URLError, OSError, ValueError, TypeError, AttributeError, http.client.HTTPException) as exc:
        partial = getattr(exc, 'partial', None)
        if isinstance(partial, bytes):
            result['response_body'] = partial.decode('utf-8', errors='replace')
        result['error'] = {'type': type(exc).__name__, 'message': str(exc),
                           'diagnostic': diagnostic(result.get('service_error_code') or result['http_status'], result['response_body'] or '')}
    finally:
        result['latency_seconds'] = round(time.perf_counter() - start, 4)
    return scrub(result, secrets)


def recommendation(rows):
    gemini = [r for r in rows if r['provider'] == 'gemini' and r['case_id'] != 'imagen_sintetica']
    if any(r.get('request_mode') == 'streaming_diagnostic' for r in gemini):
        succeeded = [r['case_id'] for r in gemini if r['status'] == 'received']
        if succeeded:
            return 'Hubo respuesta con streaming en: ' + ', '.join(succeeded) + '. Falta validar los casos editoriales; la comparación histórica sin streaming se conserva por separado.'
        return 'El diagnóstico de streaming no confirmó acceso funcional. Conservar los errores y no atribuir el fallo a una sola causa ni aprobar la migración.'
    if any(r.get('request_mode') == 'minimal' for r in gemini):
        if all(r['status'] == 'received' for r in gemini):
            return 'El acceso básico a Gemini funcionó con cuerpo mínimo. Falta aislar qué parámetro causó el fallo anterior y ejecutar los casos editoriales; no aprobar todavía la migración.'
        return 'El diagnóstico mínimo no confirmó acceso funcional a Gemini. Conservar el error observado; no habilitar facturación ni cambiar de modelo automáticamente.'
    if gemini and all(r['status'] == 'received' and (r.get('analysis') or {}).get('json_schema_valid', True) for r in gemini):
        return 'Gemini es candidato técnico para continuar con texto sintético. Falta validar calidad editorial y estabilidad; no reemplazar todavía Ollama ni aprobar uso institucional.'
    if not any(r.get('http_status') is not None for r in gemini):
        return 'Gemini pendiente de validación remota: no hay respuestas HTTP observadas. Resolver credenciales o transporte antes de concluir disponibilidad.'
    return 'Gemini todavía no supera todos los casos de conectividad/formato. Revisar errores exactos y corregir su causa antes de continuar; conservar Ollama en paralelo.'


def render_report(state):
    minimal = state.get('diagnostic_mode') == 'gemini_minimal'
    streaming = state.get('diagnostic_mode') == 'gemini_streaming'
    lines = ['# Validación comparativa: Gemma en Ollama Cloud y Gemini API', '',
        'Actualización UTC: ' + state['updated_at'] + '. Hora CDMX: ' + datetime.fromisoformat(state['updated_at']).astimezone(CDMX).isoformat() + '.', '',
        '**Conclusión:** ' + recommendation(state['attempts']), '',
        'Prueba independiente de conectividad y formato, no aprobación editorial ni continuación de consistency-v1.', '',
        '## Resumen de resultados observados', '',
        '| Vía | Solicitudes enviadas | HTTP 2xx | Latencia media (s) | Tokens entrada / salida |',
        '|---|---:|---:|---:|---|']
    for provider in state['providers']:
        rows = [r for r in state['attempts'] if r['provider'] == provider and r.get('attempted')]
        times = [r['latency_seconds'] for r in rows if r.get('latency_seconds') is not None]
        known = [r['tokens'] for r in rows if (r.get('tokens') or {}).get('input') is not None and r['tokens'].get('output') is not None]
        total = f"{sum(t['input'] for t in known)} / {sum(t['output'] for t in known)}" if known else 'N/D; no se reportaron conteos'
        mean = f'{sum(times)/len(times):.4f}' if times else 'N/D'
        lines.append(f"| {provider} | {len(rows)} | {sum(200 <= r.get('http_status', 0) < 300 for r in rows if r.get('http_status') is not None)} | {mean} | {total} |")
    lines += ['', 'Los tokens desconocidos no se cuentan como cero. La media incluye respuestas fallidas con latencia observada.', '']
    duplicate_findings = []
    for row in state['attempts']:
        if row.get('response_text') and row['case_id'] in ('C01', 'C14', 'C26'):
            try:
                strict_json(row['response_text'])
            except ValueError as exc:
                if 'Clave JSON repetida:' in str(exc):
                    duplicate_findings.append(row['provider'] + '/' + row['case_id'] + ': ' + str(exc))
    if duplicate_findings:
        lines += ['**Observación de formato en revisión posterior:** ' + '; '.join(duplicate_findings) +
                  '. El parser estándar conserva la última aparición; no se considera una respuesta inequívoca para interoperabilidad estricta. Esta observación no reescribe el diario original ni sus banderas iniciales.', '']
    lines += [
        '## Integración conservada', '',
        '- Ollama existente: `scripts/evaluate_ollama_cloud.py`, `CloudSession.chat`, POST `https://ollama.com/api/chat`, modelo `gemma4:31b`, cabecera `Authorization: Bearer` desde `OLLAMA_API_KEY`. Respuesta `message.content`; tokens `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count`.',
        '- Alternativa: POST `https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent`, cabecera `x-goog-api-key` desde `GEMINI_API_KEY`; texto visible en `candidates[0].content.parts[].text` y tokens en `usageMetadata`.',
        '- Se reutilizan el prompt CLOUD_PROMPT, el esquema y la regla actuales, sin importar dependencias externas. Mismo texto de sistema y usuario para ambos proveedores; sin generación restringida por esquema.',
        ('- Diagnóstico de streaming: contents mínimo y una segunda configuración HIGH con límite 2048; temperatura y semilla no se fijan. Los resultados son de transporte y no se combinan con la evaluación editorial.' if streaming else '- Diagnóstico mínimo: sólo contents con el saludo original; sin generationConfig, systemInstruction, semilla, límite de salida ni configuración de razonamiento. No consulta Ollama ni mide calidad editorial.' if minimal else '- Ollama: temperatura 0, semilla 20260923, think=false. Gemini: temperatura 0, misma semilla y thinkingLevel=minimal. Esto no garantiza equivalencia de servicio, plantilla interna, pesos, precisión numérica o determinismo.'), '',
        '## Ejecución', '',
        f"- Diario local: `{state['journal_path']}`. Commit: `{state['source_commit']}`.",
        f"- Modo: {'preparación sin red' if state['dry_run'] else 'solicitudes reales sólo si hay clave'}. Intentos de red registrados: {sum(r.get('attempted', False) for r in state['attempts'])}; máximo por corrida: {state['maximum_requests']}.",
        '- Claves ausentes se registran como omitidas, sin inventar HTTP 401. Sin reintentos automáticos. Los intentos inciertos no se repiten al reanudar.',
        '- No se habilita facturación, compran créditos ni consulta administración de cuentas. Una clave no permite comprobar que el proyecto sigue en tier gratuito.', '',
        *(['Diagnóstico de streaming: POST `' + GEMINI_STREAM_ENDPOINT + '`. Configuraciones de esta corrida: ' + ', '.join(c['id'] for c in state['cases']) + '. El modo HIGH tiene un máximo de 2048 tokens, límite que no aparece en el ejemplo exportado. No se incluyen Google Search ni transcripción de audio, que no forman parte del análisis editorial de texto. No es una reproducción exacta del Playground.', '',
           'Cada configuración se envía como máximo una vez. Un 500 en la primera no impide comprobar la segunda configuración distinta; autenticación, cuota, créditos y transporte detienen el proveedor. Sin reintentos de la misma configuración.', ''] if streaming else []),
        '| Proveedor | Caso | Estado | HTTP observado | Latencia (s) | Tokens entrada / salida / caché |',
        '|---|---|---|---|---:|---|']
    for row in state['attempts']:
        tokens = row.get('tokens') or {}
        lines.append(f"| {row['provider']} | {row['case_id']} | {row['status']} | {row.get('http_status') if row.get('http_status') is not None else 'N/D'} | {row.get('latency_seconds') if row.get('latency_seconds') is not None else 'N/D'} | {tokens.get('input') if tokens.get('input') is not None else 'N/D'} / {tokens.get('output') if tokens.get('output') is not None else 'N/D'} / {tokens.get('cached_input') if tokens.get('cached_input') is not None else 'N/D'} |")
    lines += ['', '## Prompts, respuestas y errores completos', '']
    for case in state['cases']:
        lines += [f"### Caso {case['id']}", '', f"Origen: `{case['source']}`. Sistema SHA-256: `{sha(case['system'].encode())}`.", '',
                  'Prompt de usuario:', '````text', case['text'].replace('````', '[delimitador omitido]'), '````', '']
        for row in (r for r in state['attempts'] if r['case_id'] == case['id']):
            lines += [f"**{row['provider']}**: {row['status']}", '', '````json',
                json.dumps({k: v for k, v in row.items() if k not in ('case_id', 'provider')}, ensure_ascii=False, indent=2).replace('````', '[delimitador omitido]'), '````', '']
    lines += ['## Imágenes y alcance', '',
        'El flujo actual extrae texto del DOCX; no envía imágenes a los modelos. ' +
        ('Se incluyó un PNG sintético rojo opcional; su resultado aparece arriba.' if state['include_image'] else 'La prueba con imagen no aplica al análisis actual y no se ejecutó; puede solicitarse con --include-image.'),
        'Un 400 INVALID_ARGUMENT con imagen sólo confirma el rechazo de ese cuerpo en esa sesión. Sin una prueba remota no se confirma el incidente reportado por el usuario desde el 1 de noviembre; la documentación de Google describe capacidad de imagen en Gemma 4.', '',
        'Existe un [reporte de usuarios en el foro de Google](https://discuss.ai.google.dev/t/gemma-4-on-the-gemini-api-every-request-with-an-image-returns-400-invalid-argument-since-1-nov/197258); es un antecedente, no una confirmación de que ocurra en esta cuenta.', '',
        '## Interpretación de errores', '',
        '- 401/403: revisar llave, permisos y restricciones; 403 también puede obedecer a región o acceso al servicio.',
        '- 429: cuota/límite del proyecto; no prueba por sí solo qué tier tiene la cuenta.',
        '- 400: revisar el cuerpo y mensaje, incluidos parámetros no admitidos, imágenes o clave inválida. 404: modelo/ruta/acceso.',
        '- 402 o mensaje explícito de créditos/pago: detener Ollama. El corte del 9 de noviembre a las 19:40 CDMX es un dato del usuario; no atribuirle un error genérico sin evidencia del servicio.',
        '- Errores TLS/DNS/timeout: HTTP no observado; no se desactiva la validación de certificados.', '',
        '## Costos, cuotas y tratamiento de datos', '',
        'Ollama publica USD 0.14 por millón de tokens de entrada, USD 0.40 de salida y USD 0.05 de entrada en caché. Estimación sin descuento: (entrada × 0.14 + salida × 0.40) / 1,000,000. La caché es parte de la entrada y no debe sumarse otra vez. Una estimación no es un cargo confirmado. [Tarifas oficiales](https://ollama.com/pricing).', '']
    for provider in ('ollama', 'gemini'):
        rows = [r for r in state['attempts'] if r['provider'] == provider]
        known = [r['tokens'] for r in rows if (r.get('tokens') or {}).get('input') is not None and r['tokens'].get('output') is not None]
        if provider == 'ollama' and known:
            estimate = sum(t['input'] * .14 + t['output'] * .40 for t in known) / 1_000_000
            lines += [f'Estimación Ollama sin descuento para {len(known)} respuestas con conteos: USD {estimate:.8f}; solicitudes sin conteos quedan fuera de la estimación.', '']
    lines += ['Gemini/Gemma puede usarse sin cargo dentro de la cuota gratuita disponible; verificar el modelo y los límites del proyecto en AI Studio. No se deduce el saldo desde una respuesta exitosa. [Precios](https://ai.google.dev/gemini-api/docs/pricing), [límites por proyecto](https://ai.google.dev/gemini-api/docs/rate-limits).', '',
        'En servicios gratuitos Google puede utilizar prompts y respuestas para mejorar sus productos; por eso esta corrida sólo usa textos sintéticos versionados, nunca DOCX ni párrafos institucionales. [Condiciones oficiales](https://ai.google.dev/gemini-api/terms).', '',
        'Google documenta el identificador solicitado y el control de razonamiento; no se sustituye por otro modelo. [Gemma en Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api).', '',
        '## Reproducción y manejo de la llave', '',
        'En PowerShell, desde la raíz del repositorio:', '', '```powershell',
        r'powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\validate_gemma_endpoints.ps1' + (' -GeminiStreamHighOnly' if state.get('stream_high_only') else ' -GeminiStreaming' if streaming else ' -GeminiMinimal' if minimal else ''), '```', '',
        'Pegar la clave únicamente en el aviso oculto de la consola. Enter vacío omite Ollama; no pegar claves en el chat, código ni comandos. El ayudante restaura las variables del proceso al finalizar y no usa setx ni archivos .env. Para sólo Gemini añadir -GeminiOnly; para imagen sintética opcional añadir -IncludeImage.', '',
        'El script Python acepta --dry-run (sin red), --providers gemini o --resume RUTA_AL_DIARIO. Cada ejecución nueva guarda otro directorio; reanudar no repite respuestas fallidas, omitidas o inciertas. Este reporte se actualiza con la última corrida; cada corrida guarda también su propio report.md y result.json.', '']
    return '\n'.join(lines)


def run(args, keys=None, opener=None):
    minimal = getattr(args, 'gemini_minimal', False)
    high_only = getattr(args, 'gemini_stream_high_only', False)
    streaming = getattr(args, 'gemini_streaming', False) or high_only
    if minimal and streaming:
        raise ValueError('Elegir un solo modo diagnóstico.')
    if (minimal or streaming) and args.include_image:
        raise ValueError('El diagnóstico mínimo sólo admite texto.')
    providers = ['gemini'] if minimal or streaming else args.providers.split(',')
    if len(set(providers)) != len(providers) or any(p not in ENDPOINTS for p in providers):
        raise ValueError('Proveedores permitidos: ollama,gemini; sin duplicados.')
    keys = keys if keys is not None else {p: os.environ.get(KEY_NAMES[p], '').strip() for p in ENDPOINTS}
    secrets = tuple(keys.values())
    cases, schema = load_cases(args.include_image)
    if minimal:
        cases = [{**cases[0], 'id': 'saludo_minimo', 'gemini_minimal': True}]
    if streaming:
        greeting = cases[0]
        cases = [{**greeting, 'id': 'saludo_stream_minimo', 'gemini_minimal': True, 'gemini_streaming': True},
                 {**greeting, 'id': 'saludo_stream_high', 'gemini_stream_high': True, 'gemini_streaming': True}]
        if high_only:
            cases = cases[1:]
    planned = len(cases) * len(providers)
    if args.resume:
        journal = Path(args.resume).resolve()
        state = json.loads(journal.read_text(encoding='utf-8'))
        if (state['cases'] != cases or state['providers'] != providers or state['dry_run'] != args.dry_run
                or state['timeout_seconds'] != args.timeout):
            raise ValueError('La configuración de reanudación cambió; no se mezclan corridas.')
    else:
        journal = ROOT / 'results/gemma_endpoint_validation' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') / 'result.json'
        try:
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
        except (OSError, subprocess.SubprocessError):
            commit = 'unavailable'
        state = {'schema_version': 'gemma-endpoint-validation-1.0', 'created_at': now(), 'providers': providers,
            'cases': cases, 'dry_run': args.dry_run, 'include_image': args.include_image, 'maximum_requests': planned,
            'source_commit': commit, 'timeout_seconds': args.timeout,
            'diagnostic_mode': 'gemini_streaming' if streaming else 'gemini_minimal' if minimal else None,
            'stream_high_only': high_only,
            'journal_path': journal.relative_to(ROOT).as_posix(), 'attempts': []}
    source_paths = ['scripts/evaluate_ollama_cloud.py', 'src/revisor_crf/editorial.py',
                    'src/revisor_crf/editorial_consistency_bank.json', 'src/revisor_crf/editorial_catalog.json',
                    'scripts/validate_gemma_endpoints.py']
    hashes = {p: sha((ROOT / p).read_bytes()) for p in source_paths}
    if state.get('source_sha256', hashes) != hashes:
        raise ValueError('Cambió la implementación o fuente del banco; no se reanuda.')
    state['source_sha256'] = hashes
    def persist():
        state['updated_at'] = now()
        save(journal, state, secrets)
        report = scrub(render_report(state), secrets)
        (journal.parent / 'report.md').write_text(report, encoding='utf-8', newline='\n')
        report_name = 'VALIDACION_GEMINI_STREAMING.md' if streaming else 'VALIDACION_GEMINI_DIAGNOSTICO.md' if minimal else 'VALIDACION_GEMINI.md'
        (ROOT / report_name).write_text(report, encoding='utf-8', newline='\n')
    persist()
    seen = {r['task_id'] for r in state['attempts']}
    if len(seen) != len(state['attempts']) or len(seen) > planned:
        raise ValueError('Diario inválido o presupuesto excedido.')
    for provider in providers:
        previous = [r for r in state['attempts'] if r['provider'] == provider]
        stopped = any(should_stop(r) and not (streaming and (r.get('service_error_code') or r.get('http_status')) == 500) for r in previous)
        for case in cases:
            task = provider + ':' + case['id']
            if task in seen:
                continue
            row = {'task_id': task, 'provider': provider, 'case_id': case['id'], 'model': MODELS[provider],
                   'request_mode': 'streaming_diagnostic' if streaming else 'minimal' if minimal else 'comparison',
                   'endpoint': endpoint(provider, case), 'started_at': now(), 'attempted': False,
                   'payload_sha256': sha(json.dumps(payload(provider, case), ensure_ascii=False).encode('utf-8'))}
            if args.dry_run or not keys.get(provider) or stopped:
                row.update(status='not_run_dry_run' if args.dry_run else 'skipped_after_error' if stopped else 'skipped_missing_key',
                           http_status=None, latency_seconds=None, response_text=None, tokens=None,
                           error='No se envió solicitud; no es una respuesta del servidor.')
                state['attempts'].append(row)
                persist()
                continue
            row.update(status='uncertain', attempted=True)
            state['attempts'].append(row)
            persist()  # Un corte desde aquí consume el intento: no se repite.
            row.update(call(provider, case, keys[provider], secrets, schema, args.timeout, opener))
            persist()
            print(provider + ' / ' + case['id'] + ': ' + row['status'] + ', HTTP ' + str(row['http_status']))
            stopped = should_stop(row) and not (streaming and (row.get('service_error_code') or row.get('http_status')) == 500)
    persist()
    return state


def should_stop(row):
    code = row.get('service_error_code') or row.get('http_status')
    text = json.dumps(row.get('error'), ensure_ascii=True).lower()
    return (row['status'] == 'uncertain' or row.get('attempted') and
            (code is None or code in (401, 402, 403, 404, 429) or code >= 500 or
             any(word in text for word in ('api_key_invalid', 'insufficient credit', 'payment required', 'purchase credits'))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--providers', default='ollama,gemini')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--include-image', action='store_true')
    parser.add_argument('--gemini-minimal', action='store_true', help='Una solicitud Gemini con sólo contents; no consulta Ollama.')
    parser.add_argument('--gemini-streaming', action='store_true', help='Hasta dos configuraciones Gemini SSE distintas; no consulta Ollama.')
    parser.add_argument('--gemini-stream-high-only', action='store_true', help='Sólo la configuración HIGH pendiente: máximo una solicitud SSE.')
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--timeout', type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120:
        parser.error('Timeout permitido: 1–120 segundos.')
    try:
        state = run(args)
    except KeyboardInterrupt:
        print('Interrumpido. El intento registrado como incierto no se repetirá al reanudar.')
        return 130
    except Exception as exc:
        secrets = [os.environ.get(name, '') for name in KEY_NAMES.values()]
        print(scrub(type(exc).__name__ + ': ' + str(exc), secrets))
        return 1
    report_name = 'VALIDACION_GEMINI_STREAMING.md' if args.gemini_streaming or args.gemini_stream_high_only else 'VALIDACION_GEMINI_DIAGNOSTICO.md' if args.gemini_minimal else 'VALIDACION_GEMINI.md'
    print('Reporte: ' + report_name + '; diario: ' + state['journal_path'])
    return 0 if args.dry_run or all(r['status'] == 'received' for r in state['attempts']) else 2


if __name__ == '__main__':
    raise SystemExit(main())
