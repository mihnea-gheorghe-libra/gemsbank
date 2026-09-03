(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const SCR = (GEMS.dashboardScreens = GEMS.dashboardScreens || {});
  const UI = GEMS.ui;
  const AUTH = GEMS.auth;
  const DASH = GEMS.dashboardUi;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const api = GEMS.api;
  const { useState, useEffect, useRef } = React;

  const QUICK_ACTIONS = [
    { icon: "Send", key: "transact", go: "payments" },
    { icon: "Plus", key: "addFunds", go: "portfolio" },
    { icon: "ArrowLeftRight", key: "exchange", go: "portfolio" },
  ];

  const formatMinor = DASH.formatMinor;

  const TX_FILTERS = {
    all: () => true,
    income: (row) => row.direction === "in",
    spending: (row) => row.direction === "out",
    pending: (row) => row.statusKey === "awaiting_signature",
    cards: (row) => row.channel === "card",
  };

  const PAGE_SIZES = [5, 10, 25, 50, 100];

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

  function formatCardKind(text) {
    const parts = text.split(" · ");
    if (parts.length === 2) {
      return (
        <React.Fragment>
          <strong style={{ fontWeight: 700 }}>{parts[0]}</strong> · {parts[1]}
        </React.Fragment>
      );
    }
    return <strong style={{ fontWeight: 700 }}>{text}</strong>;
  }

  function formatExpiry(iso) {
    if (!iso) return "";
    const [year, month] = iso.split("-");
    return month + "/" + year.slice(2);
  }

  // Cosmetic only — derived client-side from the card id, never sent to or
  // stored by the backend, which never generates or keeps a full PAN
  // (backend/cards/adapters.py — only a random last-4 exists, anywhere).
  DASH.mockFullNumber = function mockFullNumber(cardId, last4, kind) {
    let hash = 0;
    for (let i = 0; i < cardId.length; i++) {
      hash = (hash * 31 + cardId.charCodeAt(i)) >>> 0;
    }
    const filler = String(hash % 100000000).padStart(8, "0");
    const bin = kind === "virtual_mastercard" || kind === "physical_debit" ? "5412" : "4532";
    return bin + " " + filler.slice(0, 4) + " " + filler.slice(4, 8) + " " + last4;
  }

  function MastercardMark() {
    return (
      <svg className="dash-card-logo" viewBox="0 0 152 108" aria-hidden="true">
        <circle cx="46" cy="54" r="42" fill="#EB001B" />
        <circle cx="106" cy="54" r="42" fill="#F79E1B" />
        <path fill="#FF5F00" d="M76,24.61 A42,42 0 0,1 76,83.39 A42,42 0 0,1 76,24.61 Z" />
      </svg>
    );
  }

  function formatIban(iban) {
    return iban || "—";
  }

  function TxTable({ rows, compact, onRepeat }) {
    return (
      <div style={{ overflowX: "auto" }}>
        <table className="dash-table">
          <thead>
            <tr>
              <th>{t("dashboard.table.date")}</th>
              <th>{t("dashboard.table.counterparty")}</th>
              {compact ? null : <th>{t("dashboard.table.reference")}</th>}
              {compact ? null : <th>{t("dashboard.table.iban")}</th>}
              <th>{t("dashboard.table.category")}</th>
              <th>{t("dashboard.table.status")}</th>
              <th className="amount-col">{t("dashboard.table.amount")}</th>
              {compact ? null : <th aria-label={t("dashboard.table.actions")}></th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{row.date}</td>
                <td>{row.who}</td>
                {compact ? null : <td className="text-muted" style={{ fontSize: 12 }}>{row.ref}</td>}
                {compact ? null : (
                  <td className="text-muted" style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "nowrap" }}>
                    {formatIban(row.iban)}
                  </td>
                )}
                <td className="text-muted">{t("dashboard.category." + row.categoryKey)}</td>
                <td><UI.Tag variant="accent">{t("dashboard.status." + row.statusKey)}</UI.Tag></td>
                <td className="amount-col">
                  <DASH.Amount minor={row.minor} direction={row.direction} currency={row.currency || "RON"} />
                </td>
                {compact ? null : (
                  <td>
                    <UI.Button
                      type="button"
                      variant="ghost"
                      aria-label={t("dashboard.payments.repeat", { name: row.who })}
                      disabled={!row.repeatable}
                      onClick={() => onRepeat(row)}
                    >
                      <UI.Icon name="ArrowLeftRight" size={15} />
                    </UI.Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // One vendor story and one exchange-rate story. Everything else lives behind "view all".
  const INSIGHT_CARD_LIMIT = 1;

  const HOME_ACCOUNT_PREVIEW_LIMIT = 4;

  function featuredAccountsForDashboard(accounts) {
    const preferredOrder = ["RON", "EUR", "USD"];
    const normalized = (accounts || []).map((account) => ({
      ...account,
      currency: String(account.cur ?? account.currency ?? "").toUpperCase(),
      minorValue: Number(account.minor ?? account.balance?.minorUnits ?? 0),
    }));

    const pickBestForCurrency = (currency, seenIds) => {
      const best = normalized
        .filter((account) => account.currency === currency && !seenIds.has(account.id))
        .sort((left, right) => right.minorValue - left.minorValue)[0];
      if (!best) return null;
      seenIds.add(best.id);
      return best;
    };

    const selected = [];
    const seenIds = new Set();

    for (const currency of preferredOrder) {
      const best = pickBestForCurrency(currency, seenIds);
      if (best) selected.push(best);
      if (selected.length >= HOME_ACCOUNT_PREVIEW_LIMIT) break;
    }

    if (selected.length < HOME_ACCOUNT_PREVIEW_LIMIT) {
      const remaining = normalized
        .filter((account) => !seenIds.has(account.id))
        .sort((left, right) => right.minorValue - left.minorValue);
      for (const account of remaining) {
        if (selected.length >= HOME_ACCOUNT_PREVIEW_LIMIT) break;
        selected.push(account);
        seenIds.add(account.id);
      }
    }

    return selected.slice(0, HOME_ACCOUNT_PREVIEW_LIMIT);
  }

  function hostOf(url) {
    if (!url) return "";
    const match = /^https?:\/\/([^/?#]+)/i.exec(url);
    return match ? match[1].replace(/^www\./i, "") : "";
  }

  const SOURCE_NAME_LIMIT = 2;

  function vendorSource(insight) {
    const urls = (insight && insight.newsUrls) || [];
    const publishers = (insight && insight.newsPublishers) || [];
    if (urls.length === 0) {
      return { name: t("dashboard.home.insightSourceOwnHistory"), url: null };
    }
    if (publishers.length === 0) {
      return { name: hostOf(urls[0]), url: urls[0] };
    }
    const shown = publishers.slice(0, SOURCE_NAME_LIMIT).join(", ");
    const hidden = publishers.length - SOURCE_NAME_LIMIT;
    return { name: hidden > 0 ? shown + " +" + hidden : shown, url: urls[0] };
  }

  function fxSource(insight) {
    return {
      name: (insight && insight.sourceName) || t("dashboard.home.insightSourceOwnHistory"),
      url: (insight && insight.sourceUrl) || null,
    };
  }

  function InsightSource({ source, meta }) {
    if (!source || !source.name) return null;
    return (
      <div className="text-muted" style={{ fontSize: 11, marginTop: 4 }}>
        {meta ? meta + " · " : ""}
        {t("dashboard.home.insightSourceLabel")}{" "}
        {source.url ? (
          <a href={source.url} target="_blank" rel="noopener noreferrer">
            {source.name}
          </a>
        ) : (
          source.name
        )}
      </div>
    );
  }

  function renderInsightText(insight, currentLang) {
    if (!insight) return "";
    const isEn = (currentLang || (GEMS.i18n && GEMS.i18n.locale) || "en") === "en";
    const template = (isEn ? insight.longTextEn : insight.longText) || "";
    if (!template || !insight.currency) return "";
    return template
      .replace("{baseline}", UI.formatMoney(insight.baselineMinorUnits || 0, insight.currency))
      .replace("{observed}", UI.formatMoney(insight.observedMinorUnits || 0, insight.currency));
  }

  function renderFxInsightText(insight, currentLang) {
    if (!insight) return "";
    const isEn = (currentLang || (GEMS.i18n && GEMS.i18n.locale) || "en") === "en";
    const template = (isEn ? insight.longTextEn : insight.longText) || "";
    if (!template || !insight.currency) return "";
    const ron = insight.ronCurrency || "RON";
    return template
      .replace("{amount}", UI.formatMoney(insight.amountMinorUnits || 0, insight.currency))
      .replace("{ronBefore}", UI.formatMoney(insight.ronBaselineMinorUnits || 0, ron))
      .replace("{ron}", UI.formatMoney(insight.ronEquivalentMinorUnits || 0, ron));
  }

  function FxInsightRow({ insight, lang }) {
    return (
      <div>
        <div>{renderFxInsightText(insight, lang)}</div>
        <InsightSource source={fxSource(insight)} meta={insight.signalDate} />
      </div>
    );
  }

  function VendorInsightRow({ insight, lang }) {
    return (
      <div>
        <div>{renderInsightText(insight, lang)}</div>
        <InsightSource source={vendorSource(insight)} meta={insight.month} />
      </div>
    );
  }

  function InsightsDialog({ rows, fxRows, lang, onDismiss }) {
    const fx = fxRows || [];
    return (
      <UI.Dialog labelledBy="insights-title" onDismiss={onDismiss}>
        <h2 id="insights-title" className="dialog-title">{t("dashboard.home.insightsAllTitle")}</h2>
        {rows.length === 0 ? (
          <p className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.home.insightsEmpty")}</p>
        ) : (
          <div className="dash-settings-list">
            {rows.map((insight) => (
              <div className="dash-settings-row" key={insight.id} style={{ alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 15 }}>
                    {insight.vendorDisplayName}
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 2 }}>
                    {renderInsightText(insight, lang)}
                  </div>
                  <InsightSource
                    source={vendorSource(insight)}
                    meta={
                      insight.month +
                      " · " +
                      t("dashboard.home.insightConfidence." + insight.confidence)
                    }
                  />
                </div>
              </div>
            ))}
          </div>
        )}
        {fx.length > 0 ? (
          <React.Fragment>
            <h3 className="dialog-title" style={{ fontSize: 15, marginTop: 14 }}>
              {t("dashboard.home.fxInsightsAllTitle")}
            </h3>
            <div className="dash-settings-list">
              {fx.map((insight) => (
                <div className="dash-settings-row" key={insight.id} style={{ alignItems: "flex-start" }}>
                  <div>
                    <div style={{ fontFamily: "var(--font-heading)", fontSize: 15 }}>
                      {insight.currency}
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 2 }}>
                      <FxInsightRow insight={insight} lang={lang} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </React.Fragment>
        ) : null}
        <UI.Button type="button" variant="ghost" onClick={onDismiss}>
          {t("dashboard.home.insightsClose")}
        </UI.Button>
      </UI.Dialog>
    );
  }

  SCR.HomeScreen = function HomeScreen({ accounts, transactions, balanceHidden, onToggleBalance, onNavigate, onAddFunds, onExchange, onOpenAccount, insights, insightHistory, fxInsights, fxInsightHistory, lang }) {
    const { useState } = React;
    const [showAllInsights, setShowAllInsights] = useState(false);
    const allInsights = insightHistory || [];
    const allFxInsights = fxInsightHistory || [];
    const visibleInsights = (insights || []).slice(0, INSIGHT_CARD_LIMIT);
    const visibleFxInsights = (fxInsights || []).slice(0, INSIGHT_CARD_LIMIT);
    const hasMoreInsights =
      allInsights.length + allFxInsights.length >
      visibleInsights.length + visibleFxInsights.length;
    const totalBalanceMinor = accounts
      .filter((account) => account.cur === "RON")
      .reduce((sum, account) => sum + account.minor, 0);
    const featuredAccounts = featuredAccountsForDashboard(accounts);

    return (
      <div className="dash-grid-home">
        <UI.Plate className="dash-balance-card elev-sm">
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.home.totalBalance", { count: accounts.length })}</UI.Kicker>
            <UI.Button type="button" variant="ghost" style={{ gap: 6 }} onClick={onToggleBalance}>
              <UI.Icon name={balanceHidden ? "Eye" : "EyeOff"} size={15} />
              {balanceHidden ? t("dashboard.home.reveal") : t("dashboard.home.hide")}
            </UI.Button>
          </div>
          <div className="dash-balance-figure">
            {balanceHidden ? "•••••••• RON" : formatMinor(totalBalanceMinor) + " RON"}
          </div>


          <div className="hr" />

          <div className="dash-quick-grid">
            {QUICK_ACTIONS.map((action) => (
              <UI.Button
                key={action.key}
                type="button"
                variant="secondary"
                style={{ justifyContent: "flex-start", gap: 10, minHeight: 46 }}
                onClick={() => {
                  if (action.key === "addFunds") return onAddFunds();
                  if (action.key === "exchange") return onExchange();
                  return onNavigate(action.go);
                }}
              >
                <UI.Icon name={action.icon} size={16} style={{ color: "var(--color-primary)" }} />
                {t("dashboard.home.quick." + action.key)}
              </UI.Button>
            ))}
          </div>
        </UI.Plate>

        <UI.Plate className="dash-accounts-card elev-sm">
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.home.accounts")}</UI.Kicker>
            <a href="#" onClick={(event) => { event.preventDefault(); onOpenAccount(); }}>{t("dashboard.home.openAccount")}</a>
          </div>
          <div className="dash-accounts-tiles">
            {featuredAccounts.map((account) => (
              <UI.Plate key={account.id} className="dash-account-tile">
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.12em", opacity: 0.55 }}>
                  {account.cur} · {account.label || t("dashboard.accountType." + account.typeKey)}
                </div>
                <div className="dash-account-amount">{balanceHidden ? "••••••" : formatMinor(account.minor)}</div>
                <div className="text-muted" style={{ fontSize: 11 }}>{account.ibanShort}</div>
              </UI.Plate>
            ))}
          </div>
          {accounts.length > featuredAccounts.length ? (
            <a
              href="#"
              style={{ display: "inline-block", marginTop: 10, fontSize: 13 }}
              onClick={(event) => { event.preventDefault(); onNavigate("accounts"); }}
            >
              {t("dashboard.home.seeAllAccounts", { count: accounts.length })}
            </a>
          ) : null}
        </UI.Plate>

        {/* Moved below the accounts frame, same footprint (grid-column: span 2) per request. */}
        <UI.Plate className="dash-accounts-card elev-sm">
          <div className="dash-kicker-row" style={{ marginBottom: 10 }}>
            <UI.Kicker>{t("dashboard.home.insights")}</UI.Kicker>
            {visibleInsights.length + visibleFxInsights.length > 0 ? (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--color-primary)", letterSpacing: "0.08em" }}>
                {allInsights.length + allFxInsights.length} {t("dashboard.home.insightsCount")}
              </span>
            ) : null}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13, lineHeight: 1.5 }}>
            {visibleInsights.length + visibleFxInsights.length > 0 ? (
              <React.Fragment>
                {visibleInsights.map((insight, idx) => (
                  <div key={insight.id || idx}>
                    <VendorInsightRow insight={insight} lang={lang} />
                    {idx < visibleInsights.length - 1 || visibleFxInsights.length > 0 ? (
                      <div className="hr" style={{ margin: "10px 0 0 0" }} />
                    ) : null}
                  </div>
                ))}
                {visibleFxInsights.map((insight, idx) => (
                  <div key={insight.id || "fx" + idx}>
                    <FxInsightRow insight={insight} lang={lang} />
                    {idx < visibleFxInsights.length - 1 ? (
                      <div className="hr" style={{ margin: "10px 0 0 0" }} />
                    ) : null}
                  </div>
                ))}
              </React.Fragment>
            ) : (
              <div className="text-muted">{t("dashboard.home.insightsEmpty")}</div>
            )}
            <div className="dash-ai-disclaimer">
              <UI.Icon name="Sparkles" size={13} />
              {t("dashboard.home.insightsAiDisclaimer")}
            </div>
            <div className="dash-kicker-row" style={{ marginBottom: 0 }}>
              <UI.Button type="button" variant="ghost" style={{ padding: 0 }} onClick={() => onNavigate("chat")}>
                {t("dashboard.home.askAgent")}
              </UI.Button>
              {hasMoreInsights ? (
                <UI.Button type="button" variant="ghost" style={{ padding: 0 }} onClick={() => setShowAllInsights(true)}>
                  {t("dashboard.home.insightsViewAll", { count: allInsights.length + allFxInsights.length })}
                </UI.Button>
              ) : null}
            </div>
          </div>
        </UI.Plate>

        {showAllInsights ? (
          <InsightsDialog rows={allInsights} fxRows={allFxInsights} lang={lang} onDismiss={() => setShowAllInsights(false)} />
        ) : null}

        <UI.Plate className="elev-sm" style={{ padding: 18, gridColumn: "1 / -1" }}>
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.home.recentActivity")}</UI.Kicker>
            <a href="#" onClick={(event) => { event.preventDefault(); onNavigate("payments"); }}>{t("dashboard.home.allTransactions")}</a>
          </div>
          <TxTable rows={transactions.slice(0, 4)} />
        </UI.Plate>
      </div>
    );
  };

  SCR.PaymentsScreen = function PaymentsScreen({
    accounts,
    transactions,
    pending,
    templates,
    templatesError,
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
    onSign,
    onRepeat,
  }) {
    const filters = Object.keys(TX_FILTERS);
    const visible = transactions.filter((row) => TX_FILTERS[filter](row) && matchesQuery(row, query));

    const [pageSize, setPageSize] = useState(PAGE_SIZES[0]);
    const [page, setPage] = useState(1);
    const pageSizeOptions = PAGE_SIZES.map((n) => ({ value: n, label: t("dashboard.payments.perPage", { n }) }));

    useEffect(() => {
      setPage(1);
    }, [filter, query, pageSize]);

    const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
    const currentPage = Math.min(page, pageCount);
    const pageRows = visible.slice((currentPage - 1) * pageSize, currentPage * pageSize);

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

        {pending.length ? (
          <UI.Plate className="elev-sm" style={{ padding: 16, marginBottom: 18 }}>
            <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.payments.pendingTitle")}</UI.Kicker>
            <div className="dash-pending-grid">
              {pending.map((row, index) => (
                <div className="dash-pending-row" key={row.paymentId}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--color-primary)" }}>
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>{row.counterparty}</div>
                    <div className="text-muted" style={{ fontSize: 11 }}>{row.reference}</div>
                  </div>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
                    {formatMinor(row.amount.minorUnits)} {row.amount.currency}
                  </div>
                  <UI.Button type="button" variant="secondary" onClick={() => onSign(row)}>
                    {t("dashboard.payments.sign")}
                  </UI.Button>
                </div>
              ))}
            </div>
          </UI.Plate>
        ) : null}

        <UI.Plate className="elev-sm" style={{ padding: 16, marginBottom: 18 }}>
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.templates.title")}</UI.Kicker>
            <UI.Button type="button" variant="ghost" onClick={onNewTemplate}>{t("dashboard.templates.new")}</UI.Button>
          </div>
          {templatesError ? (
            <div className="dash-balance-line is-short" role="alert">{templatesError.message}</div>
          ) : null}
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
            <React.Fragment>
              <div className="dash-pagination-row">
                <DASH.PeriodPicker
                  options={pageSizeOptions}
                  value={pageSize}
                  onChange={setPageSize}
                  label={t("dashboard.payments.perPage", { n: pageSize })}
                  icon="List"
                />
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <UI.Button
                    type="button"
                    variant="secondary"
                    aria-label={t("dashboard.payments.prevPage")}
                    disabled={currentPage <= 1}
                    onClick={() => setPage(currentPage - 1)}
                  >
                    <UI.Icon name="ChevronLeft" size={15} />
                  </UI.Button>
                  <span className="text-muted" style={{ fontSize: 13 }}>
                    {t("dashboard.payments.pageOf", { page: currentPage, total: pageCount })}
                  </span>
                  <UI.Button
                    type="button"
                    variant="secondary"
                    aria-label={t("dashboard.payments.nextPage")}
                    disabled={currentPage >= pageCount}
                    onClick={() => setPage(currentPage + 1)}
                  >
                    <UI.Icon name="ChevronRight" size={15} />
                  </UI.Button>
                </div>
              </div>
              <TxTable rows={pageRows} onRepeat={onRepeat} />
            </React.Fragment>
          ) : (
            <div className="text-muted" style={{ fontSize: 13, padding: "18px 8px" }}>
              {t("dashboard.payments.noMatches")}
            </div>
          )}
        </UI.Plate>
      </div>
    );
  };
  function AccountTileMenu({ onStatement, onDelete }) {
    const [open, setOpen] = useState(false);
    const [position, setPosition] = useState(null);
    const triggerRef = useRef(null);
    const menuRef = useRef(null);

    const openMenu = () => {
      const rect = triggerRef.current.getBoundingClientRect();
      setPosition({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
      setOpen(true);
    };

    useEffect(() => {
      if (!open) return undefined;
      function onPointerDown(event) {
        if (triggerRef.current && triggerRef.current.contains(event.target)) return;
        if (menuRef.current && menuRef.current.contains(event.target)) return;
        setOpen(false);
      }
      function onKeyDown(event) {
        if (event.key === "Escape") setOpen(false);
      }
      function onDismiss() {
        setOpen(false);
      }
      document.addEventListener("mousedown", onPointerDown);
      document.addEventListener("keydown", onKeyDown);
      window.addEventListener("scroll", onDismiss, true);
      window.addEventListener("resize", onDismiss);
      return () => {
        document.removeEventListener("mousedown", onPointerDown);
        document.removeEventListener("keydown", onKeyDown);
        window.removeEventListener("scroll", onDismiss, true);
        window.removeEventListener("resize", onDismiss);
      };
    }, [open]);

    return (
      <div className="dash-tile-menu">
        <button
          type="button"
          ref={triggerRef}
          className="dash-tile-menu-trigger"
          aria-haspopup="true"
          aria-expanded={open}
          aria-label={t("dashboard.accounts.moreActions")}
          onClick={(event) => { event.stopPropagation(); if (open) setOpen(false); else openMenu(); }}
        >
          <UI.Icon name="MoreVertical" size={16} />
        </button>
        {open && position ? ReactDOM.createPortal(
          <div
            ref={menuRef}
            className="dash-tile-menu-list elev-md plate"
            role="menu"
            style={{ position: "fixed", top: position.top, right: position.right }}
          >
            <button
              type="button"
              role="menuitem"
              className="dash-tile-menu-item"
              onClick={() => { setOpen(false); onStatement(); }}
            >
              <UI.Icon name="FileText" size={14} />
              {t("dashboard.accounts.statementMenuItem")}
            </button>
            {onDelete ? (
              <button
                type="button"
                role="menuitem"
                className="dash-tile-menu-item is-danger"
                onClick={() => { setOpen(false); onDelete(); }}
              >
                <UI.Icon name="Trash2" size={14} />
                {t("dashboard.accounts.deleteMenuItem")}
              </button>
            ) : null}
          </div>,
          document.body
        ) : null}
      </div>
    );
  }

  function AccountRow({ account, onStatement, onDelete }) {
    return (
      <div className="dash-product-row">
        <div className="dash-product-head">
          <div style={{ flex: 1 }}>
            <div className="dash-account-tile-head">
              <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>
                {account.label || t("dashboard.accountType." + account.typeKey)}
              </div>
              <AccountTileMenu onStatement={onStatement} onDelete={onDelete} />
            </div>
            <div className="text-muted" style={{ fontSize: 11 }}>
              {account.cur} &middot; {t("dashboard.accountType." + account.typeKey)} &middot; {account.iban}
            </div>
          </div>
          <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
            {formatMinor(account.minor)} {account.cur}
          </div>
        </div>
      </div>
    );
  }

  function SavingsAccountRow({ account, onStatement, onTopUp, onWithdraw, onClose }) {
    return (
      <div className="dash-product-row">
        <div className="dash-product-head">
          <div style={{ flex: 1 }}>
            <div className="dash-account-tile-head">
              <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>
                {account.label || t("dashboard.accountType." + account.typeKey)}
              </div>
              <AccountTileMenu onStatement={onStatement} />
            </div>
            <div className="text-muted" style={{ fontSize: 11 }}>
              {account.cur} &middot; {t("dashboard.accountType." + account.typeKey)} &middot; {account.iban}
            </div>
          </div>
          <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
            {formatMinor(account.minor)} {account.cur}
          </div>
        </div>

        <div className="dash-product-actions">
          <UI.Button type="button" variant="secondary" onClick={() => onTopUp(account)}>
            {t("dashboard.deposit.topUp")}
          </UI.Button>
          <UI.Button type="button" variant="secondary" onClick={() => onWithdraw(account)}>
            {t("dashboard.deposit.withdraw")}
          </UI.Button>
          <UI.Button
            type="button"
            variant="secondary"
            aria-label={t("dashboard.deposit.closeLabel", { name: DASH.accountLabel(account) })}
            onClick={() => onClose(account)}
          >
            {t("dashboard.deposit.close")}
          </UI.Button>
        </div>
      </div>
    );
  }

  SCR.AccountsScreen = function AccountsScreen({
    accounts,
    termDeposits,
    depositActionError,
    creditApplications,
    creditActionError,
    onOpenAccount,
    onMoveDeposit,
    onCloseDeposit,
    onApplyCredit,
    onWithdrawApplication,
    onOpenStatement,
    onDeleteAccount,
    onOpenQuickTransfer,
    onTopUpAccount,
    onWithdrawAccount,
  }) {
    const approvedCredits = creditApplications.filter((application) => application.status === "approved");
    const reviewApplications = creditApplications.filter((application) => application.status === "review");
    const decidedApplications = creditApplications.filter(
      (application) => application.status === "rejected" || application.status === "withdrawn"
    );
    const cashAccounts = accounts.filter((account) => account.typeKey === "current" || account.typeKey === "invest");
    const depositPotIds = new Set(termDeposits.map((deposit) => deposit.accountId));
    const savingsAccounts = accounts.filter(
      (account) => account.typeKey === "savings" && !depositPotIds.has(account.id)
    );

    return (
      <div>
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.accounts.title")}</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <UI.Button type="button" variant="secondary" disabled={!accounts.length} onClick={() => onOpenStatement()}>
              {t("dashboard.accounts.generateStatement")}
            </UI.Button>
            <UI.Button type="button" variant="secondary" disabled={accounts.length < 2} onClick={onOpenQuickTransfer}>
              {t("dashboard.accounts.quickTransfer")}
            </UI.Button>
          </div>
        </div>

        <div className="dash-accounts-row">
        <UI.Plate className="elev-sm" style={{ padding: 16, display: "flex", flexDirection: "column", height: "100%" }}>
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.portfolio.cashAccounts")}</UI.Kicker>
            <UI.Button type="button" variant="primary" onClick={() => onOpenAccount("current")}>
              {t("dashboard.portfolio.openCashAccount")}
            </UI.Button>
          </div>
          {cashAccounts.length ? (
            <div style={{ flex: 1, position: "relative", minHeight: 100 }}>
              <div className="dash-product-list dash-scroll-accounts">
                {cashAccounts.map((account) => (
                  <AccountRow
                    key={account.id}
                    account={account}
                    onStatement={() => onOpenStatement(account)}
                    onDelete={() => onDeleteAccount(account)}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.accounts.empty")}</div>
          )}
        </UI.Plate>

        <UI.Plate className="elev-sm" style={{ padding: 16, display: "flex", flexDirection: "column", height: "100%" }}>
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.portfolio.deposits")}</UI.Kicker>
            <UI.Button type="button" variant="primary" onClick={() => onOpenAccount("deposit")}>
              {t("dashboard.deposit.new")}
            </UI.Button>
          </div>
          {depositActionError ? (
            <div className="dash-balance-line is-short" role="alert" style={{ marginBottom: 10 }}>
              {depositActionError.message}
            </div>
          ) : null}
          {termDeposits.length || savingsAccounts.length ? (
            <div className="dash-product-list dash-scroll-deposits">
              {termDeposits.map((deposit) => (
                <div className="dash-product-row" key={deposit.id}>
                  <div className="dash-product-head">
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>{deposit.name}</div>
                      <div className="text-muted" style={{ fontSize: 11 }}>
                        {t("dashboard.deposit.metaShort", {
                          rate: DASH.formatRate(deposit.rateBps),
                          matures: t("dashboard.deposit.maturesOn", { date: GEMS.i18n.isoToDisplayDate(deposit.matures) }),
                        })}
                      </div>
                    </div>
                    <div style={{ fontFamily: "var(--font-heading)", fontSize: 18 }}>
                      {formatMinor(deposit.minor)} {deposit.cur}
                    </div>
                  </div>

                  <div className="dash-product-actions">
                    <UI.Button type="button" variant="secondary" onClick={() => onMoveDeposit(deposit, "in")}>
                      {t("dashboard.deposit.topUp")}
                    </UI.Button>
                    <UI.Button type="button" variant="secondary" onClick={() => onMoveDeposit(deposit, "out")}>
                      {t("dashboard.deposit.withdraw")}
                    </UI.Button>
                    <UI.Button
                      type="button"
                      variant="secondary"
                      aria-label={t("dashboard.deposit.closeLabel", { name: deposit.name })}
                      onClick={() => onCloseDeposit(deposit)}
                    >
                      {t("dashboard.deposit.close")}
                    </UI.Button>
                  </div>
                </div>
              ))}
              {savingsAccounts.map((account) => (
                <SavingsAccountRow
                  key={account.id}
                  account={account}
                  onStatement={() => onOpenStatement(account)}
                  onTopUp={onTopUpAccount}
                  onWithdraw={onWithdrawAccount}
                  onClose={onDeleteAccount}
                />
              ))}
            </div>
          ) : (
            <div className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.deposit.empty")}</div>
          )}
        </UI.Plate>
        </div>

        <UI.Plate className="elev-sm" style={{ padding: 16 }}>
          <div className="dash-kicker-row">
            <UI.Kicker>{t("dashboard.portfolio.credits")}</UI.Kicker>
            <UI.Button type="button" variant="primary" onClick={onApplyCredit}>{t("dashboard.portfolio.applyCredit")}</UI.Button>
          </div>

            {creditActionError ? (
              <div className="dash-balance-line is-short" role="alert" style={{ marginBottom: 10 }}>
                {creditActionError.message}
              </div>
            ) : null}

            {!creditApplications.length ? (
              <div className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.credit.empty")}</div>
            ) : (
              <div className="dash-credits-cols">
                {/* Column 1: Credite Active */}
                <div className="dash-credits-col">
                  <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.credit.activeTitle")}</UI.Kicker>
                  {approvedCredits.length ? (
                    <div className="dash-product-list dash-scroll-credits">
                      {approvedCredits.map((application) => (
                        <div className="dash-product-row" key={application.id}>
                          <div className="dash-product-head">
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, wordBreak: "break-word" }}>
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
                            <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 8 }}>
                              <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>
                                {formatMinor(application.amountMinor)} {application.cur}
                              </div>
                              <UI.Tag variant="positive">{t("dashboard.credit.status.approved")}</UI.Tag>
                            </div>
                          </div>
                          {application.purpose ? (
                            <div className="text-muted" style={{ fontSize: 11, marginTop: 4 }}>
                              {t("dashboard.credit.purpose")}: {application.purpose}
                            </div>
                          ) : null}
                          {application.decisionReason ? (
                            <div className="text-muted" style={{ fontSize: 11, marginTop: 4 }}>
                              {t("dashboard.credit.decisionReason", { reason: application.decisionReason })}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="dash-credits-col-empty">{t("dashboard.credit.noActive")}</div>
                  )}
                </div>

                {/* Column 2: Cereri în Analiză */}
                <div className="dash-credits-col">
                  <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.credit.applicationsTitle")}</UI.Kicker>
                  {reviewApplications.length ? (
                    <div className="dash-product-list dash-scroll-credits">
                      {reviewApplications.map((application) => (
                        <div className="dash-product-row" key={application.id}>
                          <div className="dash-product-head">
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, wordBreak: "break-word" }}>
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
                            <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 8 }}>
                              <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>
                                {formatMinor(application.amountMinor)} {application.cur}
                              </div>
                              <UI.Tag variant="outline">{t("dashboard.credit.status.review")}</UI.Tag>
                            </div>
                            <UI.Button
                              type="button"
                              variant="secondary"
                              aria-label={t("dashboard.credit.withdrawLabel")}
                              onClick={() => onWithdrawApplication(application.id)}
                              style={{ padding: "2px 8px", marginLeft: 4 }}
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
                  ) : (
                    <div className="dash-credits-col-empty">{t("dashboard.credit.noReview")}</div>
                  )}
                </div>

                {/* Column 3: Istoric Cereri */}
                <div className="dash-credits-col">
                  <UI.Kicker style={{ marginBottom: 10 }}>{t("dashboard.credit.decidedTitle")}</UI.Kicker>
                  {decidedApplications.length ? (
                    <div className="dash-product-list dash-scroll-credits">
                      {decidedApplications.map((application) => (
                        <div className="dash-product-row" key={application.id}>
                          <div className="dash-product-head">
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, wordBreak: "break-word" }}>
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
                            <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 8 }}>
                              <div style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>
                                {formatMinor(application.amountMinor)} {application.cur}
                              </div>
                              <UI.Tag variant={application.status === "rejected" ? "critical" : "neutral"}>
                                {t("dashboard.credit.status." + application.status)}
                              </UI.Tag>
                            </div>
                          </div>
                          {application.decisionReason ? (
                            <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>
                              {t("dashboard.credit.decisionReason", { reason: application.decisionReason })}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="dash-credits-col-empty">{t("dashboard.credit.noDecided")}</div>
                  )}
                </div>
              </div>
            )}
        </UI.Plate>
      </div>
    );
  };

  SCR.PortfolioScreen = function PortfolioScreen({
    holdings,
    investCashMinor,
    hasInvestAccount,
    market,
    marketLoading,
    marketError,
    onRefreshMarket,
    onTrade,
    onOpenAccount,
  }) {
    const investedMinor = holdings.reduce((sum, holding) => sum + DASH.holdingValue(holding), 0) + (investCashMinor || 0);
    const ownedHoldings = holdings.filter((holding) => DASH.holdingValue(holding) > 0);
    const [focusId, setFocusId] = useState(null);
    const [chartRange, setChartRange] = useState("month");

    const focused = holdings.find((holding) => holding.id === focusId) || null;
    const totalSeries = DASH.portfolioSeries(holdings, investCashMinor);
    const rawSeries = focused ? DASH.instrumentSeries(focused) : totalSeries;
    const series = DASH.sliceSeriesByRange(rawSeries, chartRange);
    const windowChangeBps = DASH.seriesChangeBps(totalSeries);
    const chartChangeBps = DASH.seriesChangeBps(series);
    const currentPoint = rawSeries.length ? rawSeries[rawSeries.length - 1] : null;
    const currentDelta = rawSeries.length > 1
      ? currentPoint.valueMinor - rawSeries[rawSeries.length - 2].valueMinor
      : null;

    const rangeOptions = [
      { value: "day", label: t("dashboard.invest.range.day") },
      { value: "week", label: t("dashboard.invest.range.week") },
      { value: "month", label: t("dashboard.invest.range.month") },
      { value: "quarter", label: t("dashboard.invest.range.quarter") },
      { value: "half", label: t("dashboard.invest.range.half") },
      { value: "year", label: t("dashboard.invest.range.year") },
    ];

    return (
      <div>
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.portfolio.title")}</h3>
        </div>

        <UI.Plate className="elev-sm" style={{ padding: 16 }}>
          <div className="dash-kicker-row">
            <UI.Kicker>
              {windowChangeBps == null
                ? t("dashboard.portfolio.investments", { total: formatMinor(investedMinor) })
                : t("dashboard.portfolio.investmentsWithChange", {
                    total: formatMinor(investedMinor),
                    change: DASH.formatChangeBps(windowChangeBps),
                    months: DASH.seriesMonths(totalSeries),
                  })}
            </UI.Kicker>
            {hasInvestAccount ? (
              <UI.Button
                type="button"
                variant="secondary"
                disabled={!holdings.length}
                onClick={() => onTrade(null, "buy")}
              >
                {t("dashboard.invest.new")}
              </UI.Button>
            ) : (
              <UI.Button type="button" variant="secondary" onClick={() => onOpenAccount("invest")}>
                {t("dashboard.invest.openInvestAccount")}
              </UI.Button>
            )}
          </div>

          <DASH.MarketStatus
            market={market}
            loading={marketLoading}
            error={marketError}
            onRefresh={onRefreshMarket}
          />

          <div className="dash-invest-row">
            <UI.Plate className="dash-chart-plate">
              <div className="dash-chart-head">
                <div>
                  <div className="dash-chart-title-row">
                    <div className="dash-chart-title">
                      {focused ? focused.name : t("dashboard.invest.totalTitle")}
                    </div>
                    {currentPoint ? (
                      <div className="dash-chart-current" title={t("dashboard.invest.currentPrice")}>
                        <span className="dash-chart-current-value">{formatMinor(currentPoint.valueMinor)} RON</span>
                        {currentDelta == null ? null : (
                          <span
                            className={UI.classNames(
                              "dash-chart-current-delta",
                              currentDelta > 0 && "is-up",
                              currentDelta < 0 && "is-down"
                            )}
                          >
                            {(currentDelta > 0 ? "+" : currentDelta < 0 ? "−" : "") + formatMinor(Math.abs(currentDelta))}
                          </span>
                        )}
                      </div>
                    ) : null}
                  </div>
                  <div className="text-muted dash-chart-sub">
                    {focused
                      ? t("dashboard.invest.instrumentSub", {
                          symbol: focused.symbol || focused.id,
                          currency: focused.quoteCurrency || focused.cur,
                        })
                      : t("dashboard.invest.totalSub")}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <DASH.PeriodPicker
                    options={rangeOptions}
                    value={chartRange}
                    onChange={setChartRange}
                    label={t("dashboard.invest.rangeLabel")}
                  />
                  {focused ? (
                    <UI.Button type="button" variant="secondary" onClick={() => setFocusId(null)}>
                      {t("dashboard.invest.backToTotal")}
                    </UI.Button>
                  ) : null}
                </div>
              </div>

              {series.length > 1 ? (
                <DASH.PriceChart
                  key={(focusId || "total") + ":" + chartRange}
                  series={series}
                  dimmed={marketLoading}
                  label={t("dashboard.invest.chartLabel", {
                    what: focused ? focused.name : t("dashboard.invest.totalTitle"),
                    from: GEMS.i18n.isoToDisplayDate(series[0].on),
                    to: GEMS.i18n.isoToDisplayDate(series[series.length - 1].on),
                    change: chartChangeBps == null ? "—" : DASH.formatChangeBps(chartChangeBps),
                  })}
                />
              ) : (
                <div className="dash-chart-empty text-muted">
                  {marketLoading ? t("dashboard.invest.loading") : t("dashboard.invest.noHistory")}
                </div>
              )}

              {series.length > 1 && chartChangeBps != null ? (
                <div className="dash-chart-foot text-muted">
                  {t("dashboard.invest.windowChange", {
                    change: DASH.formatChangeBps(chartChangeBps),
                  })}
                </div>
              ) : null}
            </UI.Plate>
            <div className="dash-holdings-table-wrap">
              <table className="dash-table">
                <tbody>
                {ownedHoldings.map((holding) => (
                  <tr
                    key={holding.id}
                    className={UI.classNames(
                      "dash-holding-row",
                      focusId === holding.id && "is-focused"
                    )}
                  >
                    <td>
                      <button
                        type="button"
                        className="dash-holding-pick"
                        aria-pressed={focusId === holding.id}
                        disabled={!holding.history || holding.history.length < 2}
                        onClick={() => setFocusId(focusId === holding.id ? null : holding.id)}
                      >
                        <span>{holding.name}</span>
                        {holding.symbol ? (
                          <span className="dash-symbol">{holding.symbol}</span>
                        ) : null}
                      </button>
                    </td>
                    <td className="text-muted" style={{ fontSize: 12 }}>{DASH.formatUnits(holding)}</td>
                    <td className="amount-col">
                      <div>{formatMinor(DASH.holdingValue(holding))} RON</div>
                      {holding.changeBps == null ? null : (
                        <div
                          className={UI.classNames(
                            "dash-change",
                            holding.changeBps > 0 && "is-up",
                            holding.changeBps < 0 && "is-down"
                          )}
                        >
                          {DASH.formatChangeBps(holding.changeBps) + " today"}
                        </div>
                      )}
                    </td>
                    <td className="amount-col dash-trade-cell">
                      <UI.Button
                        type="button"
                        variant="secondary"
                        disabled={!hasInvestAccount}
                        onClick={() => onTrade(holding.id, "buy")}
                      >
                        {t("dashboard.invest.buy")}
                      </UI.Button>
                      <UI.Button
                        type="button"
                        variant="secondary"
                        disabled={!hasInvestAccount || DASH.holdingValue(holding) <= 0}
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
                  <td className="amount-col">
                    {investCashMinor == null ? null : formatMinor(investCashMinor) + " RON"}
                  </td>
                  <td className="amount-col dash-trade-cell">
                    {investCashMinor == null ? (
                      <UI.Button type="button" variant="secondary" onClick={() => onOpenAccount("invest")}>
                        {t("dashboard.invest.openInvestAccount")}
                      </UI.Button>
                    ) : null}
                  </td>
                </tr>
                </tbody>
              </table>
            </div>
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

  function CardPinDialog({ busy, error, revealedPin, onDismiss, onSubmit }) {
    const [pin, setPin] = useState("");

    if (revealedPin) {
      return (
        <UI.Dialog labelledBy="card-pin-title" onDismiss={onDismiss}>
          <h2 id="card-pin-title" className="dialog-title">
            {t("dashboard.cards.pinDialog.revealedTitle")}
          </h2>
          <p className="text-muted" style={{ fontSize: 13, marginTop: 4 }}>
            {t("dashboard.cards.pinDialog.revealedHint")}
          </p>

          <div
            style={{
              fontFamily: "var(--font-heading)",
              fontSize: 36,
              letterSpacing: "0.35em",
              textAlign: "center",
              padding: "20px 0",
            }}
          >
            {revealedPin.split("").join(" ")}
          </div>

          <div className="dialog-actions">
            <UI.Button type="button" variant="primary" onClick={onDismiss}>
              {t("dashboard.cards.pinDialog.close")}
            </UI.Button>
          </div>
        </UI.Dialog>
      );
    }

    return (
      <UI.Dialog labelledBy="card-pin-title" onDismiss={onDismiss}>
        <h2 id="card-pin-title" className="dialog-title">
          {t("dashboard.cards.pinDialog.title")}
        </h2>
        <p className="text-muted" style={{ fontSize: 13, marginTop: 4 }}>
          {t("dashboard.cards.pinDialog.hint")}
        </p>

        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(pin);
          }}
        >
          <div className="field">
            <AUTH.DigitGroup
              label={t("dashboard.cards.pinDialog.title")}
              length={6}
              value={pin}
              onChange={setPin}
              autoFocus
            />
            {error ? (
              <div style={{ fontSize: 11, marginTop: 4, color: "var(--color-negative)" }}>
                {error.message}
              </div>
            ) : null}
          </div>

          <div className="dialog-actions">
            <UI.Button type="button" onClick={onDismiss}>
              {t("dashboard.cards.pinDialog.cancel")}
            </UI.Button>
            <UI.Button type="submit" variant="primary" disabled={busy || pin.length !== 6}>
              {busy ? t("dashboard.cards.pinDialog.confirming") : t("dashboard.cards.pinDialog.confirm")}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  }

  function monthlyCardSpendMinor(transactions, accountId) {
    const now = new Date();
    return transactions
      .filter((row) => {
        if (row.channel !== "card" || row.direction !== "out" || row.statusKey !== "booked") return false;
        if (row.accountId !== accountId) return false;
        const [day, month, year] = row.date.split(" ")[0].split(".").map(Number);
        return month === now.getMonth() + 1 && year === now.getFullYear();
      })
      .reduce((sum, row) => sum + row.minor, 0);
  }

  SCR.CardsScreen = function CardsScreen({
    cards,
    accounts,
    transactions,
    loading,
    error,
    selectedCardId,
    onSelect,
    onOpenIssue,
    onOpenHistory,
    busy,
    onFreeze,
    onUnfreeze,
    onDelete,
    pin,
    pinShown,
    onTogglePin,
    cvv,
    detailsShown,
    onToggleDetails,
    pinPromptOpen,
    pinPromptBusy,
    pinPromptError,
    pinPromptTarget,
    onConfirmLoginPin,
    onCancelLoginPin,
    onSetAtmLimit,
    onSetOnlineLimit,
    secureTimer,
  }) {
    const [editingLimit, setEditingLimit] = useState(null);
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
    const card = cards.find((row) => row.cardId === selectedCardId) || null;
    const disabled = busy || !card || card.state === "blocked";
    const monthlySpendMinor = card ? monthlyCardSpendMinor(transactions, card.accountId) : 0;
    const onlineLimitMinor = card ? card.onlineLimitMinor : 0;
    const monthlySpendPct = onlineLimitMinor > 0
      ? Math.min(100, Math.round((monthlySpendMinor / onlineLimitMinor) * 100))
      : 100;

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
          <div style={{ display: "flex", gap: 8 }}>
            <UI.Button type="button" variant="primary" onClick={onOpenIssue}>
              {t("dashboard.cards.issue")}
            </UI.Button>
            <UI.Button type="button" variant="secondary" onClick={onOpenHistory}>
              {t("dashboard.cards.history")}
            </UI.Button>
          </div>
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
                      <span className="dash-card-kind">{formatCardKind(t("dashboard.cards.kind." + kindToI18nKey(row.kind)))}</span>
                      <UI.Tag variant="outline">{t("dashboard.cards.state." + row.state)}</UI.Tag>
                    </div>
                    <div>
                      <div className="dash-card-num">{row.numberMasked}</div>
                      <div className="dash-card-meta text-muted">
                        <span>{row.owner}</span>
                        <span>{formatExpiry(row.expiresOn)}</span>
                      </div>
                    </div>
                    <MastercardMark />
                  </div>
                );

                return (
                  <button
                    key={row.cardId}
                    type="button"
                    className={UI.classNames(
                      "dash-card-flip",
                      flipped && "is-flipped",
                      row.state === "frozen" && "is-frozen"
                    )}
                    onClick={() => onSelect(row.cardId)}
                    aria-pressed={isSelected}
                  >
                    <div className="dash-card-flip-inner">
                      <div className="dash-card-face-front">{front}</div>
                      <div className="dash-card-face-back">
                        <span className="dash-card-back-line" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          {DASH.mockFullNumber(row.cardId, row.numberMasked.slice(-4), row.kind)}
                          <button
                            type="button"
                            className="dash-copy-btn"
                            aria-label="Copy card number"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigator.clipboard.writeText(DASH.mockFullNumber(row.cardId, row.numberMasked.slice(-4), row.kind).replace(/\s/g, ''));
                            }}
                          >
                            <UI.Icon name="Copy" size={14} />
                          </button>
                        </span>
                        <span className="dash-card-back-line" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          {t("dashboard.cards.expLabel", { exp: formatExpiry(row.expiresOn) })}
                          <button
                            type="button"
                            className="dash-copy-btn"
                            aria-label="Copy expiry"
                            onClick={(e) => {
                              e.stopPropagation();
                              navigator.clipboard.writeText(formatExpiry(row.expiresOn));
                            }}
                          >
                            <UI.Icon name="Copy" size={14} />
                          </button>
                        </span>
                        <span className="dash-card-back-line" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          {cvv ? t("dashboard.cards.cvvLabel", { cvv }) : "•••"}
                          {cvv ? (
                            <button
                              type="button"
                              className="dash-copy-btn"
                              aria-label="Copy CVV"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigator.clipboard.writeText(cvv);
                              }}
                            >
                              <UI.Icon name="Copy" size={14} />
                            </button>
                          ) : null}
                        </span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            {card ? (
              <UI.Plate className="elev-sm dash-quick-settings-panel" style={{ padding: 16, alignSelf: "start" }}>
                <UI.Kicker style={{ marginBottom: 6 }}>{t("dashboard.cards.quickSettings")}</UI.Kicker>
                <div style={{ fontFamily: "var(--font-heading)", fontSize: 20, marginBottom: 4 }}>
                  {t("dashboard.cards.kind." + kindToI18nKey(card.kind)) + " " + card.numberMasked.slice(-4)}
                </div>
                <div className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
                  {t("dashboard.cards.linkedAccount", {
                    account: (() => {
                      const linked = accounts.find((row) => row.id === card.accountId);
                      return linked ? DASH.accountLabel(linked) : t("dashboard.cards.accountUnknown");
                    })(),
                  })}
                </div>
                <div className="dash-settings-list">
                  <UI.Button
                    type="button"
                    variant="secondary"
                    style={{ justifyContent: "space-between" }}
                    disabled={busy || card.state === "blocked"}
                    onClick={onTogglePin}
                  >
                    {pinShown ? t("dashboard.cards.hidePin") + (secureTimer ? ` (${secureTimer}s)` : "") : t("dashboard.cards.showPin")}
                  </UI.Button>
                  <UI.Button
                    type="button"
                    variant="secondary"
                    style={{ justifyContent: "space-between" }}
                    disabled={busy || card.state === "blocked"}
                    onClick={onToggleDetails}
                  >
                    {detailsShown ? t("dashboard.cards.hideDetails") + (secureTimer ? ` (${secureTimer}s)` : "") : t("dashboard.cards.showDetails")}
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
                    onClick={() => setDeleteConfirmOpen(true)}
                  >
                    {t("dashboard.cards.deleteCard")}
                  </UI.Button>
                </div>
                <div className="hr" />
                {(() => {
                  const spendLabel = t("dashboard.cards.monthlySpend", {
                    spent: DASH.formatMinor(monthlySpendMinor),
                    limit: DASH.formatMinor(onlineLimitMinor),
                  });
                  return (
                    <React.Fragment>
                      <div className="text-muted" style={{ fontSize: 12 }}>{spendLabel}</div>
                      <div style={{ marginTop: 6 }}>
                        <DASH.ProgressBar pct={monthlySpendPct} label={spendLabel} className="dash-progress-negative" />
                      </div>
                    </React.Fragment>
                  );
                })()}
              </UI.Plate>
            ) : null}
          </div>
        )}

        {pinPromptOpen ? (
          <CardPinDialog
            busy={pinPromptBusy}
            error={pinPromptError}
            revealedPin={pinPromptTarget === "cardPin" && pinShown ? pin : null}
            onDismiss={onCancelLoginPin}
            onSubmit={onConfirmLoginPin}
          />
        ) : null}
        {deleteConfirmOpen ? (
          <UI.Dialog labelledBy="delete-confirm-title" onDismiss={() => setDeleteConfirmOpen(false)}>
            <h2 id="delete-confirm-title" className="dialog-title">
              {t("dashboard.cards.deleteCard")}
            </h2>
            <p className="text-muted" style={{ fontSize: 13, marginTop: 4 }}>
              {t("dashboard.cards.confirmDelete")}
            </p>
            <div style={{ display: "flex", gap: 8, marginTop: 24 }}>
              <UI.Button
                type="button"
                variant="primary"
                style={{ flex: 1 }}
                onClick={() => {
                  setDeleteConfirmOpen(false);
                  onDelete();
                }}
              >
                {t("dashboard.cards.confirm")}
              </UI.Button>
              <UI.Button type="button" variant="secondary" onClick={() => setDeleteConfirmOpen(false)}>
                {t("dashboard.cards.cancel")}
              </UI.Button>
            </div>
          </UI.Dialog>
        ) : null}
      </div>
    );
  };

  const CATEGORY_COLORS = {
    groceries: "var(--chart-1)",
    utilities: "var(--chart-2)",
    transport: "var(--chart-3)",
    entertainment: "var(--chart-4)",
    transfer: "var(--chart-5)",
    income: "var(--chart-6)",
    other: "var(--chart-7)",
    investment: "var(--chart-1)",
    savings: "var(--chart-2)",
  };

  const CHART_SERIES_LABEL = {
    income: "dashboard.category.income",
    spend: "dashboard.analytics.spend",
    current: "dashboard.analytics.goal.projectionCurrent",
    needed: "dashboard.analytics.goal.projectionNeeded",
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

  function useAnalyticsData(months, accounts) {
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

    const accountById = new Map((accounts || []).map(a => [a.id, a]));
    const rowsByTx = new Map();
    (rows || []).forEach(row => {
      if (!rowsByTx.has(row.transactionId)) rowsByTx.set(row.transactionId, []);
      rowsByTx.get(row.transactionId).push(row);
    });

    (rows || []).forEach((row) => {
      if (row.amount.currency !== currency) return;
      
      const acc = accountById.get(row.accountId);
      if (!acc || acc.typeKey !== "current") return;

      const siblingRows = rowsByTx.get(row.transactionId) || [];
      const hasOtherCurrent = siblingRows.some(s => 
         s.accountId !== row.accountId && 
         accountById.get(s.accountId)?.typeKey === "current"
      );
      if (hasOtherCurrent) return;

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
        let cat = row.category;
        if (cat === "transfer" && row.kind === "internal_transfer") {
          const siblingRows = rowsByTx.get(row.transactionId) || [];
          const otherRow = siblingRows.find(s => s.accountId !== row.accountId);
          if (otherRow) {
            const otherAcc = accountById.get(otherRow.accountId);
            if (otherAcc) {
              if (otherAcc.typeKey === "invest") cat = "investment";
              else if (otherAcc.typeKey === "savings" || otherAcc.typeKey === "deposit") cat = "savings";
            }
          }
        }
        categoryTotals[cat] = (categoryTotals[cat] || 0) + spend;
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

  function EduSection({ title, hint, action, children }) {
    return (
      <section className="dash-edu-section">
        <div className="dash-edu-section-head">
          <div>
            <h4 className="dash-edu-section-title">{title}</h4>
            {hint ? <p className="dash-edu-section-hint">{hint}</p> : null}
          </div>
          {action}
        </div>
        {children}
      </section>
    );
  }

  let _globalGoalVersion = 0;

  SCR.EducationScreen = function EducationScreen({ accounts }) {
    const [goalVersion, setGoalVersion] = useState(_globalGoalVersion);

    function bumpGoalVersion() {
      _globalGoalVersion++;
      setGoalVersion(_globalGoalVersion);
    }

    return (
      <div className="dash-edu-page">
        <div className="dash-screen-head">
          <h3 style={{ margin: 0 }}>{t("dashboard.education.title")}</h3>
        </div>

        <EducationChatPanel onGoalCreated={bumpGoalVersion} />

        <GoalsPanel accounts={accounts} goalVersion={goalVersion} onGoalChange={bumpGoalVersion} />

        <RecommendationsCard goalVersion={goalVersion} />

        <LessonsPanel />
      </div>
    );
  };

  function renderInlineText(line, keyPrefix) {
    const parts = line.split(/(\*\*[^*]+\*\*)/g).filter((part) => part !== "");
    return parts.map((part, index) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={`${keyPrefix}-${index}`}>{part.slice(2, -2)}</strong>
      ) : (
        <React.Fragment key={`${keyPrefix}-${index}`}>{part}</React.Fragment>
      )
    );
  }

  function renderStructuredText(text) {
    const blocks = text
      .split(/\n{2,}/)
      .map((block) => block.trim())
      .filter(Boolean);
    if (!blocks.length) return null;

    return blocks.map((block, blockIndex) => {
      const lines = block
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      const isList = lines.length > 0 && lines.every((line) => /^[-*•]\s+/.test(line));

      if (isList) {
        return (
          <ul className="dash-msg-list" key={blockIndex}>
            {lines.map((line, lineIndex) => (
              <li key={lineIndex}>
                {renderInlineText(line.replace(/^[-*•]\s+/, ""), `${blockIndex}-${lineIndex}`)}
              </li>
            ))}
          </ul>
        );
      }
      return (
        <p className="dash-msg-paragraph" key={blockIndex}>
          {renderInlineText(lines.join(" "), String(blockIndex))}
        </p>
      );
    });
  }

  function EducationChatPanel({ onGoalCreated }) {
    const [messages, setMessages] = useState([
      { role: "ai", kind: "text", text: t("dashboard.education.chat.seed") },
    ]);
    const [draft, setDraft] = useState("");
    const [busy, setBusy] = useState(false);
    const inputRef = useRef(null);

    useEffect(() => {
      if (busy || !inputRef.current) return;
      const active = document.activeElement;
      if (active && active !== document.body && active !== inputRef.current) return;
      inputRef.current.focus();
    }, [busy]);

    function transcriptOf(list) {
      return list
        .filter((message) => typeof message.text === "string" && message.text.trim() !== "")
        .slice(-10)
        .map((message) => ({ role: message.role === "user" ? "user" : "assistant", content: message.text }));
    }

    function send() {
      const text = draft.trim();
      if (!text || busy) return;
      const history = transcriptOf(messages);
      setMessages((list) => list.concat([{ role: "user", kind: "text", text }]));
      setDraft("");
      setBusy(true);
      api
        .askGems(text, history, "education")
        .then((result) => {
          const proposals = (result.proposals || []).filter(
            (item) => item && item.status === "proposed"
          );
          const goalProposal = proposals.filter((item) => item.proposalKind === "goal")[0];
          const standingOrderProposal = proposals.filter(
            (item) => item.proposalKind === "standingOrder"
          )[0];
          const answer = (result.answer || "").trim() || t("dashboard.chat.errorNote");
          let reply = { role: "ai", kind: "text", text: answer, aiGenerated: true };
          if (goalProposal) {
            reply = { role: "ai", kind: "goalProposal", text: answer, proposal: goalProposal, aiGenerated: true };
          } else if (standingOrderProposal) {
            reply = {
              role: "ai",
              kind: "standingOrderProposal",
              text: answer,
              proposal: standingOrderProposal,
              aiGenerated: true,
            };
          }
          setMessages((list) => list.concat([reply]));
        })
        .catch((error) => {
          const retryAfter = error && error.details && error.details.retryAfterSeconds;
          const note =
            error && error.code === "rate_limited"
              ? t("dashboard.chat.rateLimitedNote", {
                  minutes: Math.max(1, Math.ceil((retryAfter || 60) / 60)),
                })
              : t("dashboard.chat.errorNote");
          setMessages((list) => list.concat([{ role: "ai", kind: "text", text: note }]));
        })
        .finally(() => setBusy(false));
    }

    return (
      <UI.Plate className="elev-sm dash-edu-panel">
        <div className="dash-edu-panel-head">
          <span className="dash-edu-avatar" aria-hidden="true">
            <UI.Icon name="Sparkles" size={16} />
          </span>
          <div>
            <div className="dash-edu-title">{t("dashboard.education.chat.title")}</div>
            <div className="dash-edu-subtitle">{t("dashboard.education.chat.subtitle")}</div>
          </div>
        </div>
        <div className="dash-chat-scroll dash-edu-scroll">
          {messages.map((message, index) => (
            <div className="dash-msg" key={index}>
              {message.role === "user" ? (
                <div className="dash-msg-user">{message.text}</div>
              ) : (
                <div className="dash-msg-ai">
                  <span className="dash-msg-ai-dot" aria-hidden="true" />
                  <div className="dash-msg-ai-body">
                    {message.text ? renderStructuredText(message.text) : null}

                    {message.kind === "goalProposal" && message.proposal ? (
                      <GoalProposalCard proposal={message.proposal} onGoalCreated={onGoalCreated} />
                    ) : null}

                    {message.kind === "standingOrderProposal" && message.proposal ? (
                      <StandingOrderProposalCard proposal={message.proposal} />
                    ) : null}

                    {message.aiGenerated ? (
                      <div className="dash-ai-disclaimer">
                        <UI.Icon name="Sparkles" size={13} />
                        {t("dashboard.analytics.aiDisclaimer")}
                      </div>
                    ) : null}
                  </div>
                </div>
              )}
            </div>
          ))}
          {busy ? (
            <div className="dash-msg">
              <div className="dash-msg-ai">
                <span className="dash-msg-ai-dot" aria-hidden="true" />
                <div className="dash-msg-ai-body text-muted">{t("dashboard.chat.thinking")}</div>
              </div>
            </div>
          ) : null}
        </div>
        <div className="dash-chat-input-row dash-edu-input-row">
          <input
            ref={inputRef}
            className="dash-chat-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") send();
            }}
            placeholder={t("dashboard.education.chat.placeholder")}
            aria-label={t("dashboard.education.chat.placeholder")}
          />
          <UI.Button type="button" variant="primary" disabled={busy} onClick={send}>
            {t("dashboard.education.chat.send")}
          </UI.Button>
        </div>
      </UI.Plate>
    );
  }

  function GoalProposalCard({ proposal, onGoalCreated }) {
    const [state, setState] = useState({ busy: false, done: false, error: false });

    function confirm() {
      setState({ busy: true, done: false, error: false });
      api
        .createGoal(proposal.accountId, proposal.name, proposal.targetMinorUnits, proposal.targetDate)
        .then(() => {
          setState({ busy: false, done: true, error: false });
          if (onGoalCreated) onGoalCreated();
        })
        .catch(() => setState({ busy: false, done: false, error: true }));
    }

    return (
      <UI.Plate className="dash-tx-card">
        <UI.Kicker style={{ marginBottom: 4 }}>{t("dashboard.education.chat.goalTitle")}</UI.Kicker>
        <div className="dash-tx-amount">{proposal.targetFormatted}</div>
        <div className="dash-tx-grid">
          <span className="text-muted">{t("dashboard.education.chat.goalTarget")}</span>
          <span>{proposal.name}</span>
          <span className="text-muted">{t("dashboard.education.chat.goalDate")}</span>
          <span>{GEMS.i18n.isoToDisplayDate(proposal.targetDate)}</span>
          <span className="text-muted">{t("dashboard.education.chat.goalAccount")}</span>
          <span>{proposal.accountLabel}</span>
        </div>
        <p className="dash-proposal-note">{t("dashboard.education.chat.goalProposalNote")}</p>
        {state.done ? (
          <p className="dash-proposal-note">{t("dashboard.education.chat.goalSuccess")}</p>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <UI.Button type="button" variant="primary" style={{ flex: 1 }} disabled={state.busy} onClick={confirm}>
              {state.busy ? t("dashboard.education.chat.goalConfirming") : t("dashboard.education.chat.goalConfirm")}
            </UI.Button>
          </div>
        )}
        {state.error ? <p className="dash-proposal-note">{t("dashboard.education.chat.goalError")}</p> : null}
      </UI.Plate>
    );
  }

  function StandingOrderProposalCard({ proposal }) {
    const [state, setState] = useState({ busy: false, done: false, error: false });

    function confirm() {
      setState({ busy: true, done: false, error: false });
      api
        .createStandingOrder(
          proposal.goalId,
          null,
          proposal.amountMinorUnits,
          proposal.frequency,
          "agent-suggestion-confirmed"
        )
        .then(() => setState({ busy: false, done: true, error: false }))
        .catch(() => setState({ busy: false, done: false, error: true }));
    }

    return (
      <UI.Plate className="dash-tx-card">
        <UI.Kicker style={{ marginBottom: 4 }}>{t("dashboard.education.chat.standingOrderTitle")}</UI.Kicker>
        <div className="dash-tx-amount">{proposal.amountFormatted}</div>
        <div className="dash-tx-grid">
          <span className="text-muted">{t("dashboard.education.chat.standingOrderAmount")}</span>
          <span>{proposal.goalName}</span>
          <span className="text-muted">{t("dashboard.education.chat.standingOrderFrequency")}</span>
          <span>
            {proposal.frequency === "weekly"
              ? t("dashboard.analytics.goal.standingOrder.weekly")
              : t("dashboard.analytics.goal.standingOrder.monthly")}
          </span>
        </div>
        <p className="dash-proposal-note">{t("dashboard.chat.proposalNotSent")}</p>
        {state.done ? (
          <p className="dash-proposal-note">{t("dashboard.education.chat.standingOrderSuccess")}</p>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <UI.Button type="button" variant="primary" style={{ flex: 1 }} disabled={state.busy} onClick={confirm}>
              {state.busy
                ? t("dashboard.education.chat.standingOrderConfirming")
                : t("dashboard.education.chat.standingOrderConfirm")}
            </UI.Button>
          </div>
        )}
        {state.error ? <p className="dash-proposal-note">{t("dashboard.education.chat.standingOrderError")}</p> : null}
      </UI.Plate>
    );
  }

  let _recoCache = { version: -1, answer: null };

  function RecommendationsCard({ goalVersion }) {
    const [state, setState] = useState({
      loading: _recoCache.version !== goalVersion,
      answer: _recoCache.version === goalVersion ? _recoCache.answer : null,
      error: null
    });

    useEffect(() => {
      if (_recoCache.version === goalVersion && _recoCache.answer !== null) {
        return; // Use cache
      }
      let cancelled = false;
      setState({ loading: true, answer: null, error: null });
      const prompt =
        GEMS.i18n.locale === "ro"
          ? "Dă-mi recomandările concrete de economisire și buget care reies din tranzacțiile mele: cel " +
            "mult trei, câte un rând pentru fiecare acțiune diferită. Dacă ai o singură recomandare, " +
            "scrie un singur rând; nu completa până la trei reformulând aceeași acțiune. Fiecare rând " +
            "începe cu '- ', spune suma exactă și categoria sau obiectivul, ca o acțiune concretă — nu doar " +
            "o cifră sau un streak; nu adăuga mențiunea că e o estimare, apare deja separat. Fără " +
            "introducere, fără concluzie, fără titluri."
          : "Give me the concrete savings and budgeting actions that follow from my transactions: at most " +
            "three, one line per distinct action. If only one follows, write only one line; do not pad to " +
            "three by rephrasing the same action. Start each line with '- ', name the exact amount and " +
            "category or goal, phrased as an action to take — never a bare figure or streak alone, and " +
            "skip the estimate note, that already shows separately. No introduction, no conclusion, no headings.";
      api
        .askAnalytics(prompt)
        .then((result) => {
          if (cancelled) return;
          const ans = (result && result.answer ? result.answer : "").trim();
          _recoCache = { version: goalVersion, answer: ans };
          setState({ loading: false, answer: ans, error: null });
        })
        .catch((err) => {
          if (!cancelled) setState({ loading: false, answer: null, error: err });
        });
      return () => {
        cancelled = true;
      };
    }, [goalVersion]);

    const body = state.loading
      ? t("dashboard.analytics.recommendations.loading")
      : state.error
      ? t("dashboard.analytics.recommendations.error")
      : state.answer || t("dashboard.analytics.recommendations.empty");

    const ready = !state.loading && !state.error && Boolean(state.answer);
    const actions = ready ? splitRecommendations(state.answer) : [];

    return (
      <EduSection
        title={t("dashboard.analytics.recommendations.title")}
        hint={t("dashboard.analytics.recommendations.hint")}
      >
        <UI.Plate className="elev-sm dash-reco-plate">
          {ready && actions.length ? (
            <ol className="dash-reco-list">
              {actions.map((action, index) => (
                <li className="dash-reco-item" key={index}>
                  <span className="dash-reco-index" aria-hidden="true">{index + 1}</span>
                  <div className="dash-reco-body">{renderInlineText(action, "reco-" + index)}</div>
                </li>
              ))}
            </ol>
          ) : (
            <div className="dash-reco-plain">{renderStructuredText(body)}</div>
          )}
          {ready ? (
            <div className="dash-ai-disclaimer">
              <UI.Icon name="Sparkles" size={13} />
              {t("dashboard.analytics.aiDisclaimer")}
            </div>
          ) : null}
        </UI.Plate>
      </EduSection>
    );
  }

  function splitRecommendations(text) {
    return (text || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => /^[-*•]\s+/.test(line))
      .map((line) => line.replace(/^[-*•]\s+/, ""))
      .filter(Boolean);
  }

  function accountPickerLabel(account) {
    return DASH.accountLabel(account);
  }

  function SetGoalDialog({ accounts, busy, error, onSubmit, onDismiss }) {
    const [accountId, setAccountId] = useState((accounts[0] && accounts[0].id) || "");
    const [name, setName] = useState("");
    const [amount, setAmount] = useState("");
    const [targetDate, setTargetDate] = useState("");
    const [initialDeposit, setInitialDeposit] = useState("");

    const amountMinor = DASH.parseMinor(amount);
    const initialDepositMinor = DASH.parseMinor(initialDeposit);
    const minDate = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const ready = Boolean(accountId) && name.trim() !== "" && amountMinor > 0 && Boolean(targetDate);

    function submit(event) {
      event.preventDefault();
      if (!ready) return;
      onSubmit({
        accountId,
        name: name.trim(),
        targetMinorUnits: amountMinor,
        targetDate,
        initialDepositMinorUnits: initialDepositMinor > 0 ? initialDepositMinor : 0,
      });
    }

    return (
      <UI.Dialog labelledBy="goal-dialog-title" onDismiss={onDismiss}>
        <h2 id="goal-dialog-title" className="dialog-title">{t("dashboard.analytics.goal.dialog.title")}</h2>
        <p className="text-muted" style={{ fontSize: 13 }}>{t("dashboard.analytics.goal.dialog.subtitle")}</p>
        <form noValidate onSubmit={submit}>
          <UI.Field id="goal-account" label={t("dashboard.analytics.goal.dialog.account")}>
            <UI.Select id="goal-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {accountPickerLabel(account)}
                </option>
              ))}
            </UI.Select>
          </UI.Field>
          <UI.Field id="goal-name" label={t("dashboard.analytics.goal.dialog.name")} error={error ? error.message : null}>
            <UI.TextInput
              id="goal-name"
              autoFocus
              value={name}
              placeholder={t("dashboard.analytics.goal.dialog.namePlaceholder")}
              onChange={(event) => setName(event.target.value)}
            />
          </UI.Field>
          <UI.Field id="goal-amount" label={t("dashboard.analytics.goal.dialog.amount")}>
            <UI.TextInput id="goal-amount" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </UI.Field>
          <UI.Field id="goal-date" label={t("dashboard.analytics.goal.dialog.date")}>
            <UI.TextInput id="goal-date" type="date" min={minDate} value={targetDate} onChange={(event) => setTargetDate(event.target.value)} />
          </UI.Field>
          <UI.Field id="goal-initial-deposit" label={t("dashboard.analytics.goal.dialog.initialDeposit")}>
            <UI.TextInput
              id="goal-initial-deposit"
              inputMode="decimal"
              value={initialDeposit}
              onChange={(event) => setInitialDeposit(event.target.value)}
            />
          </UI.Field>
          <div className="dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onDismiss}>{t("dashboard.analytics.goal.dialog.cancel")}</UI.Button>
            <UI.Button type="submit" variant="primary" disabled={!ready || busy}>
              {busy ? t("dashboard.analytics.goal.dialog.submitting") : t("dashboard.analytics.goal.dialog.submit")}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  }

  function CloseGoalDialog({ name, busy, error, onConfirm, onDismiss }) {
    return (
      <UI.Dialog labelledBy="close-goal-dialog-title" onDismiss={onDismiss}>
        <h2 id="close-goal-dialog-title" className="dialog-title">
          {t("dashboard.analytics.goal.closeDialog.title")}
        </h2>
        <p className="text-muted" style={{ fontSize: 13 }}>
          {t("dashboard.analytics.goal.closeDialog.body", { name })}
        </p>
        {error ? <p className="dash-proposal-note">{t("dashboard.analytics.goal.closeDialog.error")}</p> : null}
        <div className="dialog-actions">
          <UI.Button type="button" variant="secondary" onClick={onDismiss} disabled={busy}>
            {t("dashboard.analytics.goal.closeDialog.cancel")}
          </UI.Button>
          <UI.Button type="button" variant="primary" onClick={onConfirm} disabled={busy}>
            {busy ? t("dashboard.analytics.goal.closeDialog.confirming") : t("dashboard.analytics.goal.closeDialog.confirm")}
          </UI.Button>
        </div>
      </UI.Dialog>
    );
  }

  function GoalMovementDialog({ mode, goalName, progressPct, busy, error, onSubmit, onDismiss }) {
    const [amount, setAmount] = useState("");
    const [confirmedBelowThreshold, setConfirmedBelowThreshold] = useState(false);
    const amountMinor = DASH.parseMinor(amount);
    const needsWarning = mode === "withdraw" && progressPct < 50 && amountMinor > 0;
    const ready = amountMinor > 0 && (!needsWarning || confirmedBelowThreshold);
    const isWithdraw = mode === "withdraw";
    const copy = isWithdraw ? "withdrawDialog" : "depositDialog";

    function submit(event) {
      event.preventDefault();
      if (!ready) return;
      onSubmit(amountMinor);
    }

    return (
      <UI.Dialog labelledBy="goal-movement-dialog-title" onDismiss={onDismiss}>
        <h2 id="goal-movement-dialog-title" className="dialog-title">
          {t(`dashboard.analytics.goal.${copy}.title`, { name: goalName })}
        </h2>
        <form noValidate onSubmit={submit}>
          <UI.Field id="goal-movement-amount" label={t(`dashboard.analytics.goal.${copy}.amount`)} error={error ? error.message : null}>
            <UI.TextInput
              id="goal-movement-amount"
              autoFocus
              inputMode="decimal"
              value={amount}
              onChange={(event) => {
                setAmount(event.target.value);
                setConfirmedBelowThreshold(false);
              }}
            />
          </UI.Field>
          {needsWarning ? (
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontSize: 13 }}>
              <input
                type="checkbox"
                checked={confirmedBelowThreshold}
                onChange={(event) => setConfirmedBelowThreshold(event.target.checked)}
              />
              {t("dashboard.analytics.goal.withdrawDialog.belowThresholdWarning", {
                pct: formatGoalPct(progressPct),
              })}
            </label>
          ) : null}
          <div className="dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onDismiss}>
              {t(`dashboard.analytics.goal.${copy}.cancel`)}
            </UI.Button>
            <UI.Button type="submit" variant="primary" disabled={!ready || busy}>
              {busy ? t(`dashboard.analytics.goal.${copy}.submitting`) : t(`dashboard.analytics.goal.${copy}.submit`)}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  }

  function StandingOrderDialog({ accounts, goalCurrency, busy, error, onSubmit, onDismiss }) {
    const eligibleAccounts = (accounts || []).filter(
      (account) => (account.typeKey === "current" || account.typeKey === "invest") && account.cur === goalCurrency
    );
    const [accountId, setAccountId] = useState((eligibleAccounts[0] && eligibleAccounts[0].id) || "");
    const [amount, setAmount] = useState("");
    const [frequency, setFrequency] = useState("weekly");
    const amountMinor = DASH.parseMinor(amount);
    const ready = Boolean(accountId) && amountMinor > 0;

    function submit(event) {
      event.preventDefault();
      if (!ready) return;
      onSubmit(accountId, amountMinor, frequency);
    }

    return (
      <UI.Dialog labelledBy="standing-order-dialog-title" onDismiss={onDismiss}>
        <h2 id="standing-order-dialog-title" className="dialog-title">
          {t("dashboard.analytics.goal.standingOrder.set")}
        </h2>
        <form noValidate onSubmit={submit}>
          {eligibleAccounts.length ? (
            <UI.Field id="standing-order-account" label={t("dashboard.analytics.goal.standingOrder.account")}>
              <UI.Select id="standing-order-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
                {eligibleAccounts.map((account) => (
                  <option key={account.id} value={account.id}>{accountPickerLabel(account)}</option>
                ))}
              </UI.Select>
            </UI.Field>
          ) : (
            <div className="dash-balance-line is-short" role="alert">
              {t("dashboard.analytics.goal.standingOrder.noAccount")}
            </div>
          )}
          <UI.Field id="standing-order-amount" label={t("dashboard.analytics.goal.standingOrder.amount")} error={error ? error.message : null}>
            <UI.TextInput id="standing-order-amount" autoFocus inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </UI.Field>
          <UI.Field id="standing-order-frequency" label={t("dashboard.analytics.goal.standingOrder.frequency")}>
            <UI.Select id="standing-order-frequency" value={frequency} onChange={(event) => setFrequency(event.target.value)}>
              <option value="weekly">{t("dashboard.analytics.goal.standingOrder.weekly")}</option>
              <option value="monthly">{t("dashboard.analytics.goal.standingOrder.monthly")}</option>
            </UI.Select>
          </UI.Field>
          <div className="dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onDismiss}>
              {t("dashboard.analytics.goal.dialog.cancel")}
            </UI.Button>
            <UI.Button type="submit" variant="primary" disabled={!ready || busy}>
              {busy ? t("dashboard.analytics.goal.standingOrder.creating") : t("dashboard.analytics.goal.standingOrder.create")}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  }

  function EditStandingOrderAmountDialog({ currentAmountMinor, busy, error, onSubmit, onDismiss }) {
    const [amount, setAmount] = useState(formatMinor(currentAmountMinor));
    const amountMinor = DASH.parseMinor(amount);
    const ready = amountMinor > 0;

    function submit(event) {
      event.preventDefault();
      if (!ready) return;
      onSubmit(amountMinor);
    }

    return (
      <UI.Dialog labelledBy="standing-order-edit-title" onDismiss={onDismiss}>
        <h2 id="standing-order-edit-title" className="dialog-title">
          {t("dashboard.analytics.goal.standingOrder.editTitle")}
        </h2>
        <form noValidate onSubmit={submit}>
          <UI.Field id="standing-order-edit-amount" label={t("dashboard.analytics.goal.standingOrder.amount")} error={error ? error.message : null}>
            <UI.TextInput id="standing-order-edit-amount" autoFocus inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </UI.Field>
          <div className="dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onDismiss}>
              {t("dashboard.analytics.goal.dialog.cancel")}
            </UI.Button>
            <UI.Button type="submit" variant="primary" disabled={!ready || busy}>
              {busy ? t("dashboard.analytics.goal.standingOrder.saving") : t("dashboard.analytics.goal.standingOrder.save")}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  }

  function addMonthsIso(months) {
    const now = new Date();
    const target = new Date(now.getFullYear(), now.getMonth() + months, now.getDate());
    return (
      target.getFullYear() +
      "-" +
      String(target.getMonth() + 1).padStart(2, "0") +
      "-" +
      String(target.getDate()).padStart(2, "0")
    );
  }

  function monthsBetweenNowAnd(isoDate) {
    const target = new Date(isoDate);
    const now = new Date();
    return (
      (target.getFullYear() - now.getFullYear()) * 12 + (target.getMonth() - now.getMonth())
    );
  }

  function formatGoalPct(pct) {
    const value = pct > 0 && pct < 10 ? Math.round(pct * 10) / 10 : Math.round(pct);
    const text = Number.isInteger(value) ? String(value) : value.toFixed(1);
    return GEMS.i18n.locale === "ro" ? text.replace(".", ",") : text;
  }

  function GoalRing({ pct, size = 148, stroke = 14, children }) {
    const radius = (size - stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const share = Math.max(0, Math.min(100, pct)) / 100;
    const filled = share > 0 ? Math.max(circumference * 0.02, share * circumference) : 0;
    return (
      <div className="dash-ring" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--color-border)"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${filled} ${circumference - filled}`}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
            style={{ transition: "stroke-dasharray 0.35s ease" }}
          />
        </svg>
        <div className="dash-ring-centre">{children}</div>
      </div>
    );
  }

  function GoalsPanel({ accounts, goalVersion, onGoalChange }) {
    const [state, setState] = useState({ loading: true, goals: [], error: null });
    const [refreshKey, setRefreshKey] = useState(0);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [creating, setCreating] = useState(false);
    const [createError, setCreateError] = useState(null);

    useEffect(() => {
      let cancelled = false;
      setState((previous) => ({ loading: true, goals: previous.goals, error: null }));
      api
        .listGoals()
        .then((result) => {
          if (!cancelled) setState({ loading: false, goals: result.goals || [], error: null });
        })
        .catch((err) => {
          if (!cancelled) setState({ loading: false, goals: [], error: err });
        });
      return () => {
        cancelled = true;
      };
    }, [refreshKey, goalVersion]);

    function refresh() {
      setRefreshKey((value) => value + 1);
      if (onGoalChange) onGoalChange();
    }

    function submitGoal(payload) {
      setCreating(true);
      setCreateError(null);
      api
        .createGoal(
          payload.accountId,
          payload.name,
          payload.targetMinorUnits,
          payload.targetDate,
          payload.initialDepositMinorUnits
        )
        .then(() => {
          setCreating(false);
          setDialogOpen(false);
          refresh();
        })
        .catch((err) => {
          setCreating(false);
          setCreateError(err);
        });
    }

    const eligibleAccounts = (accounts || []).filter((account) => account.typeKey !== "invest");
    const goals = state.goals;

    const addButton = goals.length ? (
      <UI.Button
        type="button"
        variant="secondary"
        disabled={!eligibleAccounts.length}
        onClick={() => setDialogOpen(true)}
      >
        {t("dashboard.analytics.goal.addGoal")}
      </UI.Button>
    ) : null;

    return (
      <EduSection
        title={t("dashboard.analytics.goal.title")}
        hint={
          goals.length
            ? t("dashboard.analytics.goal.activeCount", { count: goals.length })
            : t("dashboard.analytics.goal.sectionHint")
        }
        action={addButton}
      >
        {state.loading ? (
          <UI.Plate className="elev-sm dash-goals-loading">
            {t("dashboard.analytics.loading")}
          </UI.Plate>
        ) : !goals.length ? (
          <UI.Plate className="elev-sm dash-goals-empty">
            <div className="text-muted" style={{ fontSize: 13 }}>
              {t("dashboard.analytics.goal.noGoal")}
            </div>
            <UI.Button
              type="button"
              variant="primary"
              disabled={!eligibleAccounts.length}
              onClick={() => setDialogOpen(true)}
            >
              {t("dashboard.analytics.goal.setGoal")}
            </UI.Button>
          </UI.Plate>
        ) : (
          <div className="dash-goals-grid">
            {goals.map((goal) => (
              <GoalCard key={goal.goalId} goal={goal} accounts={accounts} onChanged={refresh} />
            ))}
          </div>
        )}

        {dialogOpen ? (
          <SetGoalDialog
            accounts={eligibleAccounts}
            busy={creating}
            error={createError}
            onSubmit={submitGoal}
            onDismiss={() => {
              setDialogOpen(false);
              setCreateError(null);
            }}
          />
        ) : null}
      </EduSection>
    );
  }

  function GoalProjector({ goal }) {
    const remaining = Math.max(0, goal.targetMinorUnits - goal.progressMinorUnits);
    const required = Math.max(0, goal.requiredMinorUnitsPerMonth || 0);
    const actual = Math.max(0, goal.actualMinorUnitsPerMonth || 0);
    const suggested = actual > 0 ? actual : required > 0 ? required : Math.ceil(remaining / 12);
    const maxMonthly = Math.max(remaining, suggested * 2, 10000);
    const step = Math.max(1000, Math.round(maxMonthly / 100 / 1000) * 1000);

    const [monthly, setMonthly] = useState(Math.min(maxMonthly, Math.max(step, suggested)));
    const [isEditingPace, setIsEditingPace] = useState(false);
    const [editValue, setEditValue] = useState("");

    const chosen = Math.max(0, Math.min(monthly, maxMonthly));
    const months = chosen > 0 ? Math.ceil(remaining / chosen) : null;
    const projectedIso = months !== null && months <= 600 ? addMonthsIso(months) : null;
    const monthsToTarget = monthsBetweenNowAnd(goal.targetDate);
    const onTrack = months !== null && months <= Math.max(1, monthsToTarget);

    return (
      <div className="dash-projector">
        <label className="dash-projector-label" htmlFor={"pace-" + goal.goalId}>
          {t("dashboard.analytics.goal.projector.label")}
        </label>
        {isEditingPace ? (
          <div className="dash-projector-amount" style={{ display: "flex", gap: "8px", alignItems: "baseline" }}>
            <input
              type="number"
              value={editValue}
              onChange={(event) => {
                setEditValue(event.target.value);
                setMonthly(Math.round(Number(event.target.value) * 100));
              }}
              onBlur={() => setIsEditingPace(false)}
              onKeyDown={(e) => { if (e.key === "Enter") setIsEditingPace(false); }}
              min={0}
              max={maxMonthly / 100}
              step="any"
              autoFocus
              style={{
                background: "transparent",
                border: "none",
                borderBottom: "1px dashed currentColor",
                color: "inherit",
                font: "inherit",
                width: "4.5em",
                outline: "none",
                padding: 0,
                margin: 0
              }}
            />
            <span>{goal.currency}</span>
          </div>
        ) : (
          <div 
            className="dash-projector-amount" 
            onClick={() => {
              setEditValue(chosen > 0 ? String(chosen / 100) : "");
              setIsEditingPace(true);
            }}
            style={{ cursor: "text" }}
          >
            {UI.formatMoney(chosen, goal.currency)}
          </div>
        )}
        <input
          id={"pace-" + goal.goalId}
          className="dash-projector-slider"
          type="range"
          min={0}
          max={maxMonthly}
          step={step}
          value={chosen}
          onChange={(event) => setMonthly(Number(event.target.value))}
        />
        <div className="dash-projector-scale">
          <span>{UI.formatMoney(0, goal.currency)}</span>
          <span>{UI.formatMoney(maxMonthly, goal.currency)}</span>
        </div>

        <div className={"dash-projector-result" + (onTrack ? " is-on-track" : " is-behind")}>
          {chosen <= 0 ? (
            <span>{t("dashboard.analytics.goal.projector.nothing")}</span>
          ) : projectedIso ? (
            <span>
              {t("dashboard.analytics.goal.projector.reachOn", {
                date: GEMS.i18n.isoToDisplayDate(projectedIso),
                months: GEMS.i18n.countFor(months),
              })}
            </span>
          ) : (
            <span>{t("dashboard.analytics.goal.projector.tooSlow")}</span>
          )}
        </div>

        {required > 0 ? (
          <button
            type="button"
            className="dash-projector-hint"
            onClick={() => setMonthly(Math.min(maxMonthly, required))}
          >
            <span dangerouslySetInnerHTML={{ __html: t("dashboard.analytics.goal.projector.required", {
              amount: UI.formatMoney(required, goal.currency),
              date: GEMS.i18n.isoToDisplayDate(goal.targetDate),
            }) }} />
          </button>
        ) : null}
      </div>
    );
  }

  function GoalCard({ goal, accounts, onChanged }) {
    const [standingOrder, setStandingOrder] = useState(null);
    const [closeDialogOpen, setCloseDialogOpen] = useState(false);
    const [closing, setClosing] = useState(false);
    const [closeError, setCloseError] = useState(null);
    const [movementDialog, setMovementDialog] = useState(null);
    const [movementBusy, setMovementBusy] = useState(false);
    const [movementError, setMovementError] = useState(null);
    const [standingOrderDialogOpen, setStandingOrderDialogOpen] = useState(false);
    const [standingOrderBusy, setStandingOrderBusy] = useState(false);
    const [standingOrderError, setStandingOrderError] = useState(null);
    const [editAmountOpen, setEditAmountOpen] = useState(false);
    const [editAmountBusy, setEditAmountBusy] = useState(false);
    const [editAmountError, setEditAmountError] = useState(null);

    const goalId = goal.goalId;

    useEffect(() => {
      let cancelled = false;
      api
        .getStandingOrder(goalId)
        .then((result) => {
          if (!cancelled) setStandingOrder(result.standingOrder);
        })
        .catch(() => {
          if (!cancelled) setStandingOrder(null);
        });
      return () => {
        cancelled = true;
      };
    }, [goalId, goal.progressMinorUnits]);

    function submitMovement(amountMinor) {
      setMovementBusy(true);
      setMovementError(null);
      const call = movementDialog === "withdraw" ? api.withdrawFromGoal : api.depositToGoal;
      call(goalId, amountMinor)
        .then(() => {
          setMovementBusy(false);
          setMovementDialog(null);
          onChanged();
        })
        .catch((err) => {
          setMovementBusy(false);
          setMovementError(err);
        });
    }

    function submitStandingOrder(sourceAccountId, amountMinor, frequency) {
      setStandingOrderBusy(true);
      setStandingOrderError(null);
      api
        .createStandingOrder(goalId, sourceAccountId, amountMinor, frequency, "user")
        .then(() => {
          setStandingOrderBusy(false);
          setStandingOrderDialogOpen(false);
          onChanged();
        })
        .catch((err) => {
          setStandingOrderBusy(false);
          setStandingOrderError(err);
        });
    }

    function submitEditAmount(amountMinor) {
      if (!standingOrder) return;
      setEditAmountBusy(true);
      setEditAmountError(null);
      api
        .updateStandingOrderAmount(standingOrder.standingOrderId, amountMinor)
        .then(() => {
          setEditAmountBusy(false);
          setEditAmountOpen(false);
          setStandingOrder((prev) => prev && { ...prev, amount: { ...prev.amount, minorUnits: amountMinor } });
          onChanged();
        })
        .catch((err) => {
          setEditAmountBusy(false);
          setEditAmountError(err);
        });
    }

    function transitionStandingOrder(action) {
      if (!standingOrder) return;
      setStandingOrderBusy(true);
      setStandingOrderError(null);
      action(standingOrder.standingOrderId)
        .then(() => {
          setStandingOrderBusy(false);
          onChanged();
        })
        .catch((err) => {
          setStandingOrderBusy(false);
          setStandingOrderError(err);
        });
    }

    function closeGoal() {
      setClosing(true);
      setCloseError(null);
      api
        .closeGoal(goalId)
        .then(() => {
          setClosing(false);
          setCloseDialogOpen(false);
          onChanged();
        })
        .catch((err) => {
          setClosing(false);
          setCloseError(err);
        });
    }

    const reached = goal.progressMinorUnits >= goal.targetMinorUnits;
    const pct =
      goal.targetMinorUnits > 0
        ? Math.max(0, Math.min(100, (goal.progressMinorUnits / goal.targetMinorUnits) * 100))
        : 0;
    const streakWeeks = goal.streakWeeks || 0;

    return (
      <UI.Plate className="elev-sm dash-goal-card">
        <div className="dash-goal-card-head">
          <div>
            <div className="dash-goal-name">{goal.name}</div>
            <div className="text-muted" style={{ fontSize: 12 }}>
              {t("dashboard.analytics.goal.by", {
                date: GEMS.i18n.isoToDisplayDate(goal.targetDate),
              })}
            </div>
          </div>
          {streakWeeks > 0 ? (
            <span className="dash-streak-badge" title={t("dashboard.analytics.goal.streakHint")}>
              <UI.Icon name="Flame" size={14} />
              {t("dashboard.analytics.goal.streak", { count: streakWeeks })}
            </span>
          ) : null}
        </div>

        <div className="dash-goal-body">
          <div className="dash-goal-pane dash-goal-pane-ring">
            <GoalRing pct={pct}>
              <div className="dash-ring-pct">{formatGoalPct(pct)}%</div>
              <div className="dash-ring-amount">
                {UI.formatMoney(goal.progressMinorUnits, goal.currency)}
              </div>
              <div className="dash-ring-target">
                {t("dashboard.analytics.goal.ofTarget", {
                  target: UI.formatMoney(goal.targetMinorUnits, goal.currency),
                })}
              </div>
            </GoalRing>

            {reached ? (
              <div className="dash-goal-reached">
                <UI.Icon name="CircleCheck" size={16} />
                {t("dashboard.analytics.goal.reached")}
              </div>
            ) : (
              <div className="dash-goal-actions">
                <UI.Button type="button" variant="primary" onClick={() => setMovementDialog("deposit")}>
                  {t("dashboard.analytics.goal.addMoney")}
                </UI.Button>
                <UI.Button type="button" variant="secondary" onClick={() => setMovementDialog("withdraw")}>
                  {t("dashboard.analytics.goal.withdraw")}
                </UI.Button>
              </div>
            )}
          </div>

          {reached ? null : (
            <div className="dash-goal-pane">
              <GoalProjector goal={goal} />
            </div>
          )}

          <div className="dash-goal-pane dash-goal-so">
            <div className="text-muted" style={{ fontSize: 12, marginBottom: 6 }}>
              {t("dashboard.analytics.goal.standingOrder.title")}
            </div>
            {standingOrder ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
                  <span style={{ fontSize: 13 }}>
                    {t(
                      standingOrder.status === "paused"
                        ? "dashboard.analytics.goal.standingOrder.paused"
                        : "dashboard.analytics.goal.standingOrder.active",
                      {
                        amount: UI.formatMoney(
                          standingOrder.amount.minorUnits,
                          standingOrder.amount.currency
                        ),
                        frequency: t(
                          standingOrder.frequency === "weekly"
                            ? "dashboard.analytics.goal.standingOrder.frequencyWeekly"
                            : "dashboard.analytics.goal.standingOrder.frequencyMonthly"
                        ),
                        account: (() => {
                          const source = (accounts || []).find(
                            (account) => account.id === standingOrder.sourceAccountId
                          );
                          return source ? DASH.accountLabel(source) : t("dashboard.cards.accountUnknown");
                        })(),
                        date: GEMS.i18n.isoToDisplayDate((standingOrder.nextRunAt || "").slice(0, 10)),
                      }
                    )}
                  </span>
                  <button
                    type="button"
                    className="dash-copy-btn"
                    aria-label={t("dashboard.analytics.goal.standingOrder.edit")}
                    onClick={() => setEditAmountOpen(true)}
                    style={{ flex: "none" }}
                  >
                    <UI.Icon name="Pencil" size={14} />
                  </button>
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  {standingOrder.status === "active" ? (
                    <UI.Button
                      type="button"
                      variant="secondary"
                      disabled={standingOrderBusy}
                      onClick={() => transitionStandingOrder(api.pauseStandingOrder)}
                    >
                      {standingOrderBusy
                        ? t("dashboard.analytics.goal.standingOrder.working")
                        : t("dashboard.analytics.goal.standingOrder.pause")}
                    </UI.Button>
                  ) : (
                    <UI.Button
                      type="button"
                      variant="secondary"
                      disabled={standingOrderBusy}
                      onClick={() => transitionStandingOrder(api.resumeStandingOrder)}
                    >
                      {standingOrderBusy
                        ? t("dashboard.analytics.goal.standingOrder.working")
                        : t("dashboard.analytics.goal.standingOrder.resume")}
                    </UI.Button>
                  )}
                  <button
                    type="button"
                    className="dash-handoff-link"
                    style={{ padding: 0 }}
                    disabled={standingOrderBusy}
                    onClick={() => transitionStandingOrder(api.cancelStandingOrder)}
                  >
                    {t("dashboard.analytics.goal.standingOrder.cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, alignItems: "flex-start" }}>
                <span className="text-muted" style={{ fontSize: 12 }}>
                  {t("dashboard.analytics.goal.standingOrder.none")}
                </span>
                <UI.Button
                  type="button"
                  variant="secondary"
                  onClick={() => setStandingOrderDialogOpen(true)}
                >
                  {t("dashboard.analytics.goal.standingOrder.set")}
                </UI.Button>
              </div>
            )}
            {standingOrderError ? (
              <p className="dash-proposal-note">{t("dashboard.analytics.goal.standingOrder.error")}</p>
            ) : null}
          </div>
        </div>

        <div className="dash-goal-foot">
          {streakWeeks === 0 && !reached ? (
            <p className="text-muted" style={{ fontSize: 12, margin: 0 }}>
              {t("dashboard.analytics.goal.streakStart")}
            </p>
          ) : null}

          {goal.sharedParentAccount ? (
            <p className="dash-proposal-note">{t("dashboard.analytics.goal.legacyAccountNote")}</p>
          ) : null}

          <button
            type="button"
            className="dash-handoff-link dash-goal-close"
            onClick={() => setCloseDialogOpen(true)}
          >
            {t("dashboard.analytics.goal.closeGoal")}
          </button>
        </div>

        {closeDialogOpen ? (
          <CloseGoalDialog
            name={goal.name}
            busy={closing}
            error={closeError}
            onConfirm={closeGoal}
            onDismiss={() => {
              setCloseDialogOpen(false);
              setCloseError(null);
            }}
          />
        ) : null}
        {movementDialog ? (
          <GoalMovementDialog
            mode={movementDialog}
            goalName={goal.name}
            progressPct={pct}
            busy={movementBusy}
            error={movementError}
            onSubmit={submitMovement}
            onDismiss={() => {
              setMovementDialog(null);
              setMovementError(null);
            }}
          />
        ) : null}
        {standingOrderDialogOpen ? (
          <StandingOrderDialog
            accounts={accounts}
            goalCurrency={goal.currency}
            busy={standingOrderBusy}
            error={standingOrderError}
            onSubmit={submitStandingOrder}
            onDismiss={() => {
              setStandingOrderDialogOpen(false);
              setStandingOrderError(null);
            }}
          />
        ) : null}
        {editAmountOpen && standingOrder ? (
          <EditStandingOrderAmountDialog
            currentAmountMinor={standingOrder.amount.minorUnits}
            busy={editAmountBusy}
            error={editAmountError}
            onSubmit={submitEditAmount}
            onDismiss={() => {
              setEditAmountOpen(false);
              setEditAmountError(null);
            }}
          />
        ) : null}
      </UI.Plate>
    );
  }

  function LessonsPanel() {
    const [state, setState] = useState({ loading: true, lessons: [], error: null });
    const [quizLesson, setQuizLesson] = useState(null);
    const [openLessonId, setOpenLessonId] = useState(null);

    useEffect(() => {
      let cancelled = false;
      api
        .getEducationLessons()
        .then((result) => {
          if (cancelled) return;
          setState({ loading: false, lessons: result.lessons || [], error: null });
        })
        .catch((err) => {
          if (!cancelled) setState({ loading: false, lessons: [], error: err });
        });
      return () => {
        cancelled = true;
      };
    }, []);

    const ro = GEMS.i18n.locale === "ro";

    return (
      <EduSection
        title={t("dashboard.education.lessons.title")}
        hint={t("dashboard.education.lessons.subtitle")}
      >
        {state.loading ? (
          <UI.Plate className="elev-sm dash-goals-loading">
            {t("dashboard.analytics.loading")}
          </UI.Plate>
        ) : state.error || !state.lessons.length ? (
          <UI.Plate className="elev-sm dash-goals-loading">
            {t("dashboard.education.lessons.error")}
          </UI.Plate>
        ) : (
          <UI.Plate className="elev-sm dash-lesson-list">
            {state.lessons.map((lesson) => {
              const open = openLessonId === lesson.id;
              return (
                <div className={"dash-lesson-item" + (open ? " is-open" : "")} key={lesson.id}>
                  <button
                    type="button"
                    className="dash-lesson-toggle"
                    aria-expanded={open}
                    aria-controls={"lesson-panel-" + lesson.id}
                    onClick={() => setOpenLessonId(open ? null : lesson.id)}
                  >
                    <span className="dash-lesson-title">{ro ? lesson.titleRo : lesson.titleEn}</span>
                    <span className="dash-lesson-meta">
                      <span className="text-muted" style={{ fontSize: 12 }}>
                        {t("dashboard.education.quiz.questionCount", {
                          count: lesson.questions.length,
                        })}
                      </span>
                      <UI.Icon className="dash-lesson-chevron" name="ChevronDown" size={16} />
                    </span>
                  </button>
                  {open ? (
                    <div className="dash-lesson-panel" id={"lesson-panel-" + lesson.id}>
                      <p className="dash-lesson-body">{ro ? lesson.bodyRo : lesson.bodyEn}</p>
                      <UI.Button
                        type="button"
                        variant="secondary"
                        onClick={() => setQuizLesson(lesson)}
                      >
                        {t("dashboard.education.quiz.start")}
                      </UI.Button>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </UI.Plate>
        )}

        {quizLesson ? (
          <QuizDialog lesson={quizLesson} ro={ro} onDismiss={() => setQuizLesson(null)} />
        ) : null}
      </EduSection>
    );
  }

  function QuizDialog({ lesson, ro, onDismiss }) {
    const [answers, setAnswers] = useState({});
    const [submitted, setSubmitted] = useState(false);

    const questions = lesson.questions;
    const answeredCount = questions.filter((question) => answers[question.id]).length;
    const score = questions.filter(
      (question) => answers[question.id] === question.correctOptionId
    ).length;
    const title = ro ? lesson.titleRo : lesson.titleEn;

    function restart() {
      setAnswers({});
      setSubmitted(false);
    }

    return (
      <UI.Dialog labelledBy="quiz-dialog-title" onDismiss={onDismiss}>
        <div className="dash-quiz-dialog">
          <h2 id="quiz-dialog-title" className="dialog-title">
            {title}
          </h2>
          <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>
            {submitted
              ? t("dashboard.education.quiz.resultsSubtitle")
              : t("dashboard.education.quiz.subtitle", { count: questions.length })}
          </p>

          {submitted ? (
            <div
              className={
                "dash-quiz-score" +
                (score === questions.length ? " is-perfect" : score * 2 >= questions.length ? " is-ok" : " is-low")
              }
            >
              <div className="dash-quiz-score-value">
                {score} / {questions.length}
              </div>
              <div className="dash-quiz-score-label">
                {score === questions.length
                  ? t("dashboard.education.quiz.scorePerfect")
                  : t("dashboard.education.quiz.scoreLabel")}
              </div>
            </div>
          ) : (
            <div className="dash-quiz-progress">
              {t("dashboard.education.quiz.answered", {
                answered: answeredCount,
                total: questions.length,
              })}
            </div>
          )}

          <div className="dash-quiz-list">
            {questions.map((question, index) => {
              const chosen = answers[question.id];
              const gotItRight = chosen === question.correctOptionId;
              return (
                <div className="dash-quiz-question" key={question.id}>
                  <div className="dash-quiz-prompt">
                    <span className="dash-quiz-number">{index + 1}</span>
                    {ro ? question.promptRo : question.promptEn}
                  </div>
                  <div className="dash-quiz-options">
                    {question.options.map((option) => {
                      const selected = chosen === option.id;
                      const isCorrect = option.id === question.correctOptionId;
                      let tone = "";
                      if (submitted && isCorrect) tone = " is-correct";
                      else if (submitted && selected) tone = " is-wrong";
                      else if (selected) tone = " is-selected";
                      return (
                        <label className={"dash-quiz-option" + tone} key={option.id}>
                          <input
                            type="radio"
                            name={question.id}
                            checked={selected || false}
                            disabled={submitted}
                            onChange={() =>
                              setAnswers((current) => ({ ...current, [question.id]: option.id }))
                            }
                          />
                          <span>{ro ? option.labelRo : option.labelEn}</span>
                          {submitted && isCorrect ? (
                            <span className="dash-quiz-tag">
                              {t("dashboard.education.quiz.correctAnswer")}
                            </span>
                          ) : null}
                        </label>
                      );
                    })}
                  </div>
                  {submitted ? (
                    <p className="dash-quiz-explanation">
                      <strong>
                        {gotItRight
                          ? t("dashboard.education.quiz.correct")
                          : t("dashboard.education.quiz.incorrect")}
                      </strong>{" "}
                      {ro ? question.explanationRo : question.explanationEn}
                    </p>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="dialog-actions">
            {submitted ? (
              <React.Fragment>
                <UI.Button type="button" variant="secondary" onClick={restart}>
                  {t("dashboard.education.quiz.retry")}
                </UI.Button>
                <UI.Button type="button" variant="primary" onClick={onDismiss}>
                  {t("dashboard.education.quiz.done")}
                </UI.Button>
              </React.Fragment>
            ) : (
              <React.Fragment>
                <UI.Button type="button" variant="secondary" onClick={onDismiss}>
                  {t("dashboard.education.quiz.cancel")}
                </UI.Button>
                <UI.Button
                  type="button"
                  variant="primary"
                  disabled={answeredCount < questions.length}
                  onClick={() => setSubmitted(true)}
                >
                  {t("dashboard.education.quiz.submit")}
                </UI.Button>
              </React.Fragment>
            )}
          </div>
        </div>
      </UI.Dialog>
    );
  }

  SCR.AnalyticsScreen = function AnalyticsScreen({ range, onRange, accounts }) {
    const RC = window.Recharts;
    const months = range === "3" ? 3 : range === "12" ? 12 : 6;
    const periods = [
      { value: "3", label: t("dashboard.analytics.period3") },
      { value: "6", label: t("dashboard.analytics.period6") },
      { value: "12", label: t("dashboard.analytics.period12") },
    ];
    const { loading, error, currency, buckets, categories, hasActivity } = useAnalyticsData(months, accounts);

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
                  <RC.Bar dataKey="spend" name="spend" fill="var(--color-plum-400)" radius={[6, 6, 0, 0]} />
                </RC.BarChart>
              </RC.ResponsiveContainer>
            )}
          </UI.Plate>
        </div>

        <UI.Plate className="elev-sm" style={{ padding: 18, marginTop: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
             <UI.Icon name="Sparkles" size={16} color="var(--color-primary)" />
             <UI.Kicker style={{ margin: 0 }}>Sinteză inteligentă</UI.Kicker>
          </div>
          <AnalyticsInsights range={range} />
        </UI.Plate>

        <UI.ErrorNote error={error} />
      </div>
    );
  };

  const analyticsInsightsCache = {};

  function AnalyticsInsights({ range }) {
    const [insights, setInsights] = useState(analyticsInsightsCache[range] || null);
    const [loading, setLoading] = useState(!analyticsInsightsCache[range]);
    
    useEffect(() => {
      if (analyticsInsightsCache[range]) {
        setInsights(analyticsInsightsCache[range]);
        setLoading(false);
        return;
      }
      
      let cancelled = false;
      setLoading(true);
      setInsights(null);
      
      const prompt = `Analizeaza datele financiare reale ale utilizatorului pe ultimele ${range} luni (folosind tool-urile tale). Ofera-i fix 3 observatii personalizate si actionabile legate de sumele si categoriile lui de cheltuieli (de ex: "In ultima perioada ai cheltuit ... pe X. Ai putea sa mai reduci..."). NU oferi sfaturi generice, ci strict observatii aplicate pe cheltuielile lui. Fiecare observatie sa fie un bullet point scurt. Nu folosi nicio introducere.`;
      
      api.askAnalytics(prompt)
        .then(res => {
          if (!cancelled) {
             const answer = res.answer.split('\n').filter(l => l.trim().length > 0);
             analyticsInsightsCache[range] = answer;
             setInsights(answer);
          }
        })
        .catch(err => {
          if (!cancelled) {
             setInsights(["Nu am putut genera interpretarea."]);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
      return () => { cancelled = true; };
    }, [range]);

    if (loading) {
       return <div className="dash-chart-empty">{t("dashboard.analytics.loading")}</div>;
    }
    if (!insights || insights.length === 0) return null;
    return (
      <ul className="dash-msg-list">
        {insights.map((line, i) => {
          const cleanLine = line.replace(/^[\s*-]+/, '').trim();
          return (
            <li key={i}>
              {renderInlineText(cleanLine, i)}
            </li>
          );
        })}
      </ul>
    );
  }

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
          <UI.Field id="pin-new" label={t("dashboard.settings.pinDialog.newPin")}>
            <UI.TextInput id="pin-new" inputMode="numeric" autoFocus value={newPin} onChange={(event) => setNewPin(event.target.value)} />
          </UI.Field>
          <UI.Field id="pin-confirm" label={t("dashboard.settings.pinDialog.confirmPin")} error={error ? error.message : null}>
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

  function PasswordChangeDialog({ busy, error, onSubmit, onDismiss }) {
    const [newPassword, setNewPassword] = useState("");
    const [confirmation, setConfirmation] = useState("");
    return (
      <UI.Dialog labelledBy="password-change-title" onDismiss={onDismiss}>
        <h2 id="password-change-title" className="dialog-title">{t("dashboard.settings.passwordDialog.title")}</h2>
        <form noValidate onSubmit={(event) => { event.preventDefault(); onSubmit(newPassword, confirmation); }}>
          <UI.Field id="password-new" label={t("dashboard.settings.passwordDialog.newPassword")}>
            <UI.TextInput
              id="password-new"
              type="password"
              autoComplete="new-password"
              autoFocus
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </UI.Field>
          <UI.Field id="password-confirm" label={t("dashboard.settings.passwordDialog.confirmPassword")} error={error ? error.message : null}>
            <UI.TextInput
              id="password-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </UI.Field>
          <div className="dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onDismiss}>{t("dashboard.settings.pinDialog.cancel")}</UI.Button>
            <UI.Button type="submit" variant="primary" disabled={busy}>{t("dashboard.settings.passwordDialog.submit")}</UI.Button>
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

  SCR.SettingsScreen = function SettingsScreen({ lang, onLang, theme, onTheme, ttsOn, onToggleTts, onSignOut, me, onMeChange }) {
    const langs = [
      { value: "ro", label: "Română" },
      { value: "en", label: "English" },
    ];
    const identity = (me && me.identity) || null;
    const placeholder = "—";

    const [usernameDraft, setUsernameDraft] = useState("");
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

    const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
    const [passwordBusy, setPasswordBusy] = useState(false);
    const [passwordError, setPasswordError] = useState(null);
    const [passwordCase, setPasswordCase] = useState(null);
    const [passwordOtpBusy, setPasswordOtpBusy] = useState(false);
    const [passwordOtpError, setPasswordOtpError] = useState(null);
    const [passwordNotice, setPasswordNotice] = useState(null);

    const [sessionsOpen, setSessionsOpen] = useState(false);
    const [closeAccountOpen, setCloseAccountOpen] = useState(false);
    const [contactDialogOpen, setContactDialogOpen] = useState(false);

    useEffect(() => {
      if (me) {
        setUsernameDraft(me.username || "");
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
      const request =
        current.kind === "username"
          ? api.requestUsernameChange(current.value)
          : current.kind === "email"
            ? api.requestEmailChange(current.value)
            : api.requestPhoneChange(current.value);
      request
        .then((response) => {
          if (response.recoveryCaseId) {
            setActiveCase({ kind: current.kind, caseId: response.recoveryCaseId, delivery: response.delivery, rest });
          } else {
            // Immediate success without OTP (e.g. if backend is updated to skip OTP)
            onMeChange((prev) => ({
              ...(prev || {}),
              userId: response.userId,
              username: response.username,
              email: response.email,
              phone: response.phone,
            }));
            if (rest.length > 0) {
              runNextChange(rest);
            } else {
              setSavingContact(false);
              setContactNotice(t({
                username: "dashboard.settings.otp.successUsername",
                email: "dashboard.settings.otp.successEmail",
                phone: "dashboard.settings.otp.successPhone",
              }[current.kind] || "dashboard.settings.otp.successEmail"));
            }
          }
        })
        .catch((err) => {
          setContactError(err);
          setSavingContact(false);
        });
    }

    const [verifyPinOpen, setVerifyPinOpen] = useState(false);
    const [verifyPinBusy, setVerifyPinBusy] = useState(false);
    const [verifyPinError, setVerifyPinError] = useState(null);

    function saveContact() {
      if (!me) return;
      const changes = [];
      const nextUsername = usernameDraft.trim().toLowerCase();
      const nextEmail = emailDraft.trim();
      const nextPhone = phoneDraft.trim();
      if (nextUsername && nextUsername !== me.username) changes.push({ kind: "username", value: nextUsername });
      if (nextEmail && nextEmail !== me.email) changes.push({ kind: "email", value: nextEmail });
      if (nextPhone && nextPhone !== me.phone) changes.push({ kind: "phone", value: nextPhone });
      if (!changes.length) return;
      
      setVerifyPinOpen(true);
      setVerifyPinError(null);
    }

    async function submitVerifyPin(pin) {
      setVerifyPinBusy(true);
      setVerifyPinError(null);
      try {
        await api.verifyPin(me.username, pin);
        setVerifyPinOpen(false);
        
        const changes = [];
        const nextUsername = usernameDraft.trim().toLowerCase();
        const nextEmail = emailDraft.trim();
        const nextPhone = phoneDraft.trim();
        if (nextUsername && nextUsername !== me.username) changes.push({ kind: "username", value: nextUsername });
        if (nextEmail && nextEmail !== me.email) changes.push({ kind: "email", value: nextEmail });
        if (nextPhone && nextPhone !== me.phone) changes.push({ kind: "phone", value: nextPhone });
        
        if (!changes.length) return;
        setContactError(null);
        setContactNotice(null);
        setSavingContact(true);
        runNextChange(changes);
      } catch (err) {
        setVerifyPinError(err);
      } finally {
        setVerifyPinBusy(false);
      }
    }

    function submitContactOtp(code) {
      if (!activeCase) return;
      setOtpBusy(true);
      setOtpError(null);
      api
        .verifySecureChange(activeCase.caseId, code)
        .then((response) => {
          onMeChange((prev) => ({
            ...(prev || {}),
            userId: response.userId,
            username: response.username,
            email: response.email,
            phone: response.phone,
            fullName: response.fullName,
            identity: response.identity !== undefined ? response.identity : (prev && prev.identity),
          }));
          setUsernameDraft(response.username || "");
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
            setContactNotice(
              t(
                {
                  username: "dashboard.settings.otp.successUsername",
                  email: "dashboard.settings.otp.successEmail",
                  phone: "dashboard.settings.otp.successPhone",
                }[kind] || "dashboard.settings.otp.successEmail"
              )
            );
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

    function submitNewPassword(newPassword, confirmation) {
      setPasswordBusy(true);
      setPasswordError(null);
      api
        .requestPasswordChange(newPassword, confirmation)
        .then((response) => {
          setPasswordDialogOpen(false);
          setPasswordCase({ caseId: response.recoveryCaseId, delivery: response.delivery });
        })
        .catch((err) => setPasswordError(err))
        .finally(() => setPasswordBusy(false));
    }

    function submitPasswordOtp(code) {
      if (!passwordCase) return;
      setPasswordOtpBusy(true);
      setPasswordOtpError(null);
      api
        .verifySecureChange(passwordCase.caseId, code)
        .then(() => {
          setPasswordCase(null);
          setPasswordOtpBusy(false);
          setPasswordNotice(t("dashboard.settings.otp.successPassword"));
        })
        .catch((err) => {
          setPasswordOtpError(err);
          setPasswordOtpBusy(false);
        });
    }

    return (
      <div>
        <h3 style={{ margin: "0 0 18px" }}>{t("dashboard.nav.settings")}</h3>
        <div className="dash-settings-grid">
          <UI.Plate className="elev-sm" style={{ padding: 18 }}>
            <UI.Kicker style={{ marginBottom: 14 }}>{t("dashboard.settings.personalDetails")}</UI.Kicker>
            <div className="dash-field-grid">
              <div style={{ gridColumn: "1 / -1" }}>
                <UI.Field id="set-username" label={t("dashboard.settings.username")}>
                  <UI.TextInput
                    id="set-username"
                    value={usernameDraft}
                    onChange={(event) => setUsernameDraft(event.target.value)}
                    disabled={!me}
                    autoComplete="username"
                    spellCheck={false}
                  />
                </UI.Field>
              </div>
              <UI.Field id="set-name" label={t("dashboard.settings.fullName")}>
                <UI.TextInput
                  id="set-name"
                  readOnly
                  disabled={true}
                  value={identity ? GEMS.people.fullName(identity.fullName) : (me ? me.fullName : placeholder)}
                />
              </UI.Field>
              <UI.Field id="set-birth" label={t("dashboard.settings.birthDate")}>
                <UI.TextInput
                  id="set-birth"
                  readOnly
                  disabled={true}
                  value={identity ? GEMS.i18n.isoToDisplayDate(identity.birthDate) : placeholder}
                />
              </UI.Field>
              <UI.Field id="set-phone" label={t("dashboard.settings.phone")}>
                <UI.TextInput id="set-phone" value={phoneDraft} onChange={(event) => setPhoneDraft(event.target.value)} disabled={!me} />
              </UI.Field>
              <UI.Field id="set-email" label={t("dashboard.settings.email")}>
                <UI.TextInput id="set-email" value={emailDraft} onChange={(event) => setEmailDraft(event.target.value)} disabled={!me} />
              </UI.Field>
            </div>
            
            <div className="text-muted" style={{ fontSize: 12, marginTop: 14, marginBottom: 14 }}>
              {identity
                ? t("dashboard.settings.identityNote", {
                    expiry: GEMS.i18n.isoToDisplayDate(identity.documentExpiresOn),
                  })
                : t("dashboard.settings.identityMissing")}
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
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="Lock" size={15} />{t("dashboard.settings.changePassword")}</span><UI.Button type="button" variant="secondary" onClick={() => { setPasswordError(null); setPasswordDialogOpen(true); }}>{t("dashboard.settings.update")}</UI.Button></div>
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="ShieldCheck" size={15} />{t("dashboard.settings.twoFactor")}</span><UI.Tag variant="accent">{t("dashboard.settings.authenticator")}</UI.Tag></div>
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="Fingerprint" size={15} />{t("dashboard.settings.passkeys")}</span><UI.Tag variant="accent">{t("dashboard.settings.passkeysCount")}</UI.Tag></div>
              <div className="dash-settings-row"><span className="dash-settings-label"><UI.Icon name="Smartphone" size={15} />{t("dashboard.settings.sessions")}</span><UI.Button type="button" variant="secondary" onClick={() => setSessionsOpen(true)}>{t("dashboard.settings.review")}</UI.Button></div>
            </div>
            {pinNotice ? <p className="text-muted" style={{ fontSize: 12, marginTop: 10 }}>{pinNotice}</p> : null}
            {passwordNotice ? <p className="text-muted" style={{ fontSize: 12, marginTop: 10 }}>{passwordNotice}</p> : null}
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
              <UI.Button
                type="button"
                variant="secondary"
                style={{ justifyContent: "flex-start", gap: 8 }}
                onClick={() => window.open("./agent-instructions.html", "_blank", "noopener,noreferrer")}
              >
                <UI.Icon name="Bot" size={15} />
                {t("dashboard.settings.agentInstructions")}
              </UI.Button>
              <div className="hr" style={{ margin: "4px 0" }} />
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8 }} onClick={onSignOut}><UI.Icon name="LogOut" size={15} />{t("dashboard.signOut")}</UI.Button>
              <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8, color: "var(--color-negative)" }} onClick={() => setCloseAccountOpen(true)}><UI.Icon name="TriangleAlert" size={15} />{t("dashboard.settings.closeAccount")}</UI.Button>
            </div>
          </UI.Plate>
        </div>

        {activeCase ? (
          <OtpDialog
            titleId="contact-otp-title"
            busy={otpBusy}
            error={otpError}
            delivery={activeCase.delivery}
            onDismiss={() => {
              setActiveCase(null);
              setSavingContact(false);
            }}
            onSubmit={submitContactOtp}
          />
        ) : null}

        {verifyPinOpen ? (
          <CardPinDialog
            busy={verifyPinBusy}
            error={verifyPinError}
            onSubmit={submitVerifyPin}
            onDismiss={() => {
              setVerifyPinOpen(false);
              setSavingContact(false);
            }}
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

        {passwordDialogOpen ? (
          <PasswordChangeDialog
            busy={passwordBusy}
            error={passwordError}
            onSubmit={submitNewPassword}
            onDismiss={() => setPasswordDialogOpen(false)}
          />
        ) : null}

        {passwordCase ? (
          <OtpDialog
            titleId="password-otp-title"
            delivery={passwordCase.delivery}
            busy={passwordOtpBusy}
            error={passwordOtpError}
            onSubmit={submitPasswordOtp}
            onDismiss={() => setPasswordCase(null)}
          />
        ) : null}

        {sessionsOpen ? <SessionsDialog onDismiss={() => setSessionsOpen(false)} /> : null}
        {closeAccountOpen ? <CloseAccountDialog onDismiss={() => setCloseAccountOpen(false)} /> : null}
        {contactDialogOpen ? <ContactDialog onDismiss={() => setContactDialogOpen(false)} /> : null}
      </div>
    );
  };

  SCR.ChatScreen = function ChatScreen({ messages, busy, draft, onDraftChange, onSend, onKeyDown, micOn, micBusy, micError, onToggleMic, onPromptClick, prompts, onConfirmTx, onConfirmProposal, username, ttsOn, onToggleTts, playingMessageIndex, ttsBusyIndex, onSpeakMessage, onStopSpeaking, onClearChat }) {
    const inputRef = useRef(null);
    const scrollRef = useRef(null);

    useEffect(() => {
      if (busy || !inputRef.current) return;
      const active = document.activeElement;
      if (active && active !== document.body && active !== inputRef.current) return;
      inputRef.current.focus();
    }, [busy]);

    useEffect(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    }, [messages, busy]);


    return (
      <div className="dash-chat-layout">
        <div className="dash-chat-col">
          <div className="dash-chat-header-actions">
            <UI.Button
              type="button"
              variant="secondary"
              disabled={busy || messages.length <= 1}
              onClick={onClearChat}
              style={{ fontSize: 12, padding: "4px 8px", gap: 6, marginRight: "auto" }}
              title={t("dashboard.chat.clear")}
            >
              <UI.Icon name="Trash2" size={14} />
              <span>{t("dashboard.chat.clear")}</span>
            </UI.Button>

            {(playingMessageIndex !== null || ttsBusyIndex !== null) ? (
              <UI.Button
                type="button"
                variant="secondary"
                onClick={onStopSpeaking}
                style={{ fontSize: 12, padding: "4px 10px", gap: 6, borderColor: "var(--color-negative)", color: "var(--color-negative)" }}
                title={t("dashboard.chat.stopSpeak")}
              >
                <UI.Icon name="Square" size={12} />
                <span>{t("dashboard.chat.stopSpeak")}</span>
              </UI.Button>
            ) : null}

            <UI.Button
              type="button"
              variant="secondary"
              className={ttsOn ? "dash-mic-live" : null}
              aria-pressed={ttsOn}
              onClick={() => {
                if (playingMessageIndex !== null || ttsBusyIndex !== null) {
                  onStopSpeaking && onStopSpeaking();
                }
                onToggleTts && onToggleTts();
              }}
              style={{ fontSize: 12, padding: "4px 8px", gap: 6 }}
              title={ttsOn ? t("dashboard.chat.ttsOn") : t("dashboard.chat.ttsOff")}
            >
              <UI.Icon name={ttsOn ? "Volume2" : "VolumeX"} size={14} />
              <span>{ttsOn ? t("dashboard.chat.ttsOn") : t("dashboard.chat.ttsOff")}</span>
            </UI.Button>
          </div>

          <div className="dash-chat-scroll" ref={scrollRef}>
            {messages.map((message, index) => (
              <div className="dash-msg" key={index}>
                {message.role === "user" ? (
                  <div className="dash-msg-user">{message.text}</div>
                ) : (
                  <div className="dash-msg-ai">
                    <span className="dash-msg-ai-dot" aria-hidden="true" />
                    <div className="dash-msg-ai-body">
                      {message.text ? renderStructuredText(message.text) : null}

                      {message.text ? (
                        <div className="dash-msg-actions">
                          <button
                            type="button"
                            className={UI.classNames(
                              "dash-msg-speak-btn",
                              (playingMessageIndex === index || ttsBusyIndex === index) && "is-speaking"
                            )}
                            onClick={() => {
                              if (playingMessageIndex === index || ttsBusyIndex === index) {
                                onStopSpeaking && onStopSpeaking();
                              } else {
                                onSpeakMessage && onSpeakMessage(message.text, index);
                              }
                            }}
                            title={
                              (playingMessageIndex === index || ttsBusyIndex === index)
                                ? t("dashboard.chat.stopSpeak")
                                : t("dashboard.chat.speak")
                            }
                            aria-label={
                              (playingMessageIndex === index || ttsBusyIndex === index)
                                ? t("dashboard.chat.stopSpeak")
                                : t("dashboard.chat.speak")
                            }
                          >
                            <UI.Icon
                              name={
                                (playingMessageIndex === index || ttsBusyIndex === index)
                                  ? "Square"
                                  : "Volume2"
                              }
                              size={12}
                            />
                            <span>
                              {(playingMessageIndex === index || ttsBusyIndex === index)
                                ? t("dashboard.chat.stopSpeak")
                                : t("dashboard.chat.speak")}
                            </span>
                          </button>
                        </div>
                      ) : null}

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

                      {message.kind === "proposal" && message.proposal && message.proposal.action ? (
                        <UI.Plate className="dash-tx-card">
                          <UI.Kicker style={{ marginBottom: 4 }}>{t("dashboard.chat.cardProposalTitle")}</UI.Kicker>
                          <div className="dash-tx-grid">
                            <span className="text-muted">{t("dashboard.chat.cardProposalAction")}</span>
                            <span>{t("dashboard.chat.cardAction." + message.proposal.action)}</span>
                            {message.proposal.cardLabel ? (
                              <React.Fragment>
                                <span className="text-muted">{t("dashboard.chat.cardProposalCard")}</span>
                                <span>{message.proposal.cardLabel}</span>
                              </React.Fragment>
                            ) : null}
                            {message.proposal.limitFormatted ? (
                              <React.Fragment>
                                <span className="text-muted">{t("dashboard.chat.cardProposalLimit")}</span>
                                <span>{message.proposal.limitFormatted}</span>
                              </React.Fragment>
                            ) : null}
                          </div>
                          <p className="dash-proposal-note">
                            {message.proposal.irreversible
                              ? t("dashboard.chat.cardProposalIrreversible")
                              : message.proposal.revealsSecret
                                ? t("dashboard.chat.cardProposalSecret")
                                : t("dashboard.chat.cardProposalNotDone")}
                          </p>
                          <div style={{ display: "flex", gap: 8 }}>
                            <UI.Button
                              type="button"
                              variant={message.proposal.irreversible ? "secondary" : "primary"}
                              style={{ flex: 1 }}
                              onClick={() => onConfirmProposal && onConfirmProposal(message.proposal)}
                            >
                              {message.proposal.irreversible
                                ? t("dashboard.chat.cardProposalConfirmBlock")
                                : t("dashboard.chat.cardProposalConfirm")}
                            </UI.Button>
                          </div>
                        </UI.Plate>
                      ) : null}

                      {message.kind === "proposal" && message.proposal && !message.proposal.action ? (
                        <UI.Plate className="dash-tx-card">
                          <UI.Kicker style={{ marginBottom: 4 }}>{t("dashboard.chat.proposalTitle")}</UI.Kicker>
                          <div className="dash-tx-amount">
                            {DASH.formatMinor(message.proposal.amountMinorUnits)} {message.proposal.currency}
                          </div>
                          <div className="dash-tx-grid">
                            <span className="text-muted">{t("dashboard.chat.txTo")}</span>
                            <span>{message.proposal.counterparty}</span>
                            <span className="text-muted">{t("dashboard.chat.txIban")}</span>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                              {message.proposal.targetIbanMasked || message.proposal.targetIban}
                            </span>
                            <span className="text-muted">{t("dashboard.chat.txFrom")}</span>
                            <span>{message.proposal.sourceLabel} · {message.proposal.sourceIbanMasked}</span>
                            <span className="text-muted">{t("dashboard.chat.proposalReference")}</span>
                            <span>{message.proposal.reference}</span>
                            <span className="text-muted">{t("dashboard.chat.proposalBalanceAfter")}</span>
                            <span>
                              {DASH.formatMinor(message.proposal.balanceAfterMinorUnits)} {message.proposal.currency}
                            </span>
                          </div>
                          <p className="dash-proposal-note">
                            {message.proposal.requiresSignature
                              ? t("dashboard.chat.proposalNeedsSignature")
                              : t("dashboard.chat.proposalNotSent")}
                          </p>
                          <div style={{ display: "flex", gap: 8 }}>
                            <UI.Button
                              type="button"
                              variant="primary"
                              style={{ flex: 1 }}
                              onClick={() => onConfirmProposal && onConfirmProposal(message.proposal)}
                            >
                              {t("dashboard.chat.proposalReview")}
                            </UI.Button>
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

                      {message.aiGenerated ? (
                        <div className="dash-ai-disclaimer">
                          <UI.Icon name="Sparkles" size={13} />
                          {t("dashboard.chat.aiDisclaimer")}
                        </div>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {busy ? (
              <div className="dash-msg">
                <div className="dash-msg-ai">
                  <span className="dash-msg-ai-dot" aria-hidden="true" />
                  <div className="dash-msg-ai-body text-muted">{t("dashboard.chat.thinking")}</div>
                </div>
              </div>
            ) : null}
          </div>

          <div style={{ paddingTop: 16 }}>
            <div className="dash-prompts-row">
              {(prompts || []).map((prompt) => (
                <UI.Button key={prompt.key} type="button" variant="secondary" disabled={busy} onClick={() => onPromptClick(prompt.label)}>{prompt.label}</UI.Button>
              ))}
            </div>
            <UI.Plate className="dash-chat-input-row">
              <input
                ref={inputRef}
                className="dash-chat-input"
                value={draft}
                onChange={onDraftChange}
                onKeyDown={onKeyDown}
                placeholder={t("dashboard.chat.inputPlaceholder")}
                aria-label={t("dashboard.chat.inputPlaceholder")}
              />
              <UI.Button
                type="button"
                variant="secondary"
                className={micOn ? "dash-mic-live" : null}
                aria-pressed={micOn}
                disabled={busy || micBusy}
                onClick={onToggleMic}
              >
                {micBusy ? t("dashboard.chat.micBusy") : micOn ? t("dashboard.chat.micOn") : t("dashboard.chat.micOff")}
              </UI.Button>
              <UI.Button type="button" variant="primary" disabled={busy || micOn} onClick={onSend}>{t("dashboard.chat.send")}</UI.Button>
            </UI.Plate>
            {micOn || micBusy || micError ? (
              <div className="dash-mic-status" role="status">
                {micOn ? <span className="dash-mic-dot" aria-hidden="true" /> : null}
                <span>
                  {micOn
                    ? t("dashboard.chat.micRecording")
                    : micBusy
                      ? t("dashboard.chat.micBusy")
                      : micError}
                </span>
              </div>
            ) : null}
            <div className="dash-chat-hint">
              <span>{t("dashboard.chat.orchestratorNote")}</span>
            </div>
          </div>
        </div>
      </div>
    );
  };
})();
