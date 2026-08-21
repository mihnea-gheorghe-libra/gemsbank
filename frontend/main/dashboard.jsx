(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASHBOARD = (GEMS.dashboard = GEMS.dashboard || {});
  const DASH = GEMS.dashboardUi;
  const SCR = GEMS.dashboardScreens;
  const t = GEMS.i18n.t;
  const api = GEMS.api;
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

  DASHBOARD.Dashboard = function Dashboard({ username, theme, onTheme, lang, onLang, onSignOut }) {
    const [screen, setScreen] = useState("home");
    const [balanceHidden, setBalanceHidden] = useState(true);
    const [ttsOn, setTtsOn] = useState(false);
    const [dockOpen, setDockOpen] = useState(true);
    const [payOpen, setPayOpen] = useState(false);
    const [payType, setPayType] = useState("iban");
    const [filter, setFilter] = useState("all");
    const [range, setRange] = useState("quarter");
    const [cards, setCards] = useState([]);
    const [cardsLoaded, setCardsLoaded] = useState(false);
    const [cardsLoading, setCardsLoading] = useState(false);
    const [cardsError, setCardsError] = useState(null);
    const [cardIssuing, setCardIssuing] = useState(false);
    const [cardBusy, setCardBusy] = useState(false);
    const [selectedCardId, setSelectedCardId] = useState(null);
    const [cardPin, setCardPin] = useState(null);
    const [pinShown, setPinShown] = useState(false);
    const [cardCvv, setCardCvv] = useState(null);
    const [detailsShown, setDetailsShown] = useState(false);
    const [micOn, setMicOn] = useState(false);
    const [draft, setDraft] = useState("");
    const [messages, setMessages] = useState([
      { role: "ai", kind: "text", text: t("dashboard.chat.seed", { balance: DATA.totalBalance }) },
    ]);

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

    const applyCard = useCallback((updated) => {
      setCards((list) => list.map((card) => (card.cardId === updated.cardId ? updated : card)));
    }, []);

    const loadCards = useCallback(async () => {
      setCardsLoading(true);
      setCardsError(null);
      try {
        const response = await api.listCards(username);
        setCards(response.cards);
        setCardsLoaded(true);
        setSelectedCardId((current) =>
          current && response.cards.some((card) => card.cardId === current)
            ? current
            : response.cards.length
              ? response.cards[0].cardId
              : null
        );
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardsLoading(false);
      }
    }, [username]);

    useEffect(() => {
      if (screen === "cards" && !cardsLoaded && !cardsLoading) {
        loadCards();
      }
    }, [screen, cardsLoaded, cardsLoading, loadCards]);

    const selectCard = useCallback((cardId) => {
      setSelectedCardId(cardId);
      setPinShown(false);
      setCardPin(null);
      setDetailsShown(false);
      setCardCvv(null);
    }, []);

    const issueCard = useCallback(async () => {
      setCardIssuing(true);
      setCardsError(null);
      try {
        const card = await api.issueVirtualCard(username);
        setCards((list) => list.concat([card]));
        selectCard(card.cardId);
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardIssuing(false);
      }
    }, [username, selectCard]);

    const freezeCard = useCallback(async () => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        applyCard(await api.freezeCard(username, selectedCardId));
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard]);

    const unfreezeCard = useCallback(async () => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        applyCard(await api.unfreezeCard(username, selectedCardId));
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard]);

    const blockCard = useCallback(async () => {
      if (!selectedCardId) return;
      if (!window.confirm(t("dashboard.cards.confirmBlock"))) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        applyCard(await api.blockCard(username, selectedCardId));
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard]);

    const toggleCardPin = useCallback(async () => {
      if (!selectedCardId) return;
      if (pinShown) {
        setPinShown(false);
        return;
      }
      setCardBusy(true);
      setCardsError(null);
      try {
        const result = await api.revealCardPin(username, selectedCardId);
        setCardPin(result.pin);
        setPinShown(true);
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, pinShown]);

    const toggleCardDetails = useCallback(async () => {
      if (!selectedCardId) return;
      if (detailsShown) {
        setDetailsShown(false);
        return;
      }
      setCardBusy(true);
      setCardsError(null);
      try {
        const result = await api.revealCardDetails(username, selectedCardId);
        setCardCvv(result.cvv);
        setDetailsShown(true);
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, detailsShown]);

    const setCardAtmLimit = useCallback(async (minor) => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        applyCard(await api.setCardAtmLimit(username, selectedCardId, minor));
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard]);

    const setCardOnlineLimit = useCallback(async (minor) => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        applyCard(await api.setCardOnlineLimit(username, selectedCardId, minor));
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard]);

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
                cards={cards}
                loading={cardsLoading && !cardsLoaded}
                error={cardsError}
                selectedCardId={selectedCardId}
                onSelect={selectCard}
                onIssue={issueCard}
                issuing={cardIssuing}
                busy={cardBusy}
                onFreeze={freezeCard}
                onUnfreeze={unfreezeCard}
                onBlock={blockCard}
                pin={cardPin}
                pinShown={pinShown}
                onTogglePin={toggleCardPin}
                cvv={cardCvv}
                detailsShown={detailsShown}
                onToggleDetails={toggleCardDetails}
                onSetAtmLimit={setCardAtmLimit}
                onSetOnlineLimit={setCardOnlineLimit}
              />
            ) : null}
            {screen === "analytics" ? <SCR.AnalyticsScreen range={range} onRange={setRange} /> : null}
            {screen === "settings" ? (
              <SCR.SettingsScreen
                lang={lang}
                onLang={onLang}
                theme={theme}
                onTheme={onTheme}
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
