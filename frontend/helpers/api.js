(function () {
  const GEMS = (window.GEMS = window.GEMS || {});

  function newIdempotencyKey() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "k-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  class ApiError extends Error {
    constructor(payload, status) {
      super((payload && payload.message) || "Request failed");
      this.name = "ApiError";
      this.status = status;
      this.code = (payload && payload.code) || "unknown";
      this.details = (payload && payload.details) || {};
      this.correlationId = payload && payload.correlationId;
    }
  }

  async function parse(response) {
    let body = null;
    try {
      body = await response.json();
    } catch (err) {
      body = null;
    }
    if (!response.ok) {
      throw new ApiError(body && body.error, response.status);
    }
    return body;
  }

  let sessionToken = null;

  GEMS.session = {
    set(token) {
      sessionToken = token || null;
    },
    clear() {
      sessionToken = null;
    },
    has() {
      return Boolean(sessionToken);
    },
  };

  async function send(path, { method = "GET", json, form } = {}) {
    const headers = {};
    let body;

    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(json);
    } else if (form !== undefined) {
      body = form;
    }
    if (method !== "GET") {
      headers["Idempotency-Key"] = newIdempotencyKey();
    }
    if (sessionToken) {
      headers["Authorization"] = "Bearer " + sessionToken;
    }

    const response = await fetch(path, { method, headers, body });
    return parse(response);
  }

  async function downloadFile(path) {
    const headers = {};
    if (sessionToken) {
      headers["Authorization"] = "Bearer " + sessionToken;
    }
    const response = await fetch(path, { method: "GET", headers });
    if (!response.ok) {
      let body = null;
      try {
        body = await response.json();
      } catch (err) {
        body = null;
      }
      throw new ApiError(body && body.error, response.status);
    }
    const disposition = response.headers.get("Content-Disposition") || "";
    const match = /filename="?([^"]+)"?/.exec(disposition);
    const filename = match ? match[1] : "download";
    const blob = await response.blob();
    return { blob, filename };
  }

  function query(params) {
    const search = new URLSearchParams();
    Object.keys(params || {}).forEach((key) => {
      if (params[key] !== null && params[key] !== undefined && params[key] !== "") {
        search.set(key, params[key]);
      }
    });
    const text = search.toString();
    return text ? "?" + text : "";
  }

  GEMS.ApiError = ApiError;
  GEMS.api = {
    startOnboarding: () => send("/onboarding", { method: "POST" }),
    readCase: (id) => send("/onboarding/" + id),
    submitDocument: (id, file, docType) => {
      const form = new FormData();
      form.append("file", file);
      form.append("docType", docType || "ci_front");
      return send("/onboarding/" + id + "/document", { method: "POST", form });
    },
    setContact: (id, email, phone) =>
      send("/onboarding/" + id + "/contact", { method: "POST", json: { email, phone } }),
    resendCode: (id) => send("/onboarding/" + id + "/code/resend", { method: "POST" }),
    verifyCode: (id, code) =>
      send("/onboarding/" + id + "/code/verify", { method: "POST", json: { code } }),
    complete: (id, payload) =>
      send("/onboarding/" + id + "/complete", { method: "POST", json: payload }),

    login: async (username, pin) => {
      const response = await send("/auth/login", { method: "POST", json: { username, pin } });
      GEMS.session.set(response.sessionToken);
      return response;
    },
    verifyPin: (username, pin) => send("/auth/pin/verify", { method: "POST", json: { username, pin } }),
    revealPin: async (username, password) => {
      const response = await send("/auth/pin/reveal", { method: "POST", json: { username, password } });
      GEMS.session.set(response.sessionToken);
      return response;
    },
    requestPasswordReset: (username) =>
      send("/auth/password/reset", { method: "POST", json: { username } }),
    verifyResetCode: (id, code) =>
      send("/auth/password/reset/" + id + "/verify", { method: "POST", json: { code } }),
    completePasswordReset: async (id, payload) => {
      const response = await send("/auth/password/reset/" + id + "/complete", { method: "POST", json: payload });
      GEMS.session.set(response.sessionToken);
      return response;
    },
    logout: () => send("/auth/logout", { method: "POST" }),
    me: () => send("/auth/me"),
    listSessions: () => send("/auth/sessions"),
    revokeSession: (sessionId) => send("/auth/sessions/" + sessionId + "/revoke", { method: "POST" }),
    requestUsernameChange: (newUsername) =>
      send("/auth/username/change", { method: "POST", json: { newUsername } }),
    requestEmailChange: (newEmail) =>
      send("/auth/email/change", { method: "POST", json: { newEmail } }),
    requestPhoneChange: (newPhone) =>
      send("/auth/phone/change", { method: "POST", json: { newPhone } }),
    requestPinChange: (newPin, newPinConfirmation) =>
      send("/auth/pin/change", {
        method: "POST",
        json: { newPin, newPinConfirmation },
      }),
    requestPasswordChange: (newPassword, newPasswordConfirmation) =>
      send("/auth/password/change", {
        method: "POST",
        json: { newPassword, newPasswordConfirmation },
      }),
    verifySecureChange: (caseId, code) =>
      send("/auth/secure-change/" + caseId + "/verify", { method: "POST", json: { code } }),
    requestAccountClosure: (pin) =>
      send("/auth/account/closure-request", { method: "POST", json: { pin } }),
    updatePreferences: (prefs) => send("/auth/preferences", { method: "PUT", json: { prefs } }),

    listAccounts: () => send("/accounts"),
    openAccount: (currency, kind, label) =>
      send("/accounts", { method: "POST", json: { currency, kind, label: label || null } }),
    closeAccount: (accountId) => send("/accounts/" + accountId + "/close", { method: "POST", json: {} }),
    exchangeRate: (from, to) => send("/exchange/rate" + query({ from, to })),
    exchange: (payload) => send("/exchange/convert", { method: "POST", json: payload }),
    paymentsSummary: () => send("/payments/summary"),
    listTransactions: (params) => send("/payments/transactions" + query(params)),
    listPending: () => send("/payments/pending"),
    listBeneficiaries: () => send("/payments/beneficiaries"),
    addBeneficiary: (name, iban) =>
      send("/payments/beneficiaries", { method: "POST", json: { name, iban } }),
    listTemplates: () => send("/payments/templates"),
    createTemplate: (payload) => send("/payments/templates", { method: "POST", json: payload }),
    updateTemplate: (id, payload) =>
      send("/payments/templates/" + id, { method: "PUT", json: payload }),
    deleteTemplate: (id) => send("/payments/templates/" + id, { method: "DELETE" }),
    addFunds: (accountId, amountMinorUnits) =>
      send("/payments/add-funds", { method: "POST", json: { accountId, amountMinorUnits } }),
    downloadStatement: (accountId, format, from, to) =>
      downloadFile("/payments/statement" + query({ accountId, format, from, to })),
    transfer: (payload) => send("/payments/transfers", { method: "POST", json: payload }),
    signTransfer: (id, code) =>
      send("/payments/transfers/" + id + "/sign", { method: "POST", json: { code } }),

    marketSnapshot: (range, refresh) =>
      send("/investments/market" + query({ range, refresh: refresh ? "true" : "" })),
    investPortfolio: () => send("/investments/portfolio"),
    investBuy: (payload) => send("/investments/buy", { method: "POST", json: payload }),
    investSell: (payload) => send("/investments/sell", { method: "POST", json: payload }),

    listCards: () => send("/cards"),
    issueVirtualCard: (accountId) =>
      send("/cards/virtual", { method: "POST", json: { accountId } }),
    issuePhysicalCard: (accountId) =>
      send("/cards/physical", { method: "POST", json: { accountId } }),
    freezeCard: (cardId) => send("/cards/" + cardId + "/freeze", { method: "POST", json: {} }),
    unfreezeCard: (cardId) => send("/cards/" + cardId + "/unfreeze", { method: "POST", json: {} }),
    blockCard: (cardId) => send("/cards/" + cardId + "/block", { method: "POST", json: {} }),
    revealCardPin: (cardId) =>
      send("/cards/" + cardId + "/pin/reveal", { method: "POST", json: {} }),
    revealCardDetails: (cardId) =>
      send("/cards/" + cardId + "/details/reveal", { method: "POST", json: {} }),
    setCardAtmLimit: (cardId, limitMinor) =>
      send("/cards/" + cardId + "/limits/atm", { method: "POST", json: { limitMinor } }),
    setCardOnlineLimit: (cardId, limitMinor) =>
      send("/cards/" + cardId + "/limits/online", { method: "POST", json: { limitMinor } }),

    listInsights: () => send("/insights"),
    listGoals: () => send("/goals"),
    getEducationLessons: () => send("/education/lessons"),
    getGoalProgress: () => send("/goals/progress"),
    getGoalPace: () => send("/goals/pace"),
    createGoal: (parentAccountId, name, targetMinorUnits, targetDate, initialDepositMinorUnits) =>
      send("/goals", {
        method: "POST",
        json: {
          parentAccountId,
          name,
          targetMinorUnits,
          targetDate,
          initialDepositMinorUnits: initialDepositMinorUnits || 0,
        },
      }),
    closeGoal: (goalId) =>
      send("/goals/" + encodeURIComponent(goalId) + "/close", { method: "POST" }),
    depositToGoal: (goalId, amountMinorUnits) =>
      send("/goals/" + encodeURIComponent(goalId) + "/deposit", {
        method: "POST",
        json: { amountMinorUnits },
      }),
    withdrawFromGoal: (goalId, amountMinorUnits) =>
      send("/goals/" + encodeURIComponent(goalId) + "/withdraw", {
        method: "POST",
        json: { amountMinorUnits },
      }),
    getStandingOrder: (goalId) =>
      send("/goals/" + encodeURIComponent(goalId) + "/standing-order"),
    createStandingOrder: (goalId, amountMinorUnits, frequency, createdVia) =>
      send("/goals/" + encodeURIComponent(goalId) + "/standing-order", {
        method: "POST",
        json: { amountMinorUnits, frequency, createdVia: createdVia || "user" },
      }),
    pauseStandingOrder: (standingOrderId) =>
      send("/goals/standing-order/" + encodeURIComponent(standingOrderId) + "/pause", {
        method: "POST",
      }),
    resumeStandingOrder: (standingOrderId) =>
      send("/goals/standing-order/" + encodeURIComponent(standingOrderId) + "/resume", {
        method: "POST",
      }),
    cancelStandingOrder: (standingOrderId) =>
      send("/goals/standing-order/" + encodeURIComponent(standingOrderId) + "/cancel", {
        method: "POST",
      }),

    listTermDeposits: () => send("/deposits"),
    createTermDeposit: (parentAccountId, name, termMonths, initialDepositMinorUnits) =>
      send("/deposits", {
        method: "POST",
        json: { parentAccountId, name, termMonths, initialDepositMinorUnits },
      }),
    topUpTermDeposit: (depositId, amountMinorUnits, sourceAccountId) =>
      send("/deposits/" + encodeURIComponent(depositId) + "/topup", {
        method: "POST",
        json: { amountMinorUnits, sourceAccountId: sourceAccountId || null },
      }),
    withdrawFromTermDeposit: (depositId, amountMinorUnits) =>
      send("/deposits/" + encodeURIComponent(depositId) + "/withdraw", {
        method: "POST",
        json: { amountMinorUnits },
      }),
    closeTermDeposit: (depositId) =>
      send("/deposits/" + encodeURIComponent(depositId) + "/close", { method: "POST" }),

    listCreditApplications: () => send("/credits/applications"),
    submitCreditApplication: (payload) =>
      send("/credits/applications", { method: "POST", json: payload }),
    withdrawCreditApplication: (applicationId) =>
      send("/credits/applications/" + encodeURIComponent(applicationId) + "/withdraw", {
        method: "POST",
      }),
    askSupport: (question) =>
      send("/agents/support/ask", { method: "POST", json: { question } }),
    askAnalytics: (question) =>
      send("/agents/analytics/ask", { method: "POST", json: { question } }),
    askPaymentsAgent: (question) =>
      send("/agents/payments/ask", { method: "POST", json: { question } }),
    askGems: (question, history, screen) =>
      send("/agents/ask", { method: "POST", json: { question, history, screen } }),
    requestHandoff: (question, reason, history) =>
      send("/agents/handoff", { method: "POST", json: { question, reason, history } }),
    transcribeVoice: (blob, language) => {
      const form = new FormData();
      form.append("audio", blob, "voice");
      if (language) form.append("language", language);
      return send("/agents/transcribe", { method: "POST", form });
    },
    synthesizeSpeech: async (text, language, voice, signal) => {
      const headers = { "Content-Type": "application/json" };
      if (sessionToken) {
        headers["Authorization"] = "Bearer " + sessionToken;
      }
      const response = await fetch("/agents/synthesize", {
        method: "POST",
        headers,
        body: JSON.stringify({ text, language, voice }),
        signal,
      });
      if (!response.ok) {
        let body = null;
        try {
          body = await response.json();
        } catch (err) {
          body = null;
        }
        throw new ApiError(body && body.error, response.status);
      }
      return response.blob();
    },
  };
})();
