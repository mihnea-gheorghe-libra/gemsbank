(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const formatDate = GEMS.i18n.isoToDisplayDate;
  const { useState, useRef, useEffect } = React;

  const CODE_LENGTH = 6;

  function DropZone({ id, label, required, file, onFile }) {
    const inputRef = useRef(null);
    const [dragging, setDragging] = useState(false);
    const [preview, setPreview] = useState(null);

    useEffect(() => {
      if (!file) {
        setPreview(null);
        return undefined;
      }
      const url = URL.createObjectURL(file);
      setPreview(url);
      return () => URL.revokeObjectURL(url);
    }, [file]);

    function pick(list) {
      const chosen = list && list[0];
      if (chosen) onFile(chosen);
    }

    return (
      <div>
        <button
          type="button"
          className="onb-dropzone"
          data-filled={Boolean(file)}
          data-required={Boolean(required)}
          data-dragging={dragging}
          aria-label={label}
          onClick={() => inputRef.current && inputRef.current.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            pick(event.dataTransfer.files);
          }}
        >
          {preview ? (
            <img src={preview} alt="" />
          ) : (
            <span className="onb-dropzone-label">{label}</span>
          )}
        </button>
        <input
          ref={inputRef}
          id={id}
          className="visually-hidden"
          type="file"
          accept="image/png,image/jpeg,image/webp,application/pdf"
          onChange={(event) => pick(event.target.files)}
        />
        <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>
          {file ? file.name : required ? "" : t("document.backOptional")}
        </div>
      </div>
    );
  }

  ONB.DocumentStep = function DocumentStep({ extracted, busy, onExtract, onNext }) {
    const [front, setFront] = useState(null);
    const [back, setBack] = useState(null);

    return (
      <div className="onb-fade">
        <div className="onb-two-col">
          <DropZone
            id="id-front"
            label={t("document.front")}
            required
            file={front}
            onFile={setFront}
          />
          <DropZone id="id-back" label={t("document.back")} file={back} onFile={setBack} />
        </div>

        {extracted ? (
          <UI.Plate style={{ padding: 14, marginTop: 20, maxWidth: 660 }}>
            <UI.Kicker style={{ marginBottom: 8 }}>{t("document.extractedBy")}</UI.Kicker>
            <dl className="onb-extract-grid" style={{ margin: 0 }}>
              <dt className="text-muted">{t("document.name")}</dt>
              <dd style={{ margin: 0 }}>{extracted.fullName}</dd>
              <dt className="text-muted">{t("document.birthDate")}</dt>
              <dd style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
                <span>{formatDate(extracted.birthDate)}</span>
                <UI.Tag>{t("document.ageOk", { age: extracted.ageYears })}</UI.Tag>
              </dd>
              <dt className="text-muted">{t("document.cnp")}</dt>
              <dd style={{ margin: 0 }}>{extracted.cnpMasked}</dd>
              <dt className="text-muted">{t("document.docNumber")}</dt>
              <dd style={{ margin: 0 }}>{extracted.documentNumberMasked}</dd>
              <dt className="text-muted">{t("document.expiry")}</dt>
              <dd style={{ margin: 0 }}>{formatDate(extracted.expiresOn)}</dd>
            </dl>
            <div className="text-muted" style={{ fontSize: 11, marginTop: 10 }}>
              {t("document.syntheticNote")}
            </div>
          </UI.Plate>
        ) : null}

        <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
          <UI.Button
            type="button"
            variant={extracted ? "secondary" : "primary"}
            disabled={!front || busy}
            onClick={() => onExtract(front)}
          >
            {busy ? t("document.reading") : t("document.read")}
          </UI.Button>
          {extracted ? (
            <UI.Button type="button" variant="primary" onClick={onNext}>
              {t("document.cta")}
            </UI.Button>
          ) : null}
        </div>
      </div>
    );
  };

  ONB.ContactStep = function ContactStep({ busy, fieldErrors, onSubmit }) {
    const [phone, setPhone] = useState("");
    const [email, setEmail] = useState("");

    return (
      <form
        className="onb-fade"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ email: email.trim(), phone: phone.trim() });
        }}
      >
        <div className="onb-two-col" style={{ maxWidth: 560 }}>
          <UI.Field id="phone" label={t("contact.phone")} error={fieldErrors.phone}>
            <UI.TextInput
              id="phone"
              name="phone"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              required
              placeholder="+40 7.. ... ..."
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </UI.Field>
          <UI.Field id="email" label={t("contact.email")} error={fieldErrors.email}>
            <UI.TextInput
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              placeholder="nume@exemplu.ro"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </UI.Field>
        </div>

        <UI.Button
          type="submit"
          variant="primary"
          style={{ marginTop: 18 }}
          disabled={busy || !email || !phone}
        >
          {busy ? t("contact.sending") : t("contact.cta")}
        </UI.Button>
      </form>
    );
  };

  function formatSeconds(total) {
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return minutes + ":" + String(seconds).padStart(2, "0");
  }

  ONB.CodeStep = function CodeStep({ delivery, busy, resending, onSubmit, onResend }) {
    const [digits, setDigits] = useState(Array(CODE_LENGTH).fill(""));
    const [cooldown, setCooldown] = useState(0);
    const inputs = useRef([]);

    useEffect(() => {
      setDigits(Array(CODE_LENGTH).fill(""));
      setCooldown((delivery && delivery.resendAvailableInSeconds) || 0);
      if (inputs.current[0]) inputs.current[0].focus();
    }, [delivery]);

    useEffect(() => {
      if (cooldown <= 0) return undefined;
      const timer = window.setTimeout(() => setCooldown((value) => value - 1), 1000);
      return () => window.clearTimeout(timer);
    }, [cooldown]);

    function setDigit(index, value) {
      const clean = value.replace(/\D/g, "");
      setDigits((previous) => {
        const next = previous.slice();
        if (clean.length > 1) {
          clean.split("").forEach((character, offset) => {
            if (index + offset < CODE_LENGTH) next[index + offset] = character;
          });
        } else {
          next[index] = clean;
        }
        return next;
      });
      const jump = Math.min(index + (clean.length > 1 ? clean.length : 1), CODE_LENGTH - 1);
      if (clean && inputs.current[jump]) inputs.current[jump].focus();
    }

    function onKeyDown(index, event) {
      if (event.key === "Backspace" && !digits[index] && index > 0) {
        inputs.current[index - 1].focus();
      }
      if (event.key === "ArrowLeft" && index > 0) inputs.current[index - 1].focus();
      if (event.key === "ArrowRight" && index < CODE_LENGTH - 1) inputs.current[index + 1].focus();
    }

    const code = digits.join("");
    const complete = code.length === CODE_LENGTH;

    return (
      <form
        className="onb-fade"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(code);
        }}
      >
        <div className="onb-otp" role="group" aria-label={t("code.title")}>
          {digits.map((digit, index) => (
            <input
              key={index}
              ref={(node) => {
                inputs.current[index] = node;
              }}
              className="input"
              type="text"
              inputMode="numeric"
              autoComplete={index === 0 ? "one-time-code" : "off"}
              maxLength={CODE_LENGTH}
              aria-label={t("code.digit", { n: index + 1 })}
              value={digit}
              onChange={(event) => setDigit(index, event.target.value)}
              onKeyDown={(event) => onKeyDown(index, event)}
            />
          ))}
        </div>

        <div className="text-muted" style={{ fontSize: 12, marginTop: 12 }}>
          {delivery ? t("code.sentTo", { target: delivery.sentTo }) : null}
          {cooldown > 0 ? " · " + t("code.resendIn", { seconds: formatSeconds(cooldown) }) : null}
        </div>

        {delivery && delivery.devCode ? (
          <div className="text-muted" style={{ fontSize: 12, marginTop: 6 }}>
            {t("code.devCode", { code: delivery.devCode })}
          </div>
        ) : null}

        <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
          <UI.Button type="submit" variant="primary" disabled={!complete || busy}>
            {busy ? t("code.verifying") : t("code.cta")}
          </UI.Button>
          <UI.Button
            type="button"
            disabled={cooldown > 0 || resending || (delivery && delivery.resendsLeft <= 0)}
            onClick={onResend}
          >
            {t("code.resendNow")}
          </UI.Button>
        </div>

        {delivery && typeof delivery.resendsLeft === "number" ? (
          <div className="text-muted" style={{ fontSize: 11, marginTop: 8 }}>
            {t("code.resendsLeft", { n: delivery.resendsLeft })}
          </div>
        ) : null}
      </form>
    );
  };

  ONB.CredentialsStep = function CredentialsStep({ busy, fieldErrors, onSubmit }) {
    const [form, setForm] = useState({
      username: "",
      password: "",
      pin: "",
      pinConfirmation: "",
    });

    function update(name, value) {
      setForm((previous) => Object.assign({}, previous, { [name]: value }));
    }

    function digitsOnly(value) {
      return value.replace(/\D/g, "").slice(0, CODE_LENGTH);
    }

    const ready =
      form.username &&
      form.password &&
      form.pin.length === CODE_LENGTH &&
      form.pinConfirmation.length === CODE_LENGTH;

    return (
      <form
        className="onb-fade"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(form);
        }}
      >
        <div className="onb-two-col" style={{ maxWidth: 560 }}>
          <UI.Field id="username" label={t("credentials.username")} error={fieldErrors.username}>
            <UI.TextInput
              id="username"
              name="username"
              autoComplete="username"
              required
              value={form.username}
              onChange={(event) => update("username", event.target.value)}
            />
          </UI.Field>
          <UI.Field id="password" label={t("credentials.password")} error={fieldErrors.password}>
            <UI.TextInput
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              value={form.password}
              onChange={(event) => update("password", event.target.value)}
            />
          </UI.Field>
          <UI.Field id="pin" label={t("credentials.pin")} error={fieldErrors.pin}>
            <UI.TextInput
              id="pin"
              name="pin"
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              required
              value={form.pin}
              onChange={(event) => update("pin", digitsOnly(event.target.value))}
            />
          </UI.Field>
          <UI.Field
            id="pinConfirmation"
            label={t("credentials.pinConfirm")}
            error={fieldErrors.pinConfirm}
          >
            <UI.TextInput
              id="pinConfirmation"
              name="pinConfirmation"
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              required
              value={form.pinConfirmation}
              onChange={(event) => update("pinConfirmation", digitsOnly(event.target.value))}
            />
          </UI.Field>
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 16, fontSize: 13 }}>
          <UI.Tag>{t("credentials.passkeyTag")}</UI.Tag>
          <span className="text-muted">{t("credentials.passkeyNote")}</span>
        </div>

        <UI.Button
          type="submit"
          variant="primary"
          style={{ marginTop: 20 }}
          disabled={busy || !ready}
        >
          {busy ? t("credentials.creating") : t("credentials.cta")}
        </UI.Button>
      </form>
    );
  };

  ONB.DoneStep = function DoneStep({ result, onSignIn }) {
    return (
      <div className="onb-fade">
        <UI.Plate style={{ padding: 20, maxWidth: 560, background: "var(--color-surface)" }}>
          <UI.Kicker style={{ marginBottom: 8 }}>{t("done.caseLabel")}</UI.Kicker>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 14 }}>
            {result.kycCaseId}
          </div>
          <UI.Tag>{t("credentials.passkeyTag")}</UI.Tag>
        </UI.Plate>

        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <UI.Button type="button" variant="primary" onClick={onSignIn}>
            {t("done.goToSignIn")}
          </UI.Button>
          <UI.Button type="button" disabled>
            {t("done.comingSoon")}
          </UI.Button>
        </div>
      </div>
    );
  };
})();
