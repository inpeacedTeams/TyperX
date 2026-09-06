import io
import json
import unittest
from unittest.mock import MagicMock, patch

from typerx.ai import AIError, defaults
from typerx.llm_stream import StreamClient, completion_url, read_answer
from typerx.studio_hotkeys import GlobalHotkeys, KeyEdges


class Response(io.BytesIO):
    def __init__(self, body, kind='text/event-stream'):
        super().__init__(body)
        self.headers = {'Content-Type': kind}


def event(content='', reason=None):
    return ('data: ' + json.dumps({'choices': [{'delta': {'content': content}, 'finish_reason': reason}]}) + '\n\n').encode()


class StreamTests(unittest.TestCase):
    def test_stream_is_assembled_before_output(self):
        result = read_answer(Response(event('При') + event('вет') + b'data: [DONE]\n\n'))
        self.assertEqual(result, 'Привет')

    def test_normal_json_is_also_supported(self):
        body = json.dumps({'choices': [{'message': {'content': 'OK'}, 'finish_reason': 'stop'}]}).encode()
        self.assertEqual(read_answer(Response(body, 'application/json')), 'OK')

    def test_interrupted_stream_is_not_used(self):
        with self.assertRaisesRegex(AIError, 'оборвался'):
            read_answer(Response(event('partial')))

    def test_truncated_answer_is_not_used(self):
        with self.assertRaisesRegex(AIError, 'не завершила'):
            read_answer(Response(event('partial', 'length')))

    def test_finish_reason_without_done_is_accepted(self):
        self.assertEqual(read_answer(Response(event('OK', 'stop'))), 'OK')

    def test_in_stream_error_does_not_leak_remote_text(self):
        with self.assertRaises(AIError) as caught:
            read_answer(Response(b'data: {"error":{"message":"SECRET"}}\n\n'))
        self.assertNotIn('SECRET', str(caught.exception))

    def test_response_length_is_bounded(self):
        with self.assertRaises(AIError):
            read_answer(Response(event('a' * 8001) + b'data: [DONE]\n\n'))

    def test_heartbeat_and_usage_are_ignored(self):
        body = b': heartbeat\n\ndata: {"choices":[]}\n\n' + event('OK') + b'data: [DONE]\n\n'
        self.assertEqual(read_answer(Response(body)), 'OK')

    def test_normalizes_full_endpoint_base_and_host(self):
        expected = 'https://example.com/v1/chat/completions'
        for base in ['https://example.com', 'https://example.com/v1/', expected]:
            self.assertEqual(completion_url(base), expected)
        with self.assertRaises(AIError):
            completion_url('http://example.com/v1')
        with self.assertRaises(AIError):
            completion_url('https://user:secret@example.com/v1')

    def test_each_generation_has_a_fresh_anonymous_session(self):
        opener = MagicMock()
        opener.open.side_effect = [Response(event('OK', 'stop')), Response(event('OK', 'stop'))]
        with patch('urllib.request.build_opener', return_value=opener):
            for _ in range(2):
                self.assertEqual(StreamClient._request('https://example.com/v1/chat/completions', 'key', b'{}'), 'OK')
        headers = [call.args[0].get_header('X-agent-session') for call in opener.open.call_args_list]
        self.assertNotEqual(*headers)
        self.assertTrue(all(value.startswith('typerx-') for value in headers))


class PayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_test_request_never_contains_history(self):
        client = StreamClient()
        with patch.object(client, '_request', return_value='OK') as request:
            await client.complete(defaults(), '', [{'role': 'user', 'content': 'PRIVATE'}], check=True)
        payload = json.loads(request.call_args.args[-1])
        self.assertNotIn('PRIVATE', str(payload))
        self.assertTrue(payload['stream'])
        self.assertEqual(payload['max_tokens'], 600)

    async def test_all_selected_personas_and_only_supplied_history(self):
        config = defaults()
        config['presets'][0]['prompts'] = ['first persona', 'second persona']
        with patch.object(StreamClient, '_request', return_value='OK') as request:
            await StreamClient().complete(config, '', [{'role': 'user', 'content': 'TARGET'}])
        payload = json.loads(request.call_args.args[-1])
        self.assertEqual([m['content'] for m in payload['messages'][:2]], ['first persona', 'second persona'])
        self.assertEqual(payload['messages'][-1]['content'], 'TARGET')


class HotkeyTests(unittest.TestCase):
    def test_hold_does_not_repeat(self):
        keys = KeyEdges()
        self.assertEqual(keys.update(True, False), 'start')
        self.assertIsNone(keys.update(True, False))
        keys.update(False, False)
        self.assertEqual(keys.update(True, False), 'start')

    def test_f9_wins_and_held_f9_blocks_start(self):
        keys = KeyEdges()
        self.assertEqual(keys.update(True, True), 'stop')
        keys.update(False, True)
        self.assertIsNone(keys.update(True, True))

    def test_initially_held_key_does_not_start(self):
        self.assertIsNone(KeyEdges(True, False).update(True, False))

    def test_polling_routes_callbacks_without_qt_or_registration(self):
        start, stop = MagicMock(), MagicMock()
        hotkeys = GlobalHotkeys(start, stop)
        hotkeys._key = MagicMock(side_effect=[0, 0, 0x8000, 0, 0x8000, 0, 0, 0x8000, 0x8000])
        hotkeys._closed = MagicMock()
        hotkeys._closed.wait.side_effect = [False, False, False, False, True]
        hotkeys._run()
        start.assert_called_once()
        stop.assert_called_once()

    def test_polling_failure_stops_and_reports(self):
        start, stop, error = MagicMock(), MagicMock(), MagicMock()
        hotkeys = GlobalHotkeys(start, stop, error)
        hotkeys._key = MagicMock(side_effect=OSError())
        hotkeys._run()
        stop.assert_called_once()
        error.assert_called_once()
        start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
