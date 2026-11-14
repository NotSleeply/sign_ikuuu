"""在本机完成验证码，将登录 Cookie 直接保存到 GitHub Actions Secret。"""

import argparse
import getpass
import json
from pathlib import Path
import subprocess
import sys

from sign_ikuuu import BASE_URL, USER_AGENT, mask_email, session_from_cookies, verify_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='GitHub 仓库，格式为所有者/仓库名')
    parser.add_argument('--email', action='append', help='登录邮箱，多账号可重复传入')
    parser.add_argument('--password-file', type=Path, help='单账号的临时密码文件，不会上传密码')
    parser.add_argument('--channel', choices=('chrome', 'msedge', 'chromium'), default='chromium')
    args = parser.parse_args()
    emails = args.email or [input('ikuuu 登录邮箱：').strip()]
    if not all(emails) or (args.password_file and len(emails) != 1):
        parser.error('邮箱不能为空，密码文件仅支持单账号登录')
    subprocess.run(['gh', 'repo', 'view', args.repo, '--json', 'nameWithOwner'],
                   check=True, stdout=subprocess.DEVNULL)

    from playwright.sync_api import sync_playwright

    saved = {}
    with sync_playwright() as playwright:
        launch = {'headless': False}
        if args.channel != 'chromium':
            launch['channel'] = args.channel
        browser = playwright.chromium.launch(**launch)
        try:
            for email in emails:
                password = (
                    args.password_file.read_text(encoding='utf-8-sig').rstrip('\r\n')
                    if args.password_file else getpass.getpass(f'{mask_email(email)} 的密码：')
                )
                context = browser.new_context(user_agent=USER_AGENT, locale='zh-CN')
                try:
                    page = context.new_page()
                    page.goto(f'{BASE_URL}/auth/login', wait_until='domcontentloaded')
                    page.fill('#email', email)
                    page.fill('#password', password)
                    password = None
                    print('请在浏览器中完成验证码并点击登录，等待时间为 5 分钟。', flush=True)
                    page.wait_for_url(f'{BASE_URL}/user**', wait_until='domcontentloaded', timeout=300000)
                    cookies = context.cookies(BASE_URL)
                    with session_from_cookies(cookies) as session:
                        verify_session(session)
                    saved[email] = cookies
                    print(f'已验证登录会话：{mask_email(email)}', flush=True)
                finally:
                    context.close()
        finally:
            browser.close()

    subprocess.run(
        ['gh', 'secret', 'set', 'IKUUU_COOKIES', '--repo', args.repo],
        input=json.dumps(saved, ensure_ascii=False).encode('utf-8'),
        check=True,
    )
    print('IKUUU_COOKIES 已保存至 GitHub，未在本机写入 Cookie 文件。')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'登录会话未保存：{error}', file=sys.stderr)
        sys.exit(1)
