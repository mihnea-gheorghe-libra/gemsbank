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

    const response = await fetch(path, { method, headers, body });
    return parse(response);
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

    login: (username, pin) => send("/auth/login", { method: "POST", json: { username, pin } }),
    revealPin: (username, password) =>
      send("/auth/pin/reveal", { method: "POST", json: { username, password } }),
    requestPasswordReset: (username) =>
      send("/auth/password/reset", { method: "POST", json: { username } }),
    verifyResetCode: (id, code) =>
      send("/auth/password/reset/" + id + "/verify", { method: "POST", json: { code } }),
    completePasswordReset: (id, payload) =>
      send("/auth/password/reset/" + id + "/complete", { method: "POST", json: payload }),

    listCards: (username) => send("/cards?username=" + encodeURIComponent(username)),
    issueVirtualCard: (username) =>
      send("/cards/virtual", { method: "POST", json: { username } }),
    freezeCard: (username, cardId) =>
      send("/cards/" + cardId + "/freeze", { method: "POST", json: { username } }),
    unfreezeCard: (username, cardId) =>
      send("/cards/" + cardId + "/unfreeze", { method: "POST", json: { username } }),
    blockCard: (username, cardId) =>
      send("/cards/" + cardId + "/block", { method: "POST", json: { username } }),
    revealCardPin: (username, cardId) =>
      send("/cards/" + cardId + "/pin/reveal", { method: "POST", json: { username } }),
    revealCardDetails: (username, cardId) =>
      send("/cards/" + cardId + "/details/reveal", { method: "POST", json: { username } }),
    setCardAtmLimit: (username, cardId, limitMinor) =>
      send("/cards/" + cardId + "/limits/atm", {
        method: "POST",
        json: { username, limitMinor },
      }),
    setCardOnlineLimit: (username, cardId, limitMinor) =>
      send("/cards/" + cardId + "/limits/online", {
        method: "POST",
        json: { username, limitMinor },
      }),
  };
})();
