#!/usr/bin/env python3
"""出版前审计：扫描目录里不该公开的内容。

用法：
    python audit_secrets.py <目录> [--extra-pattern 词] [--quiet]

输出两档：
    必须修 —— 真实凭证、本机绝对路径、内网 IP、私钥块
    建议修 —— 真实域名、邮箱、手机号、可能的学校名

退出码：0 = 无「必须修」；1 = 有「必须修」。
"""

import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".pytest_cache", ".mypy_cache", ".idea",
    ".gradle", "target", "coverage", ".nuxt", ".svelte-kit",
}
SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".rar",
    ".pyc", ".pyd", ".so", ".dll", ".exe", ".dylib", ".o", ".a",
    ".mp4", ".mp3", ".wav", ".webm", ".mov",
    ".lock", ".map",
}
SKIP_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock"}

MUST = [
    ("真实 token", re.compile(
        r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|"
        r"github_pat_[A-Za-z0-9_]{20,}|AT_[A-Za-z0-9]{20,}|"
        r"xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("私钥块", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("本机绝对路径", re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"'<>|]+")),
    ("内网 IP", re.compile(
        r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|"
        r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})\b")),
]

WARN = [
    ("真实域名", re.compile(r"\b(?:[a-z0-9][a-z0-9-]{1,62}\.)+(?:cn|com|net|io|dev|top|xyz|site|app)\b", re.I)),
    ("邮箱", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
]

# 这些域名出现在说明文档里是正常的，不算泄露
DOMAIN_ALLOW = {
    "example.com", "example.org", "examples.com",
    "github.com", "githubusercontent.com", "gitlab.com",
    "nodejs.org", "python.org", "npmjs.com", "pypi.org",
    "docker.com", "dockerhub.com", "hub.docker.com",
    "openai.com", "deepseek.com", "anthropic.com",
    "aliyun.com", "aliyuncs.com", "tencent.com", "huaweicloud.com",
    "qweather.com", "siliconflow.cn", "minimaxi.com", "wxpusher.zjiecode.com",
    "tailscale.com", "wikipedia.org", "stackoverflow.com",
    "nextjs.org", "react.dev", "prisma.io", "postgresql.org", "mysql.com",
    "tailwindcss.com", "google.com", "microsoft.com",
}

# 学校/单位名默认只做提示，可用 --school 追加
SCHOOL_DEFAULT = ["湖州学院", "湖州师范学院", "吴兴区"]


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_EXTS:
            continue
        if path.name in SKIP_NAMES:
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        yield path


def scan(root: Path, extra: list, school_words: list, quiet: bool):
    must_hits = []
    warn_hits = []

    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()

        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            # 行内豁免：文档里描述检测规则时，示例本身会命中规则
            if "noqa" in line.lower() or "audit-ignore" in line.lower():
                continue

            for label, pattern in MUST:
                m = pattern.search(line)
                if not m:
                    continue
                # 网段定义（100.64.0.0/10）不是主机地址，代码里判断私网是正常逻辑
                if label == "内网 IP" and m.end() < len(line) and line[m.end()] == "/":
                    continue
                must_hits.append((rel, lineno, label, stripped[:120]))

            for label, pattern in WARN:
                if label == "真实域名":
                    for m in pattern.finditer(line):
                        host = m.group(0).lower()
                        if host in DOMAIN_ALLOW or host.endswith(".example.com"):
                            continue
                        warn_hits.append((rel, lineno, label, host))
                        break
                elif pattern.search(line):
                    warn_hits.append((rel, lineno, label, stripped[:120]))

            for word in school_words:
                if word in line:
                    warn_hits.append((rel, lineno, "单位/学校名", stripped[:120]))

            for word in extra:
                if word and word in line:
                    must_hits.append((rel, lineno, f"自定义:{word}", stripped[:120]))

    # 去重（同一行同一类型只报一次）
    must_hits = list(dict.fromkeys(must_hits))
    warn_hits = list(dict.fromkeys(warn_hits))

    print(f"扫描目录：{root}")
    print(f"文件数：{sum(1 for _ in iter_files(root))}")
    print()

    if must_hits:
        print(f"【必须修】{len(must_hits)} 处")
        for rel, lineno, label, snippet in must_hits:
            print(f"  {rel}:{lineno}  [{label}]  {snippet}")
        print()
    else:
        print("【必须修】0 处 ✓")
        print()

    if warn_hits and not quiet:
        print(f"【建议修】{len(warn_hits)} 处（人工判断，可能误报）")
        for rel, lineno, label, snippet in warn_hits[:60]:
            print(f"  {rel}:{lineno}  [{label}]  {snippet}")
        if len(warn_hits) > 60:
            print(f"  …… 另有 {len(warn_hits) - 60} 处")
        print()

    return 1 if must_hits else 0


def main():
    ap = argparse.ArgumentParser(description="出版前敏感信息审计")
    ap.add_argument("root", nargs="?", default=".", help="要扫描的项目目录")
    ap.add_argument("--extra-pattern", action="append", default=[],
                    help="额外必须命中的词（如真实域名、服务名），可多次")
    ap.add_argument("--school", action="append", default=None,
                    help="额外要提示的单位/学校名，可多次（默认内置几个）")
    ap.add_argument("--quiet", action="store_true", help="只输出「必须修」")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"不是目录：{root}", file=sys.stderr)
        return 2

    school = SCHOOL_DEFAULT if args.school is None else args.school
    return scan(root, args.extra_pattern, school, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
