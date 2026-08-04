"""The quality/safety fixture set must remain executable and passing."""

import pytest

from app.evals.agent_quality import load_cases, run_evaluation


def test_agent_evaluation_set_covers_required_categories() -> None:
    categories = {case["category"] for case in load_cases()}
    assert categories == {
        "citations",
        "fallback",
        "grounding",
        "multilingual",
        "prompt_injection",
        "tenant_isolation",
    }


@pytest.mark.asyncio
async def test_agent_quality_evaluation_passes() -> None:
    report = await run_evaluation()
    assert report.failed == 0, report.as_json()
    assert report.passed == report.total == 6

