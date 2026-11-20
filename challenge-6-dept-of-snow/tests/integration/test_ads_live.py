"""Integration tests against the real datastores and Google Maps MCP.

Needs Google Cloud credentials, the two datastores from create_datastores.sh, and
GOOGLE_MAPS_API_KEY in .env. No model calls: these test the agents' data sources.
"""

import asyncio

import pytest
from ads_operations.agent import maps_tools, search_ads_policies, search_backend_status

pytestmark = pytest.mark.integration


def test_backend_search_returns_the_closed_road():
    result = search_backend_status("Turnagain Pass status")
    assert "R-301" in result
    assert "avalanche debris" in result


def test_backend_search_returns_the_plow_fleet():
    assert "P-04" in search_backend_status("which plows are available")


def test_policy_search_returns_the_reopening_rule():
    result = search_ads_policies("who can reopen a closed road")
    assert "Regional Duty Supervisor" in result


def test_maps_mcp_computes_a_route():
    async def route():
        toolset = maps_tools("compute_routes")
        (tool,) = await toolset.get_tools()
        result = await tool.run_async(
            args={
                "origin": {"address": "Anchorage, AK"},
                "destination": {"address": "Wasilla, AK"},
            },
            tool_context=None,
        )
        await toolset.close()
        return str(result)

    assert "distanceMeters" in asyncio.run(route())
