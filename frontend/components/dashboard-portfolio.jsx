(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASH = (GEMS.dashboardUi = GEMS.dashboardUi || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const api = GEMS.api;
  const { useState, useRef, useEffect } = React;

  const CURRENCIES = ["RON", "EUR", "USD"];
  const RATE_SCALE = 1000000;

  function sameCurrencyFirst(accounts, cur) {
    return accounts.slice().sort((a, b) => (a.cur === cur ? 0 : 1) - (b.cur === cur ? 0 : 1));
  }

  function randomBlock() {
    return String(Math.floor(Math.random() * 10000)).padStart(4, "0");
  }

  DASH.buildIban = function buildIban() {
    const blocks = [randomBlock(), randomBlock(), randomBlock(), randomBlock()];
    return "RO" + String(Math.floor(Math.random() * 90) + 10) + " GEMS " + blocks.join(" ");
  };

  DASH.shortIban = function shortIban(iban) {
    const parts = iban.split(" ");
    return parts[0] + " •••• " + parts[parts.length - 1];
  };

  DASH.addMonths = function addMonths(date, months) {
    const moved = new Date(date.getTime());
    const targetDay = moved.getDate();
    moved.setMonth(moved.getMonth() + months);
    if (moved.getDate() < targetDay) moved.setDate(0);
    return moved.toISOString().slice(0, 10);
  };

  DASH.formatRate = function formatRate(rateBps) {
    return (rateBps / 100).toFixed(2).replace(".", ",") + "%";
  };

  const UNIT_FORMAT = new Intl.NumberFormat("ro-RO", { maximumFractionDigits: 6 });

  DASH.formatUnits = function formatUnits(holding) {
    return UNIT_FORMAT.format(holding.units) + " " + t("dashboard.portfolio.unit." + holding.unitKey);
  };

  DASH.holdingValue = function holdingValue(holding) {
    return Math.round(holding.units * holding.unitPriceMinor);
  };

  DASH.formatChangeBps = function formatChangeBps(changeBps) {
    const sign = changeBps > 0 ? "+" : changeBps < 0 ? "−" : "";
    return sign + (Math.abs(changeBps) / 100).toFixed(2).replace(".", ",") + "%";
  };

  DASH.portfolioSeries = function portfolioSeries(holdings, cashMinor) {
    const priced = holdings.filter((holding) => holding.history && holding.history.length);
    if (!priced.length) return [];

    const days = new Set();
    priced.forEach((holding) => holding.history.forEach((point) => days.add(point.on)));

    const cursors = priced.map((holding) => ({
      holding,
      prices: new Map(holding.history.map((point) => [point.on, point.unitPriceMinor])),
      last: null,
    }));

    const series = [];
    Array.from(days).sort().forEach((on) => {
      let total = cashMinor || 0;
      let complete = true;
      cursors.forEach((cursor) => {
        const price = cursor.prices.get(on);
        if (price !== undefined) cursor.last = price;
        if (cursor.last === null) complete = false;
        else total += Math.round(cursor.holding.units * cursor.last);
      });
      if (complete) series.push({ on, valueMinor: total });
    });
    return series;
  };

  DASH.instrumentSeries = function instrumentSeries(holding) {
    if (!holding || !holding.history) return [];
    return holding.history.map((point) => ({ on: point.on, valueMinor: point.unitPriceMinor }));
  };

  DASH.seriesChangeBps = function seriesChangeBps(series) {
    if (!series || series.length < 2) return null;
    const opening = series[0].valueMinor;
    if (!opening) return null;
    return Math.round(((series[series.length - 1].valueMinor - opening) * 10000) / opening);
  };

  DASH.seriesMonths = function seriesMonths(series) {
    if (!series || series.length < 2) return 0;
    const first = new Date(series[0].on);
    const last = new Date(series[series.length - 1].on);
    return Math.max(1, Math.round((last - first) / (1000 * 60 * 60 * 24 * 30.44)));
  };

  const RANGE_DAYS = { week: 7, month: 31, quarter: 93, half: 186 };

  DASH.sliceSeriesByRange = function sliceSeriesByRange(series, range) {
    if (!series || series.length < 2) return series;

    if (range === "day") {
      return series.slice(-2);
    }

    const days = RANGE_DAYS[range];
    if (!days) return series;
    const cutoff = new Date(series[series.length - 1].on);
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffIso = cutoff.toISOString().slice(0, 10);
    const sliced = series.filter((point) => point.on >= cutoffIso);
    return sliced.length >= 2 ? sliced : series;
  };

  function AmountField({ id, label, value, onChange, account, shortfall }) {
    return (
      <div>
        <UI.Field id={id} label={label}>
          <UI.TextInput
            id={id}
            className={shortfall == null ? undefined : "is-invalid"}
            aria-invalid={shortfall == null ? undefined : "true"}
            inputMode="decimal"
            value={value}
            placeholder="0,00"
            onChange={(event) => onChange(event.target.value)}
          />
        </UI.Field>
        {account ? (
          <div className={UI.classNames("dash-balance-line", shortfall != null && "is-short")} role={shortfall == null ? "status" : "alert"} style={{ marginTop: 8 }}>
            {shortfall == null
              ? t("dashboard.payDialog.availableBalance", {
                  amount: DASH.formatMinor(account.minor) + " " + account.cur,
                })
              : t("dashboard.payDialog.insufficient", {
                  amount: DASH.formatMinor(account.minor) + " " + account.cur,
                  missing: DASH.formatMinor(shortfall) + " " + account.cur,
                })}
          </div>
        ) : null}
      </div>
    );
  }

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function stampFor(market) {
    if (!market) return "";
    const when = new Date(market.refreshedAt);
    return pad2(when.getDate()) + "." + pad2(when.getMonth() + 1) + "." + when.getFullYear() +
      " " + pad2(when.getHours()) + ":" + pad2(when.getMinutes()) + ":" + pad2(when.getSeconds());
  }

  DASH.MarketStatus = function MarketStatus({ market, loading, error, onRefresh }) {
    if (loading && !market) {
      return (
        <div className="dash-market-status" role="status">
          {t("dashboard.invest.loading")}
        </div>
      );
    }

    if (error && !market) {
      return (
        <div className="dash-market-status is-stale" role="alert">
          <span>{t("dashboard.invest.unavailable")}</span>
          <UI.Button type="button" variant="secondary" onClick={() => onRefresh(true)}>
            {t("dashboard.invest.retry")}
          </UI.Button>
        </div>
      );
    }

    if (!market) return null;

    const rate = (market.rates || []).find((item) => item.base === "USD");

    return (
      <div className={UI.classNames("dash-market-status", !market.live && "is-stale")} role="status">
        <span>
          {market.live
            ? t("dashboard.invest.liveAt", { stamp: stampFor(market) })
            : t("dashboard.invest.staleAt", { stamp: stampFor(market) })}
        </span>
        {rate ? (
          <span className="text-muted">
            {t("dashboard.invest.fxNote", {
              rate: (rate.rateMicro / 1000000).toFixed(4).replace(".", ","),
              date: GEMS.i18n.isoToDisplayDate(rate.asOf),
            })}
          </span>
        ) : null}
        <UI.Button type="button" variant="secondary" onClick={() => onRefresh(true)} disabled={loading}>
          {loading ? t("dashboard.invest.refreshing") : t("dashboard.invest.refresh")}
        </UI.Button>
      </div>
    );
  };

  const CHART = { width: 720, height: 240, top: 18, right: 14, bottom: 26, left: 86 };

  function chartGeometry(series) {
    const plotWidth = CHART.width - CHART.left - CHART.right;
    const plotHeight = CHART.height - CHART.top - CHART.bottom;

    let low = Infinity;
    let high = -Infinity;
    series.forEach((point) => {
      if (point.valueMinor < low) low = point.valueMinor;
      if (point.valueMinor > high) high = point.valueMinor;
    });
    const span = high - low || 1;

    const x = (index) =>
      CHART.left + (series.length < 2 ? plotWidth / 2 : (index / (series.length - 1)) * plotWidth);
    const y = (value) => CHART.top + plotHeight - ((value - low) / span) * plotHeight;

    return { low, high, x, y, plotWidth, plotHeight };
  }

  function ChartTooltip({ point, x, previous }) {
    const delta = previous ? point.valueMinor - previous : null;
    const anchorLeft = x / CHART.width;
    const align = anchorLeft < 0.18 ? "0%" : anchorLeft > 0.82 ? "-100%" : "-50%";

    return (
      <div
        className="dash-chart-tip"
        style={{ left: (anchorLeft * 100).toFixed(2) + "%", transform: "translateX(" + align + ")" }}
      >
        <div className="dash-chart-tip-value">{DASH.formatMinor(point.valueMinor)} RON</div>
        <div className="dash-chart-tip-date">{GEMS.i18n.isoToDisplayDate(point.on)}</div>
        {delta === null ? null : (
          <div
            className={UI.classNames(
              "dash-chart-tip-delta",
              delta > 0 && "is-up",
              delta < 0 && "is-down"
            )}
          >
            {(delta > 0 ? "+" : delta < 0 ? "−" : "") + DASH.formatMinor(Math.abs(delta))}
          </div>
        )}
      </div>
    );
  }

  DASH.PriceChart = function PriceChart({ series, label, dimmed }) {
    const [active, setActive] = useState(null);
    const frame = useRef(null);

    if (!series || series.length < 2) return null;

    const geometry = chartGeometry(series);
    const line = series.map((point, index) => geometry.x(index) + "," + geometry.y(point.valueMinor));
    const baseline = CHART.height - CHART.bottom;
    const area =
      "M" + geometry.x(0) + "," + baseline +
      " L" + line.join(" L") +
      " L" + geometry.x(series.length - 1) + "," + baseline + " Z";

    const lastIndex = series.length - 1;
    const shown = active == null ? lastIndex : active;
    const point = series[shown];
    const gradientId = "dash-chart-fill";

    const track = (clientX) => {
      const box = frame.current && frame.current.getBoundingClientRect();
      if (!box || !box.width) return;
      const viewX = ((clientX - box.left) / box.width) * CHART.width;
      const ratio = (viewX - CHART.left) / geometry.plotWidth;
      const index = Math.round(ratio * (series.length - 1));
      setActive(Math.max(0, Math.min(series.length - 1, index)));
    };

    const step = (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const next = shown + (event.key === "ArrowRight" ? 1 : -1);
      setActive(Math.max(0, Math.min(series.length - 1, next)));
    };

    return (
      <div className={UI.classNames("dash-chart", dimmed && "is-dimmed")} ref={frame}>
        <svg
          viewBox={"0 0 " + CHART.width + " " + CHART.height}
          className="dash-chart-svg"
          role="img"
          tabIndex={0}
          aria-label={label}
          onPointerMove={(event) => track(event.clientX)}
          onPointerLeave={() => setActive(null)}
          onKeyDown={step}
          onBlur={() => setActive(null)}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.26" />
              <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0.02" />
            </linearGradient>
          </defs>

          {[geometry.high, (geometry.high + geometry.low) / 2, geometry.low].map((value) => (
            <line
              key={value}
              x1={CHART.left}
              x2={CHART.width - CHART.right}
              y1={geometry.y(value)}
              y2={geometry.y(value)}
              className="dash-chart-grid"
              vectorEffect="non-scaling-stroke"
            />
          ))}

          <path d={area} fill={"url(#" + gradientId + ")"} />
          <polyline
            points={line.join(" ")}
            className="dash-chart-line"
            vectorEffect="non-scaling-stroke"
          />

          <text
            x={CHART.left - 8}
            y={geometry.y(geometry.high) + 3}
            textAnchor="end"
            className="dash-chart-tick"
          >
            {DASH.formatMinor(geometry.high)} RON
          </text>
          <text
            x={CHART.left - 8}
            y={geometry.y(geometry.low) + 3}
            textAnchor="end"
            className="dash-chart-tick"
          >
            {DASH.formatMinor(geometry.low)} RON
          </text>

          <text x={CHART.left} y={CHART.height - 8} className="dash-chart-tick">
            {GEMS.i18n.isoToDisplayDate(series[0].on)}
          </text>
          <text
            x={CHART.width - CHART.right}
            y={CHART.height - 8}
            textAnchor="end"
            className="dash-chart-tick"
          >
            {GEMS.i18n.isoToDisplayDate(series[lastIndex].on)}
          </text>

          <line
            x1={CHART.left}
            x2={CHART.width - CHART.right}
            y1={geometry.y(series[lastIndex].valueMinor)}
            y2={geometry.y(series[lastIndex].valueMinor)}
            className="dash-chart-current-line"
            vectorEffect="non-scaling-stroke"
          />

          {active == null ? null : (
            <line
              x1={geometry.x(shown)}
              x2={geometry.x(shown)}
              y1={CHART.top - 6}
              y2={baseline}
              className="dash-chart-crosshair"
              vectorEffect="non-scaling-stroke"
            />
          )}

          <circle
            cx={geometry.x(shown)}
            cy={geometry.y(point.valueMinor)}
            r="4.5"
            className="dash-chart-dot"
            vectorEffect="non-scaling-stroke"
          />

        </svg>

        {active == null ? null : (
          <ChartTooltip
            point={point}
            x={geometry.x(shown)}
            previous={shown > 0 ? series[shown - 1].valueMinor : null}
          />
        )}
      </div>
    );
  };

  function InfoRow({ label, value }) {
    return (
      <div className="dash-info-row">
        <span className="text-muted">{label}</span>
        <span>{value}</span>
      </div>
    );
  }

  function AccountTypeTerms({ type, cur, showRate }) {
    const money = (minor) => DASH.formatMinor(minor) + " " + cur;

    return (
      <div className="dash-info-card">
        <UI.Kicker>{t("dashboard.openAccount.termsTitle")}</UI.Kicker>
        <p className="text-muted" style={{ fontSize: 12, margin: "6px 0 10px" }}>
          {t("dashboard.openAccount.blurb." + type.key)}
        </p>
        {showRate ? (
          <InfoRow
            label={t("dashboard.openAccount.rate")}
            value={type.rateBps
              ? t("dashboard.openAccount.rateValue", { rate: DASH.formatRate(type.rateBps) })
              : t("dashboard.openAccount.noRate")}
          />
        ) : null}
        <InfoRow
          label={t("dashboard.openAccount.fee")}
          value={type.monthlyFeeMinor ? money(type.monthlyFeeMinor) : t("dashboard.openAccount.noFee")}
        />
        <InfoRow
          label={t("dashboard.openAccount.minOpen")}
          value={type.minOpenMinor ? money(type.minOpenMinor) : t("dashboard.openAccount.noMinimum")}
        />
        <InfoRow
          label={t("dashboard.openAccount.access")}
          value={t("dashboard.openAccount.accessValue." + type.accessKey)}
        />
      </div>
    );
  }

  function Dialog({ labelledBy, title, subtitle, onClose, children, action, actionDisabled, onAction }) {
    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby={labelledBy} onClick={(event) => event.stopPropagation()}>
          <h2 id={labelledBy} style={{ margin: 0 }}>{title}</h2>
          {subtitle ? <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>{subtitle}</p> : null}
          {children}
          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={actionDisabled} onClick={onAction}>{action}</UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  }

  DASH.OpenAccountDialog = function OpenAccountDialog({ accounts, initialTypeKey, busy, error, onClose, onSubmit }) {
    const depositFor = (item) => (item.creates === "deposit" ? DATA.depositProducts[item.depositKind] : null);
    const defaultMonths = (item) => {
      const found = depositFor(item);
      return found && found.defaultMonths ? String(found.defaultMonths) : "";
    };

    const initialType = DATA.accountTypes.find((item) => item.key === initialTypeKey) || DATA.accountTypes[0];

    const [typeKey, setTypeKey] = useState(initialType.key);
    const [cur, setCur] = useState("RON");
    const [fundFromId, setFundFromId] = useState("");
    const [amount, setAmount] = useState("");
    const [name, setName] = useState("");
    const [months, setMonths] = useState(defaultMonths(initialType));

    const type = DATA.accountTypes.find((item) => item.key === typeKey) || DATA.accountTypes[0];
    const product = depositFor(type);
    const opensDeposit = Boolean(product);
    const terms = product ? product.terms : [];
    const term = terms.find((option) => String(option.months) === months) || null;
    const rateBps = term ? term.rateBps : type.rateBps;

    const sources = accounts.filter((account) => account.cur === cur);
    const from = sources.find((account) => account.id === fundFromId) || null;
    const amountMinor = DASH.parseMinor(amount);
    const shortfall = from && amountMinor != null && amountMinor > from.minor ? amountMinor - from.minor : null;

    const ready = shortfall == null
      && (opensDeposit
        ? name.trim() !== "" && Boolean(from) && amountMinor > 0
        : !from || amountMinor == null || amountMinor > 0)
      && !busy;

    const selectType = (value) => {
      const next = DATA.accountTypes.find((item) => item.key === value) || DATA.accountTypes[0];
      setTypeKey(value);
      setMonths(defaultMonths(next));
    };

    const submit = () => {
      if (opensDeposit) {
        onSubmit({
          termDeposit: {
            parentAccountId: from.id,
            name: name.trim(),
            termMonths: term.months,
            initialDepositMinorUnits: amountMinor,
          },
        });
        return;
      }

      onSubmit({
        account: { cur, typeKey, label: name.trim() || t("dashboard.accountType." + typeKey) },
        fundFromId: from && amountMinor > 0 ? from.id : null,
        fundMinor: from && amountMinor > 0 ? amountMinor : 0,
      });
    };

    return (
      <Dialog
        labelledBy="open-account-title"
        title={t("dashboard.portfolio.openAccount")}
        subtitle={opensDeposit ? t("dashboard.deposit.subtitle") : t("dashboard.openAccount.subtitle")}
        onClose={onClose}
        action={busy ? t("dashboard.payDialog.sending") : (opensDeposit ? t("dashboard.deposit.submit") : t("dashboard.openAccount.submit"))}
        actionDisabled={!ready}
        onAction={submit}
      >
        <div className="dash-field-grid">
          <UI.Field id="open-type" label={t("dashboard.openAccount.type")}>
            <UI.Select id="open-type" value={typeKey} onChange={(event) => selectType(event.target.value)}>
              {DATA.accountTypes.map((item) => (
                <option key={item.key} value={item.key}>{t("dashboard.accountType." + item.key)}</option>
              ))}
            </UI.Select>
          </UI.Field>
          <UI.Field id="open-currency" label={t("dashboard.payDialog.currency")}>
            <UI.Select id="open-currency" value={cur} onChange={(event) => { setCur(event.target.value); setFundFromId(""); }}>
              {CURRENCIES.map((code) => <option key={code} value={code}>{code}</option>)}
            </UI.Select>
          </UI.Field>
        </div>

        {terms.length ? (
          <UI.Field id="open-term" label={t("dashboard.deposit.term")} hint={t("dashboard.deposit.rateHint")}>
            <UI.Select id="open-term" value={months} onChange={(event) => setMonths(event.target.value)}>
              {terms.map((option) => (
                <option key={option.months} value={String(option.months)}>
                  {t("dashboard.deposit.months", { n: option.months })}
                </option>
              ))}
            </UI.Select>
          </UI.Field>
        ) : null}

        {term ? (
          <div className="dash-rate-card" role="status">
            <span className="dash-rate-label">{t("dashboard.deposit.rateTitle")}</span>
            <span className="dash-rate-value">{DASH.formatRate(rateBps)}</span>
            <span className="text-muted dash-rate-note">
              {t("dashboard.deposit.rateForTerm", { term: t("dashboard.deposit.months", { n: term.months }) })}
            </span>
          </div>
        ) : null}

        <AccountTypeTerms type={type} cur={cur} showRate={!term} />

        <UI.Field
          id="open-name"
          label={opensDeposit ? t("dashboard.deposit.name") : t("dashboard.openAccount.name")}
          hint={opensDeposit ? null : t("dashboard.openAccount.nameHint")}
        >
          <UI.TextInput
            id="open-name"
            value={name}
            placeholder={opensDeposit ? t("dashboard.deposit.namePh") : t("dashboard.openAccount.namePh")}
            onChange={(event) => setName(event.target.value)}
          />
        </UI.Field>

        {opensDeposit && !sources.length ? (
          <div className="dash-balance-line is-short" role="alert">
            {t("dashboard.deposit.noAccount", { currency: cur })}
          </div>
        ) : (
          <UI.Field
            id="open-fund"
            label={opensDeposit ? t("dashboard.deposit.fundFrom") : t("dashboard.openAccount.fundFrom")}
            hint={t("dashboard.openAccount.fundHint")}
          >
            <UI.Select id="open-fund" value={fundFromId} onChange={(event) => setFundFromId(event.target.value)}>
              <option value="">
                {opensDeposit ? t("dashboard.openAccount.pickAccount") : t("dashboard.openAccount.noFunding")}
              </option>
              {sources.map((account) => (
                <option key={account.id} value={account.id}>{DASH.accountLabel(account)}</option>
              ))}
            </UI.Select>
          </UI.Field>
        )}

        {from ? (
          <AmountField
            id="open-amount"
            label={opensDeposit ? t("dashboard.deposit.openingAmount") : t("dashboard.payDialog.amount")}
            value={amount}
            onChange={setAmount}
            account={from}
            shortfall={shortfall}
          />
        ) : null}

        {error ? (
          <div className="dash-balance-line is-short" role="alert">{error.message}</div>
        ) : null}
      </Dialog>
    );
  };

  DASH.MoveDepositDialog = function MoveDepositDialog({ deposit, accounts, direction, busy, error, onClose, onSubmit }) {
    const [amount, setAmount] = useState("");
    const parent = accounts.find((item) => item.id === deposit.parentAccountId) || null;

    const amountMinor = DASH.parseMinor(amount);
    const topUp = direction === "in";
    const source = topUp ? parent : { minor: deposit.minor, cur: deposit.cur };
    const shortfall = source && amountMinor != null && amountMinor > source.minor ? amountMinor - source.minor : null;
    const ready = Boolean(parent) && amountMinor > 0 && shortfall == null && !busy;

    return (
      <Dialog
        labelledBy="move-deposit-title"
        title={topUp ? t("dashboard.deposit.topUpTitle", { name: deposit.name }) : t("dashboard.deposit.withdrawTitle", { name: deposit.name })}
        subtitle={topUp ? t("dashboard.deposit.topUpSubtitle") : t("dashboard.deposit.withdrawSubtitle")}
        onClose={onClose}
        action={busy ? t("dashboard.payDialog.sending") : (topUp ? t("dashboard.deposit.topUp") : t("dashboard.deposit.withdraw"))}
        actionDisabled={!ready}
        onAction={() => onSubmit({ depositId: deposit.id, amountMinor, direction })}
      >
        <AmountField
          id="move-amount"
          label={t("dashboard.payDialog.amount")}
          value={amount}
          onChange={setAmount}
          account={topUp ? parent : { minor: deposit.minor, cur: deposit.cur }}
          shortfall={shortfall}
        />

        {error ? (
          <div className="dash-balance-line is-short" role="alert">{error.message}</div>
        ) : null}
      </Dialog>
    );
  };

  DASH.DeleteAccountDialog = function DeleteAccountDialog({ account, busy, error, onClose, onSubmit }) {
    return (
      <Dialog
        labelledBy="delete-account-title"
        title={t("dashboard.accounts.deleteDialogTitle")}
        subtitle={t("dashboard.accounts.deleteDialogBody", { label: DASH.accountLabel(account) })}
        onClose={onClose}
        action={busy ? t("dashboard.payDialog.sending") : t("dashboard.accounts.deleteConfirm")}
        actionDisabled={busy}
        onAction={() => onSubmit(account.id)}
      >
        {error ? (
          <div className="dash-balance-line is-short" role="alert">{error.message}</div>
        ) : null}
      </Dialog>
    );
  };

  DASH.InvestDialog = function InvestDialog({ holdings, investCashMinor, holdingId, direction, busy, error, onClose, onSubmit }) {
    const [selectedId, setSelectedId] = useState(holdingId || holdings[0].id);
    const [amount, setAmount] = useState("");

    const holding = holdings.find((item) => item.id === selectedId) || holdings[0];
    const amountMinor = DASH.parseMinor(amount);
    const buying = direction === "buy";

    const available = buying ? investCashMinor || 0 : DASH.holdingValue(holding);
    const shortfall = amountMinor != null && amountMinor > available ? amountMinor - available : null;
    const ready = amountMinor > 0 && shortfall == null && !busy;

    const units = amountMinor > 0 ? amountMinor / holding.unitPriceMinor : 0;

    return (
      <Dialog
        labelledBy="invest-title"
        title={buying ? t("dashboard.invest.buyTitle") : t("dashboard.invest.sellTitle")}
        subtitle={t("dashboard.invest.subtitle")}
        onClose={onClose}
        action={busy ? t("dashboard.payDialog.sending") : (buying ? t("dashboard.invest.buy") : t("dashboard.invest.sell"))}
        actionDisabled={!ready}
        onAction={() => onSubmit({ holdingId: holding.id, amountMinor, direction })}
      >
        <UI.Field id="invest-holding" label={t("dashboard.invest.instrument")}>
          <UI.Select id="invest-holding" value={holding.id} onChange={(event) => setSelectedId(event.target.value)}>
            {holdings.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </UI.Select>
        </UI.Field>

        <div className="dash-balance-line" role="status">
          {t("dashboard.invest.unitPrice", {
            price: DASH.formatMinor(holding.unitPriceMinor) + " " + holding.cur,
          })}
        </div>

        <AmountField
          id="invest-amount"
          label={t("dashboard.payDialog.amount")}
          value={amount}
          onChange={setAmount}
          account={{ minor: available, cur: holding.cur }}
          shortfall={shortfall}
        />

        <div className="dash-balance-line" role="status">
          {buying
            ? t("dashboard.invest.buyPreview", { units: UNIT_FORMAT.format(units), unit: t("dashboard.portfolio.unit." + holding.unitKey) })
            : t("dashboard.invest.sellPreview", { units: UNIT_FORMAT.format(Math.min(units, holding.units)), unit: t("dashboard.portfolio.unit." + holding.unitKey) })}
        </div>

        {error ? (
          <div className="dash-balance-line is-short" role="alert">{error.message}</div>
        ) : null}
      </Dialog>
    );
  };

  DASH.CreditApplicationDialog = function CreditApplicationDialog({ accounts, busy, error, onClose, onSubmit }) {
    const defaultTerm = (item) => (item.terms.length ? String(item.terms[item.terms.length - 1].months) : "");

    const [productId, setProductId] = useState(DATA.creditProducts[0].id);
    const [amount, setAmount] = useState("");
    const [months, setMonths] = useState(defaultTerm(DATA.creditProducts[0]));
    const [purpose, setPurpose] = useState("");
    const [payoutId, setPayoutId] = useState(accounts[0].id);

    const product = DATA.creditProducts.find((item) => item.id === productId) || DATA.creditProducts[0];
    const term = product.terms.find((option) => String(option.months) === months) || null;
    const rateBps = term ? term.rateBps : product.rateBps;
    const payout = accounts.find((account) => account.id === payoutId) || accounts[0];
    const amountMinor = DASH.parseMinor(amount);
    const overMax = amountMinor != null && amountMinor > product.maxMinor ? amountMinor - product.maxMinor : null;
    const ready = amountMinor > 0 && overMax == null && !busy;

    const selectProduct = (id) => {
      const next = DATA.creditProducts.find((item) => item.id === id) || DATA.creditProducts[0];
      setProductId(id);
      setMonths(defaultTerm(next));
    };

    const submit = () => {
      onSubmit({
        productId: product.id,
        amountMinorUnits: amountMinor,
        termMonths: term ? term.months : null,
        purpose: purpose.trim(),
        payoutAccountId: payout.id,
      });
    };

    return (
      <Dialog
        labelledBy="credit-title"
        title={t("dashboard.portfolio.applyCredit")}
        subtitle={t("dashboard.credit.subtitle")}
        onClose={onClose}
        action={busy ? t("dashboard.payDialog.sending") : t("dashboard.credit.submit")}
        actionDisabled={!ready}
        onAction={submit}
      >
        <UI.Field id="credit-product" label={t("dashboard.credit.product")}>
          <UI.Select id="credit-product" value={product.id} onChange={(event) => selectProduct(event.target.value)}>
            {DATA.creditProducts.map((item) => (
              <option key={item.id} value={item.id}>{t("dashboard.credit.name." + item.id)}</option>
            ))}
          </UI.Select>
        </UI.Field>

        <UI.Field
          id="credit-amount"
          label={t("dashboard.payDialog.amount")}
          hint={t("dashboard.credit.maxNote", { amount: DASH.formatMinor(product.maxMinor) + " " + payout.cur })}
        >
          <UI.TextInput
            id="credit-amount"
            className={overMax == null ? undefined : "is-invalid"}
            aria-invalid={overMax == null ? undefined : "true"}
            inputMode="decimal"
            value={amount}
            placeholder="0,00"
            onChange={(event) => setAmount(event.target.value)}
          />
        </UI.Field>

        {overMax == null ? null : (
          <div className="dash-balance-line is-short" role="alert">
            {t("dashboard.credit.overMax", { amount: DASH.formatMinor(product.maxMinor) + " " + payout.cur })}
          </div>
        )}

        {product.terms.length ? (
          <UI.Field id="credit-term" label={t("dashboard.credit.term")} hint={t("dashboard.credit.rateHint")}>
            <UI.Select id="credit-term" value={months} onChange={(event) => setMonths(event.target.value)}>
              {product.terms.map((option) => (
                <option key={option.months} value={String(option.months)}>
                  {t("dashboard.deposit.months", { n: option.months })}
                </option>
              ))}
            </UI.Select>
          </UI.Field>
        ) : null}

        <div className="dash-rate-card" role="status">
          <span className="dash-rate-label">{t("dashboard.credit.rateTitle")}</span>
          <span className="dash-rate-value">{DASH.formatRate(rateBps)}</span>
          <span className="text-muted dash-rate-note">
            {term
              ? t("dashboard.credit.rateForTerm", { term: t("dashboard.deposit.months", { n: term.months }) })
              : t("dashboard.credit.rateRevolving")}
          </span>
        </div>

        <UI.Field id="credit-payout" label={t("dashboard.credit.payout")}>
          <UI.Select id="credit-payout" value={payout.id} onChange={(event) => setPayoutId(event.target.value)}>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>{DASH.accountLabel(account)}</option>
            ))}
          </UI.Select>
        </UI.Field>

        <UI.Field id="credit-purpose" label={t("dashboard.credit.purpose")}>
          <UI.TextInput id="credit-purpose" value={purpose} placeholder={t("dashboard.credit.purposePh")} onChange={(event) => setPurpose(event.target.value)} />
        </UI.Field>

        <p className="text-muted" style={{ fontSize: 12, margin: 0 }}>{t("dashboard.credit.agentNote")}</p>

        {error ? (
          <div className="dash-balance-line is-short" role="alert">{error.message}</div>
        ) : null}
      </Dialog>
    );
  };

  DASH.QuickTransferDialog = function QuickTransferDialog({ accounts, busy, error, onClose, onSubmit }) {
    const [sourceId, setSourceId] = useState(accounts[0] ? accounts[0].id : "");
    const [amount, setAmount] = useState("");

    const source = accounts.find((account) => account.id === sourceId) || null;
    const targets = sameCurrencyFirst(accounts.filter((account) => account.id !== sourceId), source && source.cur);
    const [targetId, setTargetId] = useState(targets[0] ? targets[0].id : "");
    const target = targets.find((account) => account.id === targetId) || null;

    const crossCurrency = Boolean(source && target && source.cur !== target.cur);

    const [rate, setRate] = useState(null);
    const [rateLoading, setRateLoading] = useState(false);
    const [rateError, setRateError] = useState(null);

    useEffect(() => {
      if (!crossCurrency) {
        setRate(null);
        setRateError(null);
        return;
      }
      let cancelled = false;
      setRateLoading(true);
      setRateError(null);
      api
        .exchangeRate(source.cur, target.cur)
        .then((result) => {
          if (!cancelled) setRate(result);
        })
        .catch((err) => {
          if (!cancelled) setRateError(err);
        })
        .finally(() => {
          if (!cancelled) setRateLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }, [crossCurrency, source && source.cur, target && target.cur]);

    const amountMinor = DASH.parseMinor(amount);
    const shortfall = source && amountMinor != null && amountMinor > source.minor ? amountMinor - source.minor : null;
    const targetAmountMinor = crossCurrency && rate && amountMinor > 0
      ? Math.round((amountMinor * rate.rateMicro) / RATE_SCALE)
      : null;
    const ready = Boolean(source) && Boolean(target) && amountMinor > 0 && shortfall == null
      && (!crossCurrency || Boolean(rate)) && !busy;

    const selectSource = (value) => {
      setSourceId(value);
      const nextSource = accounts.find((account) => account.id === value) || null;
      const nextTargets = sameCurrencyFirst(
        accounts.filter((account) => account.id !== value), nextSource && nextSource.cur
      );
      setTargetId(nextTargets[0] ? nextTargets[0].id : "");
    };

    return (
      <Dialog
        labelledBy="quick-transfer-title"
        title={t("dashboard.accounts.quickTransferTitle")}
        subtitle={t("dashboard.accounts.quickTransferSubtitle")}
        onClose={onClose}
        action={busy ? t("dashboard.payDialog.sending") : t("dashboard.accounts.quickTransferSubmit")}
        actionDisabled={!ready}
        onAction={() => onSubmit({ sourceAccountId: source.id, targetAccountId: target.id, amountMinor })}
      >
        <UI.Field id="quick-transfer-source" label={t("dashboard.accounts.quickTransferFrom")}>
          <UI.Select id="quick-transfer-source" value={sourceId} onChange={(event) => selectSource(event.target.value)}>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>{DASH.accountLabel(account)}</option>
            ))}
          </UI.Select>
        </UI.Field>

        {targets.length ? (
          <UI.Field id="quick-transfer-target" label={t("dashboard.accounts.quickTransferTo")}>
            <UI.Select id="quick-transfer-target" value={targetId} onChange={(event) => setTargetId(event.target.value)}>
              {targets.map((account) => (
                <option key={account.id} value={account.id}>{DASH.accountLabel(account)}</option>
              ))}
            </UI.Select>
          </UI.Field>
        ) : (
          <div className="dash-balance-line is-short" role="alert">
            {t("dashboard.accounts.quickTransferNoTarget")}
          </div>
        )}

        <AmountField
          id="quick-transfer-amount"
          label={t("dashboard.payDialog.amount")}
          value={amount}
          onChange={setAmount}
          account={source}
          shortfall={shortfall}
        />

        {crossCurrency ? (
          <div className="dash-balance-line" role="status">
            {rateLoading
              ? t("dashboard.exchange.rateLoading")
              : rateError
                ? t("dashboard.exchange.rateUnavailable")
                : rate
                  ? t("dashboard.exchange.rateNote", {
                      source: source.cur,
                      rate: (rate.rateMicro / RATE_SCALE).toFixed(4).replace(".", ","),
                      target: target.cur,
                    })
                  : null}
          </div>
        ) : null}

        {targetAmountMinor != null ? (
          <div className="dash-balance-line" role="status">
            {t("dashboard.exchange.youReceive", {
              amount: DASH.formatMinor(targetAmountMinor) + " " + target.cur,
            })}
          </div>
        ) : null}

        {error ? (
          <div className="dash-balance-line is-short" role="alert">{error.message}</div>
        ) : null}
      </Dialog>
    );
  };
})();
