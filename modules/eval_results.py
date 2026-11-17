"""Reads the evaluation results written by eval/compute_metrics.py, for the Evaluation page.

Kept apart from the page so it can be tested offline, and so the page only formats what
compute_metrics.py already calculated (the app never recomputes or rounds differently).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import config

RESULTS_DIR = config.ROOT / "eval" / "results"

# Plain-language names for the scenario ids used in questions.json / controlled_cases.json.
SCENARIO_NAMES = {
    "approval": "Wrong approver or limit",
    "correct": "Correct answer (control)",
    "missing_evidence": "No policy covers it",
    "missing_step": "Required step left out",
    "outdated": "Outdated policy version",
}


@dataclass
class EvalRun:
    folder: str               # e.g. 20261116_210411_controlled
    path: Path
    kind: str                 # "controlled", "live" or "merged"
    started: str              # timestamp from run_info, e.g. 20261116_210411
    metrics: dict
    failures_md: str = ""
    run_info: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        s = self.started
        when = f"{s[6:8]}/{s[4:6]}/{s[:4]} {s[9:11]}:{s[11:13]}" if len(s) >= 13 and s[:8].isdigit() else s
        return f"{self.kind.capitalize()} run · {when} · {self.metrics.get('answers', {}).get('answers_total', 0)} answers"


def list_runs(results_dir: Path = RESULTS_DIR) -> list[EvalRun]:
    """Every results folder that has a metrics.json, newest first. Folders without one
    (a run that was never scored) are skipped rather than shown half-empty."""
    runs = []
    if not results_dir.is_dir():
        return runs
    for folder in results_dir.iterdir():
        metrics_file = folder / "metrics.json"
        if not metrics_file.is_file():
            continue
        try:
            metrics = json.loads(metrics_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        info = metrics.get("run_info", {})
        failures = folder / "failures.md"
        runs.append(EvalRun(
            folder=folder.name, path=folder,
            kind=info.get("kind") or ("controlled" if "controlled" in folder.name else "live"),
            started=info.get("started") or folder.name.split("_controlled")[0],
            metrics=metrics, run_info=info,
            failures_md=failures.read_text(encoding="utf-8") if failures.is_file() else ""))
    return sorted(runs, key=lambda r: r.started, reverse=True)


def default_run(runs: list[EvalRun]) -> EvalRun | None:
    """Live results are the main evidence, so prefer the newest live (or merged live) run;
    fall back to the newest controlled run."""
    for r in runs:
        if r.kind != "controlled":
            return r
    return runs[0] if runs else None


def ratio(metric: dict | None) -> tuple[str, str]:
    """{'value': 0.667, 'num': 8, 'den': 12} -> ('67%', '8 of 12'). Unmeasured -> ('n/a', reason)."""
    if not metric or metric.get("value") is None or not metric.get("den"):
        return "n/a", "not measured yet"
    return f"{round(metric['value'] * 100)}%", f"{metric['num']} of {metric['den']}"


def seconds(value) -> str:
    return "n/a" if value is None else f"{value:.1f} s"
