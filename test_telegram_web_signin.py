import contextlib
import io
import json
import os
import unittest
from unittest.mock import Mock, patch

import telegram_web_signin as sign


def state_value(account=None, origin=sign.ORIGIN):
    if account is None:
        account = {'userId': 123, 'dc1_auth_key': 'test-key'}
    return json.dumps({'cookies': [], 'origins': [{
        'origin': origin,
        'localStorage': [{'name': 'account1', 'value': json.dumps(account)}],
    }]})


def bubble(identifier, text, *, outgoing=False, peer=sign.BOT_ID, reply_to=None):
    return {'id': identifier, 'text': text, 'peer': peer, 'outgoing': outgoing,
            'incoming': not outgoing, 'replyTo': reply_to}


def mock_page(draft=''):
    page = Mock()
    page.locator.return_value.inner_text.return_value = draft
    return page


class StateTests(unittest.TestCase):
    def test_valid_authorization_and_only_auth_storage(self):
        state = json.loads(state_value())
        state['cookies'] = [{'name': 'unrelated', 'value': 'private'}]
        state['origins'][0]['localStorage'].extend([
            {'name': 'dc1_server_salt', 'value': 'salt'},
            {'name': 'unrelated_chat_cache', 'value': 'private'},
        ])
        result = sign.load_state(json.dumps(state))
        self.assertEqual(result['cookies'], [])
        self.assertEqual([entry['name'] for entry in result['origins'][0]['localStorage']],
                         ['account1', 'dc1_server_salt'])

    def test_missing_or_invalid_state_fails(self):
        for value in (None, '', 'bad-json', 'null', '[]', '{}', '{"origins": [null]}'):
            with self.subTest(value=value), self.assertRaises(sign.TelegramCheckinError):
                sign.load_state(value)

    def test_foreign_origin_fails(self):
        with self.assertRaisesRegex(sign.TelegramCheckinError, '官方域名'):
            sign.load_state(state_value(origin='https://example.test'))

    def test_missing_authorization_fails(self):
        for account in ({}, {'userId': 123}, {'dc1_auth_key': 'test-key'}, []):
            with self.subTest(account=account), self.assertRaisesRegex(sign.TelegramCheckinError, '重新扫码'):
                sign.load_state(state_value(account=account))

    def test_malformed_storage_entry_fails(self):
        state = json.loads(state_value())
        state['origins'][0]['localStorage'].append({'name': 'bad', 'value': 123})
        with self.assertRaisesRegex(sign.TelegramCheckinError, '存储格式'):
            sign.load_state(json.dumps(state))


class ReplyTests(unittest.TestCase):
    def test_history_wrong_peer_wrong_reply_and_outgoing_do_not_count(self):
        bubbles = [
            bubble(99, '签到成功'),
            bubble(100, '签到成功'),
            bubble(101, '签到成功', peer='another-bot'),
            bubble(102, '签到成功', reply_to=50),
            bubble(103, '签到成功', outgoing=True),
            bubble(104, '正在处理'),
        ]
        self.assertIsNone(sign.fresh_reply(bubbles, 100))

    def test_current_reply_is_accepted(self):
        self.assertEqual(sign.fresh_reply([
            bubble(101, '您今天已经签过到了！', reply_to=100),
        ], 100), '今天已签到')
        self.assertEqual(sign.fresh_reply([
            bubble(101, '签到成功，获得 1234 MB 流量'),
        ], 100), '签到成功，获得 1234 MB')

    def test_unbound_and_explicit_failure_fail(self):
        for text in ('您未绑定本站账号', '签到失败，请确认是否已经签到'):
            with self.subTest(text=text), self.assertRaises(sign.TelegramCheckinError):
                sign.fresh_reply([bubble(101, text, reply_to=100)], 100)


class PageTests(unittest.TestCase):
    def test_sends_once_and_waits_for_current_reply(self):
        page = mock_page()
        history = [bubble(99, '/checkin', outgoing=True), bubble(100, '今天已签到', reply_to=99)]
        sent = history + [bubble(101, '/checkin', outgoing=True)]
        replied = sent + [bubble(102, '您今天已经签过到了！', reply_to=101)]
        with patch.object(sign, 'read_bubbles', side_effect=[history, sent, replied]):
            self.assertEqual(sign.checkin_page(page), '今天已签到')
        page.locator.return_value.fill.assert_called_once_with('/checkin')
        page.locator.return_value.press.assert_called_once_with('Enter')

    def test_existing_draft_is_preserved(self):
        page = mock_page(draft='unsent text')
        with patch.object(sign, 'read_bubbles', return_value=[bubble(100, 'old')]), \
                self.assertRaisesRegex(sign.TelegramCheckinError, '草稿'):
            sign.checkin_page(page)
        page.locator.return_value.fill.assert_not_called()
        page.locator.return_value.press.assert_not_called()

    def test_missing_history_does_not_send(self):
        page = mock_page()
        with patch.object(sign, 'read_bubbles', return_value=[]), \
                self.assertRaisesRegex(sign.TelegramCheckinError, '聊天记录'):
            sign.checkin_page(page)
        page.locator.return_value.press.assert_not_called()

    def test_old_success_cannot_mask_reply_timeout(self):
        page = mock_page()
        history = [bubble(100, '今天已签到')]
        sent = history + [bubble(101, '/checkin', outgoing=True)]
        with patch.object(sign, 'read_bubbles', side_effect=[history, sent]), \
                patch.object(sign.time, 'monotonic', side_effect=[0, 0, 46]), \
                self.assertRaisesRegex(sign.TelegramCheckinError, '回复超时'):
            sign.checkin_page(page)
        page.locator.return_value.press.assert_called_once()

    def test_unconfirmed_send_is_not_retried(self):
        page = mock_page()
        with patch.object(sign, 'read_bubbles', return_value=[bubble(100, '今天已签到')]), \
                patch.object(sign.time, 'monotonic', side_effect=[0, 0, 46]), \
                self.assertRaisesRegex(sign.TelegramCheckinError, '不会自动重复发送'):
            sign.checkin_page(page)
        page.locator.return_value.press.assert_called_once()

    def test_unexpected_errors_do_not_log_private_values(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, {'TELEGRAM_WEB_SESSION': state_value()}), \
                patch('sys.argv', ['telegram_web_signin.py']), \
                patch.object(sign, 'run', side_effect=RuntimeError('private-session-data')), \
                contextlib.redirect_stderr(stderr):
            self.assertEqual(sign.main(), 1)
        self.assertIn('RuntimeError', stderr.getvalue())
        self.assertNotIn('private-session-data', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
