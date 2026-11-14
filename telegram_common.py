"""Telegram 签到的固定目标和结果判定。"""

import re


BOT_USERNAME = 'iKuuuu_VPN_bot'
BOT_ID = '745814644'
COMMAND = '/checkin'


class TelegramCheckinError(Exception):
    pass


def classify_reply(text):
    if not isinstance(text, str) or not text.strip():
        return None
    if any(word in text for word in ('未绑定', '没有绑定', '尚未绑定')):
        raise TelegramCheckinError('当前 Telegram 账号尚未绑定网站账号')
    if any(word in text for word in ('签到失败', '签到出错', '用户不存在', '账号被封', '账户被封')):
        raise TelegramCheckinError('机器人明确返回签到失败，请查看官方机器人对话')
    if any(word in text for word in ('已经签到', '已经签过', '已签到', '已签过')):
        return '今天已签到'
    if '签到成功' in text:
        traffic = re.search(r'(\d+(?:\.\d+)?)\s*(GB|MB|KB)', text, re.IGNORECASE)
        return f'签到成功，获得 {traffic.group(1)} {traffic.group(2).upper()}' if traffic else '签到成功'
    return None
