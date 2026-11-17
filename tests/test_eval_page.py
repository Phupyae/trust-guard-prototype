"""Offline tests for the Evaluation page and the results loader it uses. Run: pytest -q"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.eval_results import default_run, list_runs, ratio  # noqa: E402


def _write_run(base: Path, name: str, kind: str, started: str) -> None:
    folder = base / name
    folder.mkdir()
    (folder / "metrics.json").write_text(json.dumps({
        "run_info": {"kind": kind, "started": started},
        "answers": {"answers_total": 3}, "claims": {}}), encoding="utf-8")


def test_ratio_formats_and_handles_unmeasured():
    assert ratio({"value": 0.667, "num": 8, "den": 12}) == ("67%", "8 of 12")
    assert ratio({"value": None, "num": 0, "den": 0}) == ("n/a", "not measured yet")
    assert ratio(None) == ("n/a", "not measured yet")


def test_list_runs_skips_unscored_and_prefers_live(tmp_path):
    _write_run(tmp_path, "20261116_210411_controlled", "controlled", "20261116_210411")
    _write_run(tmp_path, "20261115_100000_live", "live", "20261115_100000")
    (tmp_path / "20261117_090000_live").mkdir()  # never scored: no metrics.json
    runs = list_runs(tmp_path)
    assert [r.folder for r in runs] == ["20261116_210411_controlled", "20261115_100000_live"]
    assert default_run(runs).kind == "live"  # live is the main evidence, even if older
    assert default_run([]) is None


def test_repository_results_load():
    runs = list_runs()
    assert runs, "eval/results/ should contain at least one scored run"
    assert "system_b_unflagged_wrong" in runs[0].metrics["answers"]


def test_evaluation_page_renders_without_errors():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "pages" / "reliability.py"), default_timeout=60).run()
    assert not at.exception
    assert at.selectbox, "the run selector should be shown when results exist"
