(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;

  function speak(text) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB";
    window.speechSynthesis.speak(utterance);
  }

  ONB.AgentPanel = function AgentPanel({ stepKey, lede }) {
    const message = t("agent.messages." + stepKey);

    return (
      <aside className="onb-panel" aria-label={t("agent.header")}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <span className="onb-dot" aria-hidden="true" />
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-kicker)",
              letterSpacing: "0.18em",
            }}
          >
            {t("agent.header")}
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <p className="onb-agent-bubble" style={{ margin: 0 }}>
            {message}
          </p>

          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-kicker)",
              letterSpacing: "0.12em",
              opacity: 0.5,
            }}
          >
            {t("agent.suggested")}
          </div>

          <UI.Button
            type="button"
            style={{ justifyContent: "flex-start" }}
            onClick={() => speak(message)}
          >
            {t("agent.whyId")}
          </UI.Button>
          <UI.Button
            type="button"
            style={{ justifyContent: "flex-start" }}
            onClick={() => speak([lede, message].filter(Boolean).join(" "))}
          >
            {t("agent.readAloud")}
          </UI.Button>
        </div>
      </aside>
    );
  };
})();
