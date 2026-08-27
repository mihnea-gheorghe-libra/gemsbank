import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.config import settings

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_help_html() -> Path | None:
    candidates = [
        Path(settings.web_dir) / "help.html",
        _REPO_ROOT / "frontend" / "help.html",
        Path("frontend/help.html"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


_SPAN = r'<span class="lang-en">(.*?)</span>\s*<span class="lang-ro">(.*?)</span>'
_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"\w+", re.UNICODE)

_FAQ_PATTERN = re.compile(
    r"<details>\s*<summary>\s*" + _SPAN + r"\s*</summary>\s*<p>\s*" + _SPAN + r"\s*</p>\s*</details>",
    re.DOTALL,
)
_GUIDE_PATTERN = re.compile(
    r'<div class="plate help-card">\s*<h3>' + _SPAN + r"</h3>\s*<p>\s*" + _SPAN + r"\s*</p>",
    re.DOTALL,
)


def _clean(text: str) -> str:
    return _TAG.sub("", text).strip()


@dataclass(slots=True, frozen=True)
class SupportDoc:
    id: str
    label_en: str
    label_ro: str
    body_en: str
    body_ro: str


@lru_cache(maxsize=1)
def load_support_docs() -> list[SupportDoc]:
    help_path = _find_help_html()
    if not help_path:
        return []
    html = help_path.read_text(encoding="utf-8")
    docs: list[SupportDoc] = []

    for index, match in enumerate(_FAQ_PATTERN.finditer(html)):
        q_en, q_ro, a_en, a_ro = (_clean(group) for group in match.groups())
        docs.append(
            SupportDoc(id=f"faq.{index}", label_en=q_en, label_ro=q_ro, body_en=a_en, body_ro=a_ro)
        )

    for index, match in enumerate(_GUIDE_PATTERN.finditer(html)):
        t_en, t_ro, b_en, b_ro = (_clean(group) for group in match.groups())
        docs.append(
            SupportDoc(id=f"guide.{index}", label_en=t_en, label_ro=t_ro, body_en=b_en, body_ro=b_ro)
        )

    return docs


def _score(doc: SupportDoc, terms: set[str]) -> int:
    haystack = f"{doc.label_en} {doc.label_ro} {doc.body_en} {doc.body_ro}".lower()
    words = set(_WORD.findall(haystack))
    return len(terms & words)


def search_support_docs(query: str, limit: int = 4) -> list[SupportDoc]:
    docs = load_support_docs()
    terms = {word for word in _WORD.findall(query.lower()) if len(word) > 2}
    ranked = sorted(docs, key=lambda doc: _score(doc, terms), reverse=True)
    matched = [doc for doc in ranked if _score(doc, terms) > 0]
    return (matched or docs)[:limit]
