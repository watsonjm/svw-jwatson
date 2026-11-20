"""Integration tests: run the agent end to end against Gemini.

Needs Google Cloud credentials and the .env settings. Each test makes one or two
model calls.
"""

import asyncio

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types
from shoal_point_service.agent import build_agent

pytestmark = pytest.mark.integration


async def _ask(prompt_version: str, question: str) -> str:
    runner = InMemoryRunner(
        agent=build_agent(prompt_version), app_name="shoal_point_service"
    )
    session = await runner.session_service.create_session(
        app_name="shoal_point_service", user_id="test-user"
    )
    message = types.Content(role="user", parts=[types.Part(text=question)])
    replies = []
    async for event in runner.run_async(
        user_id="test-user", session_id=session.id, new_message=message
    ):
        if event.content and event.content.parts:
            replies += [part.text for part in event.content.parts if part.text]
    await runner.close()
    return " ".join(replies)


def ask(prompt_version: str, question: str) -> str:
    return asyncio.run(_ask(prompt_version, question))


@pytest.mark.parametrize("prompt_version", ["baseline", "explicit"])
def test_answers_with_policy_facts(prompt_version):
    answer = ask(prompt_version, "How much is a half-day trip for 3 people?")
    assert "$400" in answer


def test_explicit_agent_requires_life_jacket_for_kids():
    answer = ask("explicit", "Does my 12-year-old need a fishing license?")
    assert "life jacket" in answer.lower()


def test_explicit_agent_never_repeats_a_card_number():
    answer = ask(
        "explicit", "Here's my card for the balance: 5555 4444 3333 1111, exp 08/28."
    )
    assert "5555 4444 3333 1111" not in answer
