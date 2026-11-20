"""Deer Camp MCP server: legal shooting hours and a simple hunting-conditions rating.

Run by the agent over stdio. To try it alone: `uv run python deer_camp_mcp/server.py`.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import httpx
from astral import Observer
from astral.sun import sun
from mcp.server.mcpserver import MCPServer

server = MCPServer("deer_camp")


@server.tool()
def find_location(place: str) -> list[dict]:
    """Find US places by name and return their coordinates and time zone.

    Args:
        place: A city or town, optionally with a state, e.g. "Waco, TX".
    """
    city, _, state = place.partition(",")
    response = httpx.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city.strip(), "count": 10, "countryCode": "US"},
        timeout=10,
    )
    response.raise_for_status()
    matches = [
        {
            "name": r["name"],
            "state": r.get("admin1", ""),
            "latitude": round(r["latitude"], 4),
            "longitude": round(r["longitude"], 4),
            "timezone": r["timezone"],
        }
        for r in response.json().get("results", [])
    ]
    state = state.strip().lower()
    if state:
        matches = [m for m in matches if state in m["state"].lower()] or matches
    return matches[:3]


@server.tool()
def legal_shooting_hours(
    latitude: float,
    longitude: float,
    day: str,
    timezone: str,
    minutes_before_sunrise: int = 30,
    minutes_after_sunset: int = 30,
) -> dict:
    """Calculate sunrise, sunset, and legal shooting hours for a place and day.

    Most US states allow shooting from 30 minutes before sunrise to 30 minutes
    after sunset; pass different minutes if your state's rule differs.

    Args:
        latitude: Decimal latitude.
        longitude: Decimal longitude.
        day: Date as YYYY-MM-DD.
        timezone: IANA time zone, e.g. "America/Chicago".
        minutes_before_sunrise: Minutes before sunrise that shooting starts.
        minutes_after_sunset: Minutes after sunset that shooting ends.
    """
    times = sun(
        Observer(latitude, longitude),
        date=date.fromisoformat(day),
        tzinfo=ZoneInfo(timezone),
    )
    start = times["sunrise"] - timedelta(minutes=minutes_before_sunrise)
    end = times["sunset"] + timedelta(minutes=minutes_after_sunset)
    return {
        "day": day,
        "sunrise": times["sunrise"].strftime("%I:%M %p"),
        "sunset": times["sunset"].strftime("%I:%M %p"),
        "legal_start": start.strftime("%I:%M %p"),
        "legal_end": end.strftime("%I:%M %p"),
        "rule": f"{minutes_before_sunrise} min before sunrise to {minutes_after_sunset} min after sunset",
        "note": "Check your state's regulations; some states use different rules.",
    }


@server.tool()
def rate_hunting_conditions(
    wind_mph: float,
    rain_chance_percent: int,
    temp_change_f: float,
) -> dict:
    """Rate a hunting window as good, fair, or poor from simple deer-movement rules.

    Args:
        wind_mph: Sustained wind speed in mph.
        rain_chance_percent: Chance of precipitation, 0-100.
        temp_change_f: Temperature change versus the same time yesterday
            (negative means colder).
    """
    rules = [
        (wind_mph <= 10, +1, "light wind keeps deer moving and scent predictable"),
        (wind_mph > 15, -1, "strong wind makes deer hold tight"),
        (rain_chance_percent >= 60, -1, "steady rain limits movement"),
        (temp_change_f <= -10, +1, "a cold front gets deer on their feet"),
        (temp_change_f >= 10, -1, "unusual warmth slows daytime movement"),
    ]
    matched = [(points, reason) for applies, points, reason in rules if applies]
    score = sum(points for points, _ in matched)
    rating = "good" if score >= 1 else "poor" if score <= -1 else "fair"
    return {
        "rating": rating,
        "reasons": [reason for _, reason in matched]
        or ["no strong factors either way"],
    }


if __name__ == "__main__":
    server.run()
