(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const { useState } = React;

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
      return value.replace(/\D/g, "").slice(0, 6);
    }

    const ready =
      form.username && form.password && form.pin.length === 6 && form.pinConfirmation.length === 6;

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
})();
