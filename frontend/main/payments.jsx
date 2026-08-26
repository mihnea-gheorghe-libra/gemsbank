(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const PAY = (GEMS.payments = GEMS.payments || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const api = GEMS.api;
  const { useState, useEffect, useCallback, useRef } = React;

  PAY.PaymentsPage = function PaymentsPage({ username, onSignOut }) {
    const [accounts, setAccounts] = useState([]);
    const [summary, setSummary] = useState(null);
    const [pending, setPending] = useState([]);
    const [beneficiaries, setBeneficiaries] = useState([]);
    const [rows, setRows] = useState([]);
    const [nextCursor, setNextCursor] = useState(null);
    const [filter, setFilter] = useState("all");
    const [search, setSearch] = useState("");
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState(null);
    const [formError, setFormError] = useState(null);
    const [dialog, setDialog] = useState(null);
    const [signing, setSigning] = useState(null);
    const [receipt, setReceipt] = useState(null);
    const searchTimer = useRef(null);

    const loadContext = useCallback(async () => {
      const [accountList, totals, pendingList, payees] = await Promise.all([
        api.listAccounts(),
        api.paymentsSummary(),
        api.listPending(),
        api.listBeneficiaries(),
      ]);
      setAccounts(accountList.accounts);
      setSummary(totals);
      setPending(pendingList.pending);
      setBeneficiaries(payees.beneficiaries);
    }, []);

    const loadRows = useCallback(async (nextFilter, nextSearch) => {
      setLoading(true);
      try {
        if (nextFilter === "pending") {
          const response = await api.listPending();
          setPending(response.pending);
          setRows(
            response.pending.map((payment) => ({
              transactionId: payment.paymentId,
              accountId: payment.sourceAccountId,
              postedAt: payment.createdAt,
              counterparty: payment.counterparty,
              reference: payment.reference,
              category: payment.category,
              status: "awaiting_signature",
              direction: "debit",
              amount: {
                minorUnits: -payment.amount.minorUnits,
                currency: payment.amount.currency,
              },
            }))
          );
          setNextCursor(null);
          return;
        }
        const chosen = PAY.FILTERS.find((item) => item.key === nextFilter);
        const response = await api.listTransactions(
          Object.assign({}, chosen ? chosen.params : {}, { search: nextSearch || null })
        );
        setRows(response.transactions);
        setNextCursor(response.nextCursor);
      } finally {
        setLoading(false);
      }
    }, []);

    const fail = useCallback(
      (err) => {
        if (err && err.status === 401) {
          GEMS.session.clear();
          onSignOut();
          return;
        }
        setError(err);
        setLoading(false);
      },
      [onSignOut]
    );

    const refresh = useCallback(
      async (nextFilter, nextSearch) => {
        setError(null);
        try {
          await loadContext();
          await loadRows(nextFilter, nextSearch);
        } catch (err) {
          fail(err);
        }
      },
      [loadContext, loadRows, fail]
    );

    useEffect(() => {
      refresh(filter, search);
    }, []);

    function changeFilter(key) {
      setFilter(key);
      setError(null);
      loadRows(key, search).catch(fail);
    }

    function changeSearch(value) {
      setSearch(value);
      if (searchTimer.current) window.clearTimeout(searchTimer.current);
      searchTimer.current = window.setTimeout(() => {
        loadRows(filter, value).catch(fail);
      }, 300);
    }

    async function loadMore() {
      if (!nextCursor) return;
      setBusy(true);
      try {
        const chosen = PAY.FILTERS.find((item) => item.key === filter);
        const response = await api.listTransactions(
          Object.assign({}, chosen ? chosen.params : {}, {
            search: search || null,
            cursor: nextCursor,
          })
        );
        setRows((current) => current.concat(response.transactions));
        setNextCursor(response.nextCursor);
      } catch (err) {
        fail(err);
      } finally {
        setBusy(false);
      }
    }

    async function submitPayment(form) {
      setBusy(true);
      setFormError(null);
      try {
        const response = await api.transfer({
          sourceAccountId: form.sourceAccountId,
          targetAccountId: form.targetAccountId,
          iban: form.iban,
          counterparty: form.counterparty,
          amountMinorUnits: form.amountMinorUnits,
          reference: form.reference,
          category: form.category,
          acknowledgePayeeMismatch: form.acknowledgePayeeMismatch,
        });
        if (form.saveBeneficiary && form.iban) {
          try {
            await api.addBeneficiary(form.counterparty, form.iban);
          } catch (err) {
            setError(err);
          }
        }
        setDialog(null);
        if (response.status === "awaiting_signature") {
          setSigning(response);
        } else {
          setReceipt(response);
        }
        await refresh(filter, search);
      } catch (err) {
        setFormError(err);
      } finally {
        setBusy(false);
      }
    }

    async function submitSignature(paymentId, code) {
      setBusy(true);
      setFormError(null);
      try {
        const response = await api.signTransfer(paymentId, code);
        setSigning(null);
        setReceipt(response);
        await refresh(filter, search);
      } catch (err) {
        setFormError(err);
      } finally {
        setBusy(false);
      }
    }

    async function signOut() {
      try {
        await api.logout();
      } catch (err) {
        setError(err);
      }
      GEMS.session.clear();
      onSignOut();
    }

    const canPay = accounts.length > 0;

    return (
      <div className="onb-shell">
        <header className="onb-topbar">
          <UI.Logo size={20} />
          <span className="auth-screen-tag">{t("payments.screenTag")}</span>
          <div className="pay-topbar-actions">
            <UI.Button type="button" disabled title={t("comingSoon")}>
              {t("payments.readAloud")}
            </UI.Button>
            <span className="pay-avatar" aria-hidden="true">
              {(username || "?").slice(0, 2).toUpperCase()}
            </span>
            <UI.Button type="button" variant="ghost" onClick={signOut}>
              {t("auth.signOut")}
            </UI.Button>
          </div>
        </header>

        <main className="onb-main pay-main">
          <div className="pay-head">
            <div>
              <h1 className="pay-title">{t("payments.title")}</h1>
              <p className="text-muted pay-sub">
                {summary
                  ? t("payments.summary", {
                      movements: summary.movements,
                      pending: summary.pendingSignatures,
                    })
                  : t("payments.loading")}
              </p>
            </div>
            <div className="pay-head-actions">
              <UI.Button type="button" disabled title={t("comingSoon")}>
                {t("payments.splitBill")}
              </UI.Button>
              <UI.Button type="button" disabled title={t("comingSoon")}>
                {t("payments.scanQr")}
              </UI.Button>
              <UI.Button
                type="button"
                variant="primary"
                disabled={!canPay}
                onClick={() => {
                  setFormError(null);
                  setDialog("new");
                }}
              >
                {t("payments.newPayment")}
              </UI.Button>
            </div>
          </div>

          <PAY.AccountStrip accounts={accounts} />

          {!loading && !accounts.length ? (
            <div className="onb-error" role="status">
              {t("payments.noAccounts")}
            </div>
          ) : null}

          <PAY.PendingPanel
            pending={pending}
            busy={busy}
            onSign={(payment) => {
              setFormError(null);
              setSigning(payment);
            }}
          />

          <section className="plate pay-panel" aria-labelledby="movements-heading">
            <h2 id="movements-heading" className="visually-hidden">
              {t("payments.tableCaption")}
            </h2>

            <div className="pay-filters">
              <div className="pay-chips" role="group" aria-label={t("payments.filterBy")}>
                {PAY.FILTERS.map((item) => (
                  <UI.Chip
                    key={item.key}
                    active={filter === item.key}
                    disabled={item.comingSoon}
                    comingSoon={item.comingSoon}
                    onClick={() => changeFilter(item.key)}
                  >
                    {t("payments.filters." + item.key)}
                  </UI.Chip>
                ))}
              </div>
              <div className="pay-search">
                <label htmlFor="pay-search" className="visually-hidden">
                  {t("payments.searchLabel")}
                </label>
                <UI.TextInput
                  id="pay-search"
                  type="search"
                  placeholder={t("payments.searchPlaceholder")}
                  value={search}
                  onChange={(event) => changeSearch(event.target.value)}
                />
              </div>
            </div>

            <PAY.TransactionsTable rows={rows} loading={loading} mode={filter} />

            {nextCursor ? (
              <div className="pay-more">
                <UI.Button type="button" disabled={busy} onClick={loadMore}>
                  {busy ? t("payments.loading") : t("payments.loadMore")}
                </UI.Button>
              </div>
            ) : null}
          </section>

          <UI.ErrorNote error={error} />

          <div className="pay-agent">
            <UI.Button type="button" disabled title={t("comingSoon")}>
              {t("payments.askGems")}
            </UI.Button>
          </div>
        </main>

        <footer className="onb-footer">{t("footer")}</footer>

        {dialog === "new" ? (
          <PAY.NewPaymentDialog
            accounts={accounts}
            beneficiaries={beneficiaries}
            busy={busy}
            error={formError}
            onDismiss={() => setDialog(null)}
            onSubmit={submitPayment}
          />
        ) : null}

        {signing ? (
          <PAY.SignDialog
            payment={signing}
            busy={busy}
            error={formError}
            onDismiss={() => setSigning(null)}
            onSubmit={submitSignature}
          />
        ) : null}

        {receipt ? <PAY.Receipt receipt={receipt} onDismiss={() => setReceipt(null)} /> : null}
      </div>
    );
  };
})();
