import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCREENS = ROOT / "frontend" / "components" / "dashboard-screens.jsx"
ROUTES = ROOT / "backend" / "server" / "routes.py"


def _joined_literals(fragment: str) -> str:
    return "".join(fragment.split('"')[1::2])


def _recommendation_prompts() -> tuple[str, str]:
    source = SCREENS.read_text(encoding="utf-8")
    start = source.index("const prompt =", source.index("function RecommendationsCard"))
    block = source[start : source.index(".askAnalytics(prompt)", start)]
    romanian, english = block.split("\n          : ")
    romanian = romanian.split("\n          ? ")[1]
    return _joined_literals(romanian), _joined_literals(english)


def _ask_agent_question_limit() -> int:
    source = ROUTES.read_text(encoding="utf-8")
    start = source.index("class AskAgentRequest")
    declaration = source[start : source.index("class ", start + 1)]
    match = re.search(r"question: str = Field\([^)]*max_length=(\d+)", declaration)
    assert match is not None
    return int(match.group(1))


@pytest.mark.parametrize("index", [0, 1])
def test_the_recommendations_card_prompt_fits_what_the_analytics_endpoint_accepts(
    index: int,
) -> None:
    prompt = _recommendation_prompts()[index]

    assert prompt.strip()
    assert len(prompt) <= _ask_agent_question_limit()
