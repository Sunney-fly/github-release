---
name: github-release
description: "把一个本地项目整理成可公开发布的 GitHub 仓库：脱敏扫描、发布四件套、认证方式选择、push 与验收。用户说「发到 GitHub / 开源这个项目 / 帮我发布 / 推上去」时使用。"
---
> **验证**：未记录（下次用完后回填 —— `<日期>/<provider:model>/<可复跑命令>/ok|部分`）沉默不等于验证过。


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

### 4. 选认证方式（血泪教训）

| 方式 | 适用 | 坑 |
|---|---|---|
| **SSH key** | 推荐，一次配置长期可用 | 加 key 需要 GitHub sudo 密码，**必须用户本人输** |
| **HTTPS + GCM** | 凭证还有效时最省事 | 缓存失效时报 `Invalid username or token`，需要 `git credential-manager github logout` 重新授权 |
| **网页上传** | ❌ **不要用** | 见下方「最大坑」 |

**SSH 配置（22 端口常被墙，走 443）**：

```powershell
ssh-keygen -t ed25519 -f <工作区>/_work/gh-publish-key -N "" -C "publish"
# 把 .pub 内容贴到 https://github.com/settings/ssh/new
# push 时：
$env:GIT_SSH_COMMAND = "ssh -i <工作区>/_work/gh-publish-key -p 443 -o StrictHostKeyChecking=accept-new"
git push -f ssh://git@ssh.github.com:443/<owner>/<repo>.git main
```

> 密钥放工作区内，**不要放 `~/.ssh`**（会触发安全策略拦截）。

### 5. 发布后必须验证

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
