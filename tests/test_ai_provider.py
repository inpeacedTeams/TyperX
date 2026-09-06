import io
import json
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from typerx.ai import AIError
from typerx.llm_provider import ProviderClient, ProviderRuntime, explain_http_error


def failure(status=403, body=b'{}', content_type='application/json'):
    return urllib.error.HTTPError('https://example.com/v1/chat/completions', status, 'Denied',
                                  {'Content-Type': content_type}, io.BytesIO(body))


class ProviderTests(unittest.TestCase):
    def test_permission_denied_is_not_reported_as_bad_key(self):
        error = failure(body=json.dumps({'error': {'code': 'permission_denied',
                                                   'message': 'SECRET private history'}}).encode())
        result = explain_http_error(error)
        self.assertIn('доступ к выбранной модели', result)
        self.assertNotIn('SECRET', result)
        self.assertNotIn('private history', result)
        self.assertTrue(error.fp.closed)

    def test_html_block_is_distinct(self):
        result = explain_http_error(failure(body=b'<html>secret</html>', content_type='text/html'))
        self.assertIn('HTML', result)
        self.assertNotIn('secret', result)

    def test_unknown_403_does_not_invent_cause(self):
        for body in [b'{}', b'null', b'[]', b'broken', b'x' * 20000]:
            self.assertIn('точную причину определить нельзя', explain_http_error(failure(body=body)))

    def test_statuses_are_distinguished(self):
        for status, expected in [(401, 'Ключ не принят'), (402, 'баланса'),
                                 (404, 'не найдены'), (429, 'лимит')]:
            self.assertIn(expected, explain_http_error(failure(status)))

    def test_actual_client_uses_json_headers_and_surfaces_safe_error(self):
        opener = MagicMock()
        opener.open.side_effect = failure(body=b'{"error":{"type":"permission_error"}}')
        with patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaisesRegex(AIError, 'доступ к выбранной модели'):
                ProviderClient._request('https://example.com/v1/chat/completions', 'private-key', b'{}')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer private-key')
        self.assertEqual(request.get_header('Accept'), 'application/json')
        self.assertTrue(request.get_header('User-agent').startswith('TyperX/'))
        self.assertEqual(opener.open.call_count, 1)

    def test_runtime_uses_provider_client(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = ProviderRuntime(root, lambda *_: None)
            try:
                self.assertIsInstance(runtime.llm, ProviderClient)
            finally:
                runtime.close()


if __name__ == '__main__':
    unittest.main()
