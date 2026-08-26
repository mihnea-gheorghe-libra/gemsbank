from backend.capabilities import service as capabilities_service
from backend.helpers.context import Actor


class _StubAuthService:
    def __init__(self, prefs: dict[str, str]) -> None:
        self._prefs = prefs

    async def get_me(self, user_id: str) -> dict[str, object]:
        return {"prefs": self._prefs}


async def test_preferences_resolver_reads_lang_and_theme_from_the_users_prefs(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities_service,
        "get_auth_service",
        lambda: _StubAuthService({"lang": "en", "theme": "dark"}),
    )
    actor = Actor(kind="agent", id="support-agent", on_behalf_of="user-1")

    output = await capabilities_service._resolve_preferences(
        actor, capabilities_service.PreferencesInput()
    )

    assert output.lang == "en"
    assert output.theme == "dark"


async def test_preferences_resolver_falls_back_to_defaults_when_prefs_are_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities_service, "get_auth_service", lambda: _StubAuthService({})
    )
    actor = Actor(kind="agent", id="support-agent", on_behalf_of="user-1")

    output = await capabilities_service._resolve_preferences(
        actor, capabilities_service.PreferencesInput()
    )

    assert output.lang == "ro"
    assert output.theme == "light"
