(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const AUTH = (GEMS.auth = GEMS.auth || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const { useState, useRef, useEffect } = React;

  const PIN_LENGTH = 6;
  const CODE_LENGTH = 6;

  function digitsOnly(value, max) {
    return value.replace(/\D/g, "").slice(0, max);
  }

  function formatClockTime(isoString) {
    const moment = new Date(isoString);
    if (isNaN(moment.getTime())) return "";
    return moment.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  AUTH.DigitGroup = function DigitGroup({ label, length, value, onChange, autoFocus }) {
    const inputs = useRef([]);
    const digits = value.split("");

    useEffect(() => {
      if (autoFocus && inputs.current[0]) inputs.current[0].focus();
    }, [autoFocus]);

    function setDigit(index, raw) {
      const clean = raw.replace(/\D/g, "");
      const next = [];
      for (let i = 0; i < length; i += 1) next[i] = digits[i] || "";
      if (clean.length > 1) {
        clean.split("").forEach((character, offset) => {
          if (index + offset < length) next[index + offset] = character;
        });
      } else {
        next[index] = clean;
      }
      onChange(next.join("").slice(0, length));
      const jump = Math.min(index + (clean.length > 1 ? clean.length : 1), length - 1);
      if (clean && inputs.current[jump]) inputs.current[jump].focus();
    }

    function onKeyDown(index, event) {
      if (event.key === "Backspace" && !digits[index] && index > 0) {
        inputs.current[index - 1].focus();
      }
      if (event.key === "ArrowLeft" && index > 0) inputs.current[index - 1].focus();
      if (event.key === "ArrowRight" && index < length - 1) inputs.current[index + 1].focus();
    }

    const cells = [];
    for (let index = 0; index < length; index += 1) cells.push(index);

    return (
      <div className="onb-otp" role="group" aria-label={label}>
        {cells.map((index) => (
          <input
            key={index}
            ref={(node) => {
              inputs.current[index] = node;
            }}
            className="input"
            type="password"
            inputMode="numeric"
            autoComplete="off"
            maxLength={length}
            aria-label={t("auth.digitOf", { n: index + 1, total: length })}
            value={digits[index] || ""}
            onChange={(event) => setDigit(index, event.target.value)}
            onKeyDown={(event) => onKeyDown(index, event)}
          />
        ))}
      </div>
    );
  };

  AUTH.SignInForm = function SignInForm({ busy, fieldErrors, onSubmit, onForgotPin }) {
    const [username, setUsername] = useState("");
    const [pin, setPin] = useState("");

    const ready = username.trim().length >= 3 && pin.length === PIN_LENGTH;

    return (
      <form
        className="onb-fade"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ username: username.trim(), pin });
        }}
      >
        <div className="auth-stack">
          <UI.Field id="signin-username" label={t("auth.username")} error={fieldErrors.username}>
            <UI.TextInput
              id="signin-username"
              name="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </UI.Field>

          <div className="field">
            <label htmlFor="signin-pin">{t("auth.pin")}</label>
            <AUTH.DigitGroup
              label={t("auth.pin")}
              length={PIN_LENGTH}
              value={pin}
              onChange={setPin}
            />
            <input id="signin-pin" className="visually-hidden" tabIndex={-1} readOnly value={pin} />
            {fieldErrors.pin ? (
              <div style={{ fontSize: 11, marginTop: 4, color: "var(--color-negative)" }}>
                {fieldErrors.pin}
              </div>
            ) : null}
          </div>
        </div>

        <div className="auth-actions">
          <UI.Button type="submit" variant="primary" disabled={busy || !ready}>
            {busy ? t("auth.signingIn") : t("auth.signIn")}
          </UI.Button>
          <UI.Button type="button" variant="ghost" onClick={onForgotPin}>
            {t("auth.forgotPin")}
          </UI.Button>
        </div>
      </form>
    );
  };

  function formatCountdown(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return minutes + ":" + String(seconds).padStart(2, "0");
  }

  AUTH.useCountdown = function useCountdown(retryAfterSeconds) {
    const [secondsLeft, setSecondsLeft] = useState(retryAfterSeconds || 0);

    useEffect(() => {
      if (!retryAfterSeconds) {
        setSecondsLeft(0);
        return undefined;
      }
      setSecondsLeft(retryAfterSeconds);
      const id = setInterval(() => {
        setSecondsLeft((current) => (current > 0 ? current - 1 : 0));
      }, 1000);
      return () => clearInterval(id);
    }, [retryAfterSeconds]);

    return secondsLeft;
  };

  AUTH.PasswordForm = function PasswordForm({
    busy,
    fieldErrors,
    lockout,
    pinLockNotice,
    onSubmit,
    onForgotPassword,
    onBack,
  }) {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const secondsLeft = AUTH.useCountdown(lockout && lockout.retryAfterSeconds);
    const locked = (lockout && lockout.permanentlyLocked) || secondsLeft > 0;

    const ready = username.trim().length >= 3 && password.length > 0 && !locked;

    return (
      <form
        className="onb-fade"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ username: username.trim(), password });
        }}
      >
        {pinLockNotice ? (
          <div className="auth-notice" role="alert">
            {t("auth.pinLockedNotice")}
          </div>
        ) : null}

        <div className="auth-stack">
          <UI.Field id="reveal-username" label={t("auth.username")} error={fieldErrors.username}>
            <UI.TextInput
              id="reveal-username"
              name="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </UI.Field>
          <UI.Field id="reveal-password" label={t("auth.password")} error={fieldErrors.password}>
            <UI.TextInput
              id="reveal-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </UI.Field>
        </div>

        {lockout && lockout.permanentlyLocked ? (
          <div className="auth-notice" role="alert">
            {t("auth.permanentlyLocked")}
          </div>
        ) : null}

        {secondsLeft > 0 ? (
          <div className="auth-countdown" role="status" aria-live="polite">
            <div className="auth-countdown-label">{t("auth.retryInLabel")}</div>
            <div className="auth-countdown-time">{formatCountdown(secondsLeft)}</div>
          </div>
        ) : null}

        <div className="auth-actions">
          <UI.Button type="submit" variant="primary" disabled={busy || !ready}>
            {busy ? t("auth.checking") : t("auth.showPin")}
          </UI.Button>
          <UI.Button
            type="button"
            variant="ghost"
            disabled={username.trim().length < 3}
            onClick={() => onForgotPassword(username.trim())}
          >
            {t("auth.forgotPassword")}
          </UI.Button>
          <UI.Button type="button" variant="ghost" onClick={onBack}>
            {t("auth.backToSignIn")}
          </UI.Button>
        </div>
      </form>
    );
  };

  AUTH.ResetCodeForm = function ResetCodeForm({ delivery, busy, onSubmit, onBack }) {
    const [code, setCode] = useState("");

    return (
      <form
        className="onb-fade"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(code);
        }}
      >
        <AUTH.DigitGroup
          label={t("auth.codeLabel")}
          length={CODE_LENGTH}
          value={code}
          onChange={setCode}
          autoFocus
        />

        <div className="text-muted" style={{ fontSize: 12, marginTop: 12 }}>
          {delivery ? t("auth.codeSentTo", { target: delivery.sentTo }) : null}
        </div>

        {delivery && delivery.expiresAt ? (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 6 }}>
            {t("auth.codeValidUntil", { time: formatClockTime(delivery.expiresAt) })}
          </div>
        ) : null}

        {delivery && delivery.devCode ? (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 6 }}>
            {t("auth.devCode", { code: delivery.devCode })}
          </div>
        ) : null}

        <div className="auth-actions">
          <UI.Button
            type="submit"
            variant="primary"
            disabled={busy || code.length !== CODE_LENGTH}
          >
            {busy ? t("auth.checking") : t("auth.verifyCode")}
          </UI.Button>
          <UI.Button type="button" variant="ghost" onClick={onBack}>
            {t("auth.backToSignIn")}
          </UI.Button>
        </div>
      </form>
    );
  };

  AUTH.NewPasswordForm = function NewPasswordForm({ busy, fieldErrors, onSubmit }) {
    const [password, setPassword] = useState("");
    const [confirmation, setConfirmation] = useState("");

    const ready = password.length > 0 && confirmation.length > 0;

    return (
      <form
        className="onb-fade"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ password, passwordConfirmation: confirmation });
        }}
      >
        <div className="auth-stack">
          <UI.Field id="new-password" label={t("auth.newPassword")} error={fieldErrors.password}>
            <UI.TextInput
              id="new-password"
              name="newPassword"
              type="password"
              autoComplete="new-password"
              autoFocus
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </UI.Field>
          <UI.Field
            id="confirm-password"
            label={t("auth.confirmPassword")}
            error={fieldErrors.passwordConfirmation}
          >
            <UI.TextInput
              id="confirm-password"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              required
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </UI.Field>
        </div>

        <div className="auth-actions">
          <UI.Button type="submit" variant="primary" disabled={busy || !ready}>
            {busy ? t("auth.saving") : t("auth.changePassword")}
          </UI.Button>
        </div>
      </form>
    );
  };

  AUTH.PinPanel = function PinPanel({ pin }) {
    const [shown, setShown] = useState(false);

    return (
      <div>
        <UI.Plate style={{ padding: 20, maxWidth: 420, background: "var(--color-surface)" }}>
          <UI.Kicker style={{ marginBottom: 10 }}>{t("auth.yourPin")}</UI.Kicker>
          <div
            className="auth-pin"
            role="status"
            aria-live="polite"
            aria-label={shown ? t("auth.pinShown", { pin: pin.split("").join(" ") }) : t("auth.pinHidden")}
          >
            {shown ? pin : "•".repeat(pin.length)}
          </div>
          <UI.Button
            type="button"
            variant={shown ? "secondary" : "primary"}
            style={{ marginTop: 16 }}
            aria-pressed={shown}
            onClick={() => setShown((value) => !value)}
          >
            {shown ? t("auth.hide") : t("auth.reveal")}
          </UI.Button>
        </UI.Plate>

        <p className="text-muted" style={{ fontSize: 12, marginTop: 14, maxWidth: 420 }}>
          {t("auth.pinWarning")}
        </p>
      </div>
    );
  };

  AUTH.PinRevealScreen = function PinRevealScreen({ pin, pinMissing, onContinue }) {
    return (
      <div className="onb-fade">
        {pin ? <AUTH.PinPanel pin={pin} /> : null}

        {!pin && pinMissing ? (
          <UI.Plate style={{ padding: 20, maxWidth: 480 }}>
            <p style={{ margin: 0, fontSize: 14 }}>{t("auth.pinUnavailable")}</p>
          </UI.Plate>
        ) : null}

        <div className="auth-actions">
          <UI.Button type="button" variant="primary" onClick={onContinue}>
            {t("auth.continueToDashboard")}
          </UI.Button>
        </div>
      </div>
    );
  };
})();
