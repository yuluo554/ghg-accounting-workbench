"""CI workflow 守门测试。

两类历史教训的守门：
  1. **非法 YAML 静默失效**——step 名含"冒号+空格"等会让整份 workflow 非法，
     GitHub 端不建任何 job，而 `state` 仍显示 active、文件字节也洁净；只有真解析才暴露；
  2. **浅克隆静默空验**——`actions/checkout` 默认 `fetch-depth: 1`，依赖 git 历史的
     守门测试在 CI 里只看到 1 个提交、静默削弱成空验。故断言每个 checkout step `fetch-depth: 0`。
"""

import os

import pytest

yaml = pytest.importorskip("yaml", reason="需要 PyYAML（dev extra）")

WORKFLOWS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".github", "workflows",
)


def _workflow_files():
    if not os.path.isdir(WORKFLOWS_DIR):
        return []
    return sorted(f for f in os.listdir(WORKFLOWS_DIR)
                  if f.endswith((".yml", ".yaml")))


def test_workflows_dir_has_files():
    files = _workflow_files()
    assert files, "未找到任何 CI workflow 文件"


def test_all_workflows_are_valid_yaml():
    for name in _workflow_files():
        path = os.path.join(WORKFLOWS_DIR, name)
        with open(path, "r", encoding="utf-8") as fh:
            try:
                doc = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                pytest.fail("workflow %s 不是合法 YAML（GitHub 将不建任何 job）：%s" % (name, exc))
        assert isinstance(doc, dict), "workflow %s 顶层必须是映射" % name


def test_workflows_have_jobs_with_runs_on_and_steps():
    for name in _workflow_files():
        doc = yaml.safe_load(open(os.path.join(WORKFLOWS_DIR, name), encoding="utf-8"))
        jobs = doc.get("jobs") or {}
        assert jobs, "workflow %s 未定义任何 job" % name
        for job_id, job in jobs.items():
            assert "runs-on" in job, "workflow %s job %s 缺 runs-on" % (name, job_id)
            assert job.get("steps"), "workflow %s job %s 缺 steps" % (name, job_id)


def test_checkout_uses_full_history():
    """依赖 git 历史的守门测试需要全量历史（浅克隆会静默空验）。"""
    for name in _workflow_files():
        doc = yaml.safe_load(open(os.path.join(WORKFLOWS_DIR, name), encoding="utf-8"))
        for job_id, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                uses = str(step.get("uses", ""))
                if "actions/checkout" in uses:
                    depth = (step.get("with") or {}).get("fetch-depth")
                    assert depth == 0, (
                        "workflow %s job %s 的 checkout 未设 fetch-depth: 0"
                        "（历史扫描类守门测试会被静默削弱）" % (name, job_id)
                    )


def _ci_doc():
    """只取 test 矩阵所在的 workflow（当前仅 ci.yml）。"""
    docs = {}
    for name in _workflow_files():
        docs[name] = yaml.safe_load(open(os.path.join(WORKFLOWS_DIR, name), encoding="utf-8"))
    return docs


def test_ci_covers_python_matrix():
    """CI 的 test 矩阵覆盖 py3.12（v0.1.1 起的唯一受支持下限）。

    规格变更（2026-10-19，D-3 A）：原断言要求 CI 含 "3.8"，因为 3.8 是项目下限。
    Python 3.8 已于 2024-10-07 EOL，`requires-python` 抬到 >=3.12，CI 矩阵随之
    去 3.8。本断言改为**正向**锁新口径：test 矩阵必须含 windows 与 ubuntu 的
    3.12 组合，且**不得**再出现 3.8（防止悄悄退回 EOL 解释器）。
    `fetch-depth: 0` 断言（test_checkout_uses_full_history）保持不变。
    """
    versions = set()
    for _name, doc in _ci_doc().items():
        for job in (doc.get("jobs") or {}).values():
            for entry in ((job.get("strategy") or {}).get("matrix") or {}).get("include") or []:
                if "python-version" in entry:
                    versions.add(str(entry["python-version"]))
    assert "3.12" in versions, "CI test 矩阵未覆盖 Python 3.12（项目下限）"
    assert "3.8" not in versions, "CI 仍覆盖已 EOL 的 Python 3.8"


def test_ci_has_package_job_building_both_specs():
    """接线守门：CI 必须有 package job 真构建两个 spec + 双 exe --selftest。

    v0.1.1 新增（D7-2）：此前 spec 构建只在本地/发版时跑，发布物可复现性没有
    常驻门禁。这里断言"存在带这四件事的 job"，而不是只看 yml 里出现过字符串，
    避免把命令塞进注释或无关 step 也能骗过门禁。
    """
    found = None
    for _name, doc in _ci_doc().items():
        for job_id, job in (doc.get("jobs") or {}).items():
            script = "\n".join(str(step.get("run", "")) for step in (job.get("steps") or []))
            if "PyInstaller" not in script:
                continue
            checks = {
                "CLI spec": "ghg_cli.spec" in script,
                "GUI spec": "ghg_gui.spec" in script,
                "CLI selftest": "ghg-cli.exe --selftest" in script,
                "GUI selftest": "ghg-gui.exe --selftest" in script,
            }
            if all(checks.values()):
                found = job_id
                break
        if found:
            break
    assert found, "CI 缺少构建两个 spec 并跑双 exe --selftest 的 package job"


def test_workflow_actions_are_modern():
    """actions 版本不得退回已收 Node20 弃用警告的旧版（v0.1.1 升 v7）。"""
    for name in _workflow_files():
        doc = yaml.safe_load(open(os.path.join(WORKFLOWS_DIR, name), encoding="utf-8"))
        for job_id, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                uses = str(step.get("uses", ""))
                if uses.startswith("actions/checkout@"):
                    assert uses.endswith("@v7"), \
                        "workflow %s job %s 的 checkout 应为 v7：%s" % (name, job_id, uses)
                if uses.startswith("actions/setup-python@"):
                    assert uses.endswith("@v7"), \
                        "workflow %s job %s 的 setup-python 应为 v7：%s" % (name, job_id, uses)
