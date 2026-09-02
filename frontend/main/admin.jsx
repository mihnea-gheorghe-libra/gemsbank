(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ADMIN = GEMS.admin;
  const UI = GEMS.ui;
  const t = ADMIN.t;
  const { useState, useEffect, useCallback } = React;

  const EMPTY_USERS = { users: [], total: 0, nextCursor: null };
  const EMPTY_TRANSACTIONS = { transactions: [], nextCursor: null };
  const EMPTY_APPLICATIONS = { applications: [], total: 0, nextCursor: null };

  const STATUS_FILTERS = ["", "review", "approved", "rejected", "withdrawn"];

  function Topbar({ admin, lang, onLang, theme, onTheme, view, onView, onSignOut }) {
    return (
      <header className="adm-topbar">
        <UI.Logo />
        <UI.Kicker>{t("tag")}</UI.Kicker>
        <nav className="adm-nav" aria-label={t("tag")}>
          <button
            type="button"
            className="adm-nav-item"
            aria-current={view === "credits" ? undefined : "page"}
            onClick={() => onView("users")}
          >
            {t("nav.users")}
          </button>
          <button
            type="button"
            className="adm-nav-item"
            aria-current={view === "credits" ? "page" : undefined}
            onClick={() => onView("credits")}
          >
            {t("nav.credits")}
          </button>
        </nav>
        <div className="adm-topbar-spacer" />
        <span className="adm-mono">{t("signedInAs", { username: admin.username })}</span>
        <UI.Button type="button" onClick={() => onLang(lang === "ro" ? "en" : "ro")}>
          {lang === "ro" ? "EN" : "RO"}
        </UI.Button>
        <UI.Button type="button" onClick={() => onTheme(theme === "dark" ? "light" : "dark")}>
          <UI.Icon name={theme === "dark" ? "Sun" : "Moon"} size={16} />
        </UI.Button>
        <UI.Button type="button" onClick={onSignOut}>
          {t("signOut")}
        </UI.Button>
      </header>
    );
  }

  function UsersScreen({ onOpen, onError }) {
    const [page, setPage] = useState(EMPTY_USERS);
    const [term, setTerm] = useState("");
    const [applied, setApplied] = useState("");
    const [busy, setBusy] = useState(true);

    const load = useCallback(
      async (search, cursor) => {
        setBusy(true);
        try {
          const next = await GEMS.adminApi.listUsers({ search, cursor });
          setPage((current) =>
            cursor
              ? { ...next, users: current.users.concat(next.users) }
              : next
          );
        } catch (err) {
          onError(err);
        } finally {
          setBusy(false);
        }
      },
      [onError]
    );

    useEffect(() => {
      load(applied, null);
    }, [load, applied]);

    return (
      <UI.Plate className="adm-panel">
        <div className="adm-head">
          <h1>{t("users.title")}</h1>
          <span className="adm-mono">
            {t("users.count", { shown: page.users.length, total: page.total })}
          </span>
        </div>

        <form
          className="adm-filters"
          onSubmit={(event) => {
            event.preventDefault();
            setApplied(term.trim());
          }}
        >
          <UI.TextInput
            id="adm-user-search"
            type="search"
            maxLength={64}
            placeholder={t("users.search")}
            aria-label={t("users.search")}
            value={term}
            onChange={(event) => setTerm(event.target.value)}
          />
          <UI.Button type="submit" variant="primary" disabled={busy}>
            {t("users.searchAction")}
          </UI.Button>
          {applied ? (
            <UI.Button
              type="button"
              onClick={() => {
                setTerm("");
                setApplied("");
              }}
            >
              {t("users.clear")}
            </UI.Button>
          ) : null}
        </form>

        {busy && !page.users.length ? (
          <UI.Spinner label={t("users.loading")} />
        ) : (
          <ADMIN.UsersTable
            page={page}
            busy={busy}
            onOpen={onOpen}
            onMore={() => load(applied, page.nextCursor)}
          />
        )}
      </UI.Plate>
    );
  }

  function UserDetailScreen({ userId, onBack, onError, onAsk }) {
    const [detail, setDetail] = useState(null);
    const [movements, setMovements] = useState(EMPTY_TRANSACTIONS);
    const [busy, setBusy] = useState(true);
    const [accountsTab, setAccountsTab] = useState("active");
    const [viewTransactionId, setViewTransactionId] = useState(null);

    const loadDetail = useCallback(async () => {
      try {
        setDetail(await GEMS.adminApi.readUser(userId));
      } catch (err) {
        onError(err);
      }
    }, [userId, onError]);

    const loadMovements = useCallback(
      async (cursor) => {
        setBusy(true);
        try {
          const next = await GEMS.adminApi.listUserTransactions(userId, { cursor });
          setMovements((current) =>
            cursor
              ? { ...next, transactions: current.transactions.concat(next.transactions) }
              : next
          );
        } catch (err) {
          onError(err);
        } finally {
          setBusy(false);
        }
      },
      [userId, onError]
    );

    useEffect(() => {
      loadDetail();
      loadMovements(null);
    }, [loadDetail, loadMovements]);

    const refresh = useCallback(() => {
      loadDetail();
      loadMovements(null);
    }, [loadDetail, loadMovements]);

    if (!detail) {
      return (
        <UI.Plate className="adm-panel">
          <UI.Spinner label={t("detail.loading")} />
        </UI.Plate>
      );
    }

    const reversedIds = new Set(
      movements.transactions.filter((row) => row.reverses).map((row) => row.reverses)
    );

    return (
      <React.Fragment>
        <UI.Plate className="adm-panel">
          <div className="adm-head">
            <UI.Button type="button" variant="ghost" onClick={onBack}>
              <UI.Icon name="ArrowLeft" size={16} /> {t("detail.back")}
            </UI.Button>
            <h1>{detail.user.fullName || detail.user.username}</h1>
            <ADMIN.StatusTag status={detail.user.status} />
            <div className="adm-row-actions" style={{ marginLeft: "auto" }}>
              <UI.Button
                type="button"
                onClick={() => {
                  const isLocked = detail.user.status === "locked";
                  onAsk({
                    intent: isLocked ? "unlockUser" : "lockUser",
                    run: (reason) =>
                      isLocked
                        ? GEMS.adminApi.unlockUser(detail.user.userId, reason)
                        : GEMS.adminApi.lockUser(detail.user.userId, reason),
                    done: refresh,
                  });
                }}
              >
                {detail.user.status === "locked"
                  ? t("detail.unlockUser")
                  : t("detail.lockUser")}
              </UI.Button>
            </div>
          </div>

          <dl className="adm-kv">
            <div>
              <dt>{t("users.columns.username")}</dt>
              <dd className="adm-mono">{detail.user.username}</dd>
            </div>
            <div>
              <dt>{t("detail.contact")}</dt>
              <dd>{detail.user.email}</dd>
            </div>
            <div>
              <dt>{t("detail.phone")}</dt>
              <dd>{detail.user.phone || "—"}</dd>
            </div>
            <div>
              <dt>{t("detail.joined")}</dt>
              <dd>{ADMIN.formatDate(detail.user.createdAt)}</dd>
            </div>
          </dl>
        </UI.Plate>

        <UI.Plate className="adm-panel">
          <div className="adm-head">
            <h2>{t("detail.accounts")}</h2>
          </div>
          <UI.Segmented
            name="accounts-tab"
            value={accountsTab}
            onChange={setAccountsTab}
            options={[
              { value: "active", label: t("status.active") },
              { value: "closed", label: t("status.closed") },
            ]}
          />
          {(() => {
            const shown = detail.accounts.filter((account) =>
              accountsTab === "closed"
                ? account.status === "closed"
                : account.status !== "closed"
            );
            if (!shown.length) {
              return <ADMIN.Empty>{t("detail.noAccounts")}</ADMIN.Empty>;
            }
            return (
              <div className="adm-grid">
                {shown.map((account) => (
                  <ADMIN.AccountCard
                    key={account.accountId}
                    account={account}
                    onFreeze={(target) =>
                      onAsk({
                        intent: "freeze",
                        run: (reason) =>
                          GEMS.adminApi.freezeAccount(target.accountId, reason),
                        done: refresh,
                      })
                    }
                    onUnfreeze={(target) =>
                      onAsk({
                        intent: "unfreeze",
                        run: (reason) =>
                          GEMS.adminApi.unfreezeAccount(target.accountId, reason),
                        done: refresh,
                      })
                    }
                    onClose={(target) =>
                      onAsk({
                        intent: "closeAccount",
                        run: (reason) =>
                          GEMS.adminApi.closeAccount(target.accountId, reason),
                        done: refresh,
                      })
                    }
                  />
                ))}
              </div>
            );
          })()}
        </UI.Plate>

        <UI.Plate className="adm-panel">
          <div className="adm-head">
            <h2>{t("detail.transactions")}</h2>
          </div>
          <ADMIN.TransactionsTable
            page={movements}
            busy={busy}
            reversedIds={reversedIds}
            onMore={() => loadMovements(movements.nextCursor)}
            onView={(row) => setViewTransactionId(row.transactionId)}
            onReverse={(row) =>
              onAsk({
                intent: "reverse",
                run: (reason) => GEMS.adminApi.reverseTransaction(row.transactionId, reason),
                done: refresh,
              })
            }
          />
        </UI.Plate>

        {viewTransactionId ? (
          <ADMIN.TransactionDetailDialog
            transactionId={viewTransactionId}
            onClose={() => setViewTransactionId(null)}
          />
        ) : null}

        <UI.Plate className="adm-panel">
          <div className="adm-head">
            <h2>{t("detail.credits")}</h2>
          </div>
          {detail.creditApplications.length ? (
            <div className="adm-grid">
              {detail.creditApplications.map((application) => (
                <ADMIN.ApplicationCard
                  key={application.applicationId}
                  application={application}
                  showApplicant={false}
                  onApprove={(target) =>
                    onAsk({
                      intent: "approve",
                      run: (reason) =>
                        GEMS.adminApi.approveCreditApplication(target.applicationId, reason),
                      done: refresh,
                    })
                  }
                  onReject={(target) =>
                    onAsk({
                      intent: "reject",
                      run: (reason) =>
                        GEMS.adminApi.rejectCreditApplication(target.applicationId, reason),
                      done: refresh,
                    })
                  }
                />
              ))}
            </div>
          ) : (
            <ADMIN.Empty>{t("detail.noCredits")}</ADMIN.Empty>
          )}
        </UI.Plate>
      </React.Fragment>
    );
  }

  function CreditsScreen({ onError, onAsk }) {
    const [page, setPage] = useState(EMPTY_APPLICATIONS);
    const [status, setStatus] = useState("review");
    const [busy, setBusy] = useState(true);

    const load = useCallback(
      async (wanted, cursor) => {
        setBusy(true);
        try {
          const next = await GEMS.adminApi.listCreditApplications({ status: wanted, cursor });
          setPage((current) =>
            cursor
              ? { ...next, applications: current.applications.concat(next.applications) }
              : next
          );
        } catch (err) {
          onError(err);
        } finally {
          setBusy(false);
        }
      },
      [onError]
    );

    useEffect(() => {
      load(status, null);
    }, [load, status]);

    const refresh = useCallback(() => load(status, null), [load, status]);

    return (
      <UI.Plate className="adm-panel">
        <div className="adm-head">
          <h1>{t("credits.title")}</h1>
          <span className="adm-mono">
            {t("credits.count", { shown: page.applications.length, total: page.total })}
          </span>
        </div>

        <div className="adm-filters">
          <UI.Field id="adm-credit-status" label={t("credits.filter")}>
            <UI.Select
              id="adm-credit-status"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              {STATUS_FILTERS.map((value) => (
                <option key={value || "all"} value={value}>
                  {value ? GEMS.i18n.t("admin.status." + value) : t("credits.all")}
                </option>
              ))}
            </UI.Select>
          </UI.Field>
        </div>

        {busy && !page.applications.length ? (
          <UI.Spinner label={t("credits.loading")} />
        ) : page.applications.length ? (
          <React.Fragment>
            <div className="adm-grid">
              {page.applications.map((application) => (
                <ADMIN.ApplicationCard
                  key={application.applicationId}
                  application={application}
                  showApplicant
                  onApprove={(target) =>
                    onAsk({
                      intent: "approve",
                      run: (reason) =>
                        GEMS.adminApi.approveCreditApplication(target.applicationId, reason),
                      done: refresh,
                    })
                  }
                  onReject={(target) =>
                    onAsk({
                      intent: "reject",
                      run: (reason) =>
                        GEMS.adminApi.rejectCreditApplication(target.applicationId, reason),
                      done: refresh,
                    })
                  }
                />
              ))}
            </div>
            <ADMIN.LoadMore
              cursor={page.nextCursor}
              busy={busy}
              onClick={() => load(status, page.nextCursor)}
              label={t("credits.more")}
            />
          </React.Fragment>
        ) : (
          <ADMIN.Empty>{t("credits.empty")}</ADMIN.Empty>
        )}
      </UI.Plate>
    );
  }

  ADMIN.BackOffice = function BackOffice({ admin, theme, onTheme, lang, onLang, onSignOut }) {
    const [view, setView] = useState("users");
    const [openUserId, setOpenUserId] = useState(null);
    const [error, setError] = useState(null);
    const [ask, setAsk] = useState(null);
    const [askError, setAskError] = useState(null);
    const [askBusy, setAskBusy] = useState(false);

    const onError = useCallback((err) => setError(err), []);
    const openAsk = useCallback((request) => {
      setAskError(null);
      setAsk(request);
    }, []);

    const confirmAsk = async (reason) => {
      setAskBusy(true);
      setAskError(null);
      try {
        await ask.run(reason);
        const done = ask.done;
        setAsk(null);
        if (done) done();
      } catch (err) {
        setAskError(err);
      } finally {
        setAskBusy(false);
      }
    };

    return (
      <div className="adm-shell">
        <Topbar
          admin={admin}
          lang={lang}
          theme={theme}
          onTheme={onTheme}
          onLang={onLang}
          view={openUserId ? "users" : view}
          onView={(next) => {
            setOpenUserId(null);
            setView(next);
          }}
          onSignOut={onSignOut}
        />

        <main className="adm-main">
          <UI.ErrorNote error={error} />
          {openUserId ? (
            <UserDetailScreen
              userId={openUserId}
              onBack={() => setOpenUserId(null)}
              onError={onError}
              onAsk={openAsk}
            />
          ) : view === "credits" ? (
            <CreditsScreen onError={onError} onAsk={openAsk} />
          ) : (
            <UsersScreen onOpen={setOpenUserId} onError={onError} />
          )}
        </main>

        <footer className="adm-footer">{t("footer")}</footer>

        {ask ? (
          <ADMIN.ReasonDialog
            intent={ask.intent}
            busy={askBusy}
            error={askError}
            onCancel={() => setAsk(null)}
            onConfirm={confirmAsk}
          />
        ) : null}
      </div>
    );
  };
})();
