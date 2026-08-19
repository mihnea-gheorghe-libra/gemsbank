(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const { useState, useRef, useEffect } = React;

  const LENGTH = 6;

  function formatSeconds(total) {
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return minutes + ":" + String(seconds).padStart(2, "0");
  }

  ONB.CodeStep = function CodeStep({ delivery, busy, resending, onSubmit, onResend }) {
    const [digits, setDigits] = useState(Array(LENGTH).fill(""));
    const [cooldown, setCooldown] = useState(0);
    const inputs = useRef([]);

    useEffect(() => {
      setDigits(Array(LENGTH).fill(""));
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
            if (index + offset < LENGTH) next[index + offset] = character;
          });
        } else {
          next[index] = clean;
        }
        return next;
      });
      const jump = Math.min(index + (clean.length > 1 ? clean.length : 1), LENGTH - 1);
      if (clean && inputs.current[jump]) inputs.current[jump].focus();
    }

    function onKeyDown(index, event) {
      if (event.key === "Backspace" && !digits[index] && index > 0) {
        inputs.current[index - 1].focus();
      }
      if (event.key === "ArrowLeft" && index > 0) inputs.current[index - 1].focus();
      if (event.key === "ArrowRight" && index < LENGTH - 1) inputs.current[index + 1].focus();
    }

    const code = digits.join("");
    const complete = code.length === LENGTH;

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
              maxLength={LENGTH}
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
})();
