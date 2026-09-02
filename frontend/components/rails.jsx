(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;

  ONB.STEPS = [
    { key: "document", num: "01" },
    { key: "contact", num: "02" },
    { key: "code", num: "03" },
    { key: "credentials", num: "04" },
  ];



  ONB.StepRail = function StepRail({ current }) {
    return (
      <nav className="onb-rail" aria-label={t("screenTag")}>
        <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {ONB.STEPS.map((step, index) => {
            const position = index + 1;
            const state =
              position < current
                ? t("state.done")
                : position === current
                  ? t("state.inProgress")
                  : t("state.pending");
            return (
              <li
                key={step.key}
                className="onb-rail-item"
                data-state={state}
                aria-current={position === current ? "step" : undefined}
              >
                <span className="onb-rail-num" aria-hidden="true">
                  {step.num}
                </span>
                <span>
                  <span className="onb-rail-title">{t("rail." + step.key)}</span>
                  <span className="onb-rail-state" style={{ display: "block" }}>
                    {state}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      </nav>
    );
  };

  ONB.AgentPanel = function AgentPanel({ stepKey, lede }) {
    const message = t("agent.messages." + stepKey);
    const [isSpeaking, setIsSpeaking] = React.useState(false);
    const audioPlayerRef = React.useRef(null);
    const abortControllerRef = React.useRef(null);

    // Stop speaking when unmounted
    React.useEffect(() => {
      return () => {
        if (audioPlayerRef.current) {
          audioPlayerRef.current.pause();
          audioPlayerRef.current.currentTime = 0;
          audioPlayerRef.current = null;
        }
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
        }
        if (window.speechSynthesis) {
          window.speechSynthesis.cancel();
        }
      };
    }, []);

    const handleSpeak = async (text) => {
      if (isSpeaking) {
        if (audioPlayerRef.current) audioPlayerRef.current.pause();
        if (abortControllerRef.current) abortControllerRef.current.abort();
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        setIsSpeaking(false);
      } else {
        setIsSpeaking(true);
        const controller = new AbortController();
        abortControllerRef.current = controller;
        
        const fallbackSpeak = () => {
          if (!window.speechSynthesis || controller.signal.aborted) {
            setIsSpeaking(false);
            return;
          }
          const utterance = new SpeechSynthesisUtterance(text);
          utterance.lang = GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB";
          utterance.onend = () => setIsSpeaking(false);
          utterance.onerror = (e) => {
            if (e && e.error === "interrupted") return;
            setIsSpeaking(false);
          };
          window.speechSynthesis.speak(utterance);
        };

        try {
          const blob = await GEMS.api.synthesizeSpeech(text, GEMS.i18n.locale, null, controller.signal);
          if (controller.signal.aborted) return;
          const blobUrl = URL.createObjectURL(blob);
          const audio = new Audio(blobUrl);
          audioPlayerRef.current = audio;
          audio.onended = () => setIsSpeaking(false);
          audio.onerror = fallbackSpeak;
          await audio.play();
        } catch (err) {
          if (controller.signal.aborted) return;
          fallbackSpeak();
        }
      }
    };

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
            onClick={() => handleSpeak(t("agent.whyIdAnswer"))}
          >
            {t("agent.whyId")}
          </UI.Button>
          <UI.Button
            type="button"
            style={{ justifyContent: "flex-start" }}
            onClick={() => handleSpeak([lede, message].filter(Boolean).join(" "))}
          >
            {isSpeaking ? t("agent.stopReading") : t("agent.readAloud")}
          </UI.Button>
        </div>
      </aside>
    );
  };
})();

