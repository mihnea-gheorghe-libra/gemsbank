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
  const REAL_ACCOUNT_KINDS = ["current", "savings", "invest"];

  const ANSWER_KEYS = {
    pendingSign: "answerPendingSign",
    portfolioGrowth: "answerPortfolioGrowth",
    portfolioMove: "answerPortfolioMove",
    cardFreeze: "answerCardFreeze",
    cardLimit: "answerCardLimit",
    spendingTrend: "answerSpendingTrend",
    settingsPin: "answerSettingsPin",
    settings2fa: "answerSettings2fa",
  };

  function agentForScreen(originScreen) {
    return originScreen === "analytics" ? "analytics" : "support";
  }

  function answerFor(promptKey) {
    if (promptKey === "pay") return { role: "ai", kind: "tx", text: t("dashboard.chat.answerPay") };
    if (promptKey === "recurring") return { role: "ai", kind: "table", text: t("dashboard.chat.answerRecurring") };
    if (promptKey === "groceries") return { role: "ai", kind: "chart", text: t("dashboard.chat.answerGroceries") };
    const answerKey = ANSWER_KEYS[promptKey];
    if (answerKey) return { role: "ai", kind: "text", text: t("dashboard.chat." + answerKey) };
    return { role: "ai", kind: "text", text: t("dashboard.chat.answerDefault") };
  }

  function answerForFreeText(text) {
    const lower = text.toLowerCase();
    if (/pay|plat|trimit|transfer|send/.test(lower)) return answerFor("pay");
    if (/recurring|subscription|abonament|recuren/.test(lower)) return answerFor("recurring");
    if (/grocer|cumpar|cheltu|spend|cost/.test(lower)) return answerFor("groceries");
    return answerFor(null);
  }

  function formatApiDate(iso) {
    const moment = new Date(iso);
    if (isNaN(moment.getTime())) return iso;
    return new Intl.DateTimeFormat("ro-RO", { day: "2-digit", month: "2-digit", year: "numeric" })
      .format(moment)
      .replace(/\//g, ".");
  }

  function mapAccountRow(account) {
    return {
      id: account.accountId,
      cur: account.currency,
      typeKey: account.kind,
      minor: account.balance.minorUnits,
      iban: account.iban,
      ibanShort: account.ibanMasked,
    };
  }

  function mapMovementRow(row) {
    return {
      date: formatApiDate(row.postedAt),
      who: row.counterparty,
      ref: row.reference,
      iban: "",
      categoryKey: row.category,
      statusKey: row.status,
      minor: Math.abs(row.amount.minorUnits),
      currency: row.amount.currency,
      direction: row.direction === "credit" ? "in" : "out",
      channel: "transfer",
      accountId: row.accountId,
    };
  }

  function mapPendingSignatureRow(payment) {
    return {
      date: formatApiDate(payment.createdAt),
      who: payment.counterparty,
      ref: payment.reference,
      iban: payment.iban || "",
      categoryKey: payment.category,
      statusKey: "awaiting_signature",
      minor: payment.amount.minorUnits,
      currency: payment.amount.currency,
      direction: "out",
      channel: "transfer",
      accountId: payment.sourceAccountId,
    };
  }

  DASHBOARD.Dashboard = function Dashboard({ username, theme, onTheme, lang, onLang, onSignOut }) {
    const [screen, setScreen] = useState("home");
    const [balanceHidden, setBalanceHidden] = useState(true);
    const [ttsOn, setTtsOn] = useState(false);
    const [dockOpen, setDockOpen] = useState(false);
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
    const [investCashMinor, setInvestCashMinor] = useState(null);
    const [market, setMarket] = useState(null);
    const [marketLoading, setMarketLoading] = useState(false);
    const [marketError, setMarketError] = useState(null);
    const [creditApplications, setCreditApplications] = useState([]);
    const [openAccountShown, setOpenAccountShown] = useState(false);
    const [openAccountInitialType, setOpenAccountInitialType] = useState(null);
    const [depositMove, setDepositMove] = useState(null);
    const [trade, setTrade] = useState(null);
    const [creditShown, setCreditShown] = useState(false);
    const [filter, setFilter] = useState("all");
    const [query, setQuery] = useState("");
    const [range, setRange] = useState("6");
    const [cards, setCards] = useState([]);
    const [cardsLoaded, setCardsLoaded] = useState(false);
    const [cardsLoading, setCardsLoading] = useState(false);
    const [cardsError, setCardsError] = useState(null);
    const [cardIssuing, setCardIssuing] = useState(false);
    const [issueOpen, setIssueOpen] = useState(false);
    const [issueKind, setIssueKind] = useState("virtual");
    const [historyOpen, setHistoryOpen] = useState(false);
    const [cardBusy, setCardBusy] = useState(false);
    const [selectedCardId, setSelectedCardId] = useState(null);
    const [cardPin, setCardPin] = useState(null);
    const [pinShown, setPinShown] = useState(false);
    const [cardCvv, setCardCvv] = useState(null);
    const [detailsShown, setDetailsShown] = useState(false);
    const [pinPromptOpen, setPinPromptOpen] = useState(false);
    const [pinPromptBusy, setPinPromptBusy] = useState(false);
    const [pinPromptError, setPinPromptError] = useState(null);
    const [pinPromptTarget, setPinPromptTarget] = useState(null);
    const [micOn, setMicOn] = useState(false);
    const [draft, setDraft] = useState("");
    const [chatBusy, setChatBusy] = useState(false);
    const [chatAgent, setChatAgent] = useState("support");
    const [messages, setMessages] = useState([
      { role: "ai", kind: "text", text: t("dashboard.chat.seed", { balance: DATA.totalBalance }) },
    ]);
    const [me, setMe] = useState(null);
    const [payBusy, setPayBusy] = useState(false);
    const [payFormError, setPayFormError] = useState(null);
    const [signingPayment, setSigningPayment] = useState(null);
    const [signBusy, setSignBusy] = useState(false);
    const [signFormError, setSignFormError] = useState(null);
    const [openAccountBusy, setOpenAccountBusy] = useState(false);
    const [openAccountError, setOpenAccountError] = useState(null);
    const [addFundsShown, setAddFundsShown] = useState(false);
    const [addFundsError, setAddFundsError] = useState(null);
    const [exchangeShown, setExchangeShown] = useState(false);
    const [exchangeBusy, setExchangeBusy] = useState(false);
    const [exchangeError, setExchangeError] = useState(null);

    useEffect(() => {
      let cancelled = false;
      api
        .me()
        .then((response) => {
          if (!cancelled) setMe(response);
        })
        .catch(() => {});
      return () => {
        cancelled = true;
      };
    }, [username]);

    const loadPaymentsData = useCallback(async () => {
      const [accountList, txList, pendingList] = await Promise.all([
        api.listAccounts(),
        api.listTransactions({}),
        api.listPending(),
      ]);
      const mappedAccounts = accountList.accounts.map(mapAccountRow);
      setAccounts(mappedAccounts);
      setTransactions(pendingList.pending.map(mapPendingSignatureRow).concat(txList.transactions.map(mapMovementRow)));
      setPending(pendingList.pending);

      const investAccount = mappedAccounts.find((account) => account.typeKey === "invest");
      setInvestCashMinor(investAccount ? investAccount.minor : null);
    }, []);

    useEffect(() => {
      loadPaymentsData().catch(() => {});
    }, [username, loadPaymentsData]);

    const displayName = (me && me.identity && me.identity.fullName) || (me && me.fullName) || username;
    const firstName = GEMS.people.firstName(displayName) || username;

    const navigate = useCallback((key) => {
      if (SCREENS.indexOf(key) >= 0) {
        if (key === "chat" && screen !== "chat") {
          const agent = agentForScreen(screen);
          const seedKey = agent === "analytics" ? "seedAnalytics" : "seed";
          setChatAgent(agent);
          setMessages([{ role: "ai", kind: "text", text: t("dashboard.chat." + seedKey, { balance: DATA.totalBalance }) }]);
        }
        setScreen(key);
        setBalanceHidden(true);
      }
    }, [screen]);

    const toggleBalance = useCallback(() => {
      setBalanceHidden((hidden) => !hidden);
    }, []);

    const pushExchange = useCallback((userText, reply) => {
      if (screen !== "chat") setChatAgent(agentForScreen(screen));
      setMessages((list) => {
        const base = screen === "chat" ? list : [];
        return base.concat([{ role: "user", kind: "text", text: userText }, reply]);
      });
      setScreen("chat");
      setBalanceHidden(true);
    }, [screen]);

    const sendDraft = useCallback(() => {
      const text = draft.trim();
      if (!text || chatBusy) return;
      setMessages((list) => list.concat([{ role: "user", kind: "text", text }]));
      setScreen("chat");
      setBalanceHidden(true);
      setDraft("");
      setChatBusy(true);
      const ask = chatAgent === "analytics" ? api.askAnalytics : api.askSupport;
      ask(text)
        .then((result) => {
          setMessages((list) =>
            list.concat([{ role: "ai", kind: "text", text: result.answer, aiGenerated: true }])
          );
        })
        .catch(() => {
          setMessages((list) =>
            list.concat([{ role: "ai", kind: "text", text: t("dashboard.chat.errorNote") }])
          );
        })
        .finally(() => setChatBusy(false));
    }, [draft, chatBusy, chatAgent]);

    const onDockPrompt = useCallback((key) => {
      const prompt = DATA.chatPrompts[key];
      const label = prompt ? t("dashboard.chat." + prompt.labelKey) : "";
      pushExchange(label, answerFor(key));
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

    const loadMarket = useCallback(async (force) => {
      setMarketLoading(true);
      setMarketError(null);
      try {
        setMarket(await api.marketSnapshot("1y", force === true));
      } catch (err) {
        setMarketError(err);
      } finally {
        setMarketLoading(false);
      }
    }, []);

    useEffect(() => {
      if (screen === "portfolio" && !market && !marketLoading && !marketError) {
        loadMarket();
      }
    }, [screen, market, marketLoading, marketError, loadMarket]);

    const pricedHoldings = DASH.applyQuotes(holdings, market);

    const selectCard = useCallback((cardId) => {
      setSelectedCardId(cardId);
      setPinShown(false);
      setCardPin(null);
      setDetailsShown(false);
      setCardCvv(null);
    }, []);

    useEffect(() => {
      if (screen === "cards") return;
      setPinShown(false);
      setCardPin(null);
      setDetailsShown(false);
      setCardCvv(null);
      setPinPromptOpen(false);
      setPinPromptError(null);
      setPinPromptTarget(null);
    }, [screen]);

    const openIssueDialog = useCallback(() => {
      setIssueKind("virtual");
      setIssueOpen(true);
    }, []);

    const createCard = useCallback(async () => {
      setCardIssuing(true);
      setCardsError(null);
      try {
        const card = issueKind === "physical"
          ? await api.issuePhysicalCard(username)
          : await api.issueVirtualCard(username);
        setCards((list) => list.concat([card]));
        selectCard(card.cardId);
        setIssueOpen(false);
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardIssuing(false);
      }
    }, [username, issueKind, selectCard]);

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

    const deleteCard = useCallback(async () => {
      if (!selectedCardId) return;
      if (!window.confirm(t("dashboard.cards.confirmDelete"))) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        const updated = await api.blockCard(username, selectedCardId);
        applyCard(updated);
        const next = cards.find((row) => row.cardId !== updated.cardId && row.state !== "blocked");
        selectCard(next ? next.cardId : null);
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard, cards, selectCard]);

    const revealCardPin = useCallback(async () => {
      if (!selectedCardId) return false;
      setCardBusy(true);
      setCardsError(null);
      try {
        const result = await api.revealCardPin(username, selectedCardId);
        setCardPin(result.pin);
        setPinShown(true);
        return true;
      } catch (err) {
        setCardsError(err);
        return false;
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId]);

    const toggleCardPin = useCallback(() => {
      if (!selectedCardId) return;
      if (pinShown) {
        setPinShown(false);
        return;
      }
      setPinPromptError(null);
      setPinPromptTarget("cardPin");
      setPinPromptOpen(true);
    }, [selectedCardId, pinShown]);

    const revealCardDetails = useCallback(async () => {
      if (!selectedCardId) return;
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
    }, [username, selectedCardId]);

    const toggleCardDetails = useCallback(() => {
      if (!selectedCardId) return;
      if (detailsShown) {
        setDetailsShown(false);
        return;
      }
      setPinPromptError(null);
      setPinPromptTarget("details");
      setPinPromptOpen(true);
    }, [selectedCardId, detailsShown]);

    const confirmLoginPin = useCallback(async (pin) => {
      setPinPromptBusy(true);
      setPinPromptError(null);
      try {
        await api.verifyPin(username, pin);
        if (pinPromptTarget === "cardPin") {
          const revealed = await revealCardPin();
          if (!revealed) setPinPromptOpen(false);
        } else {
          setPinPromptOpen(false);
          if (pinPromptTarget === "details") await revealCardDetails();
        }
      } catch (err) {
        setPinPromptError(err);
      } finally {
        setPinPromptBusy(false);
      }
    }, [username, pinPromptTarget, revealCardPin, revealCardDetails]);

    const cancelLoginPin = useCallback(() => {
      setPinPromptOpen(false);
      setPinPromptError(null);
    }, []);

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

    const visibleCards = cards.filter((row) => row.state !== "blocked");
    const deletedCards = cards.filter((row) => row.state === "blocked");
    const today = useCallback(
      () =>
        new Intl.DateTimeFormat("ro-RO", { day: "2-digit", month: "2-digit", year: "numeric" })
          .format(new Date())
          .replace(/\//g, "."),
      []
    );

    const openPayment = useCallback((prefill) => {
      setPayFormError(null);
      setPayPrefill(prefill || null);
      setPayType(prefill && prefill.payType ? prefill.payType : "iban");
      setPayOpen(true);
    }, []);

    const closePayment = useCallback(() => {
      setPayOpen(false);
      setPayPrefill(null);
      setPayFormError(null);
    }, []);

    const submitPayment = useCallback(async (payment) => {
      setPayBusy(true);
      setPayFormError(null);
      try {
        const response = await api.transfer({
          sourceAccountId: payment.fromId,
          targetAccountId: payment.payType === "internal" ? payment.toId : null,
          iban: payment.payType === "internal" ? null : payment.iban,
          counterparty: payment.beneficiary,
          amountMinorUnits: payment.amountMinor,
          reference: payment.reference,
          category: null,
          acknowledgePayeeMismatch: payment.acknowledgeMismatch === true,
        });

        if (payment.template) setTemplates((list) => list.concat([payment.template]));
        closePayment();

        if (response.status === "awaiting_signature") {
          setSignFormError(null);
          setSigningPayment(response);
        }

        await loadPaymentsData();
      } catch (err) {
        setPayFormError(err);
      } finally {
        setPayBusy(false);
      }
    }, [closePayment, loadPaymentsData]);

    const closeSign = useCallback(() => {
      setSigningPayment(null);
      setSignFormError(null);
    }, []);

    const submitSignature = useCallback(async (paymentId, pin) => {
      setSignBusy(true);
      setSignFormError(null);
      try {
        await api.verifyPin(username, pin);
        const devCode = signingPayment && signingPayment.stepUp ? signingPayment.stepUp.devCode : null;
        await api.signTransfer(paymentId, devCode);
        setSigningPayment(null);
        await loadPaymentsData();
      } catch (err) {
        setSignFormError(err);
      } finally {
        setSignBusy(false);
      }
    }, [loadPaymentsData, username, signingPayment]);

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

    const openAddFunds = useCallback(() => {
      setAddFundsError(null);
      setAddFundsShown(true);
    }, []);

    const closeAddFunds = useCallback(() => {
      setAddFundsShown(false);
      setAddFundsError(null);
    }, []);

    const submitAddFunds = useCallback((amountMinor) => {
      const target = accounts.find((account) => account.typeKey === "current" && account.cur === "RON") || accounts[0];
      if (!target) {
        setAddFundsError({ message: t("dashboard.addFunds.noAccount") });
        return;
      }
      creditAccount(target.id, amountMinor);
      bookMovement({
        who: t("dashboard.addFunds.title"),
        ref: t("dashboard.addFunds.title"),
        categoryKey: "income",
        minor: amountMinor,
        currency: target.cur,
        direction: "in",
        accountId: target.id,
      });
      closeAddFunds();
    }, [accounts, creditAccount, bookMovement, closeAddFunds]);

    const openExchange = useCallback(() => {
      setExchangeError(null);
      setExchangeShown(true);
    }, []);

    const closeExchange = useCallback(() => {
      setExchangeShown(false);
      setExchangeError(null);
    }, []);

    const submitExchange = useCallback(async (payload) => {
      setExchangeBusy(true);
      setExchangeError(null);
      try {
        await api.exchange({
          sourceAccountId: payload.sourceAccountId,
          targetCurrency: payload.targetCurrency,
          amountMinorUnits: payload.amountMinor,
        });
        setExchangeShown(false);
        await loadPaymentsData();
      } catch (err) {
        setExchangeError(err);
      } finally {
        setExchangeBusy(false);
      }
    }, [loadPaymentsData]);

    const openAccount = useCallback(async ({ account, fundFromId, fundMinor }) => {
      if (REAL_ACCOUNT_KINDS.indexOf(account.typeKey) < 0) {
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
        return;
      }

      setOpenAccountBusy(true);
      setOpenAccountError(null);
      try {
        const opened = await api.openAccount(account.cur, account.typeKey);
        let fundResponse = null;
        if (fundFromId && fundMinor > 0) {
          fundResponse = await api.transfer({
            sourceAccountId: fundFromId,
            targetAccountId: opened.accountId,
            counterparty: displayName,
            amountMinorUnits: fundMinor,
            reference: t("dashboard.openAccount.movementRef"),
            category: null,
            acknowledgePayeeMismatch: false,
          });
        }
        await loadPaymentsData();
        setOpenAccountShown(false);
        if (fundResponse && fundResponse.status === "awaiting_signature") {
          setSignFormError(null);
          setSigningPayment(fundResponse);
        }
      } catch (err) {
        setOpenAccountError(err);
      } finally {
        setOpenAccountBusy(false);
      }
    }, [creditAccount, bookMovement, displayName, loadPaymentsData]);

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
      setOpenAccountShown(false);
    }, [creditAccount, bookMovement]);

    const openProduct = useCallback(
      (payload) => (payload.deposit ? newDeposit(payload) : openAccount(payload)),
      [newDeposit, openAccount]
    );

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
      const holding = DASH.applyQuotes(holdings, market).find((item) => item.id === holdingId);
      if (!holding) return;
      const buying = direction === "buy";

      if (buying) {
        const availableCash = investCashMinor || 0;
        const fromCash = Math.min(availableCash, amountMinor);
        const fromAccount = amountMinor - fromCash;
        if (fromCash > 0) setInvestCashMinor((cash) => (cash || 0) - fromCash);
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
    }, [holdings, market, investCashMinor, creditAccount, bookMovement]);

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
          <DASH.Topbar
            screen={screen}
            username={firstName}
            me={me}
            ttsOn={ttsOn}
            onToggleTts={() => setTtsOn((value) => !value)}
            onOpenSettings={() => navigate("settings")}
            onSignOut={onSignOut}
          />

          <main className="dash-content" aria-label={t("dashboard.tag." + screen)}>
            {screen === "home" ? (
              <SCR.HomeScreen
                accounts={accounts}
                transactions={transactions}
                balanceHidden={balanceHidden}
                onToggleBalance={toggleBalance}
                onNavigate={navigate}
                onAddFunds={openAddFunds}
                onExchange={openExchange}
              />
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
                onSign={(payment) => { setSignFormError(null); setSigningPayment(payment); }}
              />
            ) : null}
            {screen === "chat" ? (
              <SCR.ChatScreen
                messages={messages}
                busy={chatBusy}
                draft={draft}
                onDraftChange={(event) => setDraft(event.target.value)}
                onSend={sendDraft}
                onKeyDown={(event) => { if (event.key === "Enter") sendDraft(); }}
                micOn={micOn}
                onToggleMic={() => setMicOn((value) => !value)}
                onPromptClick={onDockPrompt}
                onConfirmTx={confirmTx}
                username={firstName}
              />
            ) : null}
            {screen === "portfolio" ? (
              <SCR.PortfolioScreen
                accounts={accounts}
                deposits={deposits}
                credits={credits}
                holdings={pricedHoldings}
                investCashMinor={investCashMinor}
                creditApplications={creditApplications}
                market={market}
                marketLoading={marketLoading}
                marketError={marketError}
                onRefreshMarket={loadMarket}
                onOpenAccount={(typeKey) => {
                  setOpenAccountError(null);
                  setOpenAccountInitialType(typeKey || null);
                  setOpenAccountShown(true);
                }}
                onMoveDeposit={(deposit, direction) => setDepositMove({ deposit, direction })}
                onCloseDeposit={closeDeposit}
                onTrade={(holdingId, direction) => setTrade({ holdingId, direction })}
                onApplyCredit={() => setCreditShown(true)}
                onWithdrawApplication={withdrawApplication}
              />
            ) : null}
            {screen === "cards" ? (
              <SCR.CardsScreen
                cards={visibleCards}
                transactions={transactions}
                loading={cardsLoading && !cardsLoaded}
                error={cardsError}
                selectedCardId={selectedCardId}
                onSelect={selectCard}
                onOpenIssue={openIssueDialog}
                onOpenHistory={() => setHistoryOpen(true)}
                busy={cardBusy}
                onFreeze={freezeCard}
                onUnfreeze={unfreezeCard}
                onDelete={deleteCard}
                pin={cardPin}
                pinShown={pinShown}
                onTogglePin={toggleCardPin}
                cvv={cardCvv}
                detailsShown={detailsShown}
                onToggleDetails={toggleCardDetails}
                pinPromptOpen={pinPromptOpen}
                pinPromptBusy={pinPromptBusy}
                pinPromptError={pinPromptError}
                pinPromptTarget={pinPromptTarget}
                onConfirmLoginPin={confirmLoginPin}
                onCancelLoginPin={cancelLoginPin}
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
                me={me}
                onMeChange={setMe}
              />
            ) : null}
          </main>
        </div>

        {screen !== "chat" ? (
          <DASH.AgentDock
            open={dockOpen}
            username={firstName}
            screen={screen}
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
            holderName={displayName}
            busy={payBusy}
            error={payFormError}
            onClose={closePayment}
            onSubmit={submitPayment}
          />
        ) : null}

        {signingPayment ? (
          <DASH.SignPaymentDialog
            key={signingPayment.paymentId}
            payment={signingPayment}
            busy={signBusy}
            error={signFormError}
            onClose={closeSign}
            onSubmit={submitSignature}
          />
        ) : null}

        {splitOpen ? (
          <DASH.SplitBillDialog
            accounts={accounts}
            onClose={() => setSplitOpen(false)}
            onSubmit={createSplitBill}
          />
        ) : null}

        {addFundsShown ? (
          <DASH.AddFundsDialog
            account={accounts.find((account) => account.typeKey === "current" && account.cur === "RON") || accounts[0] || null}
            error={addFundsError}
            onClose={closeAddFunds}
            onSubmit={submitAddFunds}
          />
        ) : null}

        {exchangeShown ? (
          <DASH.ExchangeDialog
            accounts={accounts}
            busy={exchangeBusy}
            error={exchangeError}
            onClose={closeExchange}
            onSubmit={submitExchange}
          />
        ) : null}

        {openAccountShown ? (
          <DASH.OpenAccountDialog
            accounts={accounts}
            initialTypeKey={openAccountInitialType}
            busy={openAccountBusy}
            error={openAccountError}
            onClose={() => setOpenAccountShown(false)}
            onSubmit={openProduct}
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
            holdings={pricedHoldings}
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

        {issueOpen ? (
          <DASH.IssueCardDialog
            kind={issueKind}
            onKind={setIssueKind}
            onClose={() => setIssueOpen(false)}
            onCreate={createCard}
            creating={cardIssuing}
          />
        ) : null}

        {historyOpen ? (
          <DASH.CardHistoryDialog cards={deletedCards} onClose={() => setHistoryOpen(false)} />
        ) : null}
      </div>
    );
  };
})();
