import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import telegram_signin as sign


def message(identifier, text, reply_to=100):
    return SimpleNamespace(id=identifier, raw_text=text, reply_to_msg_id=reply_to)


def conversation_client(replies):
    conversation = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(id=100)),
        get_response=AsyncMock(side_effect=replies),
    )
    context = Mock()
    context.__aenter__ = AsyncMock(return_value=conversation)
    context.__aexit__ = AsyncMock(return_value=False)
    client = SimpleNamespace(
        is_user_authorized=AsyncMock(return_value=True),
        get_entity=AsyncMock(return_value=SimpleNamespace(bot=True)),
        conversation=Mock(return_value=context),
    )
    return client, conversation


class ReplyTests(unittest.TestCase):
    def test_success_and_already_checked_in(self):
        for text in ('今天已签到', '您今天已经签到过了', '签到成功，获得 1234 MB 流量'):
            with self.subTest(text=text):
                self.assertIsNotNone(sign.classify_reply(text))

    def test_failure_is_not_misreported_as_success(self):
        for text in ('您未绑定本站账号', '签到失败，请确认是否已经签到'):
            with self.subTest(text=text), self.assertRaises(sign.TelegramCheckinError):
                sign.classify_reply(text)

    def test_unrecognized_and_pending_replies_are_not_success(self):
        for text in (None, '', '正在处理', '欢迎使用机器人', '使用 /checkin 进行签到'):
            with self.subTest(text=text):
                self.assertIsNone(sign.classify_reply(text))

    def test_result_does_not_echo_private_bot_content(self):
        text = '签到成功\n账号：private@example.test\n订阅：https://example.test/private-token'
        self.assertEqual(sign.classify_reply(text), '签到成功')

    def test_credentials_validation(self):
        self.assertEqual(sign.validate_credentials('1234', 'a' * 32), (1234, 'a' * 32))
        for api_id, api_hash in ((None, 'a' * 32), ('bad', 'a' * 32), ('0', 'a' * 32), ('1', 'bad')):
            with self.subTest(api_id=api_id), self.assertRaises(sign.TelegramCheckinError):
                sign.validate_credentials(api_id, api_hash)

    def test_proxy(self):
        self.assertIsNone(sign.parse_proxy(None))
        self.assertEqual(sign.parse_proxy('http://127.0.0.1:7890'),
                         ('http', '127.0.0.1', 7890, True, None, None))
        with self.assertRaises(sign.TelegramCheckinError):
            sign.parse_proxy('https://example.test:443')

    def test_invalid_session_fails_before_connecting(self):
        with self.assertRaises(sign.TelegramCheckinError):
            sign.create_client('1234', 'a' * 32, 'not-a-valid-session')

    def test_missing_session_returns_failure(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(sign.main(), 1)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_fresh_replies_for_current_command_count(self):
        client, conversation = conversation_client([
            message(99, '签到成功'),
            message(101, '签到成功', reply_to=50),
            message(102, '正在处理'),
            message(103, '今天已签到'),
        ])
        self.assertEqual(await sign.checkin(client), '今天已签到')
        client.get_entity.assert_awaited_once_with(sign.BOT_USERNAME)
        conversation.send_message.assert_awaited_once_with('/checkin')
        self.assertEqual(conversation.get_response.await_count, 4)

    async def test_unbound_account_fails(self):
        client, conversation = conversation_client([message(101, '您未绑定本站账号')])
        with self.assertRaisesRegex(sign.TelegramCheckinError, '未绑定'):
            await sign.checkin(client)
        conversation.send_message.assert_awaited_once()

    async def test_timeout_does_not_repeat_command(self):
        client, conversation = conversation_client([asyncio.TimeoutError()])
        with self.assertRaisesRegex(sign.TelegramCheckinError, '超时'):
            await sign.checkin(client)
        conversation.send_message.assert_awaited_once()

    async def test_unauthorized_session_does_not_send(self):
        client, _ = conversation_client([])
        client.is_user_authorized.return_value = False
        with self.assertRaisesRegex(sign.TelegramCheckinError, '失效'):
            await sign.checkin(client)
        client.get_entity.assert_not_awaited()
        client.conversation.assert_not_called()

    async def test_non_bot_target_does_not_receive_command(self):
        client, _ = conversation_client([])
        client.get_entity.return_value = SimpleNamespace(bot=False)
        with self.assertRaisesRegex(sign.TelegramCheckinError, '不是'):
            await sign.checkin(client)
        client.conversation.assert_not_called()


if __name__ == '__main__':
    unittest.main()
