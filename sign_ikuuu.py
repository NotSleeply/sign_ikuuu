import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import requests


BASE_URL = 'https://ikuuu.top'
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/157.0.0.0 Safari/537.36'
)
LOGIN_HELP = '请运行 python login_ikuuu.py --repo 仓库所有者/仓库名，完成验证码并更新登录会话'


class CheckinError(Exception):
    pass


def mask_email(email):
    if '@' not in email:
        return '***'
    name, domain = email.split('@', 1)
    if len(name) <= 1:
        name = '*'
    elif len(name) == 2:
        name = name[0] + '*'
    else:
        name = name[0] + '*' * (len(name) - 2) + name[-1]
    return f'{name}@{domain}'


def load_accounts(value):
    if not value or not value.strip():
        raise CheckinError('未配置 ACCOUNTS 环境变量')
    accounts = []
    for number, line in enumerate(value.lstrip('\ufeff').splitlines(), 1):
        if not line.strip():
            continue
        email, separator, password = line.strip().partition(':')
        if not separator or not email.strip() or not password.strip():
            raise CheckinError(f'ACCOUNTS 第 {number} 行格式错误，应为邮箱:密码')
        accounts.append((email.strip(), password.strip()))
    if not accounts:
        raise CheckinError('未读取到账号')
    return accounts


def load_saved_cookies(value):
    if not value or not value.strip():
        return {}
    try:
        saved = json.loads(value.lstrip('\ufeff'))
    except (ValueError, TypeError) as error:
        raise CheckinError('IKUUU_COOKIES 不是有效的 JSON，请重新运行登录助手') from error
    if not isinstance(saved, dict):
        raise CheckinError('IKUUU_COOKIES 应为邮箱到 Cookie 列表的映射')
    return saved


def playwright_login(email, password):
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale='zh-CN')
            page = context.new_page()
            page.goto(f'{BASE_URL}/auth/login', wait_until='domcontentloaded')
            page.fill('#email', email)
            page.fill('#password', password)

            if page.locator('.embed-captcha').count():
                try:
                    page.wait_for_function(
                        'window.Captcha && window.Captcha.isLoaded()', timeout=15000
                    )
                    page.locator('.geetest_btn_click').first.click(timeout=5000)
                    page.wait_for_function(
                        'window.Captcha && window.Captcha.isReady()', timeout=12000
                    )
                except PlaywrightTimeout as error:
                    raise CheckinError(f'登录需要人工完成极验验证码。{LOGIN_HELP}') from error

            page.locator('button[type="submit"]').click(timeout=10000)
            try:
                page.wait_for_url(
                    re.compile(r'https://ikuuu\.top/user(?:[/?#]|$)'),
                    wait_until='domcontentloaded',
                    timeout=20000,
                )
            except PlaywrightTimeout as error:
                raise CheckinError(f'登录未成功，未获取到有效会话。{LOGIN_HELP}') from error
            return context.cookies(BASE_URL)
        finally:
            browser.close()


def session_from_cookies(cookies):
    if not isinstance(cookies, list) or not cookies:
        raise CheckinError('登录 Cookie 为空或格式错误，请重新运行登录助手')
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT, 'Origin': BASE_URL})
    host = urlparse(BASE_URL).hostname
    try:
        for cookie in cookies:
            if not isinstance(cookie, dict):
                raise CheckinError('登录 Cookie 格式错误，请重新运行登录助手')
            name, value = cookie.get('name'), cookie.get('value')
            domain = cookie.get('domain', host)
            if not isinstance(domain, str) or domain.lstrip('.') != host:
                raise CheckinError('登录 Cookie 的域名与 ikuuu.top 不匹配')
            if not isinstance(name, str) or not name or not isinstance(value, str):
                raise CheckinError('登录 Cookie 缺少名称或值')
            expires = cookie.get('expires', -1)
            if not isinstance(expires, (int, float)):
                raise CheckinError('登录 Cookie 的过期时间格式错误')
            if expires > 0 and expires <= time.time():
                continue
            session.cookies.set(
                name,
                value,
                domain=domain,
                path=cookie.get('path', '/'),
                secure=cookie.get('secure', True),
                expires=int(expires) if expires > 0 else None,
            )
        return session
    except Exception:
        session.close()
        raise


def verify_session(session):
    response = session.get(f'{BASE_URL}/user', timeout=20)
    response.raise_for_status()
    destination = urlparse(response.url)
    if destination.hostname != urlparse(BASE_URL).hostname or not (
        destination.path == '/user' or destination.path.startswith('/user/')
    ):
        raise CheckinError(f'登录会话已失效。{LOGIN_HELP}')


def submit_checkin(session):
    response = session.post(f'{BASE_URL}/user/checkin', timeout=20, allow_redirects=False)
    if response.is_redirect:
        raise CheckinError(f'签到被重定向，登录会话可能已失效。{LOGIN_HELP}')
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError as error:
        raise CheckinError('签到接口未返回 JSON，无法确认签到成功') from error
    if not isinstance(result, dict):
        raise CheckinError('签到接口返回格式错误')
    message = result.get('msg')
    if not isinstance(message, str) or not message.strip():
        raise CheckinError('签到接口没有返回结果说明')
    already_checked_in = any(
        text in message for text in ('已经签到', '已经签过', '今日已签到', '今天已签到')
    )
    if result.get('ret') not in (1, '1') and not (
        result.get('ret') in (0, '0') and already_checked_in
    ):
        raise CheckinError(message)
    return message


def checkin_one_account(email, password, saved_cookies=None):
    safe_email = mask_email(email)
    try:
        if saved_cookies is not None:
            print(f'使用保存的登录会话：{safe_email}')
            cookies = saved_cookies
        else:
            print(f'尝试账号登录：{safe_email}')
            cookies = playwright_login(email, password)
        with session_from_cookies(cookies) as session:
            verify_session(session)
            message = submit_checkin(session)
        return True, f'✅ {safe_email} -> {message}'
    except Exception as error:
        detail = str(error).replace(email, safe_email)
        if password:
            detail = detail.replace(password, '***')
        return False, f'❌ {safe_email} -> {detail}'


def notify(message):
    config = [os.environ.get(name, '') for name in ('WX_CORPID', 'WX_CORPSECRET', 'WX_AGENTID')]
    if not all(config):
        return
    try:
        from wxmsg import send_wx
        send_wx(f'[ikuuu] 签到结果：\n{message}', *config)
    except Exception as error:
        print(f'企业微信通知失败：{error}')


def handler(event=None, context=None):
    try:
        accounts = load_accounts(os.environ.get('ACCOUNTS'))
        saved = load_saved_cookies(os.environ.get('IKUUU_COOKIES'))
    except CheckinError as error:
        print(f'签到配置错误：{error}')
        notify(str(error))
        return False

    print(f'共发现 {len(accounts)} 个账号')
    all_success = True
    messages = []
    for email, password in accounts:
        success, message = checkin_one_account(email, password, saved.get(email))
        print(message)
        messages.append(message)
        all_success = all_success and success
    notify('\n'.join(messages))
    return all_success


if __name__ == '__main__':
    sys.exit(0 if handler() else 1)
