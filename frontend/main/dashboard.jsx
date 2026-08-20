(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASHBOARD = (GEMS.dashboard = GEMS.dashboard || {});
  const DASH = GEMS.dashboardUi;
  const SCR = GEMS.dashboardScreens;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const { useState, useCallback, useEffect } = React;

  const SCREENS = ["home", "payments", "chat", "portfolio", "cards", "analytics", "settings"];

  function speak(text) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB";
    window.speechSynthesis.speak(utterance);
  }

  function answerFor(promptKey) {
    if (promptKey === "pay") return { role: "ai", kind: "tx", text: t("dashboard.chat.answerPay") };
    if (promptKey === "recurring") return { role: "ai", kind: "table", text: t("dashboard.chat.answerRecurring") };
    if (promptKey === "groceries") return { role: "ai", kind: "chart", text: t("dashboard.chat.answerGroceries") };
    return { role: "ai", kind: "text", text: t("dashboard.chat.answerDefault") };
  }

  function answerForFreeText(text) {
    const lower = text.toLowerCase();
    if (/pay|plat|trimit|transfer|send/.test(lower)) return answerFor("pay");
    if (/recurring|subscription|abonament|recuren/.test(lower)) return answerFor("recurring");
    if (/grocer|cumpar|cheltu|spend|cost/.test(lower)) return answerFor("groceries");
    return answerFor(null);
  }

  DASHBOARD.Dashboard = function Dashboard({ username, onSignOut }) {
    const [screen, setScreen] = useState("home");
    const [balanceHidden, setBalanceHidden] = useState(true);
    const [ttsOn, setTtsOn] = useState(false);
    const [theme, setTheme] = useState("light");
    const [dockOpen, setDockOpen] = useState(true);
    const [payOpen, setPayOpen] = useState(false);
    const [payType, setPayType] = useState("iban");
    const [filter, setFilter] = useState("all");
    const [range, setRange] = useState("quarter");
    const [lang, setLang] = useState(GEMS.i18n.locale);
    const [cardIndex, setCardIndex] = useState(0);
    const [cardFrozen, setCardFrozen] = useState(false);
    const [pinShown, setPinShown] = useState(false);
    const [micOn, setMicOn] = useState(false);
    const [draft, setDraft] = useState("");
    const [messages, setMessages] = useState([
      { role: "ai", kind: "text", text: t("dashboard.chat.seed", { balance: DATA.totalBalance }) },
    ]);

    useEffect(() => {
      if (theme === "dark") document.documentElement.setAttribute("data-theme", "dark");
      else document.documentElement.setAttribute("data-theme", "light");
      return () => document.documentElement.removeAttribute("data-theme");
    }, [theme]);

    const navigate = useCallback((key) => {
      if (SCREENS.indexOf(key) >= 0) setScreen(key);
    }, []);

    const speakBalance = useCallback(() => {
      speak(t("dashboard.chat.balanceSpoken", { balance: DATA.totalBalance }));
    }, []);

    const toggleBalance = useCallback(() => {
      setBalanceHidden((hidden) => {
        if (hidden && ttsOn) speakBalance();
        return !hidden;
      });
    }, [ttsOn, speakBalance]);

    const pushExchange = useCallback((userText, reply) => {
      setMessages((list) => list.concat([{ role: "user", kind: "text", text: userText }, reply]));
      if (ttsOn && reply.text) speak(reply.text);
      setScreen("chat");
    }, [ttsOn]);

    const sendDraft = useCallback(() => {
      const text = draft.trim();
      if (!text) return;
      pushExchange(text, answerForFreeText(text));
      setDraft("");
    }, [draft, pushExchange]);

    const onDockPrompt = useCallback((key) => {
      const label = t("dashboard.chat." + (key === "pay" ? "promptPay" : "promptRecurring"));
      pushExchange(label, answerFor(key));
    }, [pushExchange]);

    const onScreenPrompt = useCallback((key) => {
      const labelKey = key === "pay" ? "promptPay" : key === "recurring" ? "promptRecurring" : "promptGroceries";
      pushExchange(t("dashboard.chat." + labelKey), answerFor(key));
    }, [pushExchange]);

    const confirmTx = useCallback(() => {
      setMessages((list) => list.concat([{ role: "ai", kind: "text", text: t("dashboard.chat.txConfirmedNote") }]));
    }, []);

    return (
      <div className="dash-shell">
        <DASH.Sidebar screen={screen} onNavigate={navigate} onSignOut={onSignOut} />

        <div className="dash-main">
          <DASH.Topbar screen={screen} username={username} ttsOn={ttsOn} onToggleTts={() => setTtsOn((value) => !value)} />

          <main className="dash-content" aria-label={t("dashboard.tag." + screen)}>
            {screen === "home" ? (
              <SCR.HomeScreen balanceHidden={balanceHidden} onToggleBalance={toggleBalance} onSpeakBalance={speakBalance} onNavigate={navigate} />
            ) : null}
            {screen === "payments" ? (
              <SCR.PaymentsScreen filter={filter} onFilter={setFilter} onOpenPay={() => setPayOpen(true)} />
            ) : null}
            {screen === "chat" ? (
              <SCR.ChatScreen
                messages={messages}
                draft={draft}
                onDraftChange={(event) => setDraft(event.target.value)}
                onSend={sendDraft}
                onKeyDown={(event) => { if (event.key === "Enter") sendDraft(); }}
                micOn={micOn}
                onToggleMic={() => setMicOn((value) => !value)}
                onPromptClick={onScreenPrompt}
                onConfirmTx={confirmTx}
                username={username}
              />
            ) : null}
            {screen === "portfolio" ? <SCR.PortfolioScreen /> : null}
            {screen === "cards" ? (
              <SCR.CardsScreen
                selectedIndex={cardIndex}
                onSelect={(index) => { setCardIndex(index); setPinShown(false); }}
                frozen={cardFrozen}
                onToggleFreeze={() => setCardFrozen((value) => !value)}
                pinShown={pinShown}
                onShowPin={() => setPinShown((value) => !value)}
              />
            ) : null}
            {screen === "analytics" ? <SCR.AnalyticsScreen range={range} onRange={setRange} /> : null}
            {screen === "settings" ? (
              <SCR.SettingsScreen
                lang={lang}
                onLang={setLang}
                theme={theme}
                onTheme={setTheme}
                ttsOn={ttsOn}
                onToggleTts={() => setTtsOn((value) => !value)}
                onSignOut={onSignOut}
                onGoChat={() => navigate("chat")}
              />
            ) : null}
          </main>
        </div>

        {screen !== "chat" ? (
          <DASH.AgentDock
            open={dockOpen}
            username={username}
            onOpen={() => setDockOpen(true)}
            onClose={() => setDockOpen(false)}
            onExpand={() => navigate("chat")}
            onPrompt={onDockPrompt}
          />
        ) : null}

        {payOpen ? (
          <DASH.NewPaymentDialog
            payType={payType}
            onPayType={setPayType}
            onClose={() => setPayOpen(false)}
            onContinue={() => setPayOpen(false)}
          />
        ) : null}
      </div>
    );
  };
})();
