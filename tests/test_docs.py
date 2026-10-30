"""Repository-level smoke tests for the learning assets."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_contract_files_exist() -> None:
    for name in ("README.md", "WEEKLY_MASTER_PLAN.md", "pyproject.toml", ".env.example"):
        assert (ROOT / name).exists(), name


def test_stage_readmes_exist() -> None:
    for directory in sorted(ROOT.glob("stage_*")):
        if directory.is_dir():
            assert (directory / "README.md").exists(), directory.name


def test_sample_dataset_is_small_and_local() -> None:
    sample_dir = ROOT / "stage_02_rag_engineering" / "datasets" / "sample_documents"
    assert len(list(sample_dir.glob("*.txt"))) >= 3
    assert all(path.stat().st_size < 10_000 for path in sample_dir.glob("*.txt"))
