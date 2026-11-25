#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push a local git working tree to a GitHub repo through the Git Data API.

Why this exists: on this machine `github.com:443` (the git smart-HTTP endpoint)
is unreliable, while `api.github.com` works. So instead of `git push` we build
the commit server-side: blobs -> tree -> commit -> ref.

    python push-repo.py <local_dir> <owner/repo> [--branch main] [--message "..."]

Token comes from $GH_TOKEN or _work/gh-token.txt (first non-empty line).
The token is never printed.

Behaviour worth knowing:
  * An empty repository rejects blob creation with 409, so we "light it up"
    first by PUTting a single file through the Contents API.
  * The new tree is built WITHOUT base_tree, so the result replaces the whole
    tree — that is how a flattened upload gets corrected.
  * Exit code is 0 only when the final ref actually points at the new commit.
"""

import base64
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"

# Look for a token file relative to the current directory first, then the
# conventional workspace spot. No absolute path is baked in: this file is
# published, and a hard-coded home directory would leak the author's username.
TOKEN_CANDIDATES = ("gh-token.txt", os.path.join("_work", "gh-token.txt"))

TOKEN = None


def read_token():
    token = os.environ.get("GH_TOKEN", "").strip()
    if token:
        return token
    for candidate in TOKEN_CANDIDATES:
        path = pathlib.Path(candidate)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    return line.strip()
    sys.exit("no token: set GH_TOKEN, or put a PAT on the first line of gh-token.txt")


def token():
    global TOKEN
    if TOKEN is None:
        TOKEN = read_token()
    return TOKEN


def api(method, path, payload=None, attempts=4):
    """Call the API, retrying transport failures (not HTTP errors).

    This network drops long-lived connections unpredictably (WinError 10060
    mid-run), so a single timeout must not abort a 100+ file push.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            API + path, data=data, method=method,
            headers={
                "Authorization": "Bearer " + token(),
                "Accept": "application/vnd.github+json",
                "User-Agent": "dsh-push",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw) if raw else {}
            except ValueError:
                return exc.code, {"message": raw.decode("utf-8", "ignore")[:300]}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < attempts:
                wait = min(30, 2 ** attempt)
                print("      retry %d/%d after %s (%s)"
                      % (attempt, attempts - 1, "%ds" % wait, type(exc).__name__))
                time.sleep(wait)
    raise last


def die(step, status, body):
    message = body.get("message") if isinstance(body, dict) else body
    sys.exit("%s failed (HTTP %s): %s" % (step, status, message))


def ensure_repo(owner, name):
    status, body = api("GET", "/repos/%s/%s" % (owner, name))
    if status == 200:
        return body
    if status == 404:
        print("  repo missing -> creating %s/%s" % (owner, name))
        status, body = api("POST", "/user/repos", {
            "name": name, "private": False, "auto_init": False,
        })
        if status not in (200, 201):
            die("create repo", status, body)
        return body
    die("get repo", status, body)


def light_up(owner, name, branch):
    """An empty repo rejects blob creation (409). Put one file first."""
    status, _ = api("GET", "/repos/%s/%s/contents/README.md" % (owner, name))
    if status == 200:
        return
    print("  repo is empty -> seeding with a placeholder commit")
    status, body = api("PUT", "/repos/%s/%s/contents/.gitignore" % (owner, name), {
        "message": "chore: initialise repository",
        "content": base64.b64encode(b"__pycache__/\nnode_modules/\n").decode(),
        "branch": branch,
    })
    if status not in (200, 201):
        die("seed repo", status, body)


def tracked_files(root):
    # core.quotepath=false keeps non-ASCII names readable instead of "\351\203..."
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), "ls-files"],
        capture_output=True, text=True,
        encoding="utf-8", errors="strict",
    )
    if result.returncode != 0:
        sys.exit("git ls-files failed in %s: %s" % (root, result.stderr.strip()))
    return [line for line in result.stdout.splitlines() if line.strip()]


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    root = pathlib.Path(sys.argv[1]).resolve()
    owner, name = sys.argv[2].split("/")

    branch, message = "main", "chore: sync from local"
    rest = sys.argv[3:]
    for i, arg in enumerate(rest):
        if arg == "--branch" and i + 1 < len(rest):
            branch = rest[i + 1]
        if arg == "--message" and i + 1 < len(rest):
            message = rest[i + 1]

    files = tracked_files(root)
    if not files:
        sys.exit("no tracked files in %s" % root)

    print("target : %s/%s (%d files, branch %s)" % (owner, name, len(files), branch))
    ensure_repo(owner, name)
    light_up(owner, name, branch)

    base = "/repos/%s/%s" % (owner, name)

    # 1) blobs
    entries, failed = [], []
    for index, rel in enumerate(files, 1):
        data = (root / rel).read_bytes()
        status, body = api("POST", base + "/git/blobs", {
            "content": base64.b64encode(data).decode(),
            "encoding": "base64",
        })
        if status not in (200, 201):
            failed.append((rel, status, body.get("message")))
            continue
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": body["sha"]})
        if index % 25 == 0 or index == len(files):
            print("  blobs   %d/%d" % (index, len(files)))

    if failed:
        for rel, status, msg in failed[:5]:
            print("  FAILED %s (HTTP %s): %s" % (rel, status, msg))
        sys.exit("%d file(s) could not be uploaded" % len(failed))

    # 2) tree (no base_tree -> replaces the whole tree)
    status, body = api("POST", base + "/git/trees", {"tree": entries})
    if status not in (200, 201):
        die("create tree", status, body)
    tree_sha = body["sha"]
    print("  tree    %s" % tree_sha[:12])

    # 3) commit on top of the current branch head, if any
    status, head = api("GET", base + "/git/ref/heads/" + branch)
    parents = [head["object"]["sha"]] if status == 200 else []

    payload = {"message": message, "tree": tree_sha}
    if parents:
        payload["parents"] = parents
    status, body = api("POST", base + "/git/commits", payload)
    if status not in (200, 201):
        die("create commit", status, body)
    commit_sha = body["sha"]
    print("  commit  %s" % commit_sha[:12])

    # 4) move the ref
    if parents:
        status, body = api("PATCH", base + "/git/refs/heads/" + branch,
                           {"sha": commit_sha, "force": True})
    else:
        status, body = api("POST", base + "/git/refs",
                           {"ref": "refs/heads/%s" % branch, "sha": commit_sha})
    if status not in (200, 201):
        die("update ref", status, body)

    # 5) verify, do not assume
    status, body = api("GET", base + "/git/ref/heads/" + branch)
    actual = body.get("object", {}).get("sha") if status == 200 else None
    if actual != commit_sha:
        sys.exit("ref verification failed: expected %s, got %s" % (commit_sha, actual))

    status, repo = api("GET", "/repos/%s/%s" % (owner, name))
    print("  ok      https://github.com/%s/%s  (%d files)" % (owner, name, len(files)))
    if repo.get("default_branch") != branch:
        print("  note    default branch is %s, pushed to %s"
              % (repo.get("default_branch"), branch))
    return 0


if __name__ == "__main__":
    sys.exit(main())
