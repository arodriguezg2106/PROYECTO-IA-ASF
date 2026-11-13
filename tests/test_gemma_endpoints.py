"""Pruebas sin red ni claves reales; ejecutables con unittest estándar."""
import argparse
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gemma_validation', REPO / 'scripts/validate_gemma_endpoints.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class Response(io.BytesIO):
    status = 200

    def __init__(self, body):
        super().__init__(json.dumps(body).encode('utf-8'))


class SSEResponse(io.BytesIO):
    status = 200

    def __init__(self, events):
        raw = ': comment\r\n\r\n' + ''.join('data: ' + json.dumps(e) + '\r\n\r\n' for e in events)
        super().__init__(raw.encode('utf-8'))


def stream_success(request):
    return SSEResponse([
        {'candidates': [{'content': {'parts': [{'text': 'oculto', 'thought': True}]}}],
         'usageMetadata': {'promptTokenCount': 12, 'candidatesTokenCount': 1}},
        {'candidates': [{'content': {'parts': [{'text': 'Sí.'}]}, 'finishReason': 'STOP'}],
         'usageMetadata': {'promptTokenCount': 12, 'candidatesTokenCount': 3, 'totalTokenCount': 15}},
    ])


def success(request):
    body = json.loads(request.data)
    if request.full_url == v.ENDPOINTS['ollama']:
        return Response({'message': {'content': '{"findings": []}'}, 'prompt_eval_count': 120,
                         'eval_count': 8, 'prompt_eval_cached_count': 90, 'model': 'gemma4:31b'})
    return Response({'candidates': [{'content': {'parts': [{'text': 'oculto', 'thought': True},
                            {'text': '{"findings": []}'}]}}],
                     'usageMetadata': {'promptTokenCount': 125, 'candidatesTokenCount': 8,
                                       'totalTokenCount': 133}, 'modelVersion': 'gemma-4-31b-it'})


class Opener:
    def __init__(self, handler=success):
        self.requests = []
        self.handler = handler

    def open(self, request, timeout):
        self.requests.append(request)
        return self.handler(request)


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.schema = v.load_cases()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for relative in ['scripts/evaluate_ollama_cloud.py', 'src/revisor_crf/editorial.py',
                         'src/revisor_crf/editorial_consistency_bank.json',
                         'src/revisor_crf/editorial_catalog.json', 'scripts/validate_gemma_endpoints.py']:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, target)
        self.root_patch = patch.object(v, 'ROOT', self.root)
        self.root_patch.start()
        self.keys = {'ollama': 'fake-ollama-secret', 'gemini': 'fake-gemini-secret'}

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def args(self, **kwargs):
        values = dict(providers='ollama,gemini', dry_run=False, include_image=False,
                      resume=None, timeout=60)
        values.update(kwargs)
        return argparse.Namespace(**values)

    def run_quiet(self, args, opener, keys=None):
        with redirect_stdout(io.StringIO()):
            return v.run(args, keys=self.keys if keys is None else keys, opener=opener)

    def test_same_text_system_and_current_ollama_contract(self):
        for case in self.cases:
            ollama, gemini = v.payload('ollama', case), v.payload('gemini', case)
            self.assertEqual(ollama['messages'][-1]['content'], gemini['contents'][0]['parts'][0]['text'])
            if case['system']:
                self.assertEqual(ollama['messages'][0]['content'], gemini['systemInstruction']['parts'][0]['text'])
            self.assertFalse(ollama['stream'])
            self.assertFalse(ollama['think'])
            self.assertNotIn('format', ollama)
            self.assertEqual(ollama['options']['seed'], 20260923)

    def test_success_records_tokens_and_uses_header_not_query(self):
        for provider in self.keys:
            opener = Opener()
            row = v.call(provider, self.cases[1], self.keys[provider], tuple(self.keys.values()), self.schema, opener=opener)
            self.assertEqual(row['status'], 'received')
            self.assertEqual(row['http_status'], 200)
            self.assertEqual(row['response_text'], '{"findings": []}')
            self.assertTrue(row['analysis']['json_schema_valid'])
            self.assertEqual(row['tokens']['output'], 8)
            self.assertNotIn(self.keys[provider], opener.requests[0].full_url)
            self.assertIn('Authorization' if provider == 'ollama' else 'X-goog-api-key', opener.requests[0].headers)
            self.assertGreaterEqual(row['latency_seconds'], 0)

    def test_http_errors_are_complete_but_secrets_are_removed(self):
        for code in (400, 401, 402, 403, 429, 500):
            body = json.dumps({'error': {'code': code, 'message': 'x' * 10000 + self.keys['gemini'],
                                        'status': 'INVALID_ARGUMENT'}}).encode()
            def fail(request):
                raise urllib.error.HTTPError(request.full_url, code, 'bad ' + self.keys['ollama'], {}, io.BytesIO(body))
            row = v.call('gemini', self.cases[0], self.keys['gemini'], tuple(self.keys.values()), self.schema, opener=Opener(fail))
            self.assertEqual(row['http_status'], code)
            self.assertIn('x' * 10000, row['error']['body'])
            serialized = json.dumps(row)
            self.assertNotIn(self.keys['gemini'], serialized)
            self.assertNotIn(self.keys['ollama'], serialized)
            self.assertIn(v.REDACTED, serialized)

    def test_quota_stops_ollama_but_continues_gemini(self):
        def quota(request):
            if request.full_url == v.ENDPOINTS['ollama']:
                raise urllib.error.HTTPError(request.full_url, 429, 'quota', {}, io.BytesIO(b'{"error":"quota"}'))
            return success(request)
        opener = Opener(quota)
        state = self.run_quiet(self.args(), opener)
        self.assertEqual(len(opener.requests), 5)
        self.assertEqual(sum(r['status'] == 'skipped_after_error' for r in state['attempts']), 3)
        self.assertEqual(sum(r['status'] == 'received' for r in state['attempts']), 4)
        for path in (self.root / 'results').rglob('*'):
            if path.is_file():
                self.assertNotIn(self.keys['gemini'], path.read_text(encoding='utf-8'))

    def test_dry_run_and_missing_keys_do_not_call_network(self):
        for dry in (True, False):
            opener = Opener()
            state = self.run_quiet(self.args(dry_run=dry), opener, keys={})
            self.assertEqual(len(opener.requests), 0)
            self.assertEqual(len(state['attempts']), 8)
            self.assertTrue(all(r['http_status'] is None for r in state['attempts']))

    def test_resume_does_not_repeat_completed_requests(self):
        opener = Opener()
        state = self.run_quiet(self.args(), opener)
        resume = self.root / state['journal_path']
        self.run_quiet(self.args(resume=resume), opener)
        self.assertEqual(len(opener.requests), 8)

    def test_interrupt_remains_uncertain_and_is_never_retried(self):
        def interrupted(request):
            raise KeyboardInterrupt()
        opener = Opener(interrupted)
        with self.assertRaises(KeyboardInterrupt):
            self.run_quiet(self.args(), opener)
        journal = next((self.root / 'results').rglob('result.json'))
        self.assertEqual(json.loads(journal.read_text())['attempts'][0]['status'], 'uncertain')
        resumed = Opener()
        state = self.run_quiet(self.args(resume=journal), resumed)
        self.assertEqual(len(resumed.requests), 4)
        self.assertEqual(len(state['attempts']), 8)
        self.assertEqual(sum(r['status'] == 'uncertain' for r in state['attempts']), 1)

    def test_tls_error_is_not_reported_as_http_or_bad_key(self):
        def tls(request):
            raise urllib.error.URLError('CERTIFICATE_VERIFY_FAILED')
        row = v.call('gemini', self.cases[0], self.keys['gemini'], tuple(self.keys.values()), self.schema, opener=Opener(tls))
        self.assertIsNone(row['http_status'])
        self.assertIn('CERTIFICATE_VERIFY_FAILED', row['error']['message'])

    def test_invalid_or_empty_envelope_is_not_a_success(self):
        for body in ({'candidates': []}, {'candidates': [{'content': {'parts': [{'thought': True, 'text': 'secret thought'}]}}]}):
            row = v.call('gemini', self.cases[1], self.keys['gemini'], tuple(self.keys.values()), self.schema,
                         opener=Opener(lambda request: Response(body)))
            self.assertEqual(row['status'], 'error')
            self.assertEqual(row['http_status'], 200)
            self.assertIsNotNone(row['response_body'])

    def test_optional_image_uses_same_generated_png(self):
        cases, _ = v.load_cases(True)
        image = cases[-1]
        self.assertEqual(len(cases), 5)
        self.assertEqual(v.payload('ollama', image)['messages'][-1]['images'][0],
                         v.payload('gemini', image)['contents'][0]['parts'][1]['inlineData']['data'])
        self.assertTrue(v.red_png().startswith(b'\x89PNG'))

    def test_changed_timeout_is_not_resumed(self):
        state = self.run_quiet(self.args(), Opener())
        with self.assertRaisesRegex(ValueError, 'configuración'):
            self.run_quiet(self.args(resume=self.root/state['journal_path'], timeout=20), Opener())

    def test_duplicate_json_fields_are_rejected_and_reported(self):
        duplicate = '{"findings": [], "findings": []}'
        self.assertFalse(v.analysis_check(duplicate, self.cases[1], self.schema)['json_schema_valid'])
        state = self.run_quiet(self.args(dry_run=True), Opener(), keys={})
        state['attempts'][1].update(response_text=duplicate)
        self.assertIn('Clave JSON repetida: findings', v.render_report(state))

    def test_minimal_diagnostic_makes_one_gemini_call_and_preserves_comparison(self):
        comparison = self.root / 'VALIDACION_GEMINI.md'
        comparison.write_text('previous comparison', encoding='utf-8')
        opener = Opener()
        state = self.run_quiet(self.args(gemini_minimal=True), opener)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(opener.requests[0].full_url, v.ENDPOINTS['gemini'])
        body = json.loads(opener.requests[0].data)
        self.assertEqual(set(body), {'contents'})
        self.assertEqual(body['contents'][0]['parts'][0]['text'], self.cases[0]['text'])
        self.assertEqual(state['maximum_requests'], 1)
        self.assertEqual(comparison.read_text(encoding='utf-8'), 'previous comparison')
        self.assertIn('acceso básico', (self.root/'VALIDACION_GEMINI_DIAGNOSTICO.md').read_text(encoding='utf-8'))

    def test_minimal_diagnostic_cannot_send_images(self):
        opener = Opener()
        with self.assertRaisesRegex(ValueError, 'sólo admite texto'):
            self.run_quiet(self.args(gemini_minimal=True, include_image=True), opener)
        self.assertEqual(len(opener.requests), 0)

    def test_streaming_assembles_visible_text_and_does_not_add_cumulative_tokens(self):
        case = {**self.cases[0], 'gemini_streaming': True, 'gemini_minimal': True}
        opener = Opener(stream_success)
        row = v.call('gemini', case, self.keys['gemini'], tuple(self.keys.values()), self.schema, opener=opener)
        self.assertEqual(row['status'], 'received')
        self.assertEqual(row['response_text'], 'Sí.')
        self.assertEqual(row['tokens']['output'], 3)
        self.assertEqual(row['tokens']['input'], 12)
        self.assertEqual(row['stream_events'], 2)
        self.assertEqual(opener.requests[0].full_url, v.GEMINI_STREAM_ENDPOINT)
        self.assertEqual(opener.requests[0].headers['Accept'], 'text/event-stream')

    def test_streaming_diagnostic_has_two_distinct_payloads_and_no_ollama(self):
        (self.root/'VALIDACION_GEMINI.md').write_text('old report', encoding='utf-8')
        opener = Opener(stream_success)
        state = self.run_quiet(self.args(gemini_streaming=True), opener)
        self.assertEqual(len(opener.requests), 2)
        self.assertTrue(all(r.full_url == v.GEMINI_STREAM_ENDPOINT for r in opener.requests))
        first, second = [json.loads(r.data) for r in opener.requests]
        self.assertEqual(first, v.payload('gemini', {**self.cases[0], 'gemini_minimal': True}))
        self.assertEqual(second['generationConfig']['thinkingConfig']['thinkingLevel'], 'HIGH')
        self.assertEqual(second['generationConfig']['maxOutputTokens'], 2048)
        self.assertNotIn('tools', second)
        self.assertEqual(state['maximum_requests'], 2)
        self.assertEqual((self.root/'VALIDACION_GEMINI.md').read_text(), 'old report')

    def test_streaming_checks_second_distinct_configuration_after_http_500(self):
        def first_fails(request):
            if 'generationConfig' not in json.loads(request.data):
                raise urllib.error.HTTPError(request.full_url, 500, 'Internal', {}, io.BytesIO(b'{"error":{"code":500}}'))
            return stream_success(request)
        opener = Opener(first_fails)
        state = self.run_quiet(self.args(gemini_streaming=True), opener)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual([r['status'] for r in state['attempts']], ['error', 'received'])

    def test_streaming_error_event_stops_on_quota_even_with_http_200(self):
        opener = Opener(lambda request: SSEResponse([{'error': {'code': 429, 'message': 'quota'}}]))
        state = self.run_quiet(self.args(gemini_streaming=True), opener)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(state['attempts'][0]['service_error_code'], 429)
        self.assertEqual(state['attempts'][1]['status'], 'skipped_after_error')

    def test_streaming_without_finish_is_not_accepted(self):
        opener = Opener(lambda request: SSEResponse([{'candidates': [{'content': {'parts': [{'text': 'parcial'}]}}]}]))
        case = {**self.cases[0], 'gemini_streaming': True, 'gemini_minimal': True}
        row = v.call('gemini', case, self.keys['gemini'], tuple(self.keys.values()), self.schema, opener=opener)
        self.assertEqual(row['status'], 'error')
        self.assertIn('sin finishReason', row['error']['message'])

    def test_streaming_preserves_partial_usage_on_internal_error_and_checks_next_variant(self):
        def fail_minimal(request):
            if 'generationConfig' in json.loads(request.data):
                return stream_success(request)
            return SSEResponse([
                {'usageMetadata': {'promptTokenCount': 13, 'thoughtsTokenCount': 109, 'totalTokenCount': 122}},
                {'error': {'code': 500, 'message': 'Internal error encountered.'}},
            ])
        opener = Opener(fail_minimal)
        state = self.run_quiet(self.args(gemini_streaming=True), opener)
        self.assertEqual(len(opener.requests), 2)
        first = state['attempts'][0]
        self.assertEqual(first['status'], 'error')
        self.assertEqual(first['service_error_code'], 500)
        self.assertEqual(first['tokens']['input'], 13)
        self.assertEqual(first['tokens']['thinking'], 109)
        self.assertEqual(first['tokens']['total'], 122)
        self.assertEqual(state['attempts'][1]['status'], 'received')

    def test_high_only_diagnostic_does_not_repeat_minimal_variant(self):
        opener = Opener(stream_success)
        state = self.run_quiet(self.args(gemini_stream_high_only=True), opener)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(state['maximum_requests'], 1)
        self.assertEqual(state['attempts'][0]['case_id'], 'saludo_stream_high')
        self.assertEqual(json.loads(opener.requests[0].data)['generationConfig']['thinkingConfig']['thinkingLevel'], 'HIGH')


if __name__ == '__main__':
    unittest.main()
