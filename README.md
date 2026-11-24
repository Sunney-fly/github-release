# github-release

**发布前给自己踩刹车：先扫脱敏，再查四件套，最后验证别人 clone 下来能跑。**

两个零依赖 Python 脚本 + 一份清单。把「发个开源仓库」从两小时的试错压到二十分钟。

---

## 它解决什么

把本地项目发到 GitHub，翻车方式就那么几种，而且每次都会忘：

| 翻车方式 | 后果 | 这里怎么防 |
|---|---|---|
| 域名 / 内网 IP / 本机路径没清 | 泄露服务器位置和用户名 | `audit_secrets.py` 扫出来，分「必须修 / 建议修」 |
| 学校名、服务名没换 | 配合 GitHub 账号能定位到本人 | 同上，内置常见单位名提示 |
| README 引用了不存在的文件 | 别人点进去 404 | `preflight.py` 校验所有相对链接 |
| 说「69 项测试全绿」但实际挂 1 个 | 面试官一 clone 就穿 | 发布前在副本上真跑一遍 |
| 只有 1 个 commit | 看不出开发过程 | 提示拆成有意义的提交 |

## 两个脚本

### `audit_secrets.py` — 脱敏审计

```bash
python audit_secrets.py <项目目录> --quiet
```

输出两档：

- **必须修**：真实 token、私钥块、本机绝对路径（`D:\Users\...`）、内网 IP（`10./192.168./100.64-127.`） <!-- noqa -->
- **建议修**：真实域名、邮箱、手机号、单位/学校名

退出码 1 表示还有「必须修」，可以直接接进 CI。

自动跳过 `.git`、`node_modules`、二进制文件，以及 `example.com` 这类文档常用域名，减少误报。CIDR 网段（`100.64.0.0/10`）不会被当成主机地址——代码里判断私网是正常逻辑。

### `preflight.py` — 发布前检查

```bash
python preflight.py <项目目录> --test "pytest -q"
```

检查：

- 四件套：`README.md`、`LICENSE`、`.gitignore`、`env.example`
- README 里所有相对链接指向的文件是否真的存在
- `git status` 是否干净、有没有 commit、commit 数够不够
- 可选：跑测试，失败即阻塞

## 用法

```bash
# 1. 先把项目复制一份到发布目录，别在源码目录上动手
# 2. 审计
python audit_secrets.py ./my-project-public --quiet
# 3. 有「必须修」就改，改完再跑，直到 0 处
# 4. 检查四件套
python preflight.py ./my-project-public --test "pytest -q"
# 5. 推
```

完整的发布流程（认证方式选择、README 硬要求、发布后一小时内做什么）见 [SKILL.md](SKILL.md)。

## 一个必须知道的坑

**GitHub 网页上传会压平目录。**

实测：用网页「Upload files」传 91 个文件，设置 `File.webkitRelativePath` 后上传列表里显示 `core/pyproject.toml`，看起来成功了——但实际存储时只用了 `basename`，`docs/DEPLOY.md` 变成了根目录的 `DEPLOY.md`，85 个文件全平铺。

**任何有嵌套目录的项目必须走 `git push`。** 网页上传只适合单目录、少文件。

## 为什么做这个

发第三个开源项目时，前两次踩的坑又踩了一遍：网页上传压平、GCM 凭证失效、脱敏漏掉 `C:\Users\` 开头的路径。 <!-- noqa -->

把它固化下来——顺便，`audit_secrets.py` 第一次跑就抓到了我自己手工脱敏时漏掉的两处本机路径。

## License

MIT
