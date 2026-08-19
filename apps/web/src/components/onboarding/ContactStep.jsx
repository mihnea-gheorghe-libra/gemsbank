(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const { useState } = React;

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
})();
