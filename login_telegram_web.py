"""在官方 Telegram Web 扫码登录，直接将会话保存至 GitHub Secrets。"""

import argparse
import json
import os
import subprocess
import sys

from telegram_web_signin import BOT_URL, EDITOR, load_state


def authorize(channel=None, proxy=None):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        options = {'headless': False}
        if channel:
            options['channel'] = channel
        if proxy:
            options['proxy'] = {'server': proxy}
        browser = playwright.chromium.launch(**options)
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 800})
            page = context.new_page()
            page.goto(BOT_URL, wait_until='domcontentloaded', timeout=60000)
            print('请在浏览器中选择二维码登录，用手机 Telegram 的「设置 → 设备 → 关联桌面设备」扫码。',
                  flush=True)
            # 直接在官方页面输入两步验证密码，不通过终端收集密码或验证码。
            page.locator(EDITOR).wait_for(state='visible', timeout=300000)
            state = load_state(json.dumps(context.storage_state()))
        finally:
            # 上传前关闭本机页面，避免与云端同时使用同一会话。
            browser.close()
    return json.dumps(state, ensure_ascii=False, separators=(',', ':'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--channel', choices=('chrome', 'msedge'))
    parser.add_argument('--proxy', default=os.environ.get('TELEGRAM_WEB_PROXY'))
    args = parser.parse_args()
    subprocess.run(['gh', 'repo', 'view', args.repo, '--json', 'nameWithOwner'],
                   check=True, stdout=subprocess.DEVNULL, timeout=30)
    state = authorize(channel=args.channel, proxy=args.proxy)
    subprocess.run(['gh', 'secret', 'set', 'TELEGRAM_WEB_SESSION', '--repo', args.repo],
                   input=state.encode('utf-8'), check=True, timeout=60)
    print('Telegram Web 登录会话已保存至 GitHub Secrets。')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'Telegram Web 登录未完成：{type(error).__name__}', file=sys.stderr)
        sys.exit(1)
