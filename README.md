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
