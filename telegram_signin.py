"""使用已登录的 Telegram 用户会话向官方机器人签到。"""

import asyncio
import os
import re
import sys
from urllib.parse import unquote, urlparse

from telethon import TelegramClient
from telethon.errors import AuthKeyError, FloodWaitError, UnauthorizedError
from telethon.sessions import StringSession

from telegram_common import BOT_USERNAME, COMMAND, TelegramCheckinError, classify_reply


def validate_credentials(api_id, api_hash):
    try:
        number = int(api_id)
    except (TypeError, ValueError) as error:
        raise TelegramCheckinError('TELEGRAM_API_ID 必须是正整数') from error
    if number <= 0:
        raise TelegramCheckinError('TELEGRAM_API_ID 必须是正整数')
    if not isinstance(api_hash, str) or not re.fullmatch(r'[0-9a-fA-F]{32}', api_hash):
        raise TelegramCheckinError('TELEGRAM_API_HASH 应为 32 位十六进制字符串')
    return number, api_hash


def parse_proxy(value):
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'socks5') or not parsed.hostname or not parsed.port:
        raise TelegramCheckinError('代理地址需要使用 http:// 或 socks5://，并包含端口')
    return (
        parsed.scheme, parsed.hostname, parsed.port, True,
        unquote(parsed.username) if parsed.username else None,
        unquote(parsed.password) if parsed.password else None,
    )


def create_client(api_id, api_hash, session='', proxy=None):
    api_id, api_hash = validate_credentials(api_id, api_hash)
    try:
        stored_session = StringSession(session)
    except (ValueError, TypeError) as error:
        raise TelegramCheckinError('TELEGRAM_SESSION 格式错误，请重新运行登录助手') from error
    return TelegramClient(
        stored_session, api_id, api_hash,
        proxy=parse_proxy(proxy),
        device_model='ikuuu-checkin',
        app_version='1.0',
        connection_retries=2,
        request_retries=2,
        flood_sleep_threshold=0,
        retry_delay=1,
        timeout=10,
    )


async def checkin(client, timeout=45):
    if not await client.is_user_authorized():
        raise TelegramCheckinError('Telegram 登录会话已失效，请重新运行 login_telegram.py')
    bot = await client.get_entity(BOT_USERNAME)
    if not getattr(bot, 'bot', False):
        raise TelegramCheckinError('目标账号不是 Telegram 机器人，已停止发送')
    deadline = asyncio.get_running_loop().time() + timeout
    async with client.conversation(bot, timeout=timeout, total_timeout=timeout) as conversation:
        sent = await conversation.send_message(COMMAND)
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TelegramCheckinError('等待机器人签到结果超时，未确认成功')
            try:
                reply = await conversation.get_response(sent.id, timeout=remaining)
            except asyncio.TimeoutError as error:
                raise TelegramCheckinError('等待机器人签到结果超时，未确认成功') from error
            if reply.id <= sent.id or reply.reply_to_msg_id not in (None, sent.id):
                continue
            result = classify_reply(reply.raw_text)
            if result:
                return result


async def run():
    session = os.environ.get('TELEGRAM_SESSION', '').strip()
    if not session:
        raise TelegramCheckinError('未配置 TELEGRAM_SESSION，请先运行 login_telegram.py')
    client = create_client(
        os.environ.get('TELEGRAM_API_ID'),
        os.environ.get('TELEGRAM_API_HASH', '').strip(),
        session,
        os.environ.get('TELEGRAM_PROXY'),
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=30)
        return await checkin(client)
    finally:
        await client.disconnect()


def main():
    try:
        result = asyncio.run(asyncio.wait_for(run(), timeout=100))
        print(f'Telegram 签到结果：{result}')
        return 0
    except TelegramCheckinError as error:
        print(f'Telegram 签到失败：{error}', file=sys.stderr)
    except FloodWaitError as error:
        print(f'Telegram 要求等待 {error.seconds} 秒，任务已停止。', file=sys.stderr)
    except (AuthKeyError, UnauthorizedError):
        print('Telegram 登录会话不可用，请重新运行 login_telegram.py。', file=sys.stderr)
    except (asyncio.TimeoutError, ConnectionError, OSError):
        print('Telegram 连接或等待响应超时，未确认签到成功。', file=sys.stderr)
    except Exception as error:
        print(f'Telegram 签到失败：{type(error).__name__}，未确认成功。', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
