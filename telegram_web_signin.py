"""通过官方 Telegram Web 的扫码登录会话执行机器人签到。"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

from telegram_common import BOT_ID, BOT_USERNAME, COMMAND, TelegramCheckinError, classify_reply


ORIGIN = 'https://web.telegram.org'
WEB_URL = f'{ORIGIN}/k/'
BOT_URL = f'{WEB_URL}#@{BOT_USERNAME}'
EDITOR = f'.chat.active .input-message-input[contenteditable="true"][data-peer-id="{BOT_ID}"]'
BUBBLES = f'.chat.active .bubble[data-mid][data-peer-id="{BOT_ID}"]'
AUTH_ENTRY = re.compile(
    r'^(?:account1|number_of_accounts|k_build|dc|dc[1-5]_(?:auth_key|server_salt)'
    r'|auth_key_fingerprint|user_auth)$'
)


def load_state(value):
    try:
        state = json.loads(value)
    except (ValueError, TypeError) as error:
        raise TelegramCheckinError('Telegram Web 会话不是有效的 JSON') from error
    if not isinstance(state, dict):
        raise TelegramCheckinError('Telegram Web 会话格式错误')
    origins = state.get('origins')
    if not isinstance(origins, list) or len(origins) != 1 or not isinstance(origins[0], dict):
        raise TelegramCheckinError('Telegram Web 会话缺少唯一的官方站点存储')
    origin = origins[0]
    if origin.get('origin') != ORIGIN:
        raise TelegramCheckinError('Telegram Web 会话来源不是官方域名')
    entries = origin.get('localStorage')
    if not isinstance(entries, list) or not all(
        isinstance(entry, dict) and isinstance(entry.get('name'), str)
        and isinstance(entry.get('value'), str) for entry in entries
    ):
        raise TelegramCheckinError('Telegram Web 本地存储格式错误')
    try:
        values = {entry['name']: entry['value'] for entry in entries}
        account = json.loads(values['account1'])
        if not isinstance(account, dict) or not account.get('userId'):
            raise ValueError('missing authorization')
        if not any(account.get(f'dc{number}_auth_key') for number in range(1, 6)):
            raise ValueError('missing authorization key')
    except (ValueError, TypeError, KeyError) as error:
        raise TelegramCheckinError('Telegram Web 会话尚未登录，请重新扫码') from error
    # 仅导入认证所需的官方站点存储，不导入其他站点 Cookie 或 IndexedDB 聊天缓存。
    entries = [entry for entry in entries if AUTH_ENTRY.fullmatch(entry['name'])]
    return {'cookies': [], 'origins': [{'origin': ORIGIN, 'localStorage': entries}]}


def read_bubbles(page):
    return page.locator(BUBBLES).evaluate_all('''elements => elements.map(element => ({
        id: Number(element.dataset.mid),
        peer: element.dataset.peerId,
        outgoing: element.classList.contains('is-out'),
        incoming: element.classList.contains('is-in'),
        replyTo: element.dataset.replyToMid ? Number(element.dataset.replyToMid) : null,
        text: element.querySelector('.message')?.innerText || element.innerText || ''
    }))''')


def fresh_reply(bubbles, outgoing_id):
    for bubble in sorted(bubbles, key=lambda entry: entry['id']):
        if (bubble['peer'] != BOT_ID or not bubble['incoming'] or bubble['outgoing']
                or bubble['id'] <= outgoing_id or bubble['replyTo'] not in (None, outgoing_id)):
            continue
        result = classify_reply(bubble['text'])
        if result:
            return result
    return None


def checkin_page(page, timeout=45):
    page.goto(BOT_URL, wait_until='domcontentloaded', timeout=60000)
    editor = page.locator(EDITOR)
    editor.wait_for(state='visible', timeout=60000)
    page.locator(BUBBLES).first.wait_for(state='attached', timeout=30000)
    baseline = max((bubble['id'] for bubble in read_bubbles(page)), default=0)
    if baseline <= 0:
        raise TelegramCheckinError('未能读取机器人聊天记录，无法判断本次签到回复')
    if editor.inner_text().strip():
        raise TelegramCheckinError('机器人对话中有未发送的草稿，请清空后重试')
    editor.fill(COMMAND)
    editor.press('Enter')

    deadline = time.monotonic() + timeout
    outgoing_id = None
    while time.monotonic() < deadline:
        bubbles = read_bubbles(page)
        if outgoing_id is None:
            sent = [bubble['id'] for bubble in bubbles if bubble['peer'] == BOT_ID
                    and bubble['outgoing'] and bubble['id'] > baseline
                    and bubble['text'].strip().startswith(COMMAND)]
            if sent:
                outgoing_id = min(sent)
        if outgoing_id is not None:
            result = fresh_reply(bubbles, outgoing_id)
            if result:
                return result
        page.wait_for_timeout(500)
    if outgoing_id is None:
        raise TelegramCheckinError('未确认签到命令发送成功，任务不会自动重复发送')
    raise TelegramCheckinError('等待本次签到的机器人回复超时，未确认成功')


def run(state, channel=None, proxy=None):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        options = {'headless': True}
        if channel:
            options['channel'] = channel
        if proxy:
            options['proxy'] = {'server': proxy}
        browser = playwright.chromium.launch(**options)
        try:
            context = browser.new_context(storage_state=state, viewport={'width': 1280, 'height': 800})
            return checkin_page(context.new_page())
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-file', type=Path, help='本机临时会话文件')
    parser.add_argument('--channel', choices=('chrome', 'msedge'))
    parser.add_argument('--proxy', default=os.environ.get('TELEGRAM_WEB_PROXY'))
    args = parser.parse_args()
    try:
        value = (args.session_file.read_text(encoding='utf-8-sig') if args.session_file
                 else os.environ.get('TELEGRAM_WEB_SESSION'))
        result = run(load_state(value), channel=args.channel, proxy=args.proxy)
        print(f'Telegram Web 签到结果：{result}')
        return 0
    except TelegramCheckinError as error:
        print(f'Telegram Web 签到失败：{error}', file=sys.stderr)
    except Exception as error:
        # 不将网页、输入值或完整浏览器异常写入公开的 Actions 日志。
        print(f'Telegram Web 签到失败：{type(error).__name__}，未确认成功。', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
