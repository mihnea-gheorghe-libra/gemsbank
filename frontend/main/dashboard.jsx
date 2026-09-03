(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASHBOARD = (GEMS.dashboard = GEMS.dashboard || {});
  const DASH = GEMS.dashboardUi;
  const SCR = GEMS.dashboardScreens;
  const t = GEMS.i18n.t;
  const api = GEMS.api;
  const DATA = GEMS.dashboardData;
  const { useState, useCallback, useEffect, useMemo, useRef } = React;

  const SCREENS = ["home", "payments", "chat", "accounts", "portfolio", "cards", "analytics", "education", "settings"];
  const MARKET_AUTO_REFRESH_MS = 60000;

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

  const PROMPT_SETS = {
    payments: ["balanceTotal", "moveToSavings", "recentSpending"],
    analytics: ["whyHigher", "monthRecap", "cashflow"],
    cards: ["freezeCard", "cardLimits", "newVirtualCard"],
    investments: ["marketMonth", "investAccount", "btcPrice"],
    deposits: ["depositRates", "depositMaturity", "savingsGoal"],
    credits: ["loanCost", "creditOptions", "creditMax"],
    support: ["changePin", "activeSessions", "changeLanguage"],
  };

  const SCREEN_PROMPTS = {
    home: "payments",
    payments: "payments",
    analytics: "analytics",
    cards: "cards",
    portfolio: "investments",
    settings: "support",
  };

  function promptKeysFor(screen, lastAgents) {
    const fromAgent = (lastAgents || []).find((name) => PROMPT_SETS[name]);
    if (fromAgent) return PROMPT_SETS[fromAgent];
    return PROMPT_SETS[SCREEN_PROMPTS[screen] || "payments"];
  }

  function totalsByCurrency(accounts) {
    const grouped = {};
    accounts.forEach((account) => {
      grouped[account.cur] = (grouped[account.cur] || 0) + account.minor;
    });
    return Object.keys(grouped)
      .sort()
      .map((currency) => DASH.formatMinor(grouped[currency]) + " " + currency)
      .join(" · ");
  }

  function seedMessage(name, accounts, pending, ready) {
    if (!ready || !accounts.length) {
      return t("dashboard.chat.seedPlain");
    }
    const opening = t(
      accounts.length === 1 ? "dashboard.chat.seedAccountOne" : "dashboard.chat.seedAccounts",
      {
        name,
        count: GEMS.i18n.countFor(accounts.length),
        totals: totalsByCurrency(accounts),
      }
    );
    const waiting = (pending || []).length;
    const tail = !waiting
      ? t("dashboard.chat.seedPendingNone")
      : t(
          waiting === 1 ? "dashboard.chat.seedPendingOne" : "dashboard.chat.seedPendingSome",
          { count: GEMS.i18n.countFor(waiting) }
        );
    return opening + " " + tail;
  }

  const MAX_HISTORY_TURNS = 10;
  const MAX_RECORDING_MS = 60000;
  const RECORDER_MIME_TYPES = ["audio/webm", "audio/mp4", "audio/ogg"];

  function recorderMimeType() {
    if (typeof window.MediaRecorder === "undefined") return null;
    const supported = window.MediaRecorder.isTypeSupported;
    if (!supported) return "";
    return RECORDER_MIME_TYPES.filter((type) => supported(type))[0] || "";
  }

  function canRecord() {
    return Boolean(
      navigator.mediaDevices &&
        navigator.mediaDevices.getUserMedia &&
        typeof window.MediaRecorder !== "undefined"
    );
  }

  function transcriptOf(messages) {
    return messages
      .filter((message) => message.kind === "text" || message.kind === "proposal")
      .filter((message) => typeof message.text === "string" && message.text.trim() !== "")
      .slice(-MAX_HISTORY_TURNS)
      .map((message) => ({
        role: message.role === "user" ? "user" : "assistant",
        content: message.text,
      }));
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
    return new Intl.DateTimeFormat("ro-RO", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
      .format(moment)
      .replace(/\//g, ".");
  }

  function mapAccountRow(account) {
    return {
      id: account.accountId,
      cur: account.currency,
      typeKey: account.kind,
      label: account.label,
      minor: account.balance.minorUnits,
      iban: account.iban,
      ibanShort: account.ibanMasked,
      status: account.status,
    };
  }

  function mapTermDepositRow(deposit) {
    return {
      id: deposit.depositId,
      accountId: deposit.accountId,
      parentAccountId: deposit.parentAccountId,
      name: deposit.name,
      rateBps: deposit.rateBps,
      termMonths: deposit.termMonths,
      matures: deposit.maturesAt,
      cur: deposit.currency,
      minor: deposit.balance.minorUnits,
    };
  }

  function mapCreditApplicationRow(application) {
    return {
      id: application.applicationId,
      productId: application.productId,
      kind: application.kind,
      amountMinor: application.amount.minorUnits,
      cur: application.amount.currency,
      termMonths: application.termMonths,
      rateBps: application.rateBps,
      purpose: application.purpose,
      payoutAccountId: application.payoutAccountId,
      status: application.status,
      submitted: (application.submittedAt || "").slice(0, 10),
      decisionReason: application.decisionReason,
      decidedAt: (application.decidedAt || "").slice(0, 10),
    };
  }

  function mapMovementRow(row) {
    return {
      date: formatApiDate(row.postedAt),
      who: row.counterparty,
      ref: row.reference,
      iban: row.iban || "",
      categoryKey: row.category,
      statusKey: row.status,
      minor: Math.abs(row.amount.minorUnits),
      currency: row.amount.currency,
      direction: row.direction === "credit" ? "in" : "out",
      channel: "transfer",
      accountId: row.accountId,
      repeatable: row.direction === "debit" && Boolean(row.iban),
    };
  }

  function mapTemplateRow(template) {
    return {
      id: template.templateId,
      name: template.name,
      beneficiary: template.beneficiary,
      iban: template.iban,
      cur: template.currency,
      reference: template.reference,
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
    const [accounts, setAccounts] = useState([]);
    const [transactions, setTransactions] = useState(DATA.transactions);
    const [pending, setPending] = useState(DATA.pending);
    const [templates, setTemplates] = useState(DATA.templates);
    const [templatesError, setTemplatesError] = useState(null);
    const [templatesBusy, setTemplatesBusy] = useState(false);
    const [templatesDialogError, setTemplatesDialogError] = useState(null);
    const [splitBills, setSplitBills] = useState([]);
    const [termDeposits, setTermDeposits] = useState([]);
    const [depositMoveBusy, setDepositMoveBusy] = useState(false);
    const [depositMoveError, setDepositMoveError] = useState(null);
    const [depositActionError, setDepositActionError] = useState(null);
    const [quickTransferShown, setQuickTransferShown] = useState(false);
    const [quickTransferBusy, setQuickTransferBusy] = useState(false);
    const [quickTransferError, setQuickTransferError] = useState(null);
    const [investAccountId, setInvestAccountId] = useState(null);
    const [investCashMinor, setInvestCashMinor] = useState(null);
    const [investQuantities, setInvestQuantities] = useState({});
    const [tradeBusy, setTradeBusy] = useState(false);
    const [tradeError, setTradeError] = useState(null);
    const [market, setMarket] = useState(null);
    const [marketLoading, setMarketLoading] = useState(false);
    const [marketError, setMarketError] = useState(null);
    const [creditApplications, setCreditApplications] = useState([]);
    const [creditApplyBusy, setCreditApplyBusy] = useState(false);
    const [creditApplyError, setCreditApplyError] = useState(null);
    const [creditActionError, setCreditActionError] = useState(null);
    const [openAccountShown, setOpenAccountShown] = useState(false);
    const [openAccountInitialType, setOpenAccountInitialType] = useState(null);
    const [accountToClose, setAccountToClose] = useState(null);
    const [closeAccountBusy, setCloseAccountBusy] = useState(false);
    const [closeAccountError, setCloseAccountError] = useState(null);
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
    const [micBusy, setMicBusy] = useState(false);
    const [micError, setMicError] = useState(null);
    const recorderRef = useRef(null);
    const [draft, setDraft] = useState("");
    const [chatBusy, setChatBusy] = useState(false);
    const [lastAgents, setLastAgents] = useState([]);
    const [dataLoaded, setDataLoaded] = useState(false);
    const [messages, setMessages] = useState([
      { role: "ai", kind: "text", text: t("dashboard.chat.seedPlain") },
    ]);
    const [playingMessageIndex, setPlayingMessageIndex] = useState(null);
    const [ttsBusyIndex, setTtsBusyIndex] = useState(null);
    const audioPlayerRef = useRef(null);
    const audioCacheRef = useRef(new Map());
    const abortControllerRef = useRef(null);
    const [me, setMe] = useState(null);
    const [insights, setInsights] = useState([]);
    const [insightHistory, setInsightHistory] = useState([]);
    const [fxInsights, setFxInsights] = useState([]);
    const [fxInsightHistory, setFxInsightHistory] = useState([]);
    const [payBusy, setPayBusy] = useState(false);
    const [payFormError, setPayFormError] = useState(null);
    const [signingPayment, setSigningPayment] = useState(null);
    const [signBusy, setSignBusy] = useState(false);
    const [signFormError, setSignFormError] = useState(null);
    const [openAccountBusy, setOpenAccountBusy] = useState(false);
    const [openAccountError, setOpenAccountError] = useState(null);
    const [addFundsShown, setAddFundsShown] = useState(false);
    const [addFundsBusy, setAddFundsBusy] = useState(false);
    const [addFundsError, setAddFundsError] = useState(null);
    const [statementOpen, setStatementOpen] = useState(false);
    const [statementAccount, setStatementAccount] = useState(null);
    const [statementBusy, setStatementBusy] = useState(false);
    const [statementError, setStatementError] = useState(null);
    const [exchangeShown, setExchangeShown] = useState(false);
    const [exchangeBusy, setExchangeBusy] = useState(false);
    const [exchangeError, setExchangeError] = useState(null);
    const [secureTimer, setSecureTimer] = useState(0);

    useEffect(() => {
      if (detailsShown || pinShown) {
        setSecureTimer(30);
        const interval = setInterval(() => {
          setSecureTimer((prev) => {
            if (prev <= 1) {
              setDetailsShown(false);
              setPinShown(false);
              return 0;
            }
            return prev - 1;
          });
        }, 1000);
        return () => clearInterval(interval);
      } else {
        setSecureTimer(0);
      }
    }, [detailsShown, pinShown]);

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

    useEffect(() => {
      let cancelled = false;
      api
        .listInsights()
        .then((response) => {
          if (!cancelled && response) {
            setInsights(response.insights || []);
            setInsightHistory(response.history || []);
            setFxInsights((response.fx && response.fx.insights) || []);
            setFxInsightHistory((response.fx && response.fx.history) || []);
          }
        })
        .catch(() => {});
      return () => {
        cancelled = true;
      };
    }, [username]);

    const loadPortfolio = useCallback(async () => {
      try {
        const data = await api.investPortfolio();
        const primary = data.accounts[0] || null;
        setInvestAccountId(primary ? primary.accountId : null);
        setInvestCashMinor(primary ? primary.cashBalanceMinor : null);
        const quantities = {};
        (primary ? primary.holdings : []).forEach((holding) => {
          quantities[holding.instrumentId] = holding.quantityMicro;
        });
        setInvestQuantities(quantities);
      } catch (err) {
        if (err && err.status === 404) {
          setInvestAccountId(null);
          setInvestCashMinor(null);
          setInvestQuantities({});
          return;
        }
        throw err;
      }
    }, []);

    const loadPaymentsData = useCallback(async () => {
      const [accountList, txList, pendingList, templateList, depositList, creditList] = await Promise.all([
        api.listAccounts(),
        api.listTransactions({}),
        api.listPending(),
        api.listTemplates(),
        api.listTermDeposits(),
        api.listCreditApplications(),
      ]);
      setAccounts(accountList.accounts.map(mapAccountRow).filter((account) => account.status !== "closed"));
      setTransactions(pendingList.pending.map(mapPendingSignatureRow).concat(txList.transactions.map(mapMovementRow)));
      setPending(pendingList.pending);
      setTemplates(templateList.templates.map(mapTemplateRow));
      setTermDeposits(depositList.deposits.map(mapTermDepositRow));
      setCreditApplications(creditList.applications.map(mapCreditApplicationRow));

      await loadPortfolio();
      setDataLoaded(true);
    }, [loadPortfolio]);

    useEffect(() => {
      loadPaymentsData().catch(() => {});
    }, [username, loadPaymentsData]);

    const displayName = (me && me.identity && me.identity.fullName) || (me && me.fullName) || username;
    const firstName = GEMS.people.firstName(displayName) || username;

    const navigate = useCallback((key) => {
      if (SCREENS.indexOf(key) >= 0) {
        if (key === "chat" && screen !== "chat") {
          setMessages((list) =>
            list.some((message) => message.role === "user")
              ? list
              : [
                  {
                    role: "ai",
                    kind: "text",
                    text: seedMessage(firstName, accounts, pending, dataLoaded),
                  },
                ]
          );
        }
        setScreen(key);
        setBalanceHidden(true);
      }
    }, [screen, firstName, accounts, pending, dataLoaded]);

    const toggleBalance = useCallback(() => {
      setBalanceHidden((hidden) => !hidden);
    }, []);

    const stopSpeaking = useCallback(() => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current.currentTime = 0;
        audioPlayerRef.current = null;
      }
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
      setPlayingMessageIndex(null);
      setTtsBusyIndex(null);
    }, []);

    const speakWithBrowserVoice = useCallback((text, index) => {
      if (!window.speechSynthesis) return;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB";
      utterance.onend = () => setPlayingMessageIndex(null);
      utterance.onerror = () => setPlayingMessageIndex(null);
      setPlayingMessageIndex(index);
      window.speechSynthesis.speak(utterance);
    }, []);

    const speakMessage = useCallback(async (text, index) => {
      const clean = (text || "").trim();
      if (!clean) return;
      if (playingMessageIndex === index || ttsBusyIndex === index) {
        stopSpeaking();
        return;
      }
      stopSpeaking();
      setTtsBusyIndex(index);
      const controller = new AbortController();
      abortControllerRef.current = controller;
      try {
        let blobUrl = audioCacheRef.current.get(clean);
        if (!blobUrl) {
          const blob = await api.synthesizeSpeech(clean, GEMS.i18n.locale, null, controller.signal);
          blobUrl = URL.createObjectURL(blob);
          audioCacheRef.current.set(clean, blobUrl);
        }
        if (controller.signal.aborted) return;
        const audio = new Audio(blobUrl);
        audioPlayerRef.current = audio;
        setPlayingMessageIndex(index);
        setTtsBusyIndex(null);
        audio.onended = () => {
          setPlayingMessageIndex(null);
          audioPlayerRef.current = null;
        };
        audio.onerror = () => {
          audioPlayerRef.current = null;
          if (!controller.signal.aborted) speakWithBrowserVoice(clean, index);
          else setPlayingMessageIndex(null);
        };
        await audio.play();
      } catch (error) {
        if (controller.signal.aborted) return;
        setTtsBusyIndex(null);
        speakWithBrowserVoice(clean, index);
      }
    }, [playingMessageIndex, ttsBusyIndex, stopSpeaking, speakWithBrowserVoice]);

    const pushExchange = useCallback((userText, reply) => {
      setMessages((list) => {
        const nextIndex = list.length + 1;
        if (ttsOn && reply && reply.text) {
          setTimeout(() => speakMessage(reply.text, nextIndex), 50);
        }
        return list.concat([{ role: "user", kind: "text", text: userText }, reply]);
      });
      setScreen("chat");
      setBalanceHidden(true);
    }, [ttsOn, speakMessage]);

    const stopRecording = useCallback(() => {
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.stop();
        return;
      }
      recorderRef.current = null;
      setMicOn(false);
    }, []);

    const startRecording = useCallback(async () => {
      setMicError(null);
      if (!canRecord()) {
        setMicError(t("dashboard.chat.micUnsupported"));
        return;
      }
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (error) {
        setMicError(t("dashboard.chat.micDenied"));
        return;
      }
      const mimeType = recorderMimeType();
      const recorder = new window.MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks = [];
      const stopTimer = setTimeout(() => {
        if (recorder.state !== "inactive") recorder.stop();
      }, MAX_RECORDING_MS);

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size) chunks.push(event.data);
      };
      recorder.onstop = () => {
        clearTimeout(stopTimer);
        stream.getTracks().forEach((track) => track.stop());
        recorderRef.current = null;
        setMicOn(false);
        const type = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunks, { type });
        if (!blob.size) return;
        setMicBusy(true);
        api
          .transcribeVoice(blob, GEMS.i18n.locale)
          .then((result) => {
            const text = ((result && result.text) || "").trim();
            if (!text) {
              setMicError(t("dashboard.chat.micEmpty"));
              return;
            }
            setDraft((current) => (current.trim() ? current.trim() + " " + text : text));
          })
          .catch((error) => {
            setMicError(
              error && error.code === "rate_limited"
                ? t("dashboard.chat.micRateLimited")
                : t("dashboard.chat.micFailed")
            );
          })
          .finally(() => setMicBusy(false));
      };

      recorderRef.current = recorder;
      recorder.start();
      setMicOn(true);
    }, []);

    const toggleMic = useCallback(() => {
      if (micBusy) return;
      if (micOn) stopRecording();
      else {
        stopSpeaking();
        startRecording();
      }
    }, [micOn, micBusy, startRecording, stopRecording, stopSpeaking]);

    useEffect(() => {
      if (screen !== "chat") {
        stopRecording();
        stopSpeaking();
      }
    }, [screen, stopRecording, stopSpeaking]);

    useEffect(() => {
      return () => {
        stopRecording();
        stopSpeaking();
      };
    }, [stopRecording, stopSpeaking]);

    const sendQuestion = useCallback((raw) => {
      const text = String(raw || "").trim();
      if (!text || chatBusy) return;
      const history = transcriptOf(messages);
      const origin = screen;
      stopSpeaking();
      setMessages((list) => list.concat([{ role: "user", kind: "text", text }]));
      setScreen("chat");
      setBalanceHidden(true);
      setChatBusy(true);
      api
        .askGems(text, history, origin)
        .then((result) => {
          const proposal = (result.proposals || []).filter(
            (item) => item && item.status === "proposed"
          )[0];
          const escalation = result.escalation || {};
          const escalated = Boolean(escalation.offered);
          const answer = (result.answer || "").trim() || (escalated ? t("dashboard.chat.handoffOffered") : t("dashboard.chat.errorNote"));
          setLastAgents(result.agentsUsed || []);
          setMessages((list) => {
            const nextIndex = list.length;
            if (ttsOn && answer) {
              setTimeout(() => speakMessage(answer, nextIndex), 50);
            }
            return list.concat([
              proposal
                ? { role: "ai", kind: "proposal", text: answer, proposal, aiGenerated: true }
                : { role: "ai", kind: "text", text: answer, aiGenerated: true, escalated },
            ]);
          });
        })
        .catch((error) => {
          const retryAfter = error && error.details && error.details.retryAfterSeconds;
          const note =
            error && error.code === "rate_limited"
              ? t("dashboard.chat.rateLimitedNote", {
                  minutes: Math.max(1, Math.ceil((retryAfter || 60) / 60)),
                })
              : t("dashboard.chat.errorNote");
          setMessages((list) => {
            const nextIndex = list.length;
            if (ttsOn && note) {
              setTimeout(() => speakMessage(note, nextIndex), 50);
            }
            return list.concat([{ role: "ai", kind: "text", text: note }]);
          });
        })
        .finally(() => setChatBusy(false));
    }, [chatBusy, messages, screen, stopSpeaking, ttsOn, speakMessage]);

    const sendDraft = useCallback(() => {
      const text = draft.trim();
      if (!text || chatBusy || micOn) return;
      setDraft("");
      sendQuestion(text);
    }, [draft, chatBusy, micOn, sendQuestion]);

    const onDockPrompt = useCallback((key) => {
      const prompt = DATA.chatPrompts[key];
      const label = prompt ? t("dashboard.chat." + prompt.labelKey) : "";
      pushExchange(label, answerFor(key));
    }, [pushExchange]);

    const chatPrompts = React.useMemo(
      () =>
        promptKeysFor(screen, lastAgents).map((key) => ({
          key,
          label: t("dashboard.chat.suggest." + key),
        })),
      [screen, lastAgents]
    );

    const askSuggestion = useCallback((label) => sendQuestion(label), [sendQuestion]);

    const clearChat = useCallback(() => {
      stopSpeaking();
      audioCacheRef.current.forEach((url) => URL.revokeObjectURL(url));
      audioCacheRef.current.clear();
      setDraft("");
      setLastQuestion("");
      setLastAgents([]);
      setHandoffSent(false);
      setChatBusy(false);
      setMessages([
        {
          role: "ai",
          kind: "text",
          text: seedMessage(firstName, accounts, pending, dataLoaded),
        },
      ]);
    }, [stopSpeaking, firstName, accounts, pending, dataLoaded]);

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
        const response = await api.listCards();
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

    const marketLoadingRef = useRef(marketLoading);
    useEffect(() => {
      marketLoadingRef.current = marketLoading;
    }, [marketLoading]);

    useEffect(() => {
      if (screen !== "portfolio") return undefined;
      const interval = setInterval(() => {
        if (!marketLoadingRef.current) loadMarket();
      }, MARKET_AUTO_REFRESH_MS);
      return () => clearInterval(interval);
    }, [screen, loadMarket]);

    const pricedHoldings = useMemo(() => {
      if (!market || !market.quotes) return [];
      return market.quotes.map((quote) => ({
        id: quote.id,
        name: quote.name,
        symbol: quote.symbol,
        unitKey: quote.unitKey,
        cur: quote.currency,
        quoteCurrency: quote.quoteCurrency,
        quoteUnitPriceMinor: quote.quoteUnitPriceMinor,
        unitPriceMinor: quote.unitPriceMinor,
        changeBps: quote.changeBps,
        history: quote.history,
        live: quote.live,
        asOf: quote.asOf,
        units: (investQuantities[quote.id] || 0) / 1000000,
      }));
    }, [market, investQuantities]);

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

    const createCard = useCallback(async (accountId) => {
      setCardIssuing(true);
      setCardsError(null);
      try {
        const card = issueKind === "physical"
          ? await api.issuePhysicalCard(accountId)
          : await api.issueVirtualCard(accountId);
        setCards((list) => list.concat([card]));
        selectCard(card.cardId);
        setIssueOpen(false);
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardIssuing(false);
      }
    }, [issueKind, selectCard]);

    const freezeCard = useCallback(async () => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        applyCard(await api.freezeCard(selectedCardId));
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
        applyCard(await api.unfreezeCard(selectedCardId));
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard]);

    const deleteCard = useCallback(async () => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        const updated = await api.blockCard(selectedCardId);
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
        const result = await api.revealCardPin(selectedCardId);
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

    const promptFreezeCard = useCallback(() => {
      if (!selectedCardId) return;
      setPinPromptError(null);
      setPinPromptTarget("freezeCard");
      setPinPromptOpen(true);
    }, [selectedCardId]);

    const promptUnfreezeCard = useCallback(() => {
      if (!selectedCardId) return;
      setPinPromptError(null);
      setPinPromptTarget("unfreezeCard");
      setPinPromptOpen(true);
    }, [selectedCardId]);

    const promptDeleteCard = useCallback(() => {
      if (!selectedCardId) return;
      setPinPromptError(null);
      setPinPromptTarget("blockCard");
      setPinPromptOpen(true);
    }, [selectedCardId]);

    const revealCardDetails = useCallback(async () => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        const result = await api.revealCardDetails(selectedCardId);
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
        } else if (pinPromptTarget === "freezeCard") {
          setPinPromptOpen(false);
          await freezeCard();
        } else if (pinPromptTarget === "unfreezeCard") {
          setPinPromptOpen(false);
          await unfreezeCard();
        } else if (pinPromptTarget === "blockCard") {
          setPinPromptOpen(false);
          await deleteCard();
        } else {
          setPinPromptOpen(false);
          if (pinPromptTarget === "details") await revealCardDetails();
        }
      } catch (err) {
        setPinPromptError(err);
      } finally {
        setPinPromptBusy(false);
      }
    }, [username, pinPromptTarget, revealCardPin, revealCardDetails, freezeCard, unfreezeCard, deleteCard]);

    const cancelLoginPin = useCallback(() => {
      setPinPromptOpen(false);
      setPinPromptError(null);
      setPinShown(false);
    }, []);

    const setCardAtmLimit = useCallback(async (minor) => {
      if (!selectedCardId) return;
      setCardBusy(true);
      setCardsError(null);
      try {
        applyCard(await api.setCardAtmLimit(selectedCardId, minor));
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
        applyCard(await api.setCardOnlineLimit(selectedCardId, minor));
      } catch (err) {
        setCardsError(err);
      } finally {
        setCardBusy(false);
      }
    }, [username, selectedCardId, applyCard]);

    const visibleCards = cards.filter((row) => row.state !== "blocked");
    const deletedCards = cards
      .filter((row) => row.state === "blocked")
      .sort((a, b) => {
        const dateA = a.deletedAt || a.updatedAt || a.createdAt || "";
        const dateB = b.deletedAt || b.updatedAt || b.createdAt || "";
        return dateB.localeCompare(dateA);
      });
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

    const confirmCardProposal = useCallback(async (proposal) => {
      const cardId = proposal.cardId;
      if (proposal.action === "reveal_pin" || proposal.action === "reveal_details") {
        setSelectedCardId(cardId);
        navigate("cards");
        return;
      }
      setCardBusy(true);
      setCardsError(null);
      try {
        if (proposal.action === "issue_virtual") {
          const card = await api.issueVirtualCard();
          setCards((list) => list.concat([card]));
        } else if (proposal.action === "issue_physical") {
          const card = await api.issuePhysicalCard();
          setCards((list) => list.concat([card]));
        } else if (proposal.action === "freeze") {
          applyCard(await api.freezeCard(cardId));
        } else if (proposal.action === "unfreeze") {
          applyCard(await api.unfreezeCard(cardId));
        } else if (proposal.action === "block") {
          applyCard(await api.blockCard(cardId));
        } else if (proposal.action === "set_atm_limit") {
          applyCard(await api.setCardAtmLimit(cardId, proposal.limitMinorUnits));
        } else if (proposal.action === "set_online_limit") {
          applyCard(await api.setCardOnlineLimit(cardId, proposal.limitMinorUnits));
        }
        setMessages((list) =>
          list.concat([{ role: "ai", kind: "text", text: t("dashboard.chat.cardActionDone") }])
        );
      } catch (error) {
        setMessages((list) =>
          list.concat([
            {
              role: "ai",
              kind: "text",
              text: GEMS.i18n.tError((error && error.message) || "") || t("dashboard.chat.cardActionFailed"),
            },
          ])
        );
      } finally {
        setCardBusy(false);
      }
    }, [applyCard, navigate]);

    const confirmProposal = useCallback((proposal) => {
      if (!proposal) return;
      if (proposal.action) {
        confirmCardProposal(proposal);
        return;
      }
      const internal = Boolean(proposal.targetAccountId);
      openPayment({
        payType: internal ? "internal" : "iban",
        fromId: proposal.sourceAccountId,
        toId: proposal.targetAccountId || "",
        beneficiary: proposal.counterparty || "",
        iban: internal ? "" : proposal.targetIban || "",
        reference: proposal.reference || "",
        amount: DASH.formatMinor(proposal.amountMinorUnits),
      });
    }, [openPayment, confirmCardProposal]);

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

        if (payment.template) {
          api
            .createTemplate({
              name: payment.template.name,
              beneficiary: payment.template.beneficiary,
              iban: payment.template.iban,
              currency: payment.template.cur,
              reference: payment.template.reference,
            })
            .then((created) => setTemplates((list) => list.concat([mapTemplateRow(created.data || created)])))
            .catch(() => {});
        }
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
        await api.signTransfer(paymentId, pin);
        setSigningPayment(null);
        await loadPaymentsData();
      } catch (err) {
        setSignFormError(err);
      } finally {
        setSignBusy(false);
      }
    }, [loadPaymentsData]);

    const useTemplate = useCallback((template) => {
      const match = accounts.find((account) => account.cur === template.cur) || accounts[0] || null;
      openPayment({
        payType: "iban",
        beneficiary: template.beneficiary,
        iban: template.iban,
        reference: template.reference,
        fromId: match ? match.id : "",
      });
    }, [accounts, openPayment]);

    const repeatPayment = useCallback((transaction) => {
      const account = accounts.find((item) => item.id === transaction.accountId);
      if (!account || !transaction.repeatable) return;
      openPayment({
        payType: "iban",
        fromId: account.id,
        beneficiary: transaction.who,
        iban: transaction.iban,
        reference: transaction.ref,
        amount: DASH.formatMinor(transaction.minor),
      });
    }, [accounts, openPayment]);

    const saveTemplate = useCallback(async (template) => {
      const known = templates.some((item) => item.id === template.id);
      const payload = {
        name: template.name,
        beneficiary: template.beneficiary,
        iban: template.iban,
        currency: template.cur,
        reference: template.reference,
      };
      setTemplatesBusy(true);
      setTemplatesDialogError(null);
      try {
        const saved = known
          ? await api.updateTemplate(template.id, payload)
          : await api.createTemplate(payload);
        const mapped = mapTemplateRow(saved.data || saved);
        setTemplates((list) =>
          known ? list.map((item) => (item.id === template.id ? mapped : item)) : list.concat([mapped])
        );
        setTemplateOpen(false);
        setTemplateDraft(null);
      } catch (err) {
        setTemplatesDialogError(err);
      } finally {
        setTemplatesBusy(false);
      }
    }, [templates]);

    const deleteTemplate = useCallback(async (templateId) => {
      setTemplatesError(null);
      try {
        await api.deleteTemplate(templateId);
        setTemplates((list) => list.filter((item) => item.id !== templateId));
      } catch (err) {
        setTemplatesError(err);
      }
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

    const openAddFunds = useCallback(() => {
      setAddFundsError(null);
      setAddFundsShown(true);
    }, []);

    const closeAddFunds = useCallback(() => {
      setAddFundsShown(false);
      setAddFundsError(null);
    }, []);

    const submitAddFunds = useCallback(async (amountMinor) => {
      const target = accounts.find((account) => account.typeKey === "current" && account.cur === "RON") || accounts[0];
      if (!target) {
        setAddFundsError({ message: t("dashboard.addFunds.noAccount") });
        return;
      }
      setAddFundsBusy(true);
      setAddFundsError(null);
      try {
        await api.addFunds(target.id, amountMinor);
        closeAddFunds();
        await loadPaymentsData();
      } catch (err) {
        setAddFundsError(err);
      } finally {
        setAddFundsBusy(false);
      }
    }, [accounts, closeAddFunds, loadPaymentsData]);

    const openStatement = useCallback((account) => {
      setStatementError(null);
      setStatementAccount(account || null);
      setStatementOpen(true);
    }, []);

    const closeStatement = useCallback(() => {
      setStatementOpen(false);
      setStatementAccount(null);
      setStatementError(null);
    }, []);

    const submitStatement = useCallback(async (payload) => {
      setStatementBusy(true);
      setStatementError(null);
      try {
        const { blob, filename } = await api.downloadStatement(
          payload.accountId, payload.format, payload.from, payload.to
        );
        DASH.saveBlob(blob, filename);
        closeStatement();
      } catch (err) {
        setStatementError(err);
      } finally {
        setStatementBusy(false);
      }
    }, [closeStatement]);

    const openExchange = useCallback(() => {
      setScreen("accounts");
      setQuickTransferError(null);
      setQuickTransferShown(true);
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
      setOpenAccountBusy(true);
      setOpenAccountError(null);
      try {
        const opened = await api.openAccount(account.cur, account.typeKey, account.label);
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
    }, [displayName, loadPaymentsData]);

    const requestCloseAccount = useCallback((account) => {
      setCloseAccountError(null);
      setAccountToClose(account);
    }, []);

    const cancelCloseAccount = useCallback(() => {
      setAccountToClose(null);
      setCloseAccountError(null);
    }, []);

    const confirmCloseAccount = useCallback(async (accountId) => {
      setCloseAccountBusy(true);
      setCloseAccountError(null);
      try {
        await api.closeAccount(accountId);
        setAccountToClose(null);
        await loadPaymentsData();
      } catch (err) {
        setCloseAccountError(err);
      } finally {
        setCloseAccountBusy(false);
      }
    }, [loadPaymentsData]);

    const createTermDeposit = useCallback(async (payload) => {
      setOpenAccountBusy(true);
      setOpenAccountError(null);
      try {
        await api.createTermDeposit(
          payload.parentAccountId,
          payload.name,
          payload.termMonths,
          payload.initialDepositMinorUnits
        );
        await loadPaymentsData();
        setOpenAccountShown(false);
      } catch (err) {
        setOpenAccountError(err);
      } finally {
        setOpenAccountBusy(false);
      }
    }, [loadPaymentsData]);

    const openProduct = useCallback(
      (payload) => (payload.termDeposit ? createTermDeposit(payload.termDeposit) : openAccount(payload)),
      [createTermDeposit, openAccount]
    );

    const moveDeposit = useCallback(async ({ depositId, amountMinor, direction, sourceAccountId }) => {
      setDepositMoveBusy(true);
      setDepositMoveError(null);
      try {
        if (direction === "in") {
          await api.topUpTermDeposit(depositId, amountMinor, sourceAccountId);
        } else {
          await api.withdrawFromTermDeposit(depositId, amountMinor);
        }
        await loadPaymentsData();
        setDepositMove(null);
      } catch (err) {
        setDepositMoveError(err);
      } finally {
        setDepositMoveBusy(false);
      }
    }, [loadPaymentsData]);

    const closeDeposit = useCallback(async (deposit) => {
      setDepositActionError(null);
      try {
        await api.closeTermDeposit(deposit.id);
        await loadPaymentsData();
      } catch (err) {
        setDepositActionError(err);
      }
    }, [loadPaymentsData]);

    const runTrade = useCallback(async ({ holdingId, amountMinor, direction }) => {
      if (!investAccountId) return;
      setTradeBusy(true);
      setTradeError(null);
      try {
        const call = direction === "buy" ? api.investBuy : api.investSell;
        await call({
          accountId: investAccountId,
          instrumentId: holdingId,
          amountMinorUnits: amountMinor,
        });
        await loadPaymentsData();
        setTrade(null);
      } catch (err) {
        setTradeError(err);
      } finally {
        setTradeBusy(false);
      }
    }, [investAccountId, loadPaymentsData]);

    const applyForCredit = useCallback(async (payload) => {
      setCreditApplyBusy(true);
      setCreditApplyError(null);
      try {
        await api.submitCreditApplication(payload);
        await loadPaymentsData();
        setCreditShown(false);
      } catch (err) {
        setCreditApplyError(err);
      } finally {
        setCreditApplyBusy(false);
      }
    }, [loadPaymentsData]);

    const withdrawApplication = useCallback(async (applicationId) => {
      setCreditActionError(null);
      try {
        await api.withdrawCreditApplication(applicationId);
        await loadPaymentsData();
      } catch (err) {
        setCreditActionError(err);
      }
    }, [loadPaymentsData]);

    const topUpAccount = useCallback((account) => {
      setQuickTransferError(null);
      setQuickTransferShown({ accountId: account.id, side: "target" });
    }, []);

    const withdrawFromAccount = useCallback((account) => {
      setQuickTransferError(null);
      setQuickTransferShown({ accountId: account.id, side: "source" });
    }, []);

    const quickTransfer = useCallback(async (payload) => {
      setQuickTransferBusy(true);
      setQuickTransferError(null);
      try {
        const response = await api.transfer({
          sourceAccountId: payload.sourceAccountId,
          targetAccountId: payload.targetAccountId,
          counterparty: displayName,
          amountMinorUnits: payload.amountMinor,
          reference: t("dashboard.accounts.quickTransferRef"),
          category: null,
          acknowledgePayeeMismatch: false,
        });
        await loadPaymentsData();
        setQuickTransferShown(false);
        if (response && response.status === "awaiting_signature") {
          setSignFormError(null);
          setSigningPayment(response);
        }
      } catch (err) {
        setQuickTransferError(err);
      } finally {
        setQuickTransferBusy(false);
      }
    }, [displayName, loadPaymentsData]);

    return (
      <div className="dash-shell">
        <DASH.Sidebar screen={screen} onNavigate={navigate} onSignOut={onSignOut} />

        <div className="dash-main">
          <DASH.Topbar
            screen={screen}
            username={firstName}
            me={me}
            theme={theme}
            onTheme={onTheme}
            ttsOn={ttsOn}
            onToggleTts={() => setTtsOn((value) => !value)}
            onOpenSettings={() => navigate("settings")}
            onSignOut={onSignOut}
          />

          <main key={screen} className="dash-content" aria-label={t("dashboard.tag." + screen)}>
            {screen === "home" ? (
              <SCR.HomeScreen
                accounts={accounts}
                transactions={transactions}
                balanceHidden={balanceHidden}
                onToggleBalance={toggleBalance}
                onNavigate={navigate}
                onAddFunds={openAddFunds}
                onExchange={openExchange}
                onOpenAccount={() => {
                  setScreen("accounts");
                  setOpenAccountError(null);
                  setOpenAccountInitialType(null);
                  setOpenAccountShown(true);
                }}
                insights={insights}
                insightHistory={insightHistory}
                fxInsights={fxInsights}
                fxInsightHistory={fxInsightHistory}
                lang={lang}
              />
            ) : null}
            {screen === "payments" ? (
              <SCR.PaymentsScreen
                accounts={accounts}
                transactions={transactions}
                pending={pending}
                templates={templates}
                templatesError={templatesError}
                splitBills={splitBills}
                filter={filter}
                onFilter={setFilter}
                query={query}
                onQuery={setQuery}
                onOpenPay={() => openPayment(null)}
                onOpenSplit={() => setSplitOpen(true)}
                onNewTemplate={() => { setTemplateDraft(null); setTemplatesDialogError(null); setTemplateOpen(true); }}
                onEditTemplate={(template) => { setTemplateDraft(template); setTemplatesDialogError(null); setTemplateOpen(true); }}
                onDeleteTemplate={deleteTemplate}
                onUseTemplate={useTemplate}
                onRepeat={repeatPayment}
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
                onKeyDown={(event) => { if (event.key === "Enter" && !event.nativeEvent.isComposing) sendDraft(); }}
                micOn={micOn}
                micBusy={micBusy}
                micError={micError}
                onToggleMic={toggleMic}
                prompts={chatPrompts}
                onPromptClick={askSuggestion}
                onConfirmTx={confirmTx}
                onConfirmProposal={confirmProposal}
                username={firstName}
                ttsOn={ttsOn}
                onToggleTts={() => setTtsOn((value) => !value)}
                playingMessageIndex={playingMessageIndex}
                ttsBusyIndex={ttsBusyIndex}
                onSpeakMessage={speakMessage}
                onStopSpeaking={stopSpeaking}
                onClearChat={clearChat}
              />
            ) : null}
            {screen === "accounts" ? (
              <SCR.AccountsScreen
                accounts={accounts}
                termDeposits={termDeposits}
                depositActionError={depositActionError}
                creditApplications={creditApplications}
                creditActionError={creditActionError}
                onOpenAccount={(typeKey) => {
                  setOpenAccountError(null);
                  setOpenAccountInitialType(typeKey || null);
                  setOpenAccountShown(true);
                }}
                onMoveDeposit={(deposit, direction) => { setDepositMoveError(null); setDepositMove({ deposit, direction }); }}
                onCloseDeposit={closeDeposit}
                onApplyCredit={() => { setCreditApplyError(null); setCreditShown(true); }}
                onWithdrawApplication={withdrawApplication}
                onOpenStatement={openStatement}
                onDeleteAccount={requestCloseAccount}
                onOpenQuickTransfer={() => { setQuickTransferError(null); setQuickTransferShown(true); }}
                onTopUpAccount={topUpAccount}
                onWithdrawAccount={withdrawFromAccount}
              />
            ) : null}
            {screen === "portfolio" ? (
              <SCR.PortfolioScreen
                holdings={pricedHoldings}
                investCashMinor={investCashMinor}
                hasInvestAccount={Boolean(investAccountId)}
                market={market}
                marketLoading={marketLoading}
                marketError={marketError}
                onRefreshMarket={loadMarket}
                onTrade={(holdingId, direction) => setTrade({ holdingId, direction })}
                onOpenAccount={(typeKey) => {
                  setScreen("accounts");
                  setOpenAccountError(null);
                  setOpenAccountInitialType(typeKey || null);
                  setOpenAccountShown(true);
                }}
              />
            ) : null}
            {screen === "cards" ? (
              <SCR.CardsScreen
                cards={visibleCards}
                accounts={accounts}
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
                onDelete={promptDeleteCard}
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
                secureTimer={secureTimer}
              />
            ) : null}
            {screen === "analytics" ? <SCR.AnalyticsScreen range={range} onRange={setRange} accounts={accounts} /> : null}
            {screen === "education" ? <SCR.EducationScreen accounts={accounts} /> : null}
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
            key={payPrefill ? (payPrefill.iban || payPrefill.toId || "prefill") : "blank"}
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
            busy={addFundsBusy}
            error={addFundsError}
            onClose={closeAddFunds}
            onSubmit={submitAddFunds}
          />
        ) : null}

        {statementOpen ? (
          <DASH.StatementDialog
            account={statementAccount}
            accounts={accounts}
            busy={statementBusy}
            error={statementError}
            onClose={closeStatement}
            onSubmit={submitStatement}
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

        {accountToClose ? (
          <DASH.DeleteAccountDialog
            key={accountToClose.id}
            account={accountToClose}
            busy={closeAccountBusy}
            error={closeAccountError}
            onClose={cancelCloseAccount}
            onSubmit={confirmCloseAccount}
          />
        ) : null}

        {depositMove ? (
          <DASH.MoveDepositDialog
            key={depositMove.deposit.id + depositMove.direction}
            deposit={termDeposits.find((item) => item.id === depositMove.deposit.id) || depositMove.deposit}
            accounts={accounts}
            direction={depositMove.direction}
            busy={depositMoveBusy}
            error={depositMoveError}
            onClose={() => setDepositMove(null)}
            onSubmit={moveDeposit}
          />
        ) : null}

        {quickTransferShown ? (
          <DASH.QuickTransferDialog
            key={quickTransferShown === true ? "quick-transfer" : quickTransferShown.accountId + quickTransferShown.side}
            accounts={accounts}
            fixedAccountId={quickTransferShown === true ? null : quickTransferShown.accountId}
            fixedSide={quickTransferShown === true ? null : quickTransferShown.side}
            busy={quickTransferBusy}
            error={quickTransferError}
            onClose={() => setQuickTransferShown(false)}
            onSubmit={quickTransfer}
          />
        ) : null}

        {trade ? (
          <DASH.InvestDialog
            key={(trade.holdingId || "any") + trade.direction}
            holdings={pricedHoldings.filter((holding) => holding.units > 0 || trade.direction === "buy")}
            investCashMinor={investCashMinor}
            holdingId={trade.holdingId}
            direction={trade.direction}
            busy={tradeBusy}
            error={tradeError}
            onClose={() => {
              setTrade(null);
              setTradeError(null);
            }}
            onSubmit={runTrade}
          />
        ) : null}

        {creditShown ? (
          <DASH.CreditApplicationDialog
            accounts={accounts}
            busy={creditApplyBusy}
            error={creditApplyError}
            onClose={() => setCreditShown(false)}
            onSubmit={applyForCredit}
          />
        ) : null}

        {templateOpen ? (
          <DASH.TemplateDialog
            key={templateDraft ? templateDraft.id : "new"}
            accounts={accounts}
            template={templateDraft}
            busy={templatesBusy}
            error={templatesDialogError}
            onClose={() => { setTemplateOpen(false); setTemplateDraft(null); }}
            onSubmit={saveTemplate}
          />
        ) : null}

        {issueOpen ? (
          <DASH.IssueCardDialog
            kind={issueKind}
            onKind={setIssueKind}
            accounts={accounts}
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
