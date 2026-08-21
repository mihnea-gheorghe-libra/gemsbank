(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const UI = (GEMS.ui = GEMS.ui || {});

  function classNames() {
    return Array.prototype.filter.call(arguments, Boolean).join(" ");
  }

  UI.Plate = function Plate({ as = "div", className, children, ...rest }) {
    const Tag = as;
    return (
      <Tag className={classNames("plate", className)} {...rest}>
        {children}
      </Tag>
    );
  };

  UI.Kicker = function Kicker({ children, style }) {
    return (
      <div className="kicker" style={style}>
        {children}
      </div>
    );
  };

  UI.Button = function Button({ variant = "secondary", className, children, ...rest }) {
    return (
      <button className={classNames("btn", "btn-" + variant, className)} {...rest}>
        {children}
      </button>
    );
  };

  UI.Field = function Field({ id, label, hint, error, children }) {
    return (
      <div className="field">
        <label htmlFor={id}>{label}</label>
        {children}
        {hint ? (
          <div className="text-muted" style={{ fontSize: 11, marginTop: 4 }}>
            {hint}
          </div>
        ) : null}
        {error ? (
          <div style={{ fontSize: 11, marginTop: 4, color: "var(--color-negative)" }}>{error}</div>
        ) : null}
      </div>
    );
  };

  UI.TextInput = function TextInput({ id, className, ...rest }) {
    return <input id={id} className={classNames("input", className)} {...rest} />;
  };

  UI.Select = function Select({ id, className, children, ...rest }) {
    return (
      <select id={id} className={classNames("input", "select", className)} {...rest}>
        {children}
      </select>
    );
  };

  UI.Tag = function Tag({ variant = "accent", children }) {
    return <span className={"tag tag-" + variant}>{children}</span>;
  };

  UI.ErrorNote = function ErrorNote({ error }) {
    if (!error) return null;
    return (
      <div className="onb-error" role="alert">
        {error.message}
      </div>
    );
  };

  const MINOR_UNITS_PER_MAJOR = 100;

  UI.formatMoney = function formatMoney(minorUnits, currency) {
    return new Intl.NumberFormat(GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
    }).format(Math.abs(minorUnits) / MINOR_UNITS_PER_MAJOR);
  };

  UI.Money = function Money({ minorUnits, currency, signed = false, className }) {
    const t = GEMS.i18n.t;
    const negative = minorUnits < 0;
    const amount = UI.formatMoney(minorUnits, currency);
    const glyph = negative ? "−" : "+";

    return (
      <span
        className={classNames("money", negative ? "money-out" : "money-in", className)}
        data-direction={negative ? "debit" : "credit"}
      >
        {signed ? <span aria-hidden="true">{glyph}</span> : null}
        {signed ? (
          <span className="visually-hidden">
            {negative ? t("payments.a11y.moneyOut") : t("payments.a11y.moneyIn")}
          </span>
        ) : null}
        {amount}
      </span>
    );
  };

  UI.Chip = function Chip({ active, disabled, comingSoon, onClick, children }) {
    const t = GEMS.i18n.t;
    return (
      <button
        type="button"
        className="chip"
        aria-pressed={active ? "true" : "false"}
        disabled={disabled}
        title={comingSoon ? t("comingSoon") : undefined}
        onClick={onClick}
      >
        {children}
        {comingSoon ? <span className="chip-soon">{t("comingSoonShort")}</span> : null}
      </button>
    );
  };

  UI.Dialog = function Dialog({ labelledBy, onDismiss, children }) {
    const { useEffect, useRef } = React;
    const surface = useRef(null);

    useEffect(() => {
      const node = surface.current;
      if (node) {
        const focusable = node.querySelector(
          "input:not([disabled]), select, textarea, button:not([disabled])"
        );
        if (focusable) focusable.focus();
      }
      function onKeyDown(event) {
        if (event.key === "Escape") onDismiss();
      }
      document.addEventListener("keydown", onKeyDown);
      return () => document.removeEventListener("keydown", onKeyDown);
    }, [onDismiss]);

    return (
      <div className="dialog-backdrop" onMouseDown={(event) => {
        if (event.target === event.currentTarget) onDismiss();
      }}>
        <div
          className="dialog plate"
          role="dialog"
          aria-modal="true"
          aria-labelledby={labelledBy}
          ref={surface}
        >
          {children}
        </div>
      </div>
    );
  };

  UI.Segmented = function Segmented({ name, value, options, onChange }) {
    const t = GEMS.i18n.t;
    return (
      <div className="seg" role="radiogroup" aria-label={name}>
        {options.map((option) => (
          <label
            key={option.value}
            className="seg-opt"
            data-active={option.value === value ? "true" : "false"}
            data-disabled={option.disabled ? "true" : "false"}
            title={option.comingSoon ? t("comingSoon") : undefined}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={option.value === value}
              disabled={option.disabled}
              onChange={() => onChange(option.value)}
            />
            <span>{option.label}</span>
            {option.comingSoon ? <span className="chip-soon">{t("comingSoonShort")}</span> : null}
          </label>
        ))}
      </div>
    );
  };

  UI.Spinner = function Spinner({ label }) {
    return (
      <div className="text-muted" role="status" style={{ fontSize: 13, padding: "18px 0" }}>
        {label}
      </div>
    );
  };

  UI.classNames = classNames;
})();
