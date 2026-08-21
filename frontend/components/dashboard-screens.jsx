(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const SCR = (GEMS.dashboardScreens = GEMS.dashboardScreens || {});
  const UI = GEMS.ui;
  const DASH = GEMS.dashboardUi;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const { useState, useEffect } = React;

  const QUICK_ACTIONS = [
    { num: "01", key: "transact", go: "payments" },
    { num: "02", key: "addFunds", go: "portfolio" },
    { num: "03", key: "exchange", go: "portfolio" },
    { num: "04", key: "scanQr", go: "payments" },
  ];

  const formatMinor = DASH.formatMinor;

  const TX_FILTERS = {
    all: () => true,
    income: (row) => row.direction === "in",
    spending: (row) => row.direction === "out",
    pending: (row) => row.statusKey === "pending",
    cards: (row) => row.channel === "card",
  };

  function matchesQuery(row, query) {
    if (!query) return true;
    const needle = query.trim().toLowerCase();
    if (!needle) return true;
    return [row.who, row.ref, row.iban].some(
      (value) => typeof value === "string" && value.toLowerCase().indexOf(needle) >= 0
    );
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
                  <DASH.Amount minor={row.minor} direction={row.direction} currency={row.currency || "RON"} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  SCR.HomeScreen = function HomeScreen({ accounts, transactions, balanceHidden, onToggleBalance, onSpeakBalance, onNavigate }) {
    return (
      <div className="dash-grid-home">
        <UI.Plate className="dash-balance-card elev-sm">
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.home.totalBalance")}</UI.Kicker>
            <UI.Button type="button" variant="ghost" onClick={onToggleBalance}>
              {balanceHidden ? t("dashboard.home.reveal") : t("dashboard.home.hide")}
            </UI.Button>
          </div>
          <div className="dash-balance-figure" onClick={onSpeakBalance} role="button" tabIndex={0}
               onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSpeakBalance(); }}>
            {balanceHidden ? "•••••••• RON" : DATA.totalBalance + " RON"}
          </div>
          <div className="text-muted" style={{ fontSize: 12 }}>
            {balanceHidden ? t("dashboard.home.balanceHiddenSub") : t("dashboard.home.balanceSub")}
          </div>

          <div className="hr" />

          <div className="dash-quick-grid">
            {QUICK_ACTIONS.map((action) => (
              <UI.Button key={action.key} type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 10, minHeight: 46 }} onClick={() => onNavigate(action.go)}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-plum-700)" }}>{action.num}</span>
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
            {accounts.slice(0, 3).map((account, index) => (
              <UI.Plate key={index} className="dash-account-tile">
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.12em", opacity: 0.55 }}>
                  {account.cur} · {t("dashboard.accountType." + account.typeKey)}
                </div>
                <div className="dash-account-amount">{balanceHidden ? "••••••" : formatMinor(account.minor)}</div>
                <div className="text-muted" style={{ fontSize: 11 }}>{account.ibanShort}</div>
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
          <TxTable rows={transactions.slice(0, 4)} compact />
        </UI.Plate>
      </div>
    );
  };

  SCR.PaymentsScreen = function PaymentsScreen({
    accounts,
    transactions,
    pending,
    templates,
    splitBills,
    filter,
    onFilter,
    query,
    onQuery,
    onOpenPay,
    onOpenSplit,
    onNewTemplate,
    onEditTemplate,
    onDeleteTemplate,
    onUseTemplate,
    onSettleShare,
    onDeleteSplit,
  }) {
    const filters = Object.keys(TX_FILTERS);
    const visible = transactions.filter((row) => TX_FILTERS[filter](row) && matchesQuery(row, query));

    return (
      <div>
        <div className="dash-screen-head">
          <div>
            <h3 style={{ margin: 0 }}>{t("dashboard.payments.title")}</h3>
            <div className="text-muted" style={{ fontSize: 13 }}>
              {t("dashboard.payments.subtitle", { count: transactions.length, pending: pending.length })}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <UI.Button type="button" variant="secondary" onClick={onOpenSplit}>{t("dashboard.payments.splitBill")}</UI.Button>
            <UI.Button type="button" variant="primary" onClick={onOpenPay}>{t("dashboard.payments.newPayment")}</UI.Button>
          </div>
        </div>

        <UI.Plate className="elev-sm" style={{ padding: 16, marginBottom: 18 }}>
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.templates.title")}</UI.Kicker>
            <UI.Button type="button" variant="ghost" onClick={onNewTemplate}>{t("dashboard.templates.new")}</UI.Button>
          </div>
          {templates.length ? (
            <div className="dash-template-grid">
              {templates.map((template) => (
                <UI.Plate key={template.id} className="dash-template-card">
                  <div className="dash-template-name">{template.name}</div>
                  <div className="text-muted" style={{ fontSize: 12 }}>{template.beneficiary}</div>
                  <div className="dash-template-iban">{template.iban}</div>
                  <div className="dash-template-actions">
                    <UI.Button type="button" variant="secondary" onClick={() => onUseTemplate(template)}>
                      {t("dashboard.templates.use")}
                    </UI.Button>
                    <UI.Button type="button" variant="ghost" onClick={() => onEditTemplate(template)}>
                      {t("dashboard.templates.edit")}
                    </UI.Button>
                    <UI.Button
                      type="button"
                      variant="ghost"
                      aria-label={t("dashboard.templates.deleteLabel", { name: template.name })}
                      onClick={() => onDeleteTemplate(template.id)}
                    >
                      {t("dashboard.templates.delete")}
                    </UI.Button>
                  </div>
                </UI.Plate>
              ))}
            </div>
          ) : (
            <div className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.templates.empty")}</div>
          )}
        </UI.Plate>

        {splitBills.length ? (
          <UI.Plate className="elev-sm" style={{ padding: 16, marginBottom: 18 }}>
            <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.split.openTitle")}</UI.Kicker>
            <div className="dash-split-list">
              {splitBills.map((bill) => {
                const outstanding = bill.participants
                  .filter((person) => !person.settled)
                  .reduce((sum, person) => sum + person.minor, 0);
                const account = accounts.find((item) => item.id === bill.accountId);
                return (
                  <div className="dash-split-card" key={bill.id}>
                    <div className="dash-split-card-head">
                      <div style={{ flex: 1 }}>
                        <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>{bill.reference}</div>
                        <div className="text-muted" style={{ fontSize: 11 }}>
                          {t("dashboard.split.cardMeta", {
                            total: formatMinor(bill.totalMinor) + " " + bill.currency,
                            account: account ? account.ibanShort : "",
                            mine: formatMinor(bill.myShareMinor) + " " + bill.currency,
                          })}
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
                          {formatMinor(outstanding)} {bill.currency}
                        </div>
                        <div className="text-muted" style={{ fontSize: 11 }}>{t("dashboard.split.outstanding")}</div>
                      </div>
                      <UI.Button
                        type="button"
                        variant="ghost"
                        aria-label={t("dashboard.split.closeRequest")}
                        onClick={() => onDeleteSplit(bill.id)}
                      >
                        {"×"}
                      </UI.Button>
                    </div>
                    <ul className="dash-split-shares">
                      {bill.participants.map((person) => (
                        <li key={person.key} data-settled={person.settled ? "true" : "false"}>
                          <span className="dash-split-share-name">{person.name}</span>
                          <span className="dash-split-share-amount">{formatMinor(person.minor)} {bill.currency}</span>
                          {person.settled ? (
                            <UI.Tag variant="accent">{t("dashboard.split.paid")}</UI.Tag>
                          ) : (
                            <UI.Button type="button" variant="secondary" onClick={() => onSettleShare(bill.id, person.key)}>
                              {t("dashboard.split.markPaid")}
                            </UI.Button>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </UI.Plate>
        ) : null}

        <UI.Plate className="elev-sm" style={{ padding: 16 }}>
          <div className="dash-filters-row">
            {filters.map((key) => (
              <UI.Button key={key} type="button" variant={filter === key ? "primary" : "secondary"} aria-pressed={filter === key} onClick={() => onFilter(key)}>
                {t("dashboard.payments.filter." + key)}
              </UI.Button>
            ))}
            <UI.TextInput
              style={{ marginLeft: "auto", maxWidth: 260 }}
              type="search"
              value={query}
              placeholder={t("dashboard.payments.filterPlaceholder")}
              aria-label={t("dashboard.payments.filterPlaceholder")}
              onChange={(event) => onQuery(event.target.value)}
            />
          </div>
          {visible.length ? (
            <TxTable rows={visible} />
          ) : (
            <div className="text-muted" style={{ fontSize: 13, padding: "18px 8px" }}>
              {t("dashboard.payments.noMatches")}
            </div>
          )}
        </UI.Plate>
      </div>
    );
  };

  SCR.PortfolioScreen = function PortfolioScreen({
    accounts,
    deposits,
    credits,
    holdings,
    investCashMinor,
    creditApplications,
    onOpenAccount,
    onNewDeposit,
    onMoveDeposit,
    onCloseDeposit,
    onTrade,
    onApplyCredit,
    onWithdrawApplication,
  }) {
    const investedMinor = holdings.reduce((sum, holding) => sum + DASH.holdingValue(holding), 0) + investCashMinor;

    return (
      <div>
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.portfolio.title")}</h3>
          <UI.Button type="button" variant="primary" onClick={onOpenAccount}>{t("dashboard.portfolio.openAccount")}</UI.Button>
        </div>

        <div className="dash-portfolio-tiles">
          {accounts.map((account) => (
            <UI.Plate key={account.id} className="elev-sm" style={{ padding: 14 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.12em", opacity: 0.55 }}>
                {account.cur} · {t("dashboard.accountType." + account.typeKey)}
              </div>
              <div className="dash-account-amount">{formatMinor(account.minor)}</div>
              <div className="text-muted" style={{ fontSize: 11 }}>{account.iban}</div>
            </UI.Plate>
          ))}
        </div>

        <div className="dash-portfolio-cols">
          <UI.Plate className="elev-sm" style={{ padding: 16 }}>
            <div className="dash-kicker-row">
              <UI.Kicker>{t("dashboard.portfolio.deposits")}</UI.Kicker>
              <UI.Button type="button" variant="ghost" onClick={onNewDeposit}>{t("dashboard.portfolio.newDeposit")}</UI.Button>
            </div>
            {deposits.length ? (
              <div className="dash-product-list">
                {deposits.map((deposit) => (
                  <div className="dash-product-row" key={deposit.id}>
                    <div className="dash-product-head">
                      <div style={{ flex: 1 }}>
                        <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>{deposit.name}</div>
                        <div className="text-muted" style={{ fontSize: 11 }}>
                          {t("dashboard.deposit.meta", {
                            kind: t("dashboard.deposit.kind." + deposit.kind),
                            rate: DASH.formatRate(deposit.rateBps),
                            matures: deposit.matures
                              ? t("dashboard.deposit.maturesOn", { date: GEMS.i18n.isoToDisplayDate(deposit.matures) })
                              : t("dashboard.deposit.noMaturity"),
                          })}
                        </div>
                      </div>
                      <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
                        {formatMinor(deposit.minor)} {deposit.cur}
                      </div>
                    </div>

                    {deposit.targetMinor ? (
                      <div style={{ marginTop: 8 }}>
                        <div className="text-muted" style={{ fontSize: 11, marginBottom: 4 }}>
                          {t("dashboard.deposit.goalProgress", {
                            saved: formatMinor(deposit.minor) + " " + deposit.cur,
                            target: formatMinor(deposit.targetMinor) + " " + deposit.cur,
                          })}
                        </div>
                        <DASH.ProgressBar
                          pct={Math.min(100, Math.round((deposit.minor / deposit.targetMinor) * 100))}
                          label={deposit.name}
                        />
                      </div>
                    ) : null}

                    <div className="dash-product-actions">
                      <UI.Button type="button" variant="secondary" onClick={() => onMoveDeposit(deposit, "in")}>
                        {t("dashboard.deposit.topUp")}
                      </UI.Button>
                      <UI.Button type="button" variant="secondary" onClick={() => onMoveDeposit(deposit, "out")}>
                        {t("dashboard.deposit.withdraw")}
                      </UI.Button>
                      <UI.Button
                        type="button"
                        variant="ghost"
                        aria-label={t("dashboard.deposit.closeLabel", { name: deposit.name })}
                        onClick={() => onCloseDeposit(deposit)}
                      >
                        {t("dashboard.deposit.close")}
                      </UI.Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.deposit.empty")}</div>
            )}
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 16 }}>
            <div className="dash-kicker-row">
              <UI.Kicker>{t("dashboard.portfolio.credits")}</UI.Kicker>
              <UI.Button type="button" variant="ghost" onClick={onApplyCredit}>{t("dashboard.portfolio.applyCredit")}</UI.Button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {credits.map((credit) => {
                const loan = credit.kind === "loan";
                const pct = loan
                  ? Math.round((credit.paidMonths / credit.termMonths) * 100)
                  : Math.round((credit.usedMinor / credit.limitMinor) * 100);
                const name = loan
                  ? t("dashboard.credit.loanName", {
                      name: t("dashboard.credit.name." + credit.nameKey),
                      paid: credit.paidMonths,
                      term: credit.termMonths,
                    })
                  : t("dashboard.credit.name." + credit.nameKey);
                const right = loan
                  ? t("dashboard.credit.left", { amount: formatMinor(credit.outstandingMinor) + " " + credit.cur })
                  : t("dashboard.credit.used", {
                      used: formatMinor(credit.usedMinor),
                      limit: formatMinor(credit.limitMinor) + " " + credit.cur,
                    });
                return (
                  <div key={credit.id}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 6, gap: 12 }}>
                      <span>{name}</span>
                      <span className="text-muted">{right}</span>
                    </div>
                    <DASH.ProgressBar pct={pct} label={name} />
                  </div>
                );
              })}
            </div>

            {creditApplications.length ? (
              <div style={{ marginTop: 18 }}>
                <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.credit.applicationsTitle")}</UI.Kicker>
                <div className="dash-product-list">
                  {creditApplications.map((application) => (
                    <div className="dash-product-row" key={application.id}>
                      <div className="dash-product-head">
                        <div style={{ flex: 1 }}>
                          <div style={{ fontFamily: "var(--font-heading)", fontSize: 15 }}>
                            {t("dashboard.credit.name." + application.productId)}
                          </div>
                          <div className="text-muted" style={{ fontSize: 11 }}>
                            {t("dashboard.credit.applicationMeta", {
                              rate: DASH.formatRate(application.rateBps),
                              term: application.termMonths
                                ? t("dashboard.deposit.months", { n: application.termMonths })
                                : t("dashboard.credit.revolving"),
                              date: GEMS.i18n.isoToDisplayDate(application.submitted),
                            })}
                          </div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontFamily: "var(--font-heading)", fontSize: 17 }}>
                            {formatMinor(application.amountMinor)} {application.cur}
                          </div>
                          <UI.Tag variant="outline">{t("dashboard.credit.status.review")}</UI.Tag>
                        </div>
                        <UI.Button
                          type="button"
                          variant="ghost"
                          aria-label={t("dashboard.credit.withdrawLabel")}
                          onClick={() => onWithdrawApplication(application.id)}
                        >
                          {"×"}
                        </UI.Button>
                      </div>
                      <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>
                        {t("dashboard.credit.awaitingAgent")}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </UI.Plate>
        </div>

        <UI.Plate className="elev-sm" style={{ padding: 16, marginTop: 20 }}>
          <div className="dash-kicker-row">
            <UI.Kicker>
              {t("dashboard.portfolio.investments", { total: formatMinor(investedMinor) })}
            </UI.Kicker>
            <UI.Button type="button" variant="ghost" onClick={() => onTrade(null, "buy")}>
              {t("dashboard.invest.new")}
            </UI.Button>
          </div>
          <div className="dash-invest-row">
            <UI.Plate className="dash-spark">
              <svg viewBox="0 0 400 140" preserveAspectRatio="none" style={{ width: "100%", height: "100%" }} aria-hidden="true">
                <polyline points="0,110 40,96 80,102 120,74 160,82 200,58 240,64 280,40 320,48 360,26 400,18" fill="none" stroke="var(--color-primary)" strokeWidth="1.5" />
              </svg>
            </UI.Plate>
            <table className="dash-table">
              <tbody>
                {holdings.map((holding) => (
                  <tr key={holding.id}>
                    <td>{holding.name}</td>
                    <td className="text-muted" style={{ fontSize: 12 }}>{DASH.formatUnits(holding)}</td>
                    <td className="amount-col">{formatMinor(DASH.holdingValue(holding))}</td>
                    <td className="amount-col" style={{ whiteSpace: "nowrap" }}>
                      <UI.Button type="button" variant="ghost" onClick={() => onTrade(holding.id, "buy")}>
                        {t("dashboard.invest.buy")}
                      </UI.Button>
                      <UI.Button
                        type="button"
                        variant="ghost"
                        disabled={DASH.holdingValue(holding) <= 0}
                        onClick={() => onTrade(holding.id, "sell")}
                      >
                        {t("dashboard.invest.sell")}
                      </UI.Button>
                    </td>
                  </tr>
                ))}
                <tr>
                  <td>{t("dashboard.invest.cash")}</td>
                  <td className="text-muted" style={{ fontSize: 12 }}>—</td>
                  <td className="amount-col">{formatMinor(investCashMinor)}</td>
                  <td />
                </tr>
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
              <UI.Plate className="elev-sm" style={{ padding: 16, alignSelf: "start", background: "var(--color-surface)" }}>
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
                <div style={{ marginTop: 6 }}><DASH.ProgressBar pct={46} label={t("dashboard.cards.monthlySpend")} /></div>
              </UI.Plate>
            ) : null}
          </div>
        )}
      </div>
    );
  };

  SCR.AnalyticsScreen = function AnalyticsScreen({ range, onRange }) {
    const ranges = [
      { value: "month", label: t("dashboard.analytics.rangeMonth") },
      { value: "quarter", label: t("dashboard.analytics.rangeQuarter") },
      { value: "year", label: t("dashboard.analytics.rangeYear") },
    ];
    const slices = [
      { color: "var(--color-plum-900)", pct: 32 },
      { color: "var(--color-plum-600)", pct: 23 },
      { color: "var(--color-lime-700)", pct: 19 },
      { color: "var(--color-lime-500)", pct: 14 },
      { color: "var(--color-neutral-300)", pct: 12 },
    ];
    return (
      <div>
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.analytics.title")}</h3>
          <DASH.SegmentedControl options={ranges} value={range} onChange={onRange} label={t("dashboard.analytics.title")} />
        </div>

        <div className="dash-analytics-cols">
          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.analytics.spendByCategory")}</UI.Kicker>
            <div className="dash-donut-row">
              <DASH.Donut slices={slices} label={t("dashboard.analytics.spendByCategory")} />
              <div className="dash-donut-legend">
                {DATA.categories.map((row) => (
                  <div className="dash-donut-legend-row" key={row.key}>
                    <span>{t("dashboard.category." + row.key)}</span>
                    <span className="text-muted">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.analytics.incomeVsSpend")}</UI.Kicker>
            <DASH.BigBars items={DATA.yearBars} incomeLabel={t("dashboard.category.income")} spendLabel={t("dashboard.table.amount")} />
          </UI.Plate>
        </div>

        <UI.Plate className="dash-agent-note elev-sm">
          <span className="dash-agent-dot" aria-hidden="true" style={{ marginTop: 6, flex: "none" }} />
          <div style={{ fontSize: 14, lineHeight: 1.6, flex: 1 }}>
            {t("dashboard.analytics.agentNote")}
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <UI.Button type="button" variant="secondary">{t("dashboard.analytics.setCap")}</UI.Button>
              <UI.Button type="button" variant="ghost">{t("dashboard.analytics.discuss")}</UI.Button>
            </div>
          </div>
        </UI.Plate>
      </div>
    );
  };

  SCR.SettingsScreen = function SettingsScreen({ lang, onLang, theme, onTheme, ttsOn, onToggleTts, onSignOut, onGoChat }) {
    const langs = [
      { value: "ro", label: "Română" },
      { value: "en", label: "English" },
    ];
    return (
      <div>
        <h3 style={{ margin: "0 0 18px" }}>{t("dashboard.nav.settings")}</h3>
        <div className="dash-settings-grid">
          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.personalDetails")}</UI.Kicker>
            <div className="dash-field-grid">
              <UI.Field id="set-name" label={t("dashboard.settings.fullName")}>
                <UI.TextInput id="set-name" defaultValue="Andrei-Mihai Pop" />
              </UI.Field>
              <UI.Field id="set-phone" label={t("dashboard.settings.phone")}>
                <UI.TextInput id="set-phone" defaultValue="+40 7•• ••• 214" />
              </UI.Field>
              <div style={{ gridColumn: "span 2" }}>
                <UI.Field id="set-email" label={t("dashboard.settings.email")}>
                  <UI.TextInput id="set-email" defaultValue="andrei.pop@mail.ro" />
                </UI.Field>
              </div>
            </div>
            <UI.Button type="button" variant="primary" style={{ marginTop: 14 }}>{t("dashboard.settings.save")}</UI.Button>
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.security")}</UI.Kicker>
            <div className="dash-settings-list">
              <div className="dash-settings-row"><span>{t("dashboard.settings.changePin")}</span><UI.Button type="button" variant="secondary">{t("dashboard.settings.update")}</UI.Button></div>
              <div className="dash-settings-row"><span>{t("dashboard.settings.twoFactor")}</span><UI.Tag variant="accent">{t("dashboard.settings.authenticator")}</UI.Tag></div>
              <div className="dash-settings-row"><span>{t("dashboard.settings.passkeys")}</span><UI.Tag variant="accent">{t("dashboard.settings.passkeysCount")}</UI.Tag></div>
              <div className="dash-settings-row"><span>{t("dashboard.settings.sessions")}</span><UI.Button type="button" variant="secondary">{t("dashboard.settings.review")}</UI.Button></div>
            </div>
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
                  <UI.Button type="button" variant={theme === "light" ? "primary" : "secondary"} onClick={() => onTheme("light")}>{t("dashboard.settings.light")}</UI.Button>
                  <UI.Button type="button" variant={theme === "dark" ? "primary" : "secondary"} onClick={() => onTheme("dark")}>{t("dashboard.settings.dark")}</UI.Button>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 13, marginBottom: 6 }}>{t("dashboard.settings.tts")}</div>
                <UI.Button type="button" variant="secondary" aria-pressed={ttsOn} onClick={onToggleTts}>
                  {ttsOn ? t("dashboard.readAloudOn") : t("dashboard.readAloudOff")}
                </UI.Button>
                <div className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>{t("dashboard.settings.ttsNote")}</div>
              </div>
            </div>
          </UI.Plate>

          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.support")}</UI.Kicker>
            <div className="dash-settings-list">
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start" }} onClick={onGoChat}>{t("dashboard.settings.chatSupport")}</UI.Button>
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start" }}>{t("dashboard.settings.faq")}</UI.Button>
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start" }}>{t("dashboard.settings.agentInstructions")}</UI.Button>
              <div className="hr" style={{ margin: "4px 0" }} />
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start" }} onClick={onSignOut}>{t("dashboard.signOut")}</UI.Button>
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", color: "var(--color-negative)" }}>{t("dashboard.settings.closeAccount")}</UI.Button>
            </div>
          </UI.Plate>
        </div>
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
