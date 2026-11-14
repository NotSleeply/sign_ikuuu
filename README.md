## Telegram 自动签到

已绑定 Telegram 的账号可以使用官方机器人 `@iKuuuu_VPN_bot` 签到。此方式不依赖网站的登录 Cookie，也不需要每天处理网站验证码。

### 首次配置

1. 在网站「我的账号」→「绑定 Telegram 账号」完成绑定。向机器人发送 `/checkin`，确认返回签到成功或今天已签到。
2. 本机安装 Python、GitHub CLI，使用 `gh auth login` 登录仓库所属账号，再安装登录助手依赖和浏览器：

```powershell
python -m pip install -r requirements-telegram-web.txt
python -m playwright install chromium
```

运行官方 Telegram Web 扫码登录助手，不需要申请 Telegram API 应用：

```powershell
python login_telegram_web.py --repo NotSleeply/sign_ikuuu
```

在弹出的官方 Telegram Web 页面选择二维码登录，用手机 Telegram 的「设置 → 设备 → 关联桌面设备」扫码。如开启两步验证，在官方页面输入密码。本机需要代理时，传入 `--proxy http://127.0.0.1:7890`；已有 Edge 可传入 `--channel msedge` 使用本机浏览器。

助手关闭本机页面后，通过标准输入直接保存 `TELEGRAM_WEB_SESSION` GitHub Secret。会话不会打印或保存到仓库，也不导出聊天 IndexedDB 缓存。此会话具有 Telegram 账号访问权限，只能保存在 Secrets 中。

配置完成后，定时任务每天北京时间 07:10 向官方机器人发送一次 `/checkin`。首次可在 Actions 页面手动运行「Auto Sign-in for BBS」验证；日志中应出现「Telegram Web 签到结果」。

任务只接受本次命令发出后的机器人回复；未绑定、会话失效、超时或无法确认结果都会报错。该方式不依赖网站 Cookie 的有效期；Telegram 会话被撤销后，需要重新运行扫码助手。不要同时在其他机器长期使用导出的同一会话。

### 可选：使用自己的 Telegram API 应用

已取得自己 API 应用凭据时，也可以使用 Telethon：

1. 完成网站与官方机器人的绑定。
2. 登录 <https://my.telegram.org/apps>，在「API development tools」创建应用，取得自己的 `App api_id` 和 `App api_hash`。
3. 本机安装 Python、GitHub CLI，使用 `gh auth login` 登录仓库所属账号，再安装登录助手依赖：

```powershell
python -m pip install -r requirements-telegram.txt "qrcode[pil]" pysocks
```

运行登录助手：

```powershell
python login_telegram.py --repo NotSleeply/sign_ikuuu
```

输入应用凭据后，助手生成临时二维码，路径会显示在终端。用手机 Telegram 的「设置 → 设备 → 关联桌面设备」扫描；二维码到期后会自动刷新同一图片。如开启了 Telegram 两步验证，还需要输入两步验证密码。

本机需要代理时，可给助手传入 `--proxy` 参数，协议支持 HTTP 和 SOCKS5。GitHub Actions 默认直接连接 Telegram。

助手通过标准输入直接保存 `TELEGRAM_API_ID`、`TELEGRAM_API_HASH`、`TELEGRAM_SESSION` 三个 GitHub Secrets，不会输出会话内容或创建 `.session` 文件。登录会话就绪后，原定时任务自动改用 Telegram，每天北京时间 07:10 向官方机器人发送一次 `/checkin`。

任务只接受本次命令发出后的机器人回复；未绑定、会话失效、超时或无法确认结果都会报错。Telegram 会话如果被撤销，需要重新运行登录助手。

## 网页签到

任务按 `TELEGRAM_WEB_SESSION`、`TELEGRAM_SESSION`、网页签到的顺序选择方式。未配置两种 Telegram 会话时使用下方的网页签到方式；Telegram 模式失败时任务会报错，不会自动切换到网站登录。

### ✅ 第一步：Fork 本仓库

打开本项目页面 → 点击右上角 Fork 按钮（复制到你自己的 GitHub 账号下）

### ✅ 第二步：设置变量（多账号设置）

回到你的 GitHub 仓库页面 → 点上方 Settings → 左侧 Secrets and variables → Actions→ 点 New repository secret：
按下面格式填写

Name: 

```
ACCOUNTS
```
Secret:
```
aaa@qq.com:123456
bbb@qq.com:abcdef
ccc@qq.com:qwerty
```
一行一个账号。不要加空格。

### 登录遇到极验验证码

GitHub Actions 无法交互完成验证码。先在本机运行登录助手，人工验证一次后，将登录会话保存到仓库 Secret `IKUUU_COOKIES`，定时任务会优先复用该会话。

本机需要 Python、GitHub CLI，并已通过 `gh auth login` 登录。安装依赖和浏览器：

```powershell
python -m pip install requests playwright
python -m playwright install chromium
```

在项目目录运行，`--repo` 填写自己的仓库：

```powershell
python login_ikuuu.py --repo NotSleeply/sign_ikuuu
```

输入邮箱和密码，在弹出的浏览器中完成验证码并点击登录。助手验证会话后直接通过标准输入上传 Secret，不会打印或保存 Cookie 文件。多账号需在同一次运行中用多个 `--email` 参数指定，上传会替换原有会话集合。

会话失效后需要重新运行助手。`ACCOUNTS` 仍需保留，用于账号列表及没有保存会话时的登录。未配置企业微信时不会尝试发送通知。

### 下面为企业微信消息推送（选填）

1Name: 
```
WX_AGENTID
```
Secret:
```
填你的企业微信应用ID
```
2Name: 
```
WX_CORPID
```
Secret:
```
填你的企业微信ID
```
3Name: 
```
WX_CORPSECRET
```
Secret:
```
填你的企业微信应用密钥
```

### ✅ 第三步：测试运行

点击上方 Actions

首次 Fork 在 Actions 页面点击 Enable workflows 以启用自动任务。

选择 Auto Sign-in for BBS

点击右侧 Run workflow → 等待运行完成

签到失败、会话失效或结果无法确认时，任务会以失败状态退出；接口确认签到成功或当天已经签到时，任务才显示成功。
