"""扫码登录 Telegram，并将应用凭据和登录会话直接保存到 GitHub Secrets。"""

import argparse
import asyncio
import getpass
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from telethon.errors import SessionPasswordNeededError

from telegram_signin import create_client, validate_credentials


def read_value(path, environment, prompt, hidden=False):
    if path:
        return path.read_text(encoding='utf-8-sig').strip()
    value = os.environ.get(environment)
    if value:
        return value.strip()
    return getpass.getpass(prompt) if hidden else input(prompt).strip()


def render_qr(url, path):
    import qrcode
    image = qrcode.make(url, box_size=10, border=4)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


async def authorize(client, qr_image, agent):
    await asyncio.wait_for(client.connect(), timeout=30)
    try:
        for attempt in range(1, 11):
            qr = await client.qr_login()
            waiting = asyncio.create_task(qr.wait())
            await asyncio.sleep(0)
            render_qr(qr.url, qr_image)
            print(f'QR_READY {attempt} {qr_image}', flush=True)
            try:
                await waiting
                break
            except asyncio.TimeoutError:
                print('二维码已过期，正在刷新。', flush=True)
            except SessionPasswordNeededError:
                if agent:
                    print('TWO_FACTOR_PASSWORD_FILE_REQUIRED', flush=True)
                    password_path = await asyncio.to_thread(input)
                    password = Path(password_path.strip()).read_text(encoding='utf-8-sig').rstrip('\r\n')
                else:
                    password = await asyncio.to_thread(getpass.getpass, 'Telegram 两步验证密码：')
                await client.sign_in(password=password)
                password = None
                break
            finally:
                if not waiting.done():
                    waiting.cancel()
                    await asyncio.gather(waiting, return_exceptions=True)
        else:
            raise RuntimeError('等待扫码登录超时，请重新运行助手')
        if not await client.is_user_authorized():
            raise RuntimeError('未确认 Telegram 登录成功')
        return client.session.save()
    finally:
        await client.disconnect()
        qr_image.unlink(missing_ok=True)


def save_secret(repo, name, value):
    subprocess.run(
        ['gh', 'secret', 'set', name, '--repo', repo],
        input=str(value).encode('utf-8'), check=True, timeout=60,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--api-id-file', type=Path)
    parser.add_argument('--api-hash-file', type=Path)
    parser.add_argument('--proxy', default=os.environ.get('TELEGRAM_PROXY'))
    parser.add_argument('--qr-image', type=Path,
                        default=Path(tempfile.gettempdir()) / 'ikuuu-telegram-login.png')
    parser.add_argument('--agent', action='store_true', help='两步验证密码通过临时文件输入')
    args = parser.parse_args()
    subprocess.run(['gh', 'repo', 'view', args.repo, '--json', 'nameWithOwner'],
                   check=True, stdout=subprocess.DEVNULL, timeout=30)
    api_id, api_hash = validate_credentials(
        read_value(args.api_id_file, 'TELEGRAM_API_ID', 'App api_id：'),
        read_value(args.api_hash_file, 'TELEGRAM_API_HASH', 'App api_hash：', hidden=True),
    )
    client = create_client(api_id, api_hash, proxy=args.proxy)
    print('请打开手机 Telegram：设置 → 设备 → 关联桌面设备，扫描即将显示的二维码。', flush=True)
    session = asyncio.run(authorize(client, args.qr_image, args.agent))
    # 最后写入 SESSION，避免定时任务在应用凭据尚未写完时切换到 Telegram。
    save_secret(args.repo, 'TELEGRAM_API_ID', api_id)
    save_secret(args.repo, 'TELEGRAM_API_HASH', api_hash)
    save_secret(args.repo, 'TELEGRAM_SESSION', session)
    print('Telegram 登录会话已保存至 GitHub Secrets，未创建本机 session 文件。')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'Telegram 登录未完成：{type(error).__name__}', file=sys.stderr)
        sys.exit(1)
