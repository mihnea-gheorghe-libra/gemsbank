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

  ONB.DocumentStep = function DocumentStep({ extracted, busy, onExtract, onReset, onNext }) {
    const [front, setFront] = useState(null);
    const [back, setBack] = useState(null);

    function handleReset() {
      setFront(null);
      setBack(null);
      if (onReset) onReset();
    }

    return (
      <div className="onb-fade">
        {!extracted ? (
          <div>
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

            <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
              <UI.Button
                type="button"
                variant="primary"
                disabled={!front || busy}
                onClick={() => onExtract(front)}
              >
                {busy ? t("document.reading") : t("document.read")}
              </UI.Button>
            </div>
          </div>
        ) : (
          <div>
            <UI.Plate style={{ padding: 18, maxWidth: 660 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 12,
                }}
              >
                <UI.Kicker>{t("document.extractedBy")}</UI.Kicker>
                <UI.Tag>{t("document.ageOk", { age: extracted.ageYears })}</UI.Tag>
              </div>

              <p className="text-muted" style={{ fontSize: 13, marginTop: 0, marginBottom: 16 }}>
                {t("document.reviewInstructions")}
              </p>

              <div className="onb-two-col" style={{ gap: 14 }}>
                <UI.Field id="extracted-name" label={t("document.name")}>
                  <UI.TextInput
                    id="extracted-name"
                    readOnly
                    value={extracted.fullName}
                    style={{ background: "var(--color-surface-muted)" }}
                  />
                </UI.Field>

                <UI.Field id="extracted-cnp" label={t("document.cnp")}>
                  <UI.TextInput
                    id="extracted-cnp"
                    readOnly
                    value={extracted.cnp || extracted.cnpMasked}
                    style={{ fontFamily: "var(--font-mono)", background: "var(--color-surface-muted)" }}
                  />
                </UI.Field>

                <UI.Field id="extracted-birth" label={t("document.birthDate")}>
                  <UI.TextInput
                    id="extracted-birth"
                    readOnly
                    value={formatDate(extracted.birthDate)}
                    style={{ background: "var(--color-surface-muted)" }}
                  />
                </UI.Field>

                <UI.Field id="extracted-expiry" label={t("document.expiry")}>
                  <UI.TextInput
                    id="extracted-expiry"
                    readOnly
                    value={formatDate(extracted.expiresOn)}
                    style={{ background: "var(--color-surface-muted)" }}
                  />
                </UI.Field>

                <UI.Field id="extracted-docno" label={t("document.docNumber")}>
                  <UI.TextInput
                    id="extracted-docno"
                    readOnly
                    value={extracted.documentNumberMasked}
                    style={{ fontFamily: "var(--font-mono)", background: "var(--color-surface-muted)" }}
                  />
                </UI.Field>
              </div>

              <div className="text-muted" style={{ fontSize: 11, marginTop: 14 }}>
                {t("document.syntheticNote")}
              </div>
            </UI.Plate>

            <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
              <UI.Button type="button" variant="primary" onClick={onNext}>
                {t("document.cta")}
              </UI.Button>
              <UI.Button type="button" variant="secondary" onClick={handleReset}>
                {t("document.reupload")}
              </UI.Button>
            </div>
          </div>
        )}
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
      passwordConfirmation: "",
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
      form.passwordConfirmation &&
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
          <UI.Field
            id="passwordConfirmation"
            label={t("credentials.passwordConfirm")}
            error={fieldErrors.passwordConfirm}
          >
            <UI.TextInput
              id="passwordConfirmation"
              name="passwordConfirmation"
              type="password"
              autoComplete="new-password"
              required
              value={form.passwordConfirmation}
              onChange={(event) => update("passwordConfirmation", event.target.value)}
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
})();
