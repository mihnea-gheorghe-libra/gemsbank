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

  UI.TextInput = function TextInput({ id, ...rest }) {
    return <input id={id} className="input" {...rest} />;
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

  UI.classNames = classNames;
})();
