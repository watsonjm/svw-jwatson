"""Unit tests for the evaluation dataset and judge config. No model calls."""

import json
from pathlib import Path

import pytest
import yaml

EVAL_DIR = Path(__file__).parents[1] / "eval"
CASES = json.loads((EVAL_DIR / "datasets" / "basic-dataset.json").read_text())[
    "eval_cases"
]
CONFIG = yaml.safe_load((EVAL_DIR / "eval_config.yaml").read_text())


def test_dataset_case_ids_are_unique():
    ids = [case["eval_case_id"] for case in CASES]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["eval_case_id"])
def test_case_has_prompt_and_reference_text(case):
    assert case["prompt"]["role"] == "user"
    assert case["prompt"]["parts"][0]["text"].strip()
    assert case["reference"]["response"]["parts"][0]["text"].strip()


def test_every_metric_to_run_is_a_defined_judge():
    judges = {metric["name"]: metric for metric in CONFIG["custom_metrics"]}
    assert set(CONFIG["metrics_to_run"]) == {"response_accuracy", "safety"}
    for name in CONFIG["metrics_to_run"]:
        judge = judges[name]
        assert judge["judge_model"].startswith(
            "projects/PROJECT_ID/locations/global/publishers/google/models/"
        )
        for field in ("{prompt}", "{reference}", "{response}"):
            assert field in judge["prompt_template"]


def test_every_metric_has_a_threshold():
    assert set(CONFIG["thresholds"]) == set(CONFIG["metrics_to_run"])
