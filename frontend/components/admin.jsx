(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ADMIN = (GEMS.admin = GEMS.admin || {});
  const UI = GEMS.ui;
  const { useState } = React;

  function t(key, params) {
    return GEMS.i18n.t("admin." + key, params);
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const moment = new Date(iso);
    if (Number.isNaN(moment.getTime())) return "—";
    return moment.toLocaleDateString(GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }

  function formatDateTime(iso) {
    if (!iso) return "—";
    const moment = new Date(iso);
    if (Number.isNaN(moment.getTime())) return "—";
    return moment.toLocaleString(GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  ADMIN.t = t;
  ADMIN.formatDate = formatDate;
  ADMIN.formatDateTime = formatDateTime;

  const STATUS_TONE = {
    active: "accent",
    approved: "accent",
    frozen: "outline",
    review: "outline",
    closed: "neutral",
    rejected: "neutral",
    withdrawn: "neutral",
    locked: "neutral",
  };

  ADMIN.StatusTag = function StatusTag({ status }) {
    const label = GEMS.i18n.t("admin.status." + status);
    return (
      <UI.Tag variant={STATUS_TONE[status] || "neutral"}>
        {label === "admin.status." + status ? status : label}
      </UI.Tag>
    );
  };

  ADMIN.Empty = function Empty({ children }) {
    return <div className="adm-empty">{children}</div>;
  };

  ADMIN.LoadMore = function LoadMore({ cursor, busy, onClick, label }) {
    if (!cursor) return null;
    return (
      <div className="adm-more">
        <UI.Button type="button" disabled={busy} onClick={onClick}>
          {label}
        </UI.Button>
      </div>
    );
  };

  ADMIN.ReasonDialog = function ReasonDialog({ intent, busy, error, onCancel, onConfirm }) {
    const [reason, setReason] = useState("");
    const titleId = "adm-reason-title";

    return (
      <UI.Dialog labelledBy={titleId} onDismiss={busy ? () => {} : onCancel}>
        <form
          className="adm-dialog-body"
          onSubmit={(event) => {
            event.preventDefault();
            onConfirm(reason);
          }}
        >
          <h2 className="dialog-title" id={titleId}>
            {t("confirm." + intent)}
          </h2>
          <p className="adm-note">{t("confirm." + intent + "Lede")}</p>

          <UI.Field id="adm-reason" label={t("reason.label")} hint={t("reason.hint")}>
            <textarea
              id="adm-reason"
              className="adm-textarea"
              maxLength={280}
              required
              autoFocus
              placeholder={t("reason.placeholder")}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </UI.Field>

          <UI.ErrorNote error={error} />

          <div className="dialog-actions">
            <UI.Button type="button" disabled={busy} onClick={onCancel}>
              {t("reason.cancel")}
            </UI.Button>
            <UI.Button type="submit" variant="primary" disabled={busy || reason.trim().length < 5}>
              {busy ? t("reason.working") : t("confirm." + intent + "Action")}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  };

  ADMIN.UsersTable = function UsersTable({ page, busy, onOpen, onMore }) {
    if (!page.users.length) {
      return <ADMIN.Empty>{t("users.empty")}</ADMIN.Empty>;
    }
    return (
      <React.Fragment>
        <div className="adm-table-scroll">
          <table className="adm-table">
            <thead>
              <tr>
                <th scope="col">{t("users.columns.name")}</th>
                <th scope="col">{t("users.columns.username")}</th>
                <th scope="col">{t("users.columns.email")}</th>
                <th scope="col">{t("users.columns.status")}</th>
                <th scope="col">{t("users.columns.joined")}</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {page.users.map((user) => (
                <tr key={user.userId}>
                  <td>{user.fullName || "—"}</td>
                  <td className="adm-mono">{user.username}</td>
                  <td>{user.email}</td>
                  <td><ADMIN.StatusTag status={user.status} /></td>
                  <td className="adm-num">{formatDate(user.createdAt)}</td>
                  <td>
                    <div className="adm-row-actions">
                      <UI.Button type="button" onClick={() => onOpen(user.userId)}>
                        {t("users.open")}
                      </UI.Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ADMIN.LoadMore
          cursor={page.nextCursor}
          busy={busy}
          onClick={onMore}
          label={t("users.more")}
        />
      </React.Fragment>
    );
  };

  ADMIN.AccountCard = function AccountCard({ account, onFreeze, onUnfreeze, onClose }) {
    const frozen = account.status === "frozen";
    return (
      <UI.Plate className="adm-card">
        <div className="adm-card-head">
          <span className="adm-card-title">{account.label}</span>
          <ADMIN.StatusTag status={account.status} />
        </div>
        <div className="adm-mono">{account.iban}</div>
        <UI.Money minorUnits={account.balance.minorUnits} currency={account.balance.currency} />
        {account.statusReason ? (
          <div className="adm-reason">
            {t("detail.statusReason", { reason: account.statusReason })}
          </div>
        ) : null}
        {account.status === "closed" ? null : (
          <div className="adm-row-actions">
            <UI.Button
              type="button"
              onClick={() => (frozen ? onUnfreeze(account) : onFreeze(account))}
            >
              {frozen ? t("detail.unfreeze") : t("detail.freeze")}
            </UI.Button>
            <UI.Button
              type="button"
              onClick={() => onClose(account)}
            >
              {t("detail.closeAccount")}
            </UI.Button>
          </div>
        )}
      </UI.Plate>
    );
  };

  ADMIN.TransactionsTable = function TransactionsTable({ page, busy, reversedIds, onReverse, onView, onMore }) {
    if (!page.transactions.length) {
      return <ADMIN.Empty>{t("detail.noTransactions")}</ADMIN.Empty>;
    }
    return (
      <React.Fragment>
        <div className="adm-table-scroll">
          <table className="adm-table">
            <thead>
              <tr>
                <th scope="col">{t("detail.columns.date")}</th>
                <th scope="col">{t("detail.columns.details")}</th>
                <th scope="col">{t("detail.columns.account")}</th>
                <th scope="col">{t("users.columns.status")}</th>
                <th scope="col">{t("detail.columns.amount")}</th>
                <th scope="col" />
              </tr>
            </thead>
            <tbody>
              {page.transactions.map((row) => {
                const alreadyReversed = reversedIds.has(row.transactionId);
                return (
                  <tr
                    key={row.transactionId + ":" + row.accountId}
                    className="adm-row-clickable"
                    onClick={() => onView(row)}
                  >
                    <td className="adm-num">{formatDateTime(row.postedAt)}</td>
                    <td>
                      <div>{row.counterparty}</div>
                      <div className="adm-mono">{row.reference}</div>
                      {row.reason ? (
                        <div className="adm-reason">
                          {t("detail.statusReason", { reason: row.reason })}
                        </div>
                      ) : null}
                    </td>
                    <td>{row.accountLabel}</td>
                    <td>
                      {row.reverses ? <UI.Tag variant="outline">{t("detail.isReversal")}</UI.Tag> : null}
                      {alreadyReversed ? <UI.Tag variant="neutral">{t("detail.reversed")}</UI.Tag> : null}
                    </td>
                    <td className="adm-num">
                      <UI.Money
                        minorUnits={row.amount.minorUnits}
                        currency={row.amount.currency}
                        signed
                      />
                    </td>
                    <td>
                      <div className="adm-row-actions">
                        <UI.Button
                          type="button"
                          disabled={alreadyReversed}
                          onClick={(event) => {
                            event.stopPropagation();
                            onReverse(row);
                          }}
                        >
                          {t("detail.reverse")}
                        </UI.Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <ADMIN.LoadMore
          cursor={page.nextCursor}
          busy={busy}
          onClick={onMore}
          label={t("detail.more")}
        />
      </React.Fragment>
    );
  };

  function PartyBlock({ label, party }) {
    return (
      <div>
        <dt>{label}</dt>
        <dd>
          {party && party.isHouse ? (
            t("detail.txDialog.house")
          ) : party && party.holderName ? (
            <React.Fragment>
              <div>{party.holderName}</div>
              {party.label ? <div className="adm-note">{party.label}</div> : null}
              {party.iban ? (
                <div className="adm-mono">
                  {t("detail.txDialog.iban")}: {party.iban}
                </div>
              ) : null}
            </React.Fragment>
          ) : (
            t("detail.txDialog.unknownAccount")
          )}
        </dd>
      </div>
    );
  }

  ADMIN.TransactionDetailDialog = function TransactionDetailDialog({ transactionId, onClose }) {
    const [detail, setDetail] = useState(null);
    const [error, setError] = useState(null);
    const titleId = "adm-tx-title";

    React.useEffect(() => {
      let cancelled = false;
      setDetail(null);
      setError(null);
      GEMS.adminApi
        .readTransaction(transactionId)
        .then((response) => {
          if (!cancelled) setDetail(response);
        })
        .catch((err) => {
          if (!cancelled) setError(err);
        });
      return () => {
        cancelled = true;
      };
    }, [transactionId]);

    return (
      <UI.Dialog labelledBy={titleId} onDismiss={onClose}>
        <div className="adm-dialog-body">
          <h2 className="dialog-title" id={titleId}>
            {t("detail.txDialog.title")}
          </h2>

          {error ? <UI.ErrorNote error={error} /> : null}
          {!error && !detail ? <UI.Spinner label={t("detail.txDialog.loading")} /> : null}

          {detail ? (
            <React.Fragment>
              <dl className="adm-kv">
                <div>
                  <dt>{t("detail.txDialog.amount")}</dt>
                  <dd>
                    <UI.Money
                      minorUnits={detail.amountMinorUnits}
                      currency={detail.currency}
                    />
                  </dd>
                </div>
                <div>
                  <dt>{t("detail.txDialog.kind")}</dt>
                  <dd>{t("detail.kinds." + detail.kind)}</dd>
                </div>
                <div>
                  <dt>{t("detail.txDialog.postedAt")}</dt>
                  <dd>{formatDateTime(detail.postedAt)}</dd>
                </div>
                <div>
                  <dt>{t("detail.txDialog.category")}</dt>
                  <dd>{detail.category}</dd>
                </div>
                <PartyBlock label={t("detail.txDialog.payer")} party={detail.payer} />
                <PartyBlock label={t("detail.txDialog.payee")} party={detail.payee} />
              </dl>

              <div className="adm-note">
                {t("detail.txDialog.reference")}: {detail.reference}
              </div>
              {detail.counterparty ? (
                <div className="adm-note">{detail.counterparty}</div>
              ) : null}

              {detail.reason ? (
                <div className="adm-reason">
                  {t("detail.statusReason", { reason: detail.reason })}
                </div>
              ) : null}
              {detail.reverses ? (
                <div className="adm-note">
                  {t("detail.txDialog.reverses", { id: detail.reverses })}
                </div>
              ) : null}
              {detail.reversalTransactionId ? (
                <div className="adm-note">
                  {t("detail.txDialog.reversedBy", { id: detail.reversalTransactionId })}
                </div>
              ) : null}

              <div className="adm-mono">
                {t("detail.txDialog.transactionId")}: {detail.transactionId}
              </div>
              <div className="adm-mono">
                {t("detail.txDialog.correlationId")}: {detail.correlationId}
              </div>
            </React.Fragment>
          ) : null}

          <div className="dialog-actions">
            <UI.Button type="button" onClick={onClose}>
              {t("detail.txDialog.close")}
            </UI.Button>
          </div>
        </div>
      </UI.Dialog>
    );
  };

  ADMIN.CreditSupport = function CreditSupport({ support }) {
    return (
      <dl className="adm-kv">
        <div>
          <dt>{t("credits.income")}</dt>
          <dd>
            {support.monthlyIncomeMinorUnits ? (
              <UI.Money minorUnits={support.monthlyIncomeMinorUnits} currency="RON" />
            ) : (
              t("credits.incomeUnknown")
            )}
          </dd>
        </div>
        <div>
          <dt>{t("credits.estimatedPayment")}</dt>
          <dd>
            {support.estimatedMonthlyPaymentMinorUnits != null ? (
              <UI.Money
                minorUnits={support.estimatedMonthlyPaymentMinorUnits}
                currency="RON"
              />
            ) : (
              t("credits.openEnded")
            )}
          </dd>
        </div>
        <div>
          <dt>{t("credits.currentBalance")}</dt>
          <dd>
            <UI.Money
              minorUnits={support.currentBalanceMinorUnits}
              currency={support.currentBalanceCurrency}
            />
          </dd>
        </div>
        <div>
          <dt>{t("credits.otherActive")}</dt>
          <dd>
            {support.otherActiveCredits.length ? (
              support.otherActiveCredits.map((other) => (
                <div key={other.applicationId}>
                  {other.productId} —{" "}
                  <UI.Money
                    minorUnits={other.amount.minorUnits}
                    currency={other.amount.currency}
                  />
                </div>
              ))
            ) : (
              t("credits.noOtherActive")
            )}
          </dd>
        </div>
      </dl>
    );
  };

  ADMIN.ApplicationCard = function ApplicationCard({ application, showApplicant, onApprove, onReject }) {
    const pending = application.status === "review";
    return (
      <UI.Plate className="adm-card">
        <div className="adm-card-head">
          <span className="adm-card-title">{application.productId}</span>
          <ADMIN.StatusTag status={application.status} />
        </div>

        <dl className="adm-kv">
          {showApplicant && application.applicant ? (
            <div>
              <dt>{t("credits.applicant")}</dt>
              <dd>
                {application.applicant.fullName || application.applicant.username}
                <div className="adm-mono">{application.applicant.username}</div>
              </dd>
            </div>
          ) : null}
          <div>
            <dt>{t("credits.amount")}</dt>
            <dd>
              <UI.Money
                minorUnits={application.amount.minorUnits}
                currency={application.amount.currency}
              />
            </dd>
          </div>
          <div>
            <dt>{t("credits.term")}</dt>
            <dd>
              {application.termMonths
                ? t("credits.termMonths", { months: application.termMonths })
                : t("credits.openEnded")}
            </dd>
          </div>
          <div>
            <dt>{t("credits.rate")}</dt>
            <dd>{(application.rateBps / 100).toFixed(2)}%</dd>
          </div>
          <div>
            <dt>{t("credits.submitted")}</dt>
            <dd>{formatDate(application.submittedAt)}</dd>
          </div>
        </dl>

        {application.purpose ? (
          <div className="adm-note">
            {t("credits.purpose")}: {application.purpose}
          </div>
        ) : null}

        {pending && application.support ? (
          <ADMIN.CreditSupport support={application.support} />
        ) : null}

        {application.decisionReason ? (
          <div className="adm-reason">
            {t("credits.decidedOn", { date: formatDate(application.decidedAt) })} —{" "}
            {application.decisionReason}
          </div>
        ) : null}

        {pending ? (
          <div className="adm-row-actions">
            <UI.Button type="button" onClick={() => onReject(application)}>
              {t("credits.reject")}
            </UI.Button>
            <UI.Button type="button" variant="primary" onClick={() => onApprove(application)}>
              {t("credits.approve")}
            </UI.Button>
          </div>
        ) : null}
      </UI.Plate>
    );
  };
})();
