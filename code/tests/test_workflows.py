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


def test_ci_covers_python_matrix():
    """CI 应覆盖 py3.8 与 3.12（下限与当前主流）。"""
    text = ""
    for name in _workflow_files():
        text += open(os.path.join(WORKFLOWS_DIR, name), encoding="utf-8").read()
    assert "3.8" in text, "CI 未覆盖 Python 3.8（项目下限）"
    assert "3.12" in text, "CI 未覆盖 Python 3.12"
