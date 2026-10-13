#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发布脱敏审计与全历史提交元数据改写（M6，O-6）。

发布型仓库的脱敏面有四块（HANDOFF-M6 §八），本工具把它们固化成**可复跑**的四步：

  1. **提交元数据审计**：全历史 ``git log --format="%ae %ce"`` 只允许 GitHub noreply
     （``<id>+<login>@users.noreply.github.com``）。真实个人邮箱一旦留在提交元数据里，
     会随每一次 clone 永久带出——发布前必须清零。
  2. **工作树审计**：受版本控制的文本文件不得含个人邮箱、开发机绝对路径。
  3. **构建产物审计**：``dist/`` 内不得含个人邮箱 / 开发机绝对路径；随包真值档案必须
     显式声明为合成数据（``synthetic: true``），不得混入真实企业数据。
  4. **发布附件台账**：ASCII 名 + sha256 留档（供 ``plan/RELEASE-M6.md`` 引用）。

子命令
------
``audit``   只读审计（默认）；命中即 exit 1。
``rewrite`` 全历史改写为 noreply（破坏性；**先提交全部改动**，再跑本命令）。
``verify``  改写后验证：断言全部提交身份为 noreply，且指定字面值在 ae/ce 两字段均不存在。
``ledger``  dist 附件 ASCII 名 + sha256 台账。
``pack``    dist 目录 → ASCII 名 zip（固定时间戳，可复跑）。

豁免口径
--------
``data/knowledge/raw/**`` 是官方原文快照（字节精确、sha256 冻结），可能含官方联系地址；
它**不可改写、也不进发布包**（打包白名单 ``DATA_EXCLUDE`` 已排除），故不纳入工作树扫描。
"""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: GitHub noreply 提交地址：``<id>+<login>@users.noreply.github.com``（``<id>+`` 可省）
NOREPLY_RE = re.compile(
    r"^(?:\d+\+)?[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?@users\.noreply\.github\.com$")

#: 通用邮箱形态（用于工作树 / 构建产物扫描）
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

#: 开发机绝对路径泄露：Windows 盘符路径 / 用户主目录（POSIX 与 Windows 两种写法）。
#: 盘符形态加负向先行断言，避免把 ``https://www.mee.gov.cn/`` 这类**官方来源 URL**
#: 误判成盘符路径（``s:`` 前是字母 ``p``）。
ABS_PATH_RES = (
    re.compile(r"(?<![A-Za-z0-9:])[A-Za-z]:[\\/]{1,2}[A-Za-z0-9._-]+[\\/]"),
    re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/"),
)

#: 系统路径前缀白名单：跨机器相同的标准位置，不是"开发机路径"。
#: ``C:/Windows/Fonts/msyh.ttc`` 在**每台** Windows 上都一样，且加载中文字体必需
#: （见 HANDOFF-M6 §四.14），报出来是噪声而非泄露。判据是"换台机器是否还成立"。
SYSTEM_PATH_PREFIXES = (
    "c:/windows/",
    "c:/temp/",
)

#: 随包真值档案的合成标记：虚构统一社会信用代码必须自带 ``SYN`` 标记。
#: 真实统一社会信用代码是 18 位数字+大写字母，**不会**含 ``SYN``；因此"带 SYN"
#: 既是可读的合成声明，也保证它不可能是一个真代码。判据用标记而非固定格式，
#: 因为失败路径算例的代码段各不相同（如 ``steel2023yoybaselineSYN``）。
SYNTHETIC_CODE_MARKER = "syn"

#: 工作树扫描的文本扩展名（发布面 = 受版本控制的这些文件）
_TEXT_EXTS = (
    ".py", ".md", ".json", ".toml", ".yml", ".yaml", ".txt", ".cfg", ".ini",
    ".spec", ".csv", ".html", ".sh", ".bat",
)
_TEXT_NAMES = (".gitattributes", ".gitignore", "LICENSE", "Makefile")

#: 不可改写 / 不进包的官方原文快照目录（见模块 docstring 豁免口径）
RAW_PREFIX = "data/knowledge/raw/"

OK_MARKER = "DESENSITIZE_AUDIT_OK"


# --------------------------------------------------------------------------
# 只读审计（可被测试直接调用的纯函数）
# --------------------------------------------------------------------------

def _is_system_path(value):
    normalized = value.replace("\\", "/").lower()
    return any(normalized.startswith(prefix) for prefix in SYSTEM_PATH_PREFIXES)


def find_text_leaks(text, deny_emails=()):
    """在文本中找出泄露项；返回 ``[ (kind, value) ]``。

    ``kind`` ∈ ``{"email", "abs_path", "denied_literal"}``；``deny_emails`` 是额外的
    **必须不存在**的字面值（个人邮箱本体由调用方传入，避免把敏感字面值写进入仓脚本）。
    """
    leaks = []
    lowered = text.lower()
    for denied in deny_emails:
        if denied and denied.lower() in lowered:
            leaks.append(("denied_literal", denied))
    for match in EMAIL_RE.finditer(text):
        addr = match.group(0)
        if NOREPLY_RE.match(addr):
            continue
        leaks.append(("email", addr))
    for pattern in ABS_PATH_RES:
        for match in pattern.finditer(text):
            value = match.group(0)
            if _is_system_path(value):
                continue
            leaks.append(("abs_path", value))
    return leaks


def check_commit_identities(entries, allowed_noreply=()):
    """校验提交身份行；返回违规列表 ``[ (commit, field, email) ]``。

    ``entries`` 是 ``(sha, author_email, committer_email)`` 三元组序列。
    只允许 noreply 形态（或调用方显式放行的地址）。
    """
    allowed = {addr.lower() for addr in allowed_noreply}
    violations = []
    for sha, author_email, committer_email in entries:
        for field, addr in (("ae", author_email), ("ce", committer_email)):
            if not addr:
                continue
            if addr.lower() in allowed or NOREPLY_RE.match(addr):
                continue
            violations.append((sha, field, addr))
    return violations


def iter_commit_identities(root=None):
    """读取全历史提交身份（``--all`` 覆盖所有 ref）。"""
    root = root or ROOT
    out = _git(["log", "--all", "--format=%H\x1f%ae\x1f%ce"], root).stdout
    entries = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            entries.append(tuple(parts))
    return entries


def iter_tracked_files(root=None):
    """发布面文件相对路径：已受版本控制 + 未忽略的未跟踪文件。

    用 ``--others --exclude-standard`` 而非只看 ``--cached``：M0–M5 的改动在首次
    有序提交前是**未跟踪**的，若只扫已跟踪文件，脱敏审计会在最该扫的时候漏掉它们。
    """
    root = root or ROOT
    out = _git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], root).stdout
    return sorted({p.replace("\\", "/") for p in out.split("\x00") if p})


def is_scannable(relpath):
    """工作树扫描范围：文本类、且不在官方原文快照目录内。"""
    rel = relpath.replace("\\", "/")
    if rel.startswith(RAW_PREFIX):
        return False
    name = os.path.basename(rel)
    if name in _TEXT_NAMES:
        return True
    return rel.lower().endswith(_TEXT_EXTS)


def scan_working_tree(root=None, deny_emails=()):
    """扫描工作树文本文件；返回 ``[ (relpath, kind, value) ]``。"""
    root = root or ROOT
    hits = []
    for rel in iter_tracked_files(root):
        if not is_scannable(rel):
            continue
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            for kind, value in find_text_leaks(fh.read(), deny_emails):
                hits.append((rel, kind, value))
    return hits


def scan_build_dir(directory, deny_emails=(), deny_paths=(), max_bytes=64 * 1024 * 1024):
    """扫描构建产物目录（含二进制）；返回 ``[ (relpath, kind, value) ]``。

    扫描强度按文件性质分三档，因为发布产物里混着三类内容：

    * **本项目文本产物**（随包 ``data/`` 下的 JSON 等）：按文本全量扫描（邮箱 + 路径）。
    * **本项目二进制产物**（exe 本体）：二进制里逐字节解码会产生大量假邮箱，故**只查
      调用方给出的具体字面值**（``deny_emails`` / ``deny_paths``）——这正是"我的邮箱有没有
      被打进包"这个问题所需的最小充分判据。
    * **第三方运行时**（PySide6/Qt/MSVC 的 DLL/PYD）：只查具体字面值；其内嵌的
      **Qt 与微软构建机路径**既非本机也非我们可控，通用模式一律不报，否则会刷屏淹没真实问题。
    """
    hits = []
    root = os.path.abspath(directory)
    if not os.path.isdir(root):
        return hits
    literals = [v for v in (list(deny_emails) + list(deny_paths)) if v]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(dirnames)
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > max_bytes:
                continue
            with open(path, "rb") as fh:
                blob = fh.read()
            rel = os.path.relpath(path, root).replace("\\", "/")
            text = blob.decode("utf-8", "ignore")
            if rel.lower().endswith(_TEXT_EXTS) or rel.lower().endswith(_TEXT_NAMES):
                for kind, value in find_text_leaks(text, deny_emails):
                    hits.append((rel, kind, value))
                continue
            for value in literals:
                if value.lower() in text.lower():
                    hits.append((rel, "denied_literal", value))
    return hits


def is_project_artifact(relpath):
    """发布产物里"属于本项目"的部分：exe 本体与随包数据。"""
    rel = relpath.replace("\\", "/")
    if rel.lower().endswith(".exe"):
        return True
    return rel.startswith("data/")


def default_dev_markers(root=None):
    """当前开发机的精确路径标记（用于构建产物扫描）。

    刻意**不用裸用户名**：实测 ``ASUS`` 会命中 Qt 的厂商串 ``ASUSTek COMPUTER INC``
    （见 dist/ghg-gui/PySide6/Qt6Gui.dll），是假阳性。真正要问的是"我这台机器的
    **路径**有没有被打进包"，所以标记取主目录与仓库根的路径形态（含正反斜杠两种写法）。
    """
    root = os.path.abspath(root or ROOT)
    home = os.path.expanduser("~")
    candidates = {home, root}
    markers = set()
    for value in candidates:
        if not value:
            continue
        markers.add(value)
        markers.add(value.replace("\\", "/"))
        markers.add(value.replace("/", "\\"))
    return sorted(m for m in markers if len(m) > 3)


def check_packaged_truth_is_synthetic(root=None):
    """随包真值档案必须显式声明为合成数据（防真实企业数据混入发布产物）。"""
    root = root or ROOT
    problems = []
    profiles_dir = os.path.join(root, "data", "truth", "profiles")
    if not os.path.isdir(profiles_dir):
        return problems
    for name in sorted(os.listdir(profiles_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(profiles_dir, name)
        try:
            with io.open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (ValueError, OSError) as exc:
            problems.append((name, "unreadable", str(exc)))
            continue
        facility = payload.get("facility") or {}
        if facility.get("synthetic") is not True:
            problems.append((name, "not_synthetic", repr(facility.get("synthetic"))))
        code = facility.get("credit_code")
        # 只有填了统一社会信用代码时才校验其合成形态（部分失败路径算例不带企业信息）
        if code and SYNTHETIC_CODE_MARKER not in code.lower():
            problems.append((name, "credit_code", code))
    return problems


# --------------------------------------------------------------------------
# 全历史改写（破坏性）
# --------------------------------------------------------------------------

def _git(args, cwd=None, check=True):
    return subprocess.run(
        ["git"] + list(args), cwd=cwd or ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check,
        universal_newlines=True,
    )


def rewrite_history(old_email, new_name, new_email, root=None, log=print):
    """全历史改写提交元数据为 noreply（四步：改写 → 清 refs/original → 清 reflog → gc）。

    要求工作树干净（``filter-branch`` 在有未提交改动时会拒绝执行）。
    """
    root = root or ROOT

    dirty = _git(["status", "--porcelain"], root).stdout.strip()
    if dirty:
        raise RuntimeError("工作树有未提交改动，先提交再改写（filter-branch 会拒绝执行）")

    present = _git(["log", "--all", "--format=%ae\x1f%ce"], root).stdout
    if old_email.lower() not in present.lower():
        log("历史中已无 %s，无需改写" % old_email)
        return False

    env_filter = "; ".join([
        'if [ "$GIT_AUTHOR_EMAIL" = "%s" ]' % old_email,
        'then GIT_AUTHOR_EMAIL="%s" GIT_AUTHOR_NAME="%s" export GIT_AUTHOR_EMAIL GIT_AUTHOR_NAME' % (new_email, new_name),
        'elif [ "$GIT_COMMITTER_EMAIL" = "%s" ]' % old_email,
        'then GIT_COMMITTER_EMAIL="%s" GIT_COMMITTER_NAME="%s" export GIT_COMMITTER_EMAIL GIT_COMMITTER_NAME' % (new_email, new_name),
        "fi",
    ])
    log("改写全历史提交元数据：%s → %s" % (old_email, new_email))
    _git(["filter-branch", "--force", "--env-filter", env_filter,
          "--tag-name-filter", "cat", "--", "--all"], root)

    # 四步之二：清 refs/original（否则旧对象仍被引用，gc 不会回收）
    original_refs = _git(["for-each-ref", "--format=%(refname)", "refs/original/"],
                         root).stdout.split()
    for ref in original_refs:
        _git(["update-ref", "-d", ref], root)
    log("已清 refs/original：%d 个" % len(original_refs))

    # 四步之三：清 reflog（否则旧提交仍可从 reflog 取回）
    _git(["reflog", "expire", "--expire=now", "--all"], root)
    log("已清 reflog")

    # 四步之四：gc（回收不可达对象）
    _git(["gc", "--prune=now", "--quiet"], root)
    log("已完成 gc")

    return True


def verify_history(deny_email=None, root=None, allowed_noreply=()):
    """改写后验证：断言全部提交身份为 noreply；deny_email 在 ae/ce 两字段均不存在。"""
    root = root or ROOT
    entries = iter_commit_identities(root)
    violations = check_commit_identities(entries, allowed_noreply)
    missing = []
    if deny_email:
        for sha, author_email, committer_email in entries:
            for field, addr in (("ae", author_email), ("ce", committer_email)):
                if deny_email.lower() in (addr or "").lower():
                    missing.append((sha, field, addr))
    return entries, violations, missing


# --------------------------------------------------------------------------
# 附件台账 / 打包
# --------------------------------------------------------------------------

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attachment_ledger(dist_dir=None, root=None):
    """dist 内每个 exe 目录 → ASCII 附件名 + sha256 + 字节数。"""
    root = root or ROOT
    dist_dir = dist_dir or os.path.join(root, "dist")
    rows = []
    if not os.path.isdir(dist_dir):
        return rows
    for name in sorted(os.listdir(dist_dir)):
        sub = os.path.join(dist_dir, name)
        if not os.path.isdir(sub):
            continue
        exe = os.path.join(sub, "%s.exe" % name)
        if not os.path.isfile(exe):
            continue
        total = 0
        for dirpath, _dirnames, filenames in os.walk(sub):
            for fname in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fname))
                except OSError:
                    pass
        rows.append({
            "name": name,
            "attachment": "%s-windows-x64.zip" % name,
            "exe": "%s.exe" % name,
            "sha256": sha256_file(exe),
            "bytes": total,
        })
    return rows


#: 固定 zip 时间戳（1980-01-01 00:00:00，ZIP 纪元下限）→ 归档可复跑
_ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)


def pack_dist_archives(dist_dir=None, root=None, log=print):
    """把 dist 下每个 exe 目录打成 ASCII 名 zip（固定时间戳，可复跑）。"""
    root = root or ROOT
    dist_dir = dist_dir or os.path.join(root, "dist")
    made = []
    for name in sorted(os.listdir(dist_dir)):
        sub = os.path.join(dist_dir, name)
        if not os.path.isdir(sub):
            continue
        if not os.path.isfile(os.path.join(sub, "%s.exe" % name)):
            continue
        archive = os.path.join(dist_dir, "%s-windows-x64.zip" % name)
        entries = []
        for dirpath, dirnames, filenames in os.walk(sub):
            dirnames[:] = sorted(dirnames)
            for fname in sorted(filenames):
                full = os.path.join(dirpath, fname)
                arc = os.path.relpath(full, sub).replace("\\", "/")
                entries.append((arc, full))
        entries.sort(key=lambda item: item[0])
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            for arc, full in entries:
                info = zipfile.ZipInfo(arc, date_time=_ZIP_DATE_TIME)
                info.external_attr = 0o644 << 16
                with open(full, "rb") as fh:
                    zf.writestr(info, fh.read())
        made.append((archive, sha256_file(archive)))
        log("已打包 %s（sha256=%s）" % (os.path.basename(archive), made[-1][1]))
    return made


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------

def _cmd_audit(args):
    # 个人邮箱与开发机路径都**从本机环境派生**，不写进入仓脚本：
    # 入仓脚本里出现真实邮箱本身就是一种泄露。
    deny = list(args.deny_email or [])
    local_email = _git(["config", "user.email"], args.root, check=False).stdout.strip()
    if local_email and local_email not in deny:
        deny.append(local_email)
    deny_paths = list(args.deny_path or []) or default_dev_markers(args.root)
    problems = 0

    entries = iter_commit_identities(args.root)
    violations = check_commit_identities(entries, args.allow_noreply or ())
    print("提交元数据审计：%d 条提交" % len(entries))
    if violations:
        problems += len(violations)
        for sha, field, addr in violations:
            print("  ✗ %s %s = %s（非 noreply）" % (sha[:12], field, addr))
    else:
        print("  ✓ 全部提交身份为 GitHub noreply")

    tree_hits = scan_working_tree(args.root, deny)
    print("工作树审计：受版本控制的文本文件")
    if tree_hits:
        problems += len(tree_hits)
        for rel, kind, value in tree_hits:
            print("  ✗ %s [%s] %s" % (rel, kind, value))
    else:
        print("  ✓ 无个人邮箱 / 开发机绝对路径泄露")

    build_hits = []
    for build_dir in (args.build_dir or []):
        for rel, kind, value in scan_build_dir(build_dir, deny, deny_paths):
            build_hits.append((build_dir, rel, kind, value))
    print("构建产物审计：%s" % ("、".join(args.build_dir) if args.build_dir else "（未指定）"))
    if build_hits:
        problems += len(build_hits)
        for build_dir, rel, kind, value in build_hits:
            print("  ✗ %s/%s [%s] %s" % (build_dir, rel, kind, value))
    else:
        print("  ✓ 无泄露" if args.build_dir else "  – 跳过")

    truth_problems = check_packaged_truth_is_synthetic(args.root)
    print("随包真值档案合成标记：")
    if truth_problems:
        problems += len(truth_problems)
        for name, kind, value in truth_problems:
            print("  ✗ %s [%s] %s" % (name, kind, value))
    else:
        print("  ✓ 全部档案声明 synthetic: true")

    if problems:
        print("脱敏审计未通过：%d 项" % problems)
        return 1
    print("脱敏审计通过（%s）" % OK_MARKER)
    return 0


def _cmd_rewrite(args):
    old_email = args.old_email
    if not old_email:
        old_email = _git(["config", "user.email"], args.root, check=False).stdout.strip()
    try:
        changed = rewrite_history(old_email, args.new_name, args.new_email, args.root)
    except RuntimeError as exc:
        print("改写失败：%s" % exc)
        return 2
    entries, violations, _missing = verify_history(None, args.root, args.allow_noreply or ())
    if violations:
        print("改写后仍有非 noreply 提交身份：")
        for sha, field, addr in violations:
            print("  ✗ %s %s = %s" % (sha[:12], field, addr))
        return 1
    print("改写完成（%s）：%d 条提交全部为 noreply" % ("有变更" if changed else "无变更", len(entries)))
    return 0


def _cmd_verify(args):
    entries, violations, missing = verify_history(
        args.deny_email, args.root, args.allow_noreply or ())
    ok = True
    print("提交身份：%d 条" % len(entries))
    if violations:
        ok = False
        for sha, field, addr in violations:
            print("  ✗ %s %s = %s（非 noreply）" % (sha[:12], field, addr))
    else:
        print("  ✓ 全部为 noreply")
    if args.deny_email:
        if missing:
            ok = False
            for sha, field, addr in missing:
                print("  ✗ %s %s 仍含 %s" % (sha[:12], field, args.deny_email))
        else:
            print("  ✓ ae 与 ce 两字段均不含 %s" % args.deny_email)
    if not ok:
        return 1
    print("脱敏验证通过（%s）" % OK_MARKER)
    return 0


def _cmd_ledger(args):
    rows = attachment_ledger(args.dist_dir, args.root)
    if not rows:
        print("dist 内无已构建 exe（先跑 PyInstaller）")
        return 2
    for row in rows:
        print("%s  sha256=%s  bytes=%d" % (row["attachment"], row["sha256"], row["bytes"]))
    return 0


def _cmd_pack(args):
    made = pack_dist_archives(args.dist_dir, args.root)
    if not made:
        print("dist 内无已构建 exe（先跑 PyInstaller）")
        return 2
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="发布脱敏审计与全历史改写（M6）")
    parser.add_argument("--root", default=ROOT)
    sub = parser.add_subparsers(dest="command")

    p_audit = sub.add_parser("audit", help="只读审计（默认）")
    p_audit.add_argument("--build-dir", action="append", default=None,
                         help="构建产物目录（可多次指定，如 dist/ghg-cli）")
    p_audit.add_argument("--deny-email", action="append", default=None,
                         help="额外必须不存在的邮箱字面值（不入仓，由调用方传入）")
    p_audit.add_argument("--deny-path", action="append", default=None,
                         help="开发机路径标记（如用户名）；第三方运行时命中它才算泄露")
    p_audit.add_argument("--allow-noreply", action="append", default=None,
                         help="额外放行的提交地址（如官方机器账号）")
    p_audit.set_defaults(func=_cmd_audit)

    p_rewrite = sub.add_parser("rewrite", help="全历史改写为 noreply（破坏性）")
    p_rewrite.add_argument("--old-email", default=None,
                           help="被改写的旧地址（缺省取 git config user.email）")
    p_rewrite.add_argument("--new-email", required=True)
    p_rewrite.add_argument("--new-name", default=None)
    p_rewrite.add_argument("--allow-noreply", action="append", default=None)
    p_rewrite.set_defaults(func=_cmd_rewrite)

    p_verify = sub.add_parser("verify", help="改写后验证")
    p_verify.add_argument("--deny-email", default=None)
    p_verify.add_argument("--allow-noreply", action="append", default=None)
    p_verify.set_defaults(func=_cmd_verify)

    p_ledger = sub.add_parser("ledger", help="dist 附件 sha256 台账")
    p_ledger.add_argument("--dist-dir", default=None)
    p_ledger.set_defaults(func=_cmd_ledger)

    p_pack = sub.add_parser("pack", help="dist → ASCII 名 zip")
    p_pack.add_argument("--dist-dir", default=None)
    p_pack.set_defaults(func=_cmd_pack)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args = parser.parse_args(["audit"])
    if args.command == "rewrite" and not args.new_name:
        args.new_name = args.new_email.split("@", 1)[0].split("+", 1)[-1]
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
