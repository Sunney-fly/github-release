#!/usr/bin/env python3
"""发布前检查：四件套是否齐、README 引用的文件是否存在、git 状态是否干净。

用法：
    python preflight.py <目录> [--test "pytest -q"] [--skip-test]

退出码：0 = 可以发布；1 = 有阻塞项。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_README = ["README.md"]
REQUIRED_OTHER = ["LICENSE", ".gitignore"]

ENV_CANDIDATES = ["env.example", ".env.example", "env.sample", ".env.sample"]

LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
BLOCKING = []
WARN = []


def check_required(root: Path):
    print("【四件套】")
    readme_ok = False
    for name in REQUIRED_README:
        p = root / name
        if p.exists():
            print(f"  ✓ {name} ({p.stat().st_size} bytes)")
            readme_ok = True
        else:
            print(f"  ✗ {name} 缺失")
            BLOCKING.append(f"缺少 {name}")

    for name in REQUIRED_OTHER:
        p = root / name
        if p.exists():
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name} 缺失")
            BLOCKING.append(f"缺少 {name}")

    env_found = None
    for name in ENV_CANDIDATES:
        p = root / name
        if p.exists():
            env_found = p
            break
    if env_found:
        print(f"  ✓ {env_found.name}")
        if env_found.name.startswith("."):
            WARN.append(f"{env_found.name} 以点开头；部分安全策略会拦截，建议改名 env.example")
    else:
        print("  ⚠ 未提供环境变量模板（纯工具类项目可以没有）")
        WARN.append("没有 env.example；如果项目需要 API key，补一个")

    if readme_ok:
        text = (root / "README.md").read_text(encoding="utf-8", errors="ignore")
        if len(text) < 500:
            WARN.append("README 少于 500 字符，大概率讲不清项目")
        if "install" not in text.lower() and "快速开始" not in text and "quick start" not in text.lower():
            WARN.append("README 里找不到安装/快速开始段落")
    print()


def check_links(root: Path):
    """README 里引用的相对路径必须真实存在。"""
    print("【README 引用】")
    broken = []
    for md in root.glob("*.md"):
        text = md.read_text(encoding="utf-8", errors="ignore")
        for m in LINK_RE.finditer(text):
            target = m.group(1).strip()
            if not target or target.startswith(("http://", "https://", "#", "mailto:", "tel:")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            p = (root / target).resolve()
            if not str(p).startswith(str(root.resolve())):
                continue
            if not p.exists():
                broken.append(f"{md.name} → {target}")

    if broken:
        for b in sorted(set(broken)):
            print(f"  ✗ 引用不存在：{b}")
            BLOCKING.append(f"README 引用了不存在的文件：{b}")
    else:
        print("  ✓ 所有相对引用都存在")
    print()


def check_git(root: Path):
    print("【git 状态】")
    try:
        inside = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=10,
        )
        if inside.returncode != 0:
            print("  ⚠ 不是 git 仓库（发布前需要 git init）")
            WARN.append("尚未 git init")
            print()
            return
    except (OSError, subprocess.SubprocessError):
        print("  ⚠ 无法执行 git（PATH 里没有？）")
        print()
        return

    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if status:
        n = len(status.splitlines())
        print(f"  ⚠ 有 {n} 个未提交改动")
        WARN.append(f"{n} 个未提交改动")
    else:
        print("  ✓ 工作区干净")

    log = subprocess.run(
        ["git", "-C", str(root), "log", "--oneline", "-1"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if log:
        print(f"  ✓ 最新 commit：{log}")
    else:
        print("  ⚠ 还没有 commit")
        WARN.append("还没有 commit")

    count = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if count.isdigit() and int(count) <= 1:
        WARN.append("只有 1 个 commit；面试官会看提交历史，建议至少拆成 2–3 个有意义的提交")
    print()


def tracked_count(root: Path) -> int:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        return len([x for x in out.splitlines() if x.strip()])
    except (OSError, subprocess.SubprocessError):
        return -1


def run_tests(root: Path, cmd: str):
    print(f"【测试】{cmd}")
    try:
        r = subprocess.run(cmd, cwd=root, shell=True, capture_output=True,
                           text=True, timeout=600)
    except subprocess.TimeoutExpired:
        print("  ✗ 测试超时（10 分钟）")
        BLOCKING.append("测试超时")
        print()
        return
    tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
    for line in tail:
        print(f"  {line}")
    if r.returncode == 0:
        print("  ✓ 测试通过")
    else:
        print(f"  ✗ 测试失败（exit {r.returncode}）")
        BLOCKING.append(f"测试失败（exit {r.returncode}）")
    print()


def main():
    ap = argparse.ArgumentParser(description="GitHub 发布前检查")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--test", default=None, help='测试命令，如 "pytest -q"')
    ap.add_argument("--skip-test", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"不是目录：{root}", file=sys.stderr)
        return 2

    print(f"检查目录：{root}\n")
    check_required(root)
    check_links(root)
    check_git(root)

    n = tracked_count(root)
    if n >= 0:
        print(f"【规模】git 跟踪 {n} 个文件")
        if n == 0:
            BLOCKING.append("没有任何被 git 跟踪的文件")
        print()

    if args.test and not args.skip_test:
        run_tests(root, args.test)

    print("=" * 50)
    if BLOCKING:
        print(f"阻塞项 {len(BLOCKING)} 条：")
        for b in dict.fromkeys(BLOCKING):
            print(f"  ✗ {b}")
    else:
        print("✓ 没有阻塞项")
    if WARN:
        print(f"\n提醒 {len(WARN)} 条：")
        for w in dict.fromkeys(WARN):
            print(f"  · {w}")
    return 1 if BLOCKING else 0


if __name__ == "__main__":
    sys.exit(main())
