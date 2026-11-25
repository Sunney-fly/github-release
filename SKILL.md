---
name: github-release
description: "把一个本地项目整理成可公开发布的 GitHub 仓库：脱敏扫描、发布四件套、认证方式选择、push 与验收。用户说「发到 GitHub / 开源这个项目 / 帮我发布 / 推上去」时使用。"
---
> **验证**：2026-11-25 / deepseek-v4.1-flash / `assets/push-repo.py` 推 5 个仓库（portfolio 39、jarvis-hub 91、fang-site 122、cdp-clip 10、github-release 7），每个都核对了 ref 指向 / ok。审计与 GIF 生成同轮实测。


# GitHub 仓库发布

把本地项目变成一个别人 clone 下来能跑、不会泄露隐私、面试官愿意看的公开仓库。

## 什么时候用

- 用户说「发到 GitHub」「开源这个」「帮我发布」「推上去」
- 一个项目做完了，要变成简历资产

## 五步流程（按顺序，别跳）

### 1. 审计：先扫，再动

```powershell
python ./audit_secrets.py <项目目录>
```

输出「必须修 / 建议修」两档。**必须修清零才能继续。**

覆盖的泄露类型（都是真实踩过的）：

| 类型 | 例子 | 为什么危险 |
|---|---|---|
| 真实域名 | `xxx.cn` 出现在 nginx 配置、README | 能定位到你的服务器 |
| 内网 IP | `100.64.x.x`（Tailscale）、`192.168.x.x` | 能定位私网入口 |
| 本机绝对路径 | `D:\Users\<用户名>\...` | 泄露用户名与目录结构 |
| 学校 / 校区 | 「湖州学院」「某校区」 | 配合 GitHub 账号可定位到个人 |
| 真实 token 格式 | `sk-...`、`ghp_...`、`AT_...` | 直接盗用 |
| 服务名 / 目录名 | `nanmount-site.service`、`/var/www/nanmount` | 暴露私有部署结构 |

**改造方式**：域名 → `your-domain.example.com`；内网 IP → `<TAILSCALE_IP>`；本机路径 → `<workspace>`；学校 → `某高校`；服务名 → 通用名（`site-proxy.service`）。

**环境变量模板例外**：`.env.example` / `env.example` 里留空值是正常的，不算泄露。

### 2. 补齐四件套

```powershell
python ./preflight.py <项目目录>
```

必须存在：

| 文件 | 要求 |
|---|---|
| `README.md` | 一句话说清「这是什么 + 解决什么问题 + 怎么跑」；数字必须可复算 |
| `README.zh-CN.md` | 中文版（或反过来，取决于主受众） |
| `LICENSE` | 默认 MIT |
| `env.example` | 所有必需环境变量，值留空或写占位符 |
| `.gitignore` | 至少排除 `node_modules/`、`__pycache__/`、`.env`、构建产物 |

### 3. README 的硬要求

**必须做到**：
- 第一屏能看懂「它解决什么问题」，不是技术名词堆砌
- 「快速开始」里的每条命令**都真的能跑**（这一步最容易翻车，见第 5 步）
- 数字带出处：写「69 项测试」就要真能跑出 69
- 明确写「边界 / 已知限制」——这一节最能体现工程成熟度

**不要做**：
- 写「未来将支持 XXX」超过三条
- 为了显得厉害写「支持 100+ 网站」这种无法验证的话
- 把 commit 数、star 数当卖点（会变，且容易被查）

### 4. 选认证方式（按本机实测排序）

| 方式 | 适用 | 关键事实 |
|---|---|---|
| **API 推送** `assets/push-repo.py` | ✅ **本机首选** | `github.com:443` 不通，`api.github.com` 通；只要一个 PAT |
| SSH key | 换机器、或想长期免密 | 加 key 需要 GitHub sudo 密码，**必须用户本人输** |
| HTTPS + GCM | 凭证还有效时最省事 | 失效报 `Invalid username or token`，需 `git credential-manager github logout` |
| 网页上传 | ❌ **不要用** | 会压平目录，见「最大的坑」 |

**API 推送（推荐）**：

```powershell
# 用户建 classic PAT（只勾 repo），存到 _work/gh-token.txt 第一行，或设 GH_TOKEN
python ./push-repo.py <本地目录> <owner/repo> --message "feat: ..."
```

走 Git Data API（blobs → tree → commit → ref），自带三个处理：

- 空仓库 409 → 先 PUT 一个文件点亮
- 不带 `base_tree` → **整棵树替换**，被压平的仓库一次修好
- 推完核对 ref 指向，不通过即报错

**三个实测的坑**：

1. 端点必须带 `/repos/{owner}/{repo}` 前缀，漏了全 404
2. 长连接会中途断（`WinError 10060`），必须指数退避重试
3. `git ls-files` 默认转义中文文件名，要 `-c core.quotepath=false`

> token 用完立刻删文件；全程不打印。

**SSH 配置（22 端口常被墙，走 443）**：

```powershell
ssh-keygen -t ed25519 -f <工作区>/_work/gh-publish-key -N "" -C "publish"
# 把 .pub 内容贴到 https://github.com/settings/ssh/new
$env:GIT_SSH_COMMAND = "ssh -i <工作区>/_work/gh-publish-key -p 443 -o StrictHostKeyChecking=accept-new"
git push -f ssh://git@ssh.github.com:443/<owner>/<repo>.git main
```

> 密钥放工作区内，**不要放 `~/.ssh`**（会触发安全策略拦截）。

### 5. 录演示 GIF（`assets/make-gif.py`）

首屏动图是点击率影响最大的单项。**不用录屏**——真实执行命令、捕获输出、再用 Pillow 渲染成终端风格，既不占屏也不摆拍：

```powershell
python ./make-gif.py --title "项目名" --command "<真实命令>" --run <工作目录> --out docs/demo.gif
```

**三个实测的坑**：

1. 绝对路径会漏进 GIF → 脚本按 `--run` 目录归一化成 `./`
2. Consolas 没有中日韩字形 → 按行判断，含中文字符的行切到雅黑
3. 系统 Python 3.8 输出 GBK → subprocess 必须指定 `encoding="utf-8"` + `PYTHONUTF8=1`，否则中文全是乱码

产物控制在 50 KB 以内（实测 29–32 KB），README 用 `<img src="docs/demo.gif" width="760">`。

### 6. 发布后必须验证

```powershell
# 1. 确认文件数与目录结构
git ls-files | Measure-Object -Line
# 2. 另找一个干净目录 clone，按 README 走一遍
# 3. 跑测试（如果有）
```

**验收标准**：干净目录 clone → 按 README 三步 → 能跑起来 → 测试通过。

## 最大的坑：网页上传会压平目录

2026-11-24 实测，用 GitHub 网页的「Upload files」传 91 个文件：

- 设置 `File.webkitRelativePath` 后，**上传列表显示 `core/pyproject.toml`**，看着像成功了
- 但**实际存储时只用了 `basename`** —— `docs/DEPLOY.md` 变成根目录的 `DEPLOY.md`
- 结果：85 个文件全平铺在根目录，目录结构彻底丢失

**结论**：网页上传只适合单目录、少文件。**任何有嵌套目录的项目必须走 `git push`。**

（如果实在没有认证通道，宁可让用户自己 push，也不要用网页上传糊过去。）

## 发布后的第一小时

1. 填 Description（一句话，和专业定位一致）
2. 加 Topics（5–10 个，决定能不能被搜到）
3. 发 release（`v0.1.0`）
4. 录一段 8–12 秒 GIF 放 README 首屏 —— 这是点击率最高的单项

## 反面教材（都真踩过）

| 现象 | 根因 | 修法 |
|---|---|---|
| 别人 clone 后跑测试挂 1 个 | 测试写的是旧行为，代码已经改了 | 发布前在副本上真跑一遍 |
| README 写「55 项测试全绿」 | 文档没跟着代码更新 | 用 `grep -c 'def test_'` 现数 |
| 采访稿写「用户无感」 | 实际超时 120 秒才切换 | 改成「超时后切换，不是秒切」 |
| 文档说 PostgreSQL，快速开始写 MySQL | 两个版本混用没统一 | 以 `schema.prisma` 的 provider 为准 |
| 引用不存在的文件 | README 提到 `start-local.bat`，实际删了 | preflight 会检查 README 里引用的文件是否存在 |
