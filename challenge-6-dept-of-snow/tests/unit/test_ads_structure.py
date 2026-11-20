"""Unit tests for the agent wiring and eval files. No model calls."""

import json
from pathlib import Path

import pytest
import yaml
from ads_operations.agent import (
    field_dispatch_agent,
    public_comms_agent,
    road_status_agent,
    root_agent,
)
from google.adk.tools.mcp_tool import McpToolset

CHALLENGE_DIR = Path(__file__).parents[2]
EVAL_DIR = CHALLENGE_DIR / "tests" / "eval"
CASES = json.loads((EVAL_DIR / "datasets" / "basic-dataset.json").read_text())[
    "eval_cases"
]
CONFIG = yaml.safe_load((EVAL_DIR / "eval_config.yaml").read_text())


def tool_names(agent):
    return {
        getattr(tool, "name", None) or getattr(tool, "__name__", "")
        for tool in agent.tools
    }


def test_root_routes_to_three_specialists_policy_and_search():
    assert tool_names(root_agent) == {
        "field_dispatch_agent",
        "road_status_agent",
        "public_comms_agent",
        "search_ads_policies",
        "search_agent",
    }


@pytest.mark.parametrize(
    "specialist", [field_dispatch_agent, road_status_agent, public_comms_agent]
)
def test_each_specialist_is_grounded_in_backend_data_and_policy(specialist):
    assert {"search_backend_status", "search_ads_policies"} <= tool_names(specialist)


@pytest.mark.parametrize("specialist", [field_dispatch_agent, road_status_agent])
def test_dispatch_and_road_agents_use_maps_mcp(specialist):
    assert any(isinstance(tool, McpToolset) for tool in specialist.tools)


@pytest.mark.parametrize(
    "folder", ["policies", "backend"], ids=["policy-docs", "backend-docs"]
)
def test_datastore_documents_exist(folder):
    assert list((CHALLENGE_DIR / "ads_data" / folder).glob("*.txt"))


def test_eval_cases_are_unique_and_have_references():
    ids = [case["eval_case_id"] for case in CASES]
    assert len(set(ids)) == len(ids)
    for case in CASES:
        assert case["prompt"]["parts"][0]["text"].strip()
        assert case["reference"]["response"]["parts"][0]["text"].strip()


def test_every_metric_is_a_defined_judge_with_a_threshold():
    judges = {metric["name"]: metric for metric in CONFIG["custom_metrics"]}
    for name in CONFIG["metrics_to_run"]:
        assert judges[name]["judge_model"].startswith("projects/PROJECT_ID/")
        assert name in CONFIG["thresholds"]
