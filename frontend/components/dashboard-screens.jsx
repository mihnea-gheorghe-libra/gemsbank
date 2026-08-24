(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const SCR = (GEMS.dashboardScreens = GEMS.dashboardScreens || {});
  const UI = GEMS.ui;
  const DASH = GEMS.dashboardUi;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const api = GEMS.api;
  const { useState, useEffect } = React;

  const QUICK_ACTIONS = [
    { icon: "Send", key: "transact", go: "payments" },
    { icon: "Plus", key: "addFunds", go: "portfolio" },
    { icon: "ArrowLeftRight", key: "exchange", go: "portfolio" },
    { icon: "QrCode", key: "scanQr", go: "payments" },
  ];

  const MONEY_FORMAT = new Intl.NumberFormat("ro-RO", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function formatMinor(minor) {
    return MONEY_FORMAT.format(minor / 100);
  }

  function kindToI18nKey(kind) {
    return kind.replace(/_([a-z])/g, (match, letter) => letter.toUpperCase());
  }

  function formatExpiry(iso) {
    if (!iso) return "";
    const [year, month] = iso.split("-");
    return month + "/" + year.slice(2);
  }

  function useLiveDate() {
    const [now, setNow] = useState(() => new Date());
    useEffect(() => {
      const id = setInterval(() => setNow(new Date()), 60000);
      return () => clearInterval(id);
    }, []);
    return now;
  }

  function formatCardDate(date) {
    const locale = GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB";
    return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
  }

  function TxTable({ rows, compact }) {
    return (
      <div style={{ overflowX: "auto" }}>
        <table className="dash-table">
          <thead>
            <tr>
              <th>{t("dashboard.table.date")}</th>
              <th>{t("dashboard.table.counterparty")}</th>
              {compact ? null : <th>{t("dashboard.table.reference")}</th>}
              <th>{t("dashboard.table.category")}</th>
              <th>{t("dashboard.table.status")}</th>
              <th className="amount-col">{t("dashboard.table.amount")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{row.date}</td>
                <td>{row.who}</td>
                {compact ? null : <td className="text-muted" style={{ fontSize: 12 }}>{row.ref}</td>}
                <td className="text-muted">{t("dashboard.category." + row.categoryKey)}</td>
                <td><UI.Tag variant="accent">{t("dashboard.status." + row.statusKey)}</UI.Tag></td>
                <td className="amount-col">
                  <DASH.Amount value={row.amount} direction={row.direction} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  SCR.HomeScreen = function HomeScreen({ balanceHidden, onToggleBalance, onNavigate }) {
    return (
      <div className="dash-grid-home">
        <UI.Plate className="dash-balance-card elev-sm">
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.home.totalBalance")}</UI.Kicker>
            <UI.Button type="button" variant="ghost" style={{ gap: 6 }} onClick={onToggleBalance}>
              <UI.Icon name={balanceHidden ? "Eye" : "EyeOff"} size={15} />
              {balanceHidden ? t("dashboard.home.reveal") : t("dashboard.home.hide")}
            </UI.Button>
          </div>
          <div className="dash-balance-figure">
            {balanceHidden ? "•••••••• RON" : DATA.totalBalance + " RON"}
          </div>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {balanceHidden ? t("dashboard.home.balanceHiddenSub") : t("dashboard.home.balanceSub")}
          </div>

          <div className="hr" />

          <div className="dash-quick-grid">
            {QUICK_ACTIONS.map((action) => (
              <UI.Button key={action.key} type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 10, minHeight: 46 }} onClick={() => onNavigate(action.go)}>
                <UI.Icon name={action.icon} size={16} style={{ color: "var(--color-primary)" }} />
                {t("dashboard.home.quick." + action.key)}
              </UI.Button>
            ))}
          </div>
        </UI.Plate>

        <UI.Plate className="dash-accounts-card elev-sm">
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.home.accounts")}</UI.Kicker>
            <a href="#" onClick={(event) => { event.preventDefault(); onNavigate("portfolio"); }}>{t("dashboard.home.openAccount")}</a>
          </div>
          <div className="dash-accounts-tiles">
            {DATA.accounts.map((account, index) => (
              <UI.Plate key={index} className="dash-account-tile">
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.12em", opacity: 0.55 }}>
                  {account.cur} · {t("dashboard.accountType." + account.typeKey)}
                </div>
                <div className="dash-account-amount">{balanceHidden ? "••••••" : account.amount}</div>
                <div className="text-muted" style={{ fontSize: 11 }}>{account.iban}</div>
              </UI.Plate>
            ))}
          </div>
        </UI.Plate>

        {/* Moved below the accounts frame, same footprint (grid-column: span 2) per request. */}
        <UI.Plate className="dash-accounts-card elev-sm">
          <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.home.insights")}</UI.Kicker>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13, lineHeight: 1.5 }}>
            <div>{t("dashboard.home.insightNetflix")}</div>
            <div className="hr" style={{ margin: 0 }} />
            <div>{t("dashboard.home.insightFx")}</div>
            <UI.Button type="button" variant="ghost" style={{ alignSelf: "flex-start", padding: 0 }} onClick={() => onNavigate("chat")}>
              {t("dashboard.home.askAgent")}
            </UI.Button>
          </div>
        </UI.Plate>

        <UI.Plate className="elev-sm" style={{ padding: 18, gridColumn: "1 / -1" }}>
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.home.recentActivity")}</UI.Kicker>
            <a href="#" onClick={(event) => { event.preventDefault(); onNavigate("payments"); }}>{t("dashboard.home.allTransactions")}</a>
          </div>
          <TxTable rows={DATA.transactions.slice(0, 4)} compact />
        </UI.Plate>
      </div>
    );
  };

  SCR.PaymentsScreen = function PaymentsScreen({ filter, onFilter, onOpenPay }) {
    const filters = ["all", "income", "spending", "pending", "cards"];
    return (
      <div>
        <div className="dash-screen-head">
          <div>
            <h3 style={{ margin: 0 }}>{t("dashboard.payments.title")}</h3>
            <div className="text-muted" style={{ fontSize: 13 }}>
              {t("dashboard.payments.subtitle", { count: DATA.transactions.length, pending: DATA.pending.length })}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <UI.Button type="button" variant="secondary">{t("dashboard.payments.splitBill")}</UI.Button>
            <UI.Button type="button" variant="secondary">{t("dashboard.payments.scanQr")}</UI.Button>
            <UI.Button type="button" variant="primary" onClick={onOpenPay}>{t("dashboard.payments.newPayment")}</UI.Button>
          </div>
        </div>

        <UI.Plate className="elev-sm" style={{ padding: 16, marginBottom: 18 }}>
          <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.payments.pendingTitle")}</UI.Kicker>
          <div className="dash-pending-grid">
            {DATA.pending.map((row, index) => (
              <div className="dash-pending-row" key={index}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-primary)" }}>{row.num}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>{row.who}</div>
                  <div className="text-muted" style={{ fontSize: 11 }}>{t("dashboard.payments.note." + row.noteKey)}</div>
                </div>
                <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>{row.amount} RON</div>
                <UI.Button type="button" variant="secondary">{t("dashboard.payments.sign")}</UI.Button>
              </div>
            ))}
          </div>
        </UI.Plate>

        <UI.Plate className="elev-sm" style={{ padding: 16 }}>
          <div className="dash-filters-row">
            {filters.map((key) => (
              <UI.Button key={key} type="button" variant={filter === key ? "primary" : "secondary"} onClick={() => onFilter(key)}>
                {t("dashboard.payments.filter." + key)}
              </UI.Button>
            ))}
            <UI.TextInput style={{ marginLeft: "auto", maxWidth: 260 }} placeholder={t("dashboard.payments.filterPlaceholder")} aria-label={t("dashboard.payments.filterPlaceholder")} />
          </div>
          <TxTable rows={DATA.transactions} />
        </UI.Plate>
      </div>
    );
  };

  SCR.PortfolioScreen = function PortfolioScreen() {
    return (
      <div>
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.portfolio.title")}</h3>
          <UI.Button type="button" variant="primary">{t("dashboard.portfolio.openAccount")}</UI.Button>
        </div>

        <div className="dash-portfolio-tiles">
          {DATA.accountsFull.map((account, index) => (
            <UI.Plate key={index} className="elev-sm" style={{ padding: 14 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.12em", opacity: 0.55 }}>
                {account.cur} · {t("dashboard.accountType." + account.typeKey)}
              </div>
              <div className="dash-account-amount">{account.amount}</div>
              <div className="text-muted" style={{ fontSize: 11 }}>{account.iban}</div>
            </UI.Plate>
          ))}
        </div>

        <div className="dash-portfolio-cols">
          <UI.Plate className="elev-sm" style={{ padding: 16 }}>
            <div className="dash-kicker-row">
              <UI.Kicker>{t("dashboard.portfolio.deposits")}</UI.Kicker>
              <UI.Button type="button" variant="ghost">{t("dashboard.portfolio.newDeposit")}</UI.Button>
            </div>
            <table className="dash-table">
              <thead>
                <tr>
                  <th>{t("dashboard.portfolio.product")}</th>
                  <th>{t("dashboard.portfolio.rate")}</th>
                  <th>{t("dashboard.portfolio.matures")}</th>
                  <th className="amount-col">{t("dashboard.portfolio.value")}</th>
                </tr>
              </thead>
              <tbody>
                {DATA.deposits.map((row, index) => (
                  <tr key={index}>
                    <td>{row.name}</td>
                    <td className="text-muted">{row.rate}</td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{row.due}</td>
                    <td className="amount-col">{row.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 16 }}>
            <div className="dash-kicker-row">
              <UI.Kicker>{t("dashboard.portfolio.credits")}</UI.Kicker>
              <UI.Button type="button" variant="ghost">{t("dashboard.portfolio.applyCredit")}</UI.Button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {DATA.credits.map((row, index) => (
                <div key={index}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 6 }}>
                    <span>{row.name}</span>
                    <span className="text-muted">{row.left}</span>
                  </div>
                  <DASH.ProgressBar pct={row.pct} label={row.name} />
                </div>
              ))}
            </div>
          </UI.Plate>
        </div>

        <UI.Plate className="elev-sm" style={{ padding: 16, marginTop: 20 }}>
          <UI.Kicker style={{ marginBottom: 12 }}>{t("dashboard.portfolio.investments")}</UI.Kicker>
          <div className="dash-invest-row">
            <UI.Plate className="dash-spark">
              <svg viewBox="0 0 400 140" preserveAspectRatio="none" style={{ width: "100%", height: "100%" }} aria-hidden="true">
                <polyline points="0,110 40,96 80,102 120,74 160,82 200,58 240,64 280,40 320,48 360,26 400,18" fill="none" stroke="var(--color-primary)" strokeWidth="1.5" />
              </svg>
            </UI.Plate>
            <table className="dash-table">
              <tbody>
                {DATA.holdings.map((row, index) => (
                  <tr key={index}>
                    <td>{row.name}</td>
                    <td className="text-muted" style={{ fontSize: 12 }}>{row.qty}</td>
                    <td className="amount-col">{row.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </UI.Plate>
      </div>
    );
  };

  function LimitRow({ label, minor, editing, onStart, onCancel, onSubmit, disabled }) {
    const [draft, setDraft] = useState(() => formatMinor(minor));

    if (editing) {
      return (
        <div className="dash-settings-row" style={{ alignItems: "flex-end", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <UI.Field id={"limit-" + label} label={t("dashboard.cards.newLimitLabel")}>
              <UI.TextInput
                id={"limit-" + label}
                inputMode="decimal"
                autoFocus
                defaultValue={formatMinor(minor)}
                onChange={(event) => setDraft(event.target.value)}
              />
            </UI.Field>
          </div>
          <UI.Button type="button" variant="primary" disabled={disabled} onClick={() => onSubmit(draft)}>
            {t("dashboard.cards.save")}
          </UI.Button>
          <UI.Button type="button" variant="secondary" onClick={onCancel}>
            {t("dashboard.cards.cancel")}
          </UI.Button>
        </div>
      );
    }
    return (
      <UI.Button type="button" variant="secondary" style={{ justifyContent: "space-between" }} disabled={disabled} onClick={onStart}>
        {label}
      </UI.Button>
    );
  }

  SCR.CardsScreen = function CardsScreen({
    cards,
    loading,
    error,
    selectedCardId,
    onSelect,
    onIssue,
    issuing,
    busy,
    onFreeze,
    onUnfreeze,
    onBlock,
    pin,
    pinShown,
    onTogglePin,
    cvv,
    detailsShown,
    onToggleDetails,
    onSetAtmLimit,
    onSetOnlineLimit,
  }) {
    const [editingLimit, setEditingLimit] = useState(null);
    const now = useLiveDate();
    const card = cards.find((row) => row.cardId === selectedCardId) || null;
    const disabled = busy || !card || card.state === "blocked";

    function submitLimit(kind, raw) {
      const normalized = raw.replace(",", ".").trim();
      const value = Number(normalized);
      if (!Number.isFinite(value) || value < 0) {
        setEditingLimit(null);
        return;
      }
      const minor = Math.round(value * 100);
      setEditingLimit(null);
      if (kind === "atm") onSetAtmLimit(minor);
      else onSetOnlineLimit(minor);
    }

    return (
      <div>
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.cards.title")}</h3>
          <UI.Button type="button" variant="secondary" disabled={issuing} onClick={onIssue}>
            {issuing ? t("dashboard.cards.issuing") : t("dashboard.cards.issue")}
          </UI.Button>
        </div>

        <UI.ErrorNote error={error} />

        {loading ? (
          <p className="text-muted">{t("dashboard.cards.loading")}</p>
        ) : cards.length === 0 ? (
          <p className="text-muted">{t("dashboard.cards.empty")}</p>
        ) : (
          <div className="dash-cards-layout">
            <div className="dash-cards-grid">
              {cards.map((row) => {
                const isSelected = row.cardId === selectedCardId;
                const flipped = isSelected && detailsShown;
                const front = (
                  <div className="dash-card-tile" style={{ width: "100%", height: "100%" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <span className="dash-card-kind">{t("dashboard.cards.kind." + kindToI18nKey(row.kind))}</span>
                      <UI.Tag variant="outline">{t("dashboard.cards.state." + row.state)}</UI.Tag>
                    </div>
                    <div>
                      <div className="dash-card-num">{row.numberMasked}</div>
                      <div className="dash-card-meta text-muted">
                        <span>{row.owner}</span><span>{formatExpiry(row.expiresOn)}</span>
                      </div>
                      <div className="dash-card-date" aria-label={t("dashboard.cards.todayAria")}>
                        {formatCardDate(now)}
                      </div>
                    </div>
                  </div>
                );

                if (isSelected) {
                  return (
                    <button
                      key={row.cardId}
                      type="button"
                      className={"dash-card-flip" + (flipped ? " is-flipped" : "")}
                      onClick={() => onSelect(row.cardId)}
                      aria-pressed={isSelected}
                    >
                      <div className="dash-card-flip-inner">
                        <div className="dash-card-face-front">{front}</div>
                        <div className="dash-card-face-back">
                          <div className="dash-card-kind">{t("dashboard.cards.showDetails")}</div>
                          <div className="dash-card-cvv">
                            {cvv ? t("dashboard.cards.cvvLabel", { cvv }) : "•••"}
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                }

                return (
                  <button
                    key={row.cardId}
                    type="button"
                    className="dash-card-tile"
                    onClick={() => onSelect(row.cardId)}
                    aria-pressed={isSelected}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <span className="dash-card-kind">{t("dashboard.cards.kind." + kindToI18nKey(row.kind))}</span>
                      <UI.Tag variant="outline">{t("dashboard.cards.state." + row.state)}</UI.Tag>
                    </div>
                    <div>
                      <div className="dash-card-num">{row.numberMasked}</div>
                      <div className="dash-card-meta text-muted">
                        <span>{row.owner}</span><span>{formatExpiry(row.expiresOn)}</span>
                      </div>
                      <div className="dash-card-date" aria-label={t("dashboard.cards.todayAria")}>
                        {formatCardDate(now)}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            {card ? (
              <UI.Plate className="elev-sm dash-quick-settings-panel" style={{ padding: 16, alignSelf: "start" }}>
                <UI.Kicker style={{ marginBottom: 6 }}>{t("dashboard.cards.quickSettings")}</UI.Kicker>
                <div style={{ fontFamily: "var(--font-heading)", fontSize: 20, marginBottom: 12 }}>
                  {t("dashboard.cards.kind." + kindToI18nKey(card.kind)) + " " + card.numberMasked.slice(-4)}
                </div>
                <div className="dash-settings-list">
                  <UI.Button
                    type="button"
                    variant="secondary"
                    style={{ justifyContent: "space-between" }}
                    disabled={busy || card.state === "blocked"}
                    onClick={onTogglePin}
                  >
                    {pinShown && pin ? t("dashboard.cards.pinLabel", { pin: pin.split("").join(" ") }) : t("dashboard.cards.showPin")}
                  </UI.Button>
                  <UI.Button
                    type="button"
                    variant="secondary"
                    style={{ justifyContent: "space-between" }}
                    disabled={busy || card.state === "blocked"}
                    onClick={onToggleDetails}
                  >
                    {detailsShown ? t("dashboard.cards.hideDetails") : t("dashboard.cards.showDetails")}
                  </UI.Button>
                  <UI.Button
                    type="button"
                    variant="secondary"
                    style={{ justifyContent: "space-between" }}
                    disabled={busy || card.state === "blocked"}
                    onClick={card.state === "frozen" ? onUnfreeze : onFreeze}
                  >
                    {card.state === "frozen" ? t("dashboard.cards.unfreeze") : t("dashboard.cards.freeze")}
                  </UI.Button>
                  <LimitRow
                    key={"atm-" + card.cardId}
                    label={t("dashboard.cards.atmLimit")}
                    minor={card.atmLimitMinor}
                    editing={editingLimit === "atm"}
                    disabled={busy}
                    onStart={() => setEditingLimit("atm")}
                    onCancel={() => setEditingLimit(null)}
                    onSubmit={(raw) => submitLimit("atm", raw)}
                  />
                  <LimitRow
                    key={"online-" + card.cardId}
                    label={t("dashboard.cards.onlineLimit")}
                    minor={card.onlineLimitMinor}
                    editing={editingLimit === "online"}
                    disabled={busy}
                    onStart={() => setEditingLimit("online")}
                    onCancel={() => setEditingLimit(null)}
                    onSubmit={(raw) => submitLimit("online", raw)}
                  />
                  <UI.Button
                    type="button"
                    variant="secondary"
                    style={{ justifyContent: "space-between", color: "var(--color-negative)" }}
                    disabled={disabled}
                    onClick={onBlock}
                  >
                    {t("dashboard.cards.blockPermanently")}
                  </UI.Button>
                </div>
                <div className="hr" />
                <div className="text-muted" style={{ fontSize: 12 }}>{t("dashboard.cards.monthlySpend")}</div>
                <div style={{ marginTop: 6 }}><DASH.ProgressBar pct={46} label={t("dashboard.cards.monthlySpend")} className="dash-progress-negative" /></div>
              </UI.Plate>
            ) : null}
          </div>
        )}
      </div>
    );
  };

  const CATEGORY_COLORS = {
    groceries: "var(--color-plum-600)",
    utilities: "var(--color-lime-600)",
    transport: "var(--color-plum-400)",
    entertainment: "var(--color-lime-400)",
    transfer: "var(--color-plum-700)",
    income: "var(--color-lime-700)",
    other: "var(--color-neutral-600)",
  };

  const CHART_SERIES_LABEL = {
    income: "dashboard.category.income",
    spend: "dashboard.analytics.spend",
  };

  function monthBucketKey(date) {
    return date.getFullYear() * 12 + date.getMonth();
  }

  function buildMonthBuckets(count, locale) {
    const formatter = new Intl.DateTimeFormat(locale, { month: "short" });
    const now = new Date();
    const buckets = [];
    for (let offset = count - 1; offset >= 0; offset--) {
      const date = new Date(now.getFullYear(), now.getMonth() - offset, 1);
      buckets.push({ key: monthBucketKey(date), label: formatter.format(date), income: 0, spend: 0 });
    }
    return buckets;
  }

  function pickPrimaryCurrency(rows) {
    const counts = {};
    rows.forEach((row) => {
      const currency = row.amount.currency;
      counts[currency] = (counts[currency] || 0) + 1;
    });
    const known = Object.keys(counts);
    if (!known.length) return "RON";
    return known.sort((a, b) => counts[b] - counts[a])[0];
  }

  function useAnalyticsData(months) {
    const [rows, setRows] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
      let cancelled = false;
      setRows(null);
      setError(null);
      api
        .listTransactions({ limit: 100 })
        .then((response) => {
          if (!cancelled) setRows(response.transactions || []);
        })
        .catch((err) => {
          if (!cancelled) setError(err);
        });
      return () => {
        cancelled = true;
      };
    }, []);

    const locale = GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB";
    const loading = rows === null && !error;
    const currency = pickPrimaryCurrency(rows || []);
    const buckets = buildMonthBuckets(months, locale);
    const bucketByKey = new Map(buckets.map((bucket) => [bucket.key, bucket]));
    const oldestKey = buckets.length ? buckets[0].key : monthBucketKey(new Date());
    const categoryTotals = {};

    (rows || []).forEach((row) => {
      if (row.amount.currency !== currency) return;
      const posted = new Date(row.postedAt);
      const key = monthBucketKey(posted);
      if (key < oldestKey) return;
      const bucket = bucketByKey.get(key);
      const minor = row.amount.minorUnits;
      if (row.direction === "credit" && minor > 0) {
        if (bucket) bucket.income += minor;
      } else if (row.direction === "debit" && minor < 0) {
        const spend = -minor;
        if (bucket) bucket.spend += spend;
        categoryTotals[row.category] = (categoryTotals[row.category] || 0) + spend;
      }
    });

    const totalSpend = Object.values(categoryTotals).reduce((sum, value) => sum + value, 0);
    const categories = Object.keys(categoryTotals)
      .map((category) => ({
        category,
        minorUnits: categoryTotals[category],
        pct: totalSpend ? Math.round((categoryTotals[category] / totalSpend) * 100) : 0,
      }))
      .sort((a, b) => b.minorUnits - a.minorUnits);

    const hasActivity = buckets.some((bucket) => bucket.income || bucket.spend);

    return { loading, error, currency, buckets, categories, totalSpend, hasActivity };
  }

  function ChartTooltip({ active, payload, label, currency }) {
    if (!active || !payload || !payload.length) return null;
    return (
      <div className="dash-chart-tooltip">
        {label ? <div className="dash-chart-tooltip-label">{label}</div> : null}
        {payload.map((entry) => (
          <div key={entry.dataKey} style={{ color: entry.color }}>
            {t(CHART_SERIES_LABEL[entry.dataKey] || entry.name)}: {UI.formatMoney(entry.value, currency)}
          </div>
        ))}
      </div>
    );
  }

  function CategoryTooltip({ active, payload, currency }) {
    if (!active || !payload || !payload.length) return null;
    const point = payload[0];
    return (
      <div className="dash-chart-tooltip">
        <div className="dash-chart-tooltip-label">{point.name}</div>
        <div style={{ color: point.payload.fill }}>
          {UI.formatMoney(point.value, currency)} · {point.payload.pct}%
        </div>
      </div>
    );
  }

  SCR.AnalyticsScreen = function AnalyticsScreen({ range, onRange }) {
    const RC = window.Recharts;
    const months = range === "3" ? 3 : range === "12" ? 12 : 6;
    const periods = [
      { value: "3", label: t("dashboard.analytics.period3") },
      { value: "6", label: t("dashboard.analytics.period6") },
      { value: "12", label: t("dashboard.analytics.period12") },
    ];
    const { loading, error, currency, buckets, categories, hasActivity } = useAnalyticsData(months);

    const categoryData = categories.map((row) => ({
      name: t("dashboard.category." + row.category),
      value: row.minorUnits,
      pct: row.pct,
      fill: CATEGORY_COLORS[row.category] || "var(--color-neutral-400)",
    }));

    return (
      <div>
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.analytics.title")}</h3>
          <DASH.PeriodPicker options={periods} value={range} onChange={onRange} label={t("dashboard.analytics.title")} />
        </div>

        <div className="dash-analytics-cols">
          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.analytics.spendByCategory")}</UI.Kicker>
            {loading ? (
              <div className="dash-chart-empty">{t("dashboard.analytics.loading")}</div>
            ) : !categoryData.length ? (
              <div className="dash-chart-empty">{t("dashboard.analytics.empty")}</div>
            ) : (
              <div className="dash-donut-row">
                <RC.ResponsiveContainer width={150} height={150}>
                  <RC.PieChart>
                    <RC.Pie
                      data={categoryData}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={44}
                      outerRadius={72}
                      paddingAngle={2}
                      stroke="none"
                    >
                      {categoryData.map((entry) => (
                        <RC.Cell key={entry.name} fill={entry.fill} />
                      ))}
                    </RC.Pie>
                    <RC.Tooltip content={<CategoryTooltip currency={currency} />} />
                  </RC.PieChart>
                </RC.ResponsiveContainer>
                <div className="dash-donut-legend">
                  {categoryData.map((row) => (
                    <div className="dash-donut-legend-row" key={row.name}>
                      <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span aria-hidden="true" style={{ width: 8, height: 8, borderRadius: "50%", background: row.fill, flex: "none" }} />
                        {row.name}
                      </span>
                      <span className="text-muted">
                        {UI.formatMoney(row.value, currency)} · {row.pct}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>
              {t("dashboard.analytics.incomeVsSpend")} — <span style={{ textTransform: "uppercase" }}>{t("dashboard.analytics.period" + months)}</span>
            </UI.Kicker>
            {loading ? (
              <div className="dash-chart-empty">{t("dashboard.analytics.loading")}</div>
            ) : !hasActivity ? (
              <div className="dash-chart-empty">{t("dashboard.analytics.empty")}</div>
            ) : (
              <RC.ResponsiveContainer width="100%" height={220}>
                <RC.BarChart data={buckets} barGap={4}>
                  <RC.CartesianGrid stroke="var(--color-border)" vertical={false} />
                  <RC.XAxis dataKey="label" tick={{ fill: "var(--color-muted)", fontSize: 11 }} axisLine={{ stroke: "var(--color-border)" }} tickLine={false} />
                  <RC.YAxis tick={{ fill: "var(--color-muted)", fontSize: 11 }} axisLine={false} tickLine={false} width={36} tickFormatter={(value) => Math.round(value / 100)} />
                  <RC.Tooltip cursor={{ fill: "color-mix(in srgb, var(--color-primary) 6%, transparent)" }} content={<ChartTooltip currency={currency} />} />
                  <RC.Legend
                    formatter={(value) => t(CHART_SERIES_LABEL[value] || value)}
                    wrapperStyle={{ fontSize: 12, color: "var(--color-muted)" }}
                  />
                  <RC.Bar dataKey="income" name="income" fill="var(--color-lime-500)" radius={[6, 6, 0, 0]} />
                  <RC.Bar dataKey="spend" name="spend" fill="var(--color-plum-900)" radius={[6, 6, 0, 0]} />
                </RC.BarChart>
              </RC.ResponsiveContainer>
            )}
          </UI.Plate>
        </div>

        <UI.ErrorNote error={error} />

        <UI.Plate className="dash-agent-note elev-sm">
          <span className="dash-agent-dot" aria-hidden="true" style={{ marginTop: 6, flex: "none" }} />
          <div style={{ fontSize: 14, lineHeight: 1.6, flex: 1 }}>
            {t("dashboard.analytics.agentNote")}
            <div className="dash-ai-disclaimer">
              <UI.Icon name="Sparkles" size={13} />
              {t("dashboard.analytics.aiDisclaimer")}
            </div>
          </div>
        </UI.Plate>
      </div>
    );
  };

  function OtpDialog({ titleId, delivery, busy, error, onSubmit, onDismiss }) {
    const [code, setCode] = useState("");
    return (
      <UI.Dialog labelledBy={titleId} onDismiss={onDismiss}>
        <h2 id={titleId} className="dialog-title">{t("dashboard.settings.otp.title")}</h2>
        <p className="text-muted" style={{ fontSize: 13 }}>
          {t("dashboard.settings.otp.body", { email: delivery ? delivery.sentTo : "" })}
        </p>
        <form noValidate onSubmit={(event) => { event.preventDefault(); onSubmit(code); }}>
          <UI.Field id="otp-code" label={t("dashboard.settings.otp.codeLabel")} error={error ? error.message : null}>
            <UI.TextInput
              id="otp-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              value={code}
              onChange={(event) => setCode(event.target.value)}
            />
          </UI.Field>
          {delivery && delivery.devCode ? (
            <p className="text-muted" style={{ fontSize: 12 }}>
              {t("dashboard.settings.otp.devHint", { code: delivery.devCode })}
            </p>
          ) : null}
          <div className="dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onDismiss}>{t("dashboard.settings.otp.cancel")}</UI.Button>
            <UI.Button type="submit" variant="primary" disabled={busy}>{t("dashboard.settings.otp.confirm")}</UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  }

  function PinChangeDialog({ busy, error, onSubmit, onDismiss }) {
    const [newPin, setNewPin] = useState("");
    const [confirmation, setConfirmation] = useState("");
    return (
      <UI.Dialog labelledBy="pin-change-title" onDismiss={onDismiss}>
        <h2 id="pin-change-title" className="dialog-title">{t("dashboard.settings.pinDialog.title")}</h2>
        <form noValidate onSubmit={(event) => { event.preventDefault(); onSubmit(newPin, confirmation); }}>
          <UI.Field id="pin-new" label={t("dashboard.settings.pinDialog.newPin")} error={error ? error.message : null}>
            <UI.TextInput id="pin-new" inputMode="numeric" autoFocus value={newPin} onChange={(event) => setNewPin(event.target.value)} />
          </UI.Field>
          <UI.Field id="pin-confirm" label={t("dashboard.settings.pinDialog.confirmPin")}>
            <UI.TextInput id="pin-confirm" inputMode="numeric" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
          </UI.Field>
          <div className="dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onDismiss}>{t("dashboard.settings.pinDialog.cancel")}</UI.Button>
            <UI.Button type="submit" variant="primary" disabled={busy}>{t("dashboard.settings.pinDialog.submit")}</UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  }

  function SessionsDialog({ onDismiss }) {
    const [sessions, setSessions] = useState(null);
    const [error, setError] = useState(null);
    const [revokingId, setRevokingId] = useState(null);
    const [notice, setNotice] = useState(null);

    useEffect(() => {
      api
        .listSessions()
        .then((response) => setSessions(response.sessions))
        .catch((err) => setError(err));
    }, []);

    async function revoke(sessionId) {
      setRevokingId(sessionId);
      setError(null);
      setNotice(null);
      try {
        await api.revokeSession(sessionId);
        setSessions((current) => current.filter((row) => row.sessionId !== sessionId));
        setNotice(t("dashboard.settings.sessionsDialog.revoked"));
      } catch (err) {
        setError(err);
      } finally {
        setRevokingId(null);
      }
    }

    return (
      <UI.Dialog labelledBy="sessions-title" onDismiss={onDismiss}>
        <h2 id="sessions-title" className="dialog-title">{t("dashboard.settings.sessionsDialog.title")}</h2>
        <UI.ErrorNote error={error} />
        {notice ? <p className="text-muted" style={{ fontSize: 12 }}>{notice}</p> : null}
        {sessions === null ? (
          <p className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.settings.sessionsDialog.loading")}</p>
        ) : sessions.length === 0 ? (
          <p className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.settings.sessionsDialog.empty")}</p>
        ) : (
          <div className="dash-settings-list">
            {sessions.map((row) => (
              <div className="dash-settings-row" key={row.sessionId} style={{ alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 15 }}>
                    {row.device}
                    {row.isCurrent ? " · " + t("dashboard.settings.sessionsDialog.thisDevice") : ""}
                  </div>
                  <div className="text-muted" style={{ fontSize: 12 }}>{row.location}</div>
                  <div className="text-muted" style={{ fontSize: 12 }}>
                    {t("dashboard.settings.sessionsDialog.ip") + ": " + (row.ipAddress || "—")}
                  </div>
                  <div className="text-muted" style={{ fontSize: 12 }}>
                    {t("dashboard.settings.sessionsDialog.signedIn") + ": " + GEMS.i18n.isoToDisplayDate(row.issuedAt.slice(0, 10)) + " " + row.issuedAt.slice(11, 16)}
                  </div>
                </div>
                {row.isCurrent ? null : (
                  <UI.Button
                    type="button"
                    variant="secondary"
                    style={{ gap: 6, color: "var(--color-negative)" }}
                    disabled={revokingId === row.sessionId}
                    onClick={() => revoke(row.sessionId)}
                  >
                    <UI.Icon name="Trash2" size={14} />
                    {t("dashboard.settings.sessionsDialog.revoke")}
                  </UI.Button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="dialog-actions">
          <UI.Button type="button" variant="primary" onClick={onDismiss}>{t("dashboard.settings.sessionsDialog.close")}</UI.Button>
        </div>
      </UI.Dialog>
    );
  }

  function CloseAccountDialog({ onDismiss }) {
    const [step, setStep] = useState("confirm");
    const [pin, setPin] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);

    async function submitPin(event) {
      event.preventDefault();
      setBusy(true);
      setError(null);
      try {
        await api.requestAccountClosure(pin);
        setStep("done");
      } catch (err) {
        setError(err);
      } finally {
        setBusy(false);
      }
    }

    if (step === "done") {
      return (
        <UI.Dialog labelledBy="close-account-title" onDismiss={onDismiss}>
          <h2 id="close-account-title" className="dialog-title">{t("dashboard.settings.closeAccountDialog.doneTitle")}</h2>
          <p style={{ fontSize: 14 }}>{t("dashboard.settings.closeAccountDialog.doneBody")}</p>
          <div className="dialog-actions">
            <UI.Button type="button" variant="primary" onClick={onDismiss}>{t("dashboard.settings.closeAccountDialog.close")}</UI.Button>
          </div>
        </UI.Dialog>
      );
    }

    if (step === "pin") {
      return (
        <UI.Dialog labelledBy="close-account-title" onDismiss={onDismiss}>
          <h2 id="close-account-title" className="dialog-title">{t("dashboard.settings.closeAccountDialog.pinTitle")}</h2>
          <form noValidate onSubmit={submitPin}>
            <UI.Field id="close-account-pin" label={t("dashboard.settings.closeAccountDialog.pinLabel")} error={error ? error.message : null}>
              <UI.TextInput id="close-account-pin" inputMode="numeric" autoFocus value={pin} onChange={(event) => setPin(event.target.value)} />
            </UI.Field>
            <div className="dialog-actions">
              <UI.Button type="button" variant="secondary" onClick={onDismiss}>{t("dashboard.settings.closeAccountDialog.cancel")}</UI.Button>
              <UI.Button type="submit" variant="primary" disabled={busy}>{t("dashboard.settings.closeAccountDialog.confirm")}</UI.Button>
            </div>
          </form>
        </UI.Dialog>
      );
    }

    return (
      <UI.Dialog labelledBy="close-account-title" onDismiss={onDismiss}>
        <h2 id="close-account-title" className="dialog-title">{t("dashboard.settings.closeAccountDialog.title")}</h2>
        <p style={{ fontSize: 14 }}>{t("dashboard.settings.closeAccountDialog.body")}</p>
        <div className="dialog-actions">
          <UI.Button type="button" variant="secondary" onClick={onDismiss}>{t("dashboard.settings.closeAccountDialog.cancel")}</UI.Button>
          <UI.Button type="button" variant="primary" style={{ background: "var(--color-negative)" }} onClick={() => setStep("pin")}>
            {t("dashboard.settings.closeAccountDialog.send")}
          </UI.Button>
        </div>
      </UI.Dialog>
    );
  }

  function ContactDialog({ onDismiss }) {
    return (
      <UI.Dialog labelledBy="contact-title" onDismiss={onDismiss}>
        <h2 id="contact-title" className="dialog-title">{t("dashboard.settings.contactDialog.title")}</h2>
        <dl className="pay-receipt">
          <dt>{t("dashboard.settings.contactDialog.phoneLabel")}</dt>
          <dd>{t("dashboard.settings.contactDialog.phoneValue")}</dd>
          <dt>{t("dashboard.settings.contactDialog.emailLabel")}</dt>
          <dd>{t("dashboard.settings.contactDialog.emailValue")}</dd>
        </dl>
        <p className="text-muted" style={{ fontSize: 12 }}>{t("dashboard.settings.contactDialog.hours")}</p>
        <div className="dialog-actions">
          <UI.Button type="button" variant="primary" onClick={onDismiss}>{t("dashboard.settings.contactDialog.close")}</UI.Button>
        </div>
      </UI.Dialog>
    );
  }

  SCR.SettingsScreen = function SettingsScreen({ lang, onLang, theme, onTheme, onSignOut, onGoChat, me, onMeChange }) {
    const langs = [
      { value: "ro", label: "Română" },
      { value: "en", label: "English" },
    ];

    const [emailDraft, setEmailDraft] = useState("");
    const [phoneDraft, setPhoneDraft] = useState("");
    const [savingContact, setSavingContact] = useState(false);
    const [contactError, setContactError] = useState(null);
    const [contactNotice, setContactNotice] = useState(null);
    const [activeCase, setActiveCase] = useState(null);
    const [otpBusy, setOtpBusy] = useState(false);
    const [otpError, setOtpError] = useState(null);

    const [pinDialogOpen, setPinDialogOpen] = useState(false);
    const [pinBusy, setPinBusy] = useState(false);
    const [pinError, setPinError] = useState(null);
    const [pinCase, setPinCase] = useState(null);
    const [pinOtpBusy, setPinOtpBusy] = useState(false);
    const [pinOtpError, setPinOtpError] = useState(null);
    const [pinNotice, setPinNotice] = useState(null);

    const [sessionsOpen, setSessionsOpen] = useState(false);
    const [closeAccountOpen, setCloseAccountOpen] = useState(false);
    const [contactDialogOpen, setContactDialogOpen] = useState(false);

    useEffect(() => {
      if (me) {
        setEmailDraft(me.email);
        setPhoneDraft(me.phone);
      }
    }, [me]);

    function runNextChange(queue) {
      if (!queue.length) {
        setSavingContact(false);
        return;
      }
      const [current, ...rest] = queue;
      const request = current.kind === "email" ? api.requestEmailChange(current.value) : api.requestPhoneChange(current.value);
      request
        .then((response) => setActiveCase({ kind: current.kind, caseId: response.recoveryCaseId, delivery: response.delivery, rest }))
        .catch((err) => {
          setContactError(err);
          setSavingContact(false);
        });
    }

    function saveContact() {
      if (!me) return;
      const changes = [];
      const nextEmail = emailDraft.trim();
      const nextPhone = phoneDraft.trim();
      if (nextEmail && nextEmail !== me.email) changes.push({ kind: "email", value: nextEmail });
      if (nextPhone && nextPhone !== me.phone) changes.push({ kind: "phone", value: nextPhone });
      if (!changes.length) return;
      setContactError(null);
      setContactNotice(null);
      setSavingContact(true);
      runNextChange(changes);
    }

    function submitContactOtp(code) {
      if (!activeCase) return;
      setOtpBusy(true);
      setOtpError(null);
      api
        .verifySecureChange(activeCase.caseId, code)
        .then((response) => {
          onMeChange({
            userId: response.userId,
            username: response.username,
            email: response.email,
            phone: response.phone,
            fullName: response.fullName,
          });
          setEmailDraft(response.email);
          setPhoneDraft(response.phone);
          const rest = activeCase.rest || [];
          const kind = activeCase.kind;
          setActiveCase(null);
          setOtpBusy(false);
          if (rest.length) {
            runNextChange(rest);
          } else {
            setSavingContact(false);
            setContactNotice(t(kind === "email" ? "dashboard.settings.otp.successEmail" : "dashboard.settings.otp.successPhone"));
          }
        })
        .catch((err) => {
          setOtpError(err);
          setOtpBusy(false);
        });
    }

    function submitNewPin(newPin, confirmation) {
      setPinBusy(true);
      setPinError(null);
      api
        .requestPinChange(newPin, confirmation)
        .then((response) => {
          setPinDialogOpen(false);
          setPinCase({ caseId: response.recoveryCaseId, delivery: response.delivery });
        })
        .catch((err) => setPinError(err))
        .finally(() => setPinBusy(false));
    }

    function submitPinOtp(code) {
      if (!pinCase) return;
      setPinOtpBusy(true);
      setPinOtpError(null);
      api
        .verifySecureChange(pinCase.caseId, code)
        .then(() => {
          setPinCase(null);
          setPinOtpBusy(false);
          setPinNotice(t("dashboard.settings.otp.successPin"));
        })
        .catch((err) => {
          setPinOtpError(err);
          setPinOtpBusy(false);
        });
    }

    return (
      <div>
        <h3 style={{ margin: "0 0 18px" }}>{t("dashboard.nav.settings")}</h3>
        <div className="dash-settings-grid">
          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.personalDetails")}</UI.Kicker>
            <div className="dash-field-grid">
              <UI.Field id="set-name" label={t("dashboard.settings.fullName")}>
                <UI.TextInput id="set-name" value={me ? me.fullName : ""} disabled />
              </UI.Field>
              <UI.Field id="set-phone" label={t("dashboard.settings.phone")}>
                <UI.TextInput id="set-phone" value={phoneDraft} onChange={(event) => setPhoneDraft(event.target.value)} disabled={!me} />
              </UI.Field>
              <UI.Field id="set-email" label={t("dashboard.settings.email")}>
                <UI.TextInput id="set-email" value={emailDraft} onChange={(event) => setEmailDraft(event.target.value)} disabled={!me} />
              </UI.Field>
            </div>
            <UI.ErrorNote error={contactError} />
            {contactNotice ? <p className="text-muted" style={{ fontSize: 12 }}>{contactNotice}</p> : null}
            <UI.Button type="button" variant="primary" style={{ marginTop: 14 }} disabled={!me || savingContact} onClick={saveContact}>
              {savingContact ? t("dashboard.settings.saving") : t("dashboard.settings.save")}
            </UI.Button>
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.security")}</UI.Kicker>
            <div className="dash-settings-list">
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="KeyRound" size={15} />{t("dashboard.settings.changePin")}</span><UI.Button type="button" variant="secondary" onClick={() => { setPinError(null); setPinDialogOpen(true); }}>{t("dashboard.settings.update")}</UI.Button></div>
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="ShieldCheck" size={15} />{t("dashboard.settings.twoFactor")}</span><UI.Tag variant="accent">{t("dashboard.settings.authenticator")}</UI.Tag></div>
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="Fingerprint" size={15} />{t("dashboard.settings.passkeys")}</span><UI.Tag variant="accent">{t("dashboard.settings.passkeysCount")}</UI.Tag></div>
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="Smartphone" size={15} />{t("dashboard.settings.sessions")}</span><UI.Button type="button" variant="secondary" onClick={() => setSessionsOpen(true)}>{t("dashboard.settings.review")}</UI.Button></div>
            </div>
            {pinNotice ? <p className="text-muted" style={{ fontSize: 12, marginTop: 10 }}>{pinNotice}</p> : null}
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.preferences")}</UI.Kicker>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <div style={{ fontSize: 13, marginBottom: 6 }}>{t("dashboard.settings.language")}</div>
                <DASH.SegmentedControl options={langs} value={lang} onChange={onLang} label={t("dashboard.settings.language")} />
              </div>
              <div>
                <div style={{ fontSize: 13, marginBottom: 6 }}>{t("dashboard.settings.theme")}</div>
                <div style={{ display: "flex", gap: 8 }}>
                  <UI.Button type="button" variant={theme === "light" ? "primary" : "secondary"} style={{ gap: 6 }} onClick={() => onTheme("light")}><UI.Icon name="Sun" size={15} />{t("dashboard.settings.light")}</UI.Button>
                  <UI.Button type="button" variant={theme === "dark" ? "primary" : "secondary"} style={{ gap: 6 }} onClick={() => onTheme("dark")}><UI.Icon name="Moon" size={15} />{t("dashboard.settings.dark")}</UI.Button>
                </div>
              </div>
            </div>
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.support")}</UI.Kicker>
            <div className="dash-settings-list">
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8 }} onClick={onGoChat}><UI.Icon name="MessageCircle" size={15} />{t("dashboard.settings.chatSupport")}</UI.Button>
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8 }} onClick={() => setContactDialogOpen(true)}><UI.Icon name="Headset" size={15} />{t("dashboard.settings.customerService")}</UI.Button>
              <UI.Button
                type="button"
                variant="secondary"
                style={{ justifyContent: "flex-start", gap: 8 }}
                onClick={() => window.open("./help.html", "_blank", "noopener,noreferrer")}
              >
                <UI.Icon name="CircleHelp" size={15} />
                {t("dashboard.settings.faq")}
              </UI.Button>
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8 }}><UI.Icon name="Bot" size={15} />{t("dashboard.settings.agentInstructions")}</UI.Button>
              <div className="hr" style={{ margin: "4px 0" }} />
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8 }} onClick={onSignOut}><UI.Icon name="LogOut" size={15} />{t("dashboard.signOut")}</UI.Button>
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8, color: "var(--color-negative)" }} onClick={() => setCloseAccountOpen(true)}><UI.Icon name="TriangleAlert" size={15} />{t("dashboard.settings.closeAccount")}</UI.Button>
            </div>
          </UI.Plate>
        </div>

        {activeCase ? (
          <OtpDialog
            titleId="contact-otp-title"
            delivery={activeCase.delivery}
            busy={otpBusy}
            error={otpError}
            onSubmit={submitContactOtp}
            onDismiss={() => { setActiveCase(null); setSavingContact(false); }}
          />
        ) : null}

        {pinDialogOpen ? (
          <PinChangeDialog
            busy={pinBusy}
            error={pinError}
            onSubmit={submitNewPin}
            onDismiss={() => setPinDialogOpen(false)}
          />
        ) : null}

        {pinCase ? (
          <OtpDialog
            titleId="pin-otp-title"
            delivery={pinCase.delivery}
            busy={pinOtpBusy}
            error={pinOtpError}
            onSubmit={submitPinOtp}
            onDismiss={() => setPinCase(null)}
          />
        ) : null}

        {sessionsOpen ? <SessionsDialog onDismiss={() => setSessionsOpen(false)} /> : null}
        {closeAccountOpen ? <CloseAccountDialog onDismiss={() => setCloseAccountOpen(false)} /> : null}
        {contactDialogOpen ? <ContactDialog onDismiss={() => setContactDialogOpen(false)} /> : null}
      </div>
    );
  };

  SCR.ChatScreen = function ChatScreen({ messages, draft, onDraftChange, onSend, onKeyDown, micOn, onToggleMic, onPromptClick, onConfirmTx, username }) {
    const prompts = [
      { key: "pay", label: t("dashboard.chat.promptPay") },
      { key: "recurring", label: t("dashboard.chat.promptRecurring") },
      { key: "groceries", label: t("dashboard.chat.promptGroceries") },
    ];

    return (
      <div className="dash-chat-layout">
        <div className="dash-chat-col">
          <div className="dash-chat-scroll">
            {messages.map((message, index) => (
              <div className="dash-msg" key={index}>
                {message.role === "user" ? (
                  <div className="dash-msg-user">{message.text}</div>
                ) : (
                  <div className="dash-msg-ai">
                    <span className="dash-msg-ai-dot" aria-hidden="true" />
                    <div className="dash-msg-ai-body">
                      {message.text ? <div>{message.text}</div> : null}

                      {message.kind === "tx" ? (
                        <UI.Plate className="dash-tx-card">
                          <UI.Kicker style={{ marginBottom: 4 }}>{t("dashboard.chat.txDraftTitle")}</UI.Kicker>
                          <div className="dash-tx-amount">{t("dashboard.chat.txAmount")}</div>
                          <div className="dash-tx-grid">
                            <span className="text-muted">{t("dashboard.chat.txTo")}</span><span>Ionescu John</span>
                            <span className="text-muted">{t("dashboard.chat.txIban")}</span>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>RO49 AAAA 1B31 0075 9384 0000</span>
                            <span className="text-muted">{t("dashboard.chat.txFrom")}</span><span>{t("dashboard.accountType.current")} · •••4127</span>
                            <span className="text-muted">{t("dashboard.chat.txFee")}</span><span>0,00 RON</span>
                          </div>
                          <div style={{ display: "flex", gap: 8 }}>
                            <UI.Button type="button" variant="primary" style={{ flex: 1 }} onClick={onConfirmTx}>{t("dashboard.chat.txConfirm")}</UI.Button>
                            <UI.Button type="button" variant="secondary">{t("dashboard.chat.txEdit")}</UI.Button>
                          </div>
                        </UI.Plate>
                      ) : null}

                      {message.kind === "table" ? (
                        <UI.Plate className="dash-table-card">
                          <table className="dash-table">
                            <thead>
                              <tr><th>{t("dashboard.nav.payments")}</th><th>{t("dashboard.chat.txTo")}</th><th className="amount-col">{t("dashboard.table.amount")}</th></tr>
                            </thead>
                            <tbody>
                              {DATA.recurring.map((row, rowIndex) => (
                                <tr key={rowIndex}>
                                  <td>{row.name}</td>
                                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{row.next}</td>
                                  <td className="amount-col">{row.amount}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                            <UI.Button type="button" variant="secondary">{t("dashboard.chat.recurringCancel")}</UI.Button>
                            <UI.Button type="button" variant="secondary">{t("dashboard.chat.recurringExport")}</UI.Button>
                          </div>
                        </UI.Plate>
                      ) : null}

                      {message.kind === "chart" ? (
                        <UI.Plate className="dash-chart-card">
                          <UI.Kicker style={{ marginBottom: 12 }}>{t("dashboard.category.groceries")}</UI.Kicker>
                          <DASH.Bars items={DATA.groceryBars} />
                        </UI.Plate>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div style={{ paddingTop: 16 }}>
            <div className="dash-prompts-row">
              {prompts.map((prompt) => (
                <UI.Button key={prompt.key} type="button" variant="secondary" onClick={() => onPromptClick(prompt.key)}>{prompt.label}</UI.Button>
              ))}
            </div>
            <UI.Plate className="dash-chat-input-row">
              <input
                className="dash-chat-input"
                value={draft}
                onChange={onDraftChange}
                onKeyDown={onKeyDown}
                placeholder={t("dashboard.chat.inputPlaceholder")}
                aria-label={t("dashboard.chat.inputPlaceholder")}
              />
              <UI.Button type="button" variant="secondary" aria-pressed={micOn} onClick={onToggleMic}>
                {micOn ? t("dashboard.chat.micOn") : t("dashboard.chat.micOff")}
              </UI.Button>
              <UI.Button type="button" variant="primary" onClick={onSend}>{t("dashboard.chat.send")}</UI.Button>
            </UI.Plate>
            <div className="dash-chat-hint">{t("dashboard.chat.orchestratorNote")}</div>
          </div>
        </div>

        <div className="dash-chat-side">
          <div>
            <UI.Kicker style={{ marginBottom: 8 }}>{t("dashboard.chat.contextTitle")}</UI.Kicker>
            <div className="text-muted" style={{ fontSize: 13, lineHeight: 1.6, whiteSpace: "pre-line" }}>
              {t("dashboard.chat.contextBody")}
            </div>
          </div>
          <div className="hr" />
          <div>
            <UI.Kicker style={{ marginBottom: 8 }}>{t("dashboard.chat.logTitle")}</UI.Kicker>
            <div className="dash-chat-log">
              <div>· {t("dashboard.chat.logResolved")}</div>
              <div>· {t("dashboard.chat.logLimit")}</div>
              <div>· {t("dashboard.chat.logFx")}</div>
              <div>· {t("dashboard.chat.logDraft")}</div>
            </div>
          </div>
          <div className="hr" />
          <div className="text-muted" style={{ fontSize: 12 }}>{t("dashboard.chat.a11yNote")}</div>
        </div>
      </div>
    );
  };
})();
