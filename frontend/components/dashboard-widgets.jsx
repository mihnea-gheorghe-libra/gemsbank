(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASH = (GEMS.dashboardUi = GEMS.dashboardUi || {});
  const UI = GEMS.ui;

  const MINOR_PER_MAJOR = 100;

  const AMOUNT_FORMAT = new Intl.NumberFormat("ro-RO", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  DASH.formatMinor = function formatMinor(minor) {
    return AMOUNT_FORMAT.format(Math.abs(minor) / MINOR_PER_MAJOR);
  };

  DASH.parseMinor = function parseMinor(text) {
    const cleaned = String(text == null ? "" : text).trim().replace(/\s/g, "");
    if (!cleaned) return null;
    const normalised = cleaned.indexOf(",") >= 0
      ? cleaned.replace(/\./g, "").replace(",", ".")
      : cleaned;
    if (!/^\d+(\.\d{1,2})?$/.test(normalised)) return null;
    const [major, fraction = ""] = normalised.split(".");
    return Number(major) * MINOR_PER_MAJOR + Number((fraction + "00").slice(0, 2));
  };

  DASH.splitEvenly = function splitEvenly(totalMinor, parts) {
    if (parts <= 0) return [];
    const base = Math.floor(totalMinor / parts);
    const remainder = totalMinor - base * parts;
    return Array.from({ length: parts }, (unused, index) => base + (index < remainder ? 1 : 0));
  };

  DASH.SegmentedControl = function SegmentedControl({ options, value, onChange, label, className }) {
    return (
      <div className={UI.classNames("dash-seg", className)} role="radiogroup" aria-label={label}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={option.value === value}
            className={UI.classNames("dash-seg-opt", option.value === value && "is-active")}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    );
  };

  // Amount with an explicit sign glyph — colour alone never carries the
  // debit/credit meaning (tokens.css §4.2 / WCAG 2.2 AA 1.4.1).
  DASH.Amount = function Amount({ minor, direction, currency = "RON", className }) {
    const sign = direction === "in" ? "+" : "−";
    const cls = direction === "in" ? "dash-amt-in" : "dash-amt-out";
    return (
      <span className={UI.classNames("dash-amt", cls, className)}>
        {sign} {DASH.formatMinor(minor)} {currency}
      </span>
    );
  };

  DASH.Bars = function Bars({ items }) {
    return (
      <div className="dash-bars">
        {items.map((item, index) => (
          <div className="dash-bar-col" key={index}>
            <div className="dash-bar-fill" style={{ height: item.pct + "%" }} />
            <span className="dash-bar-label">{item.label}</span>
          </div>
        ))}
      </div>
    );
  };

  DASH.BigBars = function BigBars({ items, incomeLabel, spendLabel }) {
    return (
      <div className="dash-bigbars" role="img" aria-label={incomeLabel + " / " + spendLabel}>
        {items.map((item, index) => (
          <div className="dash-bigbar-col" key={index}>
            <div className="dash-bigbar-pair">
              <div className="dash-bigbar-in" style={{ height: item.inc + "%" }} />
              <div className="dash-bigbar-out" style={{ height: item.out + "%" }} />
            </div>
            <span className="dash-bar-label">{item.label}</span>
          </div>
        ))}
      </div>
    );
  };

  DASH.ProgressBar = function ProgressBar({ pct, label }) {
    return (
      <div className="dash-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <span style={{ width: pct + "%" }} />
      </div>
    );
  };

  DASH.Donut = function Donut({ slices, label }) {
    // slices: [{ color: 'var(--color-x)', pct }] summing to 100.
    let cursor = 0;
    const stops = slices
      .map((slice) => {
        const from = cursor;
        cursor += slice.pct;
        return slice.color + " " + from + "% " + cursor + "%";
      })
      .join(", ");
    return (
      <div
        className="dash-donut"
        role="img"
        aria-label={label}
        style={{ background: "conic-gradient(" + stops + ")" }}
      />
    );
  };
})();
