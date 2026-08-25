(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASH = (GEMS.dashboardUi = GEMS.dashboardUi || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const { useState, useRef } = React;

  const CURRENCIES = ["RON", "EUR", "USD"];

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

  DASH.applyQuotes = function applyQuotes(holdings, market) {
    if (!market || !market.quotes) return holdings;
    const byId = {};
    market.quotes.forEach((quote) => { byId[quote.id] = quote; });
    return holdings.map((holding) => {
      const quote = byId[holding.id];
      if (!quote) return holding;
      return Object.assign({}, holding, {
        name: quote.name,
        cur: quote.currency,
        unitPriceMinor: quote.unitPriceMinor,
        quoteCurrency: quote.quoteCurrency,
        quoteUnitPriceMinor: quote.quoteUnitPriceMinor,
        changeBps: quote.changeBps,
        history: quote.history,
        live: quote.live,
        symbol: quote.symbol,
        asOf: quote.asOf,
      });
    });
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
            {DASH.formatMinor(geometry.high)}
          </text>
          <text
            x={CHART.left - 8}
            y={geometry.y(geometry.low) + 3}
            textAnchor="end"
            className="dash-chart-tick"
          >
            {DASH.formatMinor(geometry.low)}
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

  DASH.OpenAccountDialog = function OpenAccountDialog({ accounts, onClose, onSubmit }) {
    const depositFor = (item) => (item.creates === "deposit" ? DATA.depositProducts[item.depositKind] : null);
    const defaultMonths = (item) => {
      const found = depositFor(item);
      return found && found.defaultMonths ? String(found.defaultMonths) : "";
    };

    const [typeKey, setTypeKey] = useState(DATA.accountTypes[0].key);
    const [cur, setCur] = useState("RON");
    const [fundFromId, setFundFromId] = useState("");
    const [amount, setAmount] = useState("");
    const [name, setName] = useState("");
    const [target, setTarget] = useState("");
    const [months, setMonths] = useState(defaultMonths(DATA.accountTypes[0]));

    const type = DATA.accountTypes.find((item) => item.key === typeKey) || DATA.accountTypes[0];
    const product = depositFor(type);
    const opensDeposit = Boolean(product);
    const isGoal = type.depositKind === "goal";
    const terms = product ? product.terms : [];
    const term = terms.find((option) => String(option.months) === months) || null;
    const rateBps = term ? term.rateBps : type.rateBps;

    const sources = accounts.filter((account) => account.cur === cur);
    const from = sources.find((account) => account.id === fundFromId) || null;
    const amountMinor = DASH.parseMinor(amount);
    const targetMinor = DASH.parseMinor(target);
    const shortfall = from && amountMinor != null && amountMinor > from.minor ? amountMinor - from.minor : null;

    const ready = shortfall == null
      && (!opensDeposit || name.trim() !== "")
      && (!isGoal || targetMinor > 0)
      && (opensDeposit
        ? Boolean(from) && amountMinor > 0
        : !from || amountMinor == null || amountMinor > 0);

    const selectType = (value) => {
      const next = DATA.accountTypes.find((item) => item.key === value) || DATA.accountTypes[0];
      setTypeKey(value);
      setMonths(defaultMonths(next));
    };

    const submit = () => {
      if (opensDeposit) {
        onSubmit({
          deposit: {
            id: "dep-" + Date.now(),
            kind: type.depositKind,
            name: name.trim(),
            rateBps,
            matures: term ? DASH.addMonths(new Date(), term.months) : null,
            minor: amountMinor,
            targetMinor: isGoal ? targetMinor : null,
            cur,
          },
          fromId: from.id,
          amountMinor,
        });
        return;
      }

      const iban = DASH.buildIban();
      onSubmit({
        account: {
          id: "acc-" + Date.now(),
          cur,
          typeKey,
          minor: 0,
          iban,
          ibanShort: DASH.shortIban(iban),
        },
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
        action={opensDeposit ? t("dashboard.deposit.submit") : t("dashboard.openAccount.submit")}
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
          <UI.Field
            id="open-term"
            label={isGoal ? t("dashboard.deposit.horizon") : t("dashboard.deposit.term")}
            hint={t("dashboard.deposit.rateHint")}
          >
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

        {opensDeposit ? (
          <UI.Field id="open-name" label={t("dashboard.deposit.name")}>
            <UI.TextInput id="open-name" value={name} placeholder={t("dashboard.deposit.namePh")} onChange={(event) => setName(event.target.value)} />
          </UI.Field>
        ) : null}

        {isGoal ? (
          <UI.Field id="open-target" label={t("dashboard.deposit.target")}>
            <UI.TextInput id="open-target" inputMode="decimal" value={target} placeholder="0,00" onChange={(event) => setTarget(event.target.value)} />
          </UI.Field>
        ) : null}

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
      </Dialog>
    );
  };

  DASH.MoveDepositDialog = function MoveDepositDialog({ deposit, accounts, direction, onClose, onSubmit }) {
    const targets = accounts.filter((account) => account.cur === deposit.cur);
    const [accountId, setAccountId] = useState(targets.length ? targets[0].id : "");
    const [amount, setAmount] = useState("");

    const account = targets.find((item) => item.id === accountId) || null;
    const amountMinor = DASH.parseMinor(amount);
    const topUp = direction === "in";
    const source = topUp ? account : { minor: deposit.minor, cur: deposit.cur };
    const shortfall = source && amountMinor != null && amountMinor > source.minor ? amountMinor - source.minor : null;
    const ready = Boolean(account) && amountMinor > 0 && shortfall == null;

    return (
      <Dialog
        labelledBy="move-deposit-title"
        title={topUp ? t("dashboard.deposit.topUpTitle", { name: deposit.name }) : t("dashboard.deposit.withdrawTitle", { name: deposit.name })}
        subtitle={topUp ? t("dashboard.deposit.topUpSubtitle") : t("dashboard.deposit.withdrawSubtitle")}
        onClose={onClose}
        action={topUp ? t("dashboard.deposit.topUp") : t("dashboard.deposit.withdraw")}
        actionDisabled={!ready}
        onAction={() => onSubmit({ depositId: deposit.id, accountId: account.id, amountMinor, direction })}
      >
        {targets.length ? (
          <UI.Field id="move-account" label={topUp ? t("dashboard.deposit.fundFrom") : t("dashboard.deposit.payInto")}>
            <UI.Select id="move-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
              {targets.map((item) => (
                <option key={item.id} value={item.id}>{DASH.accountLabel(item)}</option>
              ))}
            </UI.Select>
          </UI.Field>
        ) : (
          <div className="dash-balance-line is-short" role="alert">
            {t("dashboard.deposit.noAccount", { currency: deposit.cur })}
          </div>
        )}

        <AmountField
          id="move-amount"
          label={t("dashboard.payDialog.amount")}
          value={amount}
          onChange={setAmount}
          account={topUp ? account : { minor: deposit.minor, cur: deposit.cur }}
          shortfall={shortfall}
        />
      </Dialog>
    );
  };

  DASH.InvestDialog = function InvestDialog({ holdings, accounts, investCashMinor, holdingId, direction, onClose, onSubmit }) {
    const [selectedId, setSelectedId] = useState(holdingId || holdings[0].id);
    const [accountId, setAccountId] = useState(() => {
      const match = accounts.find((account) => account.cur === "RON");
      return match ? match.id : accounts[0].id;
    });
    const [amount, setAmount] = useState("");

    const holding = holdings.find((item) => item.id === selectedId) || holdings[0];
    const account = accounts.find((item) => item.id === accountId) || accounts[0];
    const amountMinor = DASH.parseMinor(amount);
    const buying = direction === "buy";

    const available = buying ? account.minor + investCashMinor : DASH.holdingValue(holding);
    const shortfall = amountMinor != null && amountMinor > available ? amountMinor - available : null;
    const ready = amountMinor > 0 && shortfall == null && account.cur === holding.cur;

    const units = amountMinor > 0 ? amountMinor / holding.unitPriceMinor : 0;

    return (
      <Dialog
        labelledBy="invest-title"
        title={buying ? t("dashboard.invest.buyTitle") : t("dashboard.invest.sellTitle")}
        subtitle={t("dashboard.invest.subtitle")}
        onClose={onClose}
        action={buying ? t("dashboard.invest.buy") : t("dashboard.invest.sell")}
        actionDisabled={!ready}
        onAction={() => onSubmit({ holdingId: holding.id, accountId: account.id, amountMinor, direction })}
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

        <UI.Field id="invest-account" label={buying ? t("dashboard.deposit.fundFrom") : t("dashboard.deposit.payInto")}>
          <UI.Select id="invest-account" value={account.id} onChange={(event) => setAccountId(event.target.value)}>
            {accounts.map((item) => (
              <option key={item.id} value={item.id}>{DASH.accountLabel(item)}</option>
            ))}
          </UI.Select>
        </UI.Field>

        {account.cur === holding.cur ? null : (
          <div className="dash-balance-line is-short" role="alert">
            {t("dashboard.payDialog.sameCurrency")}
          </div>
        )}

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
      </Dialog>
    );
  };

  DASH.CreditApplicationDialog = function CreditApplicationDialog({ accounts, onClose, onSubmit }) {
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
    const ready = amountMinor > 0 && overMax == null;

    const selectProduct = (id) => {
      const next = DATA.creditProducts.find((item) => item.id === id) || DATA.creditProducts[0];
      setProductId(id);
      setMonths(defaultTerm(next));
    };

    const submit = () => {
      onSubmit({
        id: "app-" + Date.now(),
        productId: product.id,
        kind: product.kind,
        amountMinor,
        termMonths: term ? term.months : null,
        rateBps,
        purpose: purpose.trim(),
        payoutAccountId: payout.id,
        cur: payout.cur,
        status: "review",
        submitted: new Date().toISOString().slice(0, 10),
      });
    };

    return (
      <Dialog
        labelledBy="credit-title"
        title={t("dashboard.portfolio.applyCredit")}
        subtitle={t("dashboard.credit.subtitle")}
        onClose={onClose}
        action={t("dashboard.credit.submit")}
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
      </Dialog>
    );
  };
})();
