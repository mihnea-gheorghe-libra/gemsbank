(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const AUTH = (GEMS.auth = GEMS.auth || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const api = GEMS.api;
  const { useState, useCallback } = React;

  const FIELD_KEYS = ["username", "pin", "password", "passwordConfirmation"];

  const VIEWS = {
    SIGN_IN: "signIn",
    PASSWORD: "password",
    RESET_CODE: "resetCode",
    NEW_PASSWORD: "newPassword",
    PIN_REVEAL: "pinReveal",
    WELCOME: "welcome",
  };

  function toFieldErrors(error) {
    if (!error || !error.details || !error.details.field) return {};
    if (FIELD_KEYS.indexOf(error.details.field) < 0) return {};
    return { [error.details.field]: error.message };
  }

  function normaliseUsername(value) {
    return value.trim().toLowerCase();
  }

  AUTH.SignInPage = function SignInPage({ onSwitchToRegister }) {
    const [view, setView] = useState(VIEWS.SIGN_IN);
    const [session, setSession] = useState(null);
    const [pin, setPin] = useState(null);
    const [pinMissing, setPinMissing] = useState(false);
    const [recovery, setRecovery] = useState(null);
    const [pinLockedUsername, setPinLockedUsername] = useState(null);
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);

    const run = useCallback(async (work) => {
      setBusy(true);
      setError(null);
      try {
        return await work();
      } catch (err) {
        setError(err);
        return null;
      } finally {
        setBusy(false);
      }
    }, []);

    const goTo = useCallback((next) => {
      setError(null);
      setView(next);
    }, []);

    const resetToSignIn = useCallback(() => {
      setPin(null);
      setPinMissing(false);
      setRecovery(null);
      setSession(null);
      setError(null);
      setView(VIEWS.SIGN_IN);
    }, []);

    const handleSignIn = (form) =>
      run(async () => {
        if (pinLockedUsername && normaliseUsername(form.username) === pinLockedUsername) {
          setView(VIEWS.PASSWORD);
          return;
        }
        try {
          const response = await api.login(form.username, form.pin);
          setSession(response);
          setPin(null);
          setPinMissing(false);
          setView(VIEWS.WELCOME);
        } catch (err) {
          if (err.details && err.details.pinLocked) {
            setPinLockedUsername(normaliseUsername(form.username));
            setView(VIEWS.PASSWORD);
          }
          throw err;
        }
      });

    const handleReveal = (form) =>
      run(async () => {
        const response = await api.revealPin(form.username, form.password);
        if (normaliseUsername(form.username) === pinLockedUsername) {
          setPinLockedUsername(null);
        }
        setSession(response);
        setPin(response.pin);
        setView(VIEWS.PIN_REVEAL);
      });

    const handleForgotPassword = (username) =>
      run(async () => {
        const response = await api.requestPasswordReset(username);
        setRecovery(response);
        setView(VIEWS.RESET_CODE);
      });

    const handleVerifyCode = (code) =>
      run(async () => {
        await api.verifyResetCode(recovery.recoveryCaseId, code);
        setView(VIEWS.NEW_PASSWORD);
      });

    const handleNewPassword = (form) =>
      run(async () => {
        const response = await api.completePasswordReset(recovery.recoveryCaseId, form);
        setPinLockedUsername(null);
        setSession(response);
        setPin(response.pin || null);
        setPinMissing(!response.pin);
        setView(VIEWS.PIN_REVEAL);
      });

    const handleContinueToDashboard = useCallback(() => {
      setPin(null);
      setPinMissing(false);
      setView(VIEWS.WELCOME);
    }, []);

    const fieldErrors = toFieldErrors(error);
    const lockout =
      error && error.details && error.details.field === "password"
        ? {
            retryAfterSeconds: error.details.retryAfterSeconds || null,
            permanentlyLocked: !!error.details.permanentlyLocked,
          }
        : null;
    const title = t("auth.views." + view + ".title", {
      username: (session && session.username) || "",
    });
    const lede = t("auth.views." + view + ".lede");

    return (
      <div className="onb-shell">
        <header className="onb-topbar">
          <span className="onb-wordmark">{t("brand")}</span>
          <span className="auth-screen-tag">{t("auth.screenTag")}</span>
          <div style={{ marginLeft: "auto" }}>
            <UI.Button type="button" onClick={onSwitchToRegister}>
              {t("auth.createAccount")}
            </UI.Button>
          </div>
        </header>

        <main className="onb-main auth-main">
          <UI.Kicker style={{ marginBottom: 8 }}>{t("auth.kicker")}</UI.Kicker>
          <h1 style={{ fontSize: "var(--text-h2)" }}>{title}</h1>
          <p className="text-muted onb-lede">{lede}</p>

          {view === VIEWS.SIGN_IN ? (
            <AUTH.SignInForm
              busy={busy}
              fieldErrors={fieldErrors}
              onSubmit={handleSignIn}
              onForgotPin={() => goTo(VIEWS.PASSWORD)}
            />
          ) : null}

          {view === VIEWS.PASSWORD ? (
            <AUTH.PasswordForm
              busy={busy}
              fieldErrors={fieldErrors}
              lockout={lockout}
              pinLockNotice={!!pinLockedUsername}
              onSubmit={handleReveal}
              onForgotPassword={handleForgotPassword}
              onBack={resetToSignIn}
            />
          ) : null}

          {view === VIEWS.RESET_CODE ? (
            <AUTH.ResetCodeForm
              delivery={recovery && recovery.delivery}
              busy={busy}
              onSubmit={handleVerifyCode}
              onBack={resetToSignIn}
            />
          ) : null}

          {view === VIEWS.NEW_PASSWORD ? (
            <AUTH.NewPasswordForm
              busy={busy}
              fieldErrors={fieldErrors}
              onSubmit={handleNewPassword}
            />
          ) : null}

          {view === VIEWS.PIN_REVEAL ? (
            <AUTH.PinRevealScreen
              pin={pin}
              pinMissing={pinMissing}
              onContinue={handleContinueToDashboard}
            />
          ) : null}

          {view === VIEWS.WELCOME && session ? (
            <AUTH.Welcome username={session.username} onSignOut={resetToSignIn} />
          ) : null}

          <UI.ErrorNote error={error} />
        </main>

        <footer className="onb-footer">{t("footer")}</footer>
      </div>
    );
  };
})();
