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

  DASHBOARD.Dashboard = function Dashboard({ username, onSignOut }) {
    const [screen, setScreen] = useState("home");
    const [balanceHidden, setBalanceHidden] = useState(true);
    const [ttsOn, setTtsOn] = useState(false);
    const [theme, setTheme] = useState("light");
    const [dockOpen, setDockOpen] = useState(true);
    const [payOpen, setPayOpen] = useState(false);
    const [payType, setPayType] = useState("iban");
    const [payPrefill, setPayPrefill] = useState(null);
    const [splitOpen, setSplitOpen] = useState(false);
    const [templateDraft, setTemplateDraft] = useState(null);
    const [templateOpen, setTemplateOpen] = useState(false);
    const [accounts, setAccounts] = useState(DATA.accounts);
    const [transactions, setTransactions] = useState(DATA.transactions);
    const [pending, setPending] = useState(DATA.pending);
    const [templates, setTemplates] = useState(DATA.templates);
    const [splitBills, setSplitBills] = useState([]);
    const [deposits, setDeposits] = useState(DATA.deposits);
    const [credits] = useState(DATA.credits);
    const [holdings, setHoldings] = useState(DATA.holdings);
    const [investCashMinor, setInvestCashMinor] = useState(DATA.investCashMinor);
    const [creditApplications, setCreditApplications] = useState([]);
    const [openAccountShown, setOpenAccountShown] = useState(false);
    const [depositShown, setDepositShown] = useState(false);
    const [depositMove, setDepositMove] = useState(null);
    const [trade, setTrade] = useState(null);
    const [creditShown, setCreditShown] = useState(false);
    const [filter, setFilter] = useState("all");
    const [query, setQuery] = useState("");
    const [range, setRange] = useState("quarter");
    const [lang, setLang] = useState(GEMS.i18n.locale);
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

    const today = useCallback(
      () =>
        new Intl.DateTimeFormat("ro-RO", { day: "2-digit", month: "2-digit", year: "numeric" })
          .format(new Date())
          .replace(/\//g, "."),
      []
    );

    const openPayment = useCallback((prefill) => {
      setPayPrefill(prefill || null);
      setPayType(prefill && prefill.payType ? prefill.payType : "iban");
      setPayOpen(true);
    }, []);

    const closePayment = useCallback(() => {
      setPayOpen(false);
      setPayPrefill(null);
    }, []);

    const submitPayment = useCallback((payment) => {
      const date = today();

      setAccounts((list) =>
        list.map((account) => {
          if (account.id === payment.fromId) return Object.assign({}, account, { minor: account.minor - payment.amountMinor });
          if (account.id === payment.toId) return Object.assign({}, account, { minor: account.minor + payment.amountMinor });
          return account;
        })
      );

      setTransactions((list) =>
        [
          {
            date,
            who: payment.beneficiary,
            ref: payment.reference || t("dashboard.payDialog.title"),
            iban: payment.iban,
            categoryKey: "transfer",
            statusKey: "pending",
            minor: payment.amountMinor,
            currency: payment.currency,
            direction: "out",
            channel: "transfer",
            accountId: payment.fromId,
          },
        ].concat(list)
      );

      setPending((list) =>
        list.concat([
          {
            num: String(list.length + 1).padStart(2, "0"),
            who: payment.beneficiary,
            note: payment.reference,
            minor: payment.amountMinor,
            currency: payment.currency,
          },
        ])
      );

      if (payment.template) setTemplates((list) => list.concat([payment.template]));
      closePayment();
    }, [today, closePayment]);

    const useTemplate = useCallback((template) => {
      const match = accounts.find((account) => account.cur === template.cur) || accounts[0];
      openPayment({
        payType: "iban",
        beneficiary: template.beneficiary,
        iban: template.iban,
        reference: template.reference,
        fromId: match.id,
      });
    }, [accounts, openPayment]);

    const saveTemplate = useCallback((template) => {
      setTemplates((list) => {
        const known = list.some((item) => item.id === template.id);
        return known ? list.map((item) => (item.id === template.id ? template : item)) : list.concat([template]);
      });
      setTemplateOpen(false);
      setTemplateDraft(null);
    }, []);

    const deleteTemplate = useCallback((templateId) => {
      setTemplates((list) => list.filter((item) => item.id !== templateId));
    }, []);

    const createSplitBill = useCallback((bill) => {
      setSplitBills((list) => [bill].concat(list));
      setSplitOpen(false);
    }, []);

    const settleShare = useCallback((billId, personKey) => {
      const bill = splitBills.find((item) => item.id === billId);
      const person = bill && bill.participants.find((item) => item.key === personKey);
      if (!bill || !person || person.settled) return;

      setSplitBills((list) =>
        list.map((item) =>
          item.id === billId
            ? Object.assign({}, item, {
                participants: item.participants.map((entry) =>
                  entry.key === personKey ? Object.assign({}, entry, { settled: true }) : entry
                ),
              })
            : item
        )
      );

      setAccounts((list) =>
        list.map((account) =>
          account.id === bill.accountId ? Object.assign({}, account, { minor: account.minor + person.minor }) : account
        )
      );

      setTransactions((list) =>
        [
          {
            date: today(),
            who: person.name,
            ref: bill.reference,
            categoryKey: "transfer",
            statusKey: "booked",
            minor: person.minor,
            currency: bill.currency,
            direction: "in",
            channel: "transfer",
            accountId: bill.accountId,
          },
        ].concat(list)
      );
    }, [splitBills, today]);

    const deleteSplitBill = useCallback((billId) => {
      setSplitBills((list) => list.filter((bill) => bill.id !== billId));
    }, []);

    const creditAccount = useCallback((accountId, minor) => {
      setAccounts((list) =>
        list.map((account) => (account.id === accountId ? Object.assign({}, account, { minor: account.minor + minor }) : account))
      );
    }, []);

    const bookMovement = useCallback((row) => {
      setTransactions((list) => [Object.assign({ date: today(), statusKey: "booked", channel: "transfer" }, row)].concat(list));
    }, [today]);

    const openAccount = useCallback(({ account, fundFromId, fundMinor }) => {
      setAccounts((list) => list.concat([Object.assign({}, account, { minor: fundMinor })]));
      if (fundFromId && fundMinor > 0) {
        creditAccount(fundFromId, -fundMinor);
        bookMovement({
          who: DASH.accountLabel(account),
          ref: t("dashboard.openAccount.movementRef"),
          categoryKey: "transfer",
          minor: fundMinor,
          currency: account.cur,
          direction: "out",
          accountId: fundFromId,
        });
      }
      setOpenAccountShown(false);
    }, [creditAccount, bookMovement]);

    const newDeposit = useCallback(({ deposit, fromId, amountMinor }) => {
      setDeposits((list) => list.concat([deposit]));
      creditAccount(fromId, -amountMinor);
      bookMovement({
        who: deposit.name,
        ref: t("dashboard.deposit.movementRef"),
        categoryKey: "transfer",
        minor: amountMinor,
        currency: deposit.cur,
        direction: "out",
        accountId: fromId,
      });
      setDepositShown(false);
    }, [creditAccount, bookMovement]);

    const moveDeposit = useCallback(({ depositId, accountId, amountMinor, direction }) => {
      const inbound = direction === "in";
      setDeposits((list) =>
        list.map((deposit) =>
          deposit.id === depositId
            ? Object.assign({}, deposit, { minor: deposit.minor + (inbound ? amountMinor : -amountMinor) })
            : deposit
        )
      );
      creditAccount(accountId, inbound ? -amountMinor : amountMinor);

      const deposit = deposits.find((item) => item.id === depositId);
      bookMovement({
        who: deposit ? deposit.name : "",
        ref: inbound ? t("dashboard.deposit.topUp") : t("dashboard.deposit.withdraw"),
        categoryKey: "transfer",
        minor: amountMinor,
        currency: deposit ? deposit.cur : "RON",
        direction: inbound ? "out" : "in",
        accountId,
      });
      setDepositMove(null);
    }, [deposits, creditAccount, bookMovement]);

    const closeDeposit = useCallback((deposit) => {
      const target = accounts.find((account) => account.cur === deposit.cur);
      if (!target) return;
      setDeposits((list) => list.filter((item) => item.id !== deposit.id));
      if (deposit.minor > 0) {
        creditAccount(target.id, deposit.minor);
        bookMovement({
          who: deposit.name,
          ref: t("dashboard.deposit.closeRef"),
          categoryKey: "transfer",
          minor: deposit.minor,
          currency: deposit.cur,
          direction: "in",
          accountId: target.id,
        });
      }
    }, [accounts, creditAccount, bookMovement]);

    const runTrade = useCallback(({ holdingId, accountId, amountMinor, direction }) => {
      const holding = holdings.find((item) => item.id === holdingId);
      if (!holding) return;
      const buying = direction === "buy";

      if (buying) {
        const fromCash = Math.min(investCashMinor, amountMinor);
        const fromAccount = amountMinor - fromCash;
        setInvestCashMinor((cash) => cash - fromCash);
        if (fromAccount > 0) {
          creditAccount(accountId, -fromAccount);
          bookMovement({
            who: holding.name,
            ref: t("dashboard.invest.buy"),
            categoryKey: "transfer",
            minor: fromAccount,
            currency: holding.cur,
            direction: "out",
            accountId,
          });
        }
      } else {
        creditAccount(accountId, amountMinor);
        bookMovement({
          who: holding.name,
          ref: t("dashboard.invest.sell"),
          categoryKey: "transfer",
          minor: amountMinor,
          currency: holding.cur,
          direction: "in",
          accountId,
        });
      }

      const deltaUnits = amountMinor / holding.unitPriceMinor;
      setHoldings((list) =>
        list.map((item) =>
          item.id === holdingId
            ? Object.assign({}, item, { units: Math.max(0, item.units + (buying ? deltaUnits : -deltaUnits)) })
            : item
        )
      );
      setTrade(null);
    }, [holdings, investCashMinor, creditAccount, bookMovement]);

    const applyForCredit = useCallback((application) => {
      setCreditApplications((list) => [application].concat(list));
      setCreditShown(false);
    }, []);

    const withdrawApplication = useCallback((applicationId) => {
      setCreditApplications((list) => list.filter((item) => item.id !== applicationId));
    }, []);

    return (
      <div className="dash-shell">
        <DASH.Sidebar screen={screen} onNavigate={navigate} onSignOut={onSignOut} />

        <div className="dash-main">
          <DASH.Topbar screen={screen} username={username} />

          <main className="dash-content" aria-label={t("dashboard.tag." + screen)}>
            {screen === "home" ? (
              <SCR.HomeScreen accounts={accounts} transactions={transactions} balanceHidden={balanceHidden} onToggleBalance={toggleBalance} onSpeakBalance={speakBalance} onNavigate={navigate} />
            ) : null}
            {screen === "payments" ? (
              <SCR.PaymentsScreen
                accounts={accounts}
                transactions={transactions}
                pending={pending}
                templates={templates}
                splitBills={splitBills}
                filter={filter}
                onFilter={setFilter}
                query={query}
                onQuery={setQuery}
                onOpenPay={() => openPayment(null)}
                onOpenSplit={() => setSplitOpen(true)}
                onNewTemplate={() => { setTemplateDraft(null); setTemplateOpen(true); }}
                onEditTemplate={(template) => { setTemplateDraft(template); setTemplateOpen(true); }}
                onDeleteTemplate={deleteTemplate}
                onUseTemplate={useTemplate}
                onSettleShare={settleShare}
                onDeleteSplit={deleteSplitBill}
              />
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
            {screen === "portfolio" ? (
              <SCR.PortfolioScreen
                accounts={accounts}
                deposits={deposits}
                credits={credits}
                holdings={holdings}
                investCashMinor={investCashMinor}
                creditApplications={creditApplications}
                onOpenAccount={() => setOpenAccountShown(true)}
                onNewDeposit={() => setDepositShown(true)}
                onMoveDeposit={(deposit, direction) => setDepositMove({ deposit, direction })}
                onCloseDeposit={closeDeposit}
                onTrade={(holdingId, direction) => setTrade({ holdingId, direction })}
                onApplyCredit={() => setCreditShown(true)}
                onWithdrawApplication={withdrawApplication}
              />
            ) : null}
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
            key={payPrefill ? payPrefill.iban : "blank"}
            payType={payType}
            onPayType={setPayType}
            accounts={accounts}
            templates={templates}
            prefill={payPrefill}
            onClose={closePayment}
            onSubmit={submitPayment}
          />
        ) : null}

        {splitOpen ? (
          <DASH.SplitBillDialog
            accounts={accounts}
            onClose={() => setSplitOpen(false)}
            onSubmit={createSplitBill}
          />
        ) : null}

        {openAccountShown ? (
          <DASH.OpenAccountDialog
            accounts={accounts}
            onClose={() => setOpenAccountShown(false)}
            onSubmit={openAccount}
          />
        ) : null}

        {depositShown ? (
          <DASH.NewDepositDialog
            accounts={accounts}
            onClose={() => setDepositShown(false)}
            onSubmit={newDeposit}
          />
        ) : null}

        {depositMove ? (
          <DASH.MoveDepositDialog
            key={depositMove.deposit.id + depositMove.direction}
            deposit={deposits.find((item) => item.id === depositMove.deposit.id) || depositMove.deposit}
            accounts={accounts}
            direction={depositMove.direction}
            onClose={() => setDepositMove(null)}
            onSubmit={moveDeposit}
          />
        ) : null}

        {trade ? (
          <DASH.InvestDialog
            key={(trade.holdingId || "any") + trade.direction}
            holdings={holdings}
            accounts={accounts}
            investCashMinor={investCashMinor}
            holdingId={trade.holdingId}
            direction={trade.direction}
            onClose={() => setTrade(null)}
            onSubmit={runTrade}
          />
        ) : null}

        {creditShown ? (
          <DASH.CreditApplicationDialog
            accounts={accounts}
            onClose={() => setCreditShown(false)}
            onSubmit={applyForCredit}
          />
        ) : null}

        {templateOpen ? (
          <DASH.TemplateDialog
            key={templateDraft ? templateDraft.id : "new"}
            accounts={accounts}
            template={templateDraft}
            onClose={() => { setTemplateOpen(false); setTemplateDraft(null); }}
            onSubmit={saveTemplate}
          />
        ) : null}
      </div>
    );
  };
})();
