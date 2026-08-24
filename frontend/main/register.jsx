(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = GEMS.onboarding;
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const api = GEMS.api;
  const { useState, useEffect, useCallback } = React;

  const FIELD_KEYS = ["email", "phone", "username", "password", "pin", "pinConfirm"];

  function toFieldErrors(error) {
    if (!error || !error.details || !error.details.field) return {};
    if (FIELD_KEYS.indexOf(error.details.field) < 0) return {};
    return { [error.details.field]: error.message };
  }

  function RegisterPage({ onSwitchToSignIn }) {
    const [caseId, setCaseId] = useState(null);
    const [step, setStep] = useState(1);
    const [extracted, setExtracted] = useState(null);
    const [delivery, setDelivery] = useState(null);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [busy, setBusy] = useState(false);
    const [resending, setResending] = useState(false);

    useEffect(() => {
      let cancelled = false;
      api
        .startOnboarding()
        .then((session) => {
          if (!cancelled) setCaseId(session.kycCaseId);
        })
        .catch((err) => {
          if (!cancelled) setError(err);
        });
      return () => {
        cancelled = true;
      };
    }, []);

    const run = useCallback(async (work, setFlag) => {
      const flag = setFlag || setBusy;
      flag(true);
      setError(null);
      try {
        return await work();
      } catch (err) {
        setError(err);
        return null;
      } finally {
        flag(false);
      }
    }, []);

    const handleExtract = (file) =>
      run(async () => {
        const response = await api.submitDocument(caseId, file, "ci_front");
        setExtracted(response.extracted);
      });

    const handleContact = (payload) =>
      run(async () => {
        const response = await api.setContact(caseId, payload.email, payload.phone);
        setDelivery(response.delivery);
        setStep(3);
      });

    const handleResend = () =>
      run(async () => {
        const response = await api.resendCode(caseId);
        setDelivery(response.delivery);
      }, setResending);

    const handleVerify = (code) =>
      run(async () => {
        await api.verifyCode(caseId, code);
        setStep(4);
      });

    const handleComplete = (form) =>
      run(async () => {
        const response = await api.complete(caseId, {
          username: form.username,
          password: form.password,
          pin: form.pin,
          pinConfirmation: form.pinConfirmation,
        });
        setResult(response);
        setStep(5);
      });

    const done = step === 5;
    const stepKey = done ? "done" : ONB.STEPS[step - 1].key;
    const title = done
      ? t("done.title", { username: (result && result.username) || "" })
      : t(stepKey + ".title");
    const lede = done ? t("done.lede") : t(stepKey + ".lede");
    const fieldErrors = toFieldErrors(error);

    return (
      <div className="onb-shell">
        <header className="onb-topbar">
          <span className="onb-wordmark">{t("brand")}</span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-kicker)",
              letterSpacing: "0.2em",
              color: "var(--color-plum-700)",
            }}
          >
            {t("screenTag")}
          </span>
          <div style={{ marginLeft: "auto" }}>
            <UI.Button type="button" onClick={onSwitchToSignIn}>
              {t("backToSignIn")}
            </UI.Button>
          </div>
        </header>

        <div className="onb-grid">
          <ONB.StepRail current={step} />

          <main className="onb-main">
            <UI.Kicker style={{ marginBottom: 8 }}>
              {done ? t("state.done") : t("stepOf", { n: step, total: ONB.STEPS.length })}
            </UI.Kicker>
            <h1 style={{ fontSize: "var(--text-h2)" }}>{title}</h1>
            <p className="text-muted onb-lede">{lede}</p>

            {!caseId && !error ? <p className="text-muted">{t("loading")}</p> : null}

            {caseId && step === 1 ? (
              <ONB.DocumentStep
                extracted={extracted}
                busy={busy}
                onExtract={handleExtract}
                onReset={() => {
                  setExtracted(null);
                  setError(null);
                }}
                onNext={() => setStep(2)}
              />
            ) : null}


            {caseId && step === 2 ? (
              <ONB.ContactStep busy={busy} fieldErrors={fieldErrors} onSubmit={handleContact} />
            ) : null}

            {caseId && step === 3 ? (
              <ONB.CodeStep
                delivery={delivery}
                busy={busy}
                resending={resending}
                onSubmit={handleVerify}
                onResend={handleResend}
              />
            ) : null}

            {caseId && step === 4 ? (
              <ONB.CredentialsStep
                busy={busy}
                fieldErrors={fieldErrors}
                onSubmit={handleComplete}
              />
            ) : null}

            {done && result ? (
              <ONB.DoneStep result={result} onSignIn={onSwitchToSignIn} />
            ) : null}

            <UI.ErrorNote error={error} />
          </main>

          <ONB.AgentPanel stepKey={stepKey} lede={lede} />
        </div>

        <footer className="onb-footer">{t("footer")}</footer>
      </div>
    );
  }

  ONB.RegisterPage = RegisterPage;
})();
