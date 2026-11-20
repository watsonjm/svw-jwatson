"""Hunt Advisor: legal shooting hours and hunting weather for deer hunters.

Two MCP servers, both started locally over stdio:
- deer_camp_mcp/server.py: our custom server (location lookup, legal shooting
  hours, conditions rating).
- Google MCP Toolbox with nws_toolbox/tools.yaml: National Weather Service
  forecast tools.
"""

import os
import shlex
import sys
from datetime import date
from pathlib import Path

from google.adk import Agent
from google.adk.models import FallbackModel, Gemini
from google.adk.tools import AgentTool
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

CHALLENGE_DIR = Path(__file__).resolve().parents[1]

# Use 3.8 Flash, and fall back to 3.5 Flash right away when it is overloaded
# (429/5xx). Both are pinned to the global endpoint, the only one serving 3.8 Flash.
MODEL = FallbackModel(
    models=[
        Gemini(
            model=os.getenv("MODEL", "gemini-3.8-flash"),
            client_kwargs={"location": "global"},
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
        Gemini(
            model=os.getenv("FALLBACK_MODEL", "gemini-3.5-flash"),
            client_kwargs={"location": "global"},
        ),
    ]
)
LOW_THINKING = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_level="low")
)


def stdio_server(command: list[str]) -> McpToolset:
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(command=command[0], args=command[1:]),
            timeout=30,
        )
    )


deer_camp_tools = stdio_server(
    [sys.executable, str(CHALLENGE_DIR / "deer_camp_mcp" / "server.py")]
)
nws_tools = stdio_server(
    shlex.split(os.getenv("TOOLBOX_COMMAND", "toolbox"))
    + ["--config", str(CHALLENGE_DIR / "nws_toolbox" / "tools.yaml"), "--stdio"]
)

deer_camp_agent = Agent(
    name="deer_camp_agent",
    model=MODEL,
    description=(
        "Finds a place's coordinates and time zone, calculates legal shooting "
        "hours, and rates hunting conditions."
    ),
    instruction="""
Use your tools to answer: find_location for coordinates and time zone,
legal_shooting_hours for sunrise, sunset, and legal shooting times, and
rate_hunting_conditions to rate weather the caller gives you. Report the tool
results plainly, including coordinates and time zone when you looked them up.
""",
    tools=[deer_camp_tools],
    generate_content_config=LOW_THINKING,
)

weather_agent = Agent(
    name="weather_agent",
    model=MODEL,
    description="Gets National Weather Service forecasts (wind, temperature, rain) for coordinates.",
    instruction="""
Get the forecast for the coordinates you are given. First call nws_point_lookup,
then nws_hourly_forecast (for specific hours) or nws_daily_forecast (for a
day overview) with its gridId, gridX, and gridY. Report temperature, wind
direction, wind speed, and chance of rain for the times asked about, plus the
temperature change from the previous day at the same time if asked.
""",
    tools=[nws_tools],
    generate_content_config=LOW_THINKING,
)


def root_instruction(_context) -> str:
    return f"""
You are Hunt Advisor, helping deer hunters plan a hunt. Today is
{date.today():%A, %B %d, %Y}.

1. If you don't have coordinates for the place, ask deer_camp_agent to find it.
2. For when it's legal to shoot, ask deer_camp_agent for legal shooting hours
   with the coordinates, date, and time zone.
3. For weather and which way the wind will blow, ask weather_agent with the
   coordinates and the times you care about (legal light at dawn and dusk if
   the user doesn't say).
4. To judge whether it's a good day to hunt, get the weather first, then ask
   deer_camp_agent to rate it with the wind speed, rain chance, and temperature
   change.

Answer with the times, wind direction at dawn and dusk, the rating, and a short
recommendation. Leave stand choice to the hunter, and remind them to confirm
shooting hours in their state's regulations.
"""


root_agent = Agent(
    name="hunt_advisor",
    model=MODEL,
    instruction=root_instruction,
    tools=[AgentTool(agent=deer_camp_agent), AgentTool(agent=weather_agent)],
    generate_content_config=LOW_THINKING,
)
