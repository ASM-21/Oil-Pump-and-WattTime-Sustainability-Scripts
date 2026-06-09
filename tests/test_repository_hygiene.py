import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def tracked_files():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [ROOT / line for line in result.stdout.splitlines()]


def iter_tracked_text_files():
    for path in tracked_files():
        if path.name == "test_repository_hygiene.py":
            continue
        if path.suffix.lower() in {".py", ".md", ".txt", ".example", ""}:
            yield path


def test_required_handoff_docs_exist():
    required = [
        "README.md",
        "docs/DOCUMENTATION_ROADMAP.md",
        "docs/PROJECT_COMPLETION_CHECKLIST.md",
        "docs/SECURITY_AND_SHARING_CHECKLIST.md",
        "docs/REPRODUCIBILITY.md",
        "docs/DATA_INVENTORY.md",
        "docs/CANONICAL_WORKFLOWS.md",
        "docs/RESEARCH_STORY.md",
        "docs/FIGURE_INDEX.md",
        "docs/FUTURE_WORK.md",
        ".env.example",
        ".gitignore",
        "requirements.txt",
    ]
    missing = [path for path in required if not (ROOT / path).exists()]
    assert not missing


def test_no_tracked_python_caches_or_runtime_logs():
    blocked = []
    for path in tracked_files():
        if path.is_file() and ("__pycache__" in path.parts or path.suffix == ".pyc" or path.name == "agent.log"):
            blocked.append(path.relative_to(ROOT).as_posix())
    assert blocked == []


def test_known_private_credentials_are_not_in_tracked_text_files():
    blocked_literals = [
        "ASM21_purdue",
        "Mango21!",
        "10.165.42.40",
        "5cff7493-7b74-4ea2-945b-8eed0441111e",
    ]
    findings = []
    for path in iter_tracked_text_files():
        text = path.read_text(errors="ignore")
        for literal in blocked_literals:
            if literal in text:
                findings.append(f"{path.relative_to(ROOT)} contains {literal}")
    assert findings == []
