(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const PAY = (GEMS.payments = GEMS.payments || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const { useState, useMemo } = React;

  const MINOR_UNITS_PER_MAJOR = 100;

  PAY.FILTERS = [
    { key: "all", params: {} },
    { key: "income", params: { direction: "credit" } },
    { key: "spending", params: { direction: "debit" } },
    { key: "pending", params: null },
    { key: "cards", params: null, comingSoon: true },
  ];

  function toMinorUnits(raw) {
    const cleaned = String(raw).replace(/\s/g, "").replace(",", ".");
    if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
    return Math.round(Number(cleaned) * MINOR_UNITS_PER_MAJOR);
  }

  function formatDate(iso) {
    const moment = new Date(iso);
    if (isNaN(moment.getTime())) return iso;
    return [
      String(moment.getDate()).padStart(2, "0"),
      String(moment.getMonth() + 1).padStart(2, "0"),
      moment.getFullYear(),
    ].join(".");
  }

  PAY.toMinorUnits = toMinorUnits;

  PAY.AccountStrip = function AccountStrip({ accounts }) {
    return (
      <ul className="pay-accounts" aria-label={t("payments.accounts")}>
        {accounts.map((account) => (
          <li key={account.accountId} className="plate pay-account">
            <div className="kicker">
              {account.currency} · {t("payments.kind." + account.kind)}
            </div>
            <div className="pay-account-balance">
              <UI.Money
                minorUnits={account.balance.minorUnits}
                currency={account.balance.currency}
              />
            </div>
            <div className="text-muted pay-account-iban">{account.ibanMasked}</div>
          </li>
        ))}
      </ul>
    );
  };

  PAY.PendingPanel = function PendingPanel({ pending, onSign, busy }) {
    if (!pending.length) return null;
    return (
      <section className="plate pay-panel" aria-labelledby="pending-heading">
        <h2 id="pending-heading" className="kicker">
          {t("payments.pending")}
        </h2>
        <ul className="pay-pending-list">
          {pending.map((payment, index) => (
            <li key={payment.paymentId} className="pay-pending">
              <span className="pay-pending-num" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="pay-pending-body">
                <span className="pay-pending-name">{payment.counterparty}</span>
                <span className="text-muted pay-pending-note">
                  {payment.reference} · {t("payments.needsSignature")}
                </span>
              </span>
              <UI.Money
                minorUnits={-payment.amount.minorUnits}
                currency={payment.amount.currency}
                signed
              />
              <UI.Button type="button" disabled={busy} onClick={() => onSign(payment)}>
                {t("payments.sign")}
              </UI.Button>
            </li>
          ))}
        </ul>
      </section>
    );
  };

  PAY.TransactionsTable = function TransactionsTable({ rows, loading, mode }) {
    if (loading) return <UI.Spinner label={t("payments.loading")} />;
    if (!rows.length) {
      return (
        <p className="text-muted pay-empty">
          {mode === "pending" ? t("payments.emptyPending") : t("payments.empty")}
        </p>
      );
    }

    return (
      <div className="pay-table-scroll">
        <table className="table pay-table">
          <caption className="visually-hidden">{t("payments.tableCaption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("payments.columns.date")}</th>
              <th scope="col">{t("payments.columns.counterparty")}</th>
              <th scope="col">{t("payments.columns.reference")}</th>
              <th scope="col">{t("payments.columns.category")}</th>
              <th scope="col">{t("payments.columns.status")}</th>
              <th scope="col" className="pay-num">
                {t("payments.columns.amount")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.transactionId + row.accountId + row.direction}>
                <td className="pay-date">{formatDate(row.postedAt)}</td>
                <td>{row.counterparty}</td>
                <td className="text-muted">{row.reference}</td>
                <td className="text-muted">{t("payments.category." + row.category)}</td>
                <td>
                  <UI.Tag variant={row.status === "booked" ? "accent" : "outline"}>
                    {t("payments.status." + row.status)}
                  </UI.Tag>
                </td>
                <td className="pay-num">
                  <UI.Money
                    minorUnits={row.amount.minorUnits}
                    currency={row.amount.currency}
                    signed
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  PAY.NewPaymentDialog = function NewPaymentDialog({
    accounts,
    beneficiaries,
    busy,
    error,
    onDismiss,
    onSubmit,
  }) {
    const [rail, setRail] = useState("iban");
    const [sourceAccountId, setSourceAccountId] = useState(
      accounts.length ? accounts[0].accountId : ""
    );
    const [targetAccountId, setTargetAccountId] = useState("");
    const [iban, setIban] = useState("");
    const [counterparty, setCounterparty] = useState("");
    const [amount, setAmount] = useState("");
    const [reference, setReference] = useState("");
    const [category, setCategory] = useState("transfer");
    const [save, setSave] = useState(false);
    const [acknowledge, setAcknowledge] = useState(false);

    const source = accounts.find((account) => account.accountId === sourceAccountId);
    const currency = source ? source.currency : "RON";
    const otherAccounts = accounts.filter(
      (account) => account.accountId !== sourceAccountId && account.currency === currency
    );

    const minorUnits = toMinorUnits(amount);
    const mismatch =
      error && error.details && error.details.payeeCheck === "no_match";
    const ready =
      Boolean(sourceAccountId) &&
      minorUnits !== null &&
      minorUnits > 0 &&
      counterparty.trim().length >= 2 &&
      reference.trim().length > 0 &&
      (rail === "internal" ? Boolean(targetAccountId) : iban.trim().length >= 15) &&
      (!mismatch || acknowledge);

    function pickBeneficiary(value) {
      const found = beneficiaries.find((item) => item.beneficiaryId === value);
      if (!found) return;
      setIban(found.iban);
      setCounterparty(found.name);
    }

    function pickTarget(value) {
      setTargetAccountId(value);
      const found = accounts.find((account) => account.accountId === value);
      if (found) setCounterparty(found.holderName);
    }

    return (
      <UI.Dialog labelledBy="new-payment-title" onDismiss={onDismiss}>
        <h2 id="new-payment-title" className="dialog-title">
          {t("payments.newPayment")}
        </h2>

        <UI.Segmented
          name={t("payments.rail")}
          value={rail}
          onChange={setRail}
          options={[
            { value: "iban", label: t("payments.rails.iban") },
            { value: "internal", label: t("payments.rails.internal") },
            { value: "split", label: t("payments.rails.split"), disabled: true, comingSoon: true },
          ]}
        />

        <form
          className="pay-form"
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit({
              sourceAccountId,
              targetAccountId: rail === "internal" ? targetAccountId : null,
              iban: rail === "internal" ? null : iban.trim(),
              counterparty: counterparty.trim(),
              amountMinorUnits: minorUnits,
              reference: reference.trim(),
              category,
              acknowledgePayeeMismatch: acknowledge,
              saveBeneficiary: save && rail === "iban",
            });
          }}
        >
          <UI.Field id="pay-source" label={t("payments.from")}>
            <select
              id="pay-source"
              className="input"
              value={sourceAccountId}
              onChange={(event) => {
                setSourceAccountId(event.target.value);
                setTargetAccountId("");
              }}
            >
              {accounts.map((account) => (
                <option key={account.accountId} value={account.accountId}>
                  {t("payments.kind." + account.kind)} · {account.ibanMasked} ·{" "}
                  {UI.formatMoney(account.balance.minorUnits, account.balance.currency)}
                </option>
              ))}
            </select>
          </UI.Field>

          {rail === "internal" ? (
            <UI.Field id="pay-target" label={t("payments.toOwn")} hint={t("payments.sameCurrency")}>
              <select
                id="pay-target"
                className="input"
                value={targetAccountId}
                onChange={(event) => pickTarget(event.target.value)}
              >
                <option value="">{t("payments.choose")}</option>
                {otherAccounts.map((account) => (
                  <option key={account.accountId} value={account.accountId}>
                    {t("payments.kind." + account.kind)} · {account.ibanMasked}
                  </option>
                ))}
              </select>
            </UI.Field>
          ) : (
            <React.Fragment>
              {beneficiaries.length ? (
                <UI.Field id="pay-beneficiary" label={t("payments.savedPayees")}>
                  <select
                    id="pay-beneficiary"
                    className="input"
                    defaultValue=""
                    onChange={(event) => pickBeneficiary(event.target.value)}
                  >
                    <option value="">{t("payments.choose")}</option>
                    {beneficiaries.map((item) => (
                      <option key={item.beneficiaryId} value={item.beneficiaryId}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </UI.Field>
              ) : null}
              <UI.Field
                id="pay-iban"
                label={t("payments.iban")}
                hint={t("payments.ibanHint")}
                error={error && error.details && error.details.field === "iban" ? error.message : null}
              >
                <UI.TextInput
                  id="pay-iban"
                  name="iban"
                  autoComplete="off"
                  spellCheck="false"
                  placeholder="RO49 GEMS 1234 …"
                  value={iban}
                  onChange={(event) => setIban(event.target.value.toUpperCase())}
                />
              </UI.Field>
            </React.Fragment>
          )}

          <UI.Field
            id="pay-counterparty"
            label={t("payments.beneficiary")}
            error={
              error && error.details && error.details.field === "counterparty"
                ? error.message
                : null
            }
          >
            <UI.TextInput
              id="pay-counterparty"
              name="counterparty"
              autoComplete="off"
              value={counterparty}
              onChange={(event) => setCounterparty(event.target.value)}
            />
          </UI.Field>

          <div className="pay-form-row">
            <UI.Field
              id="pay-amount"
              label={t("payments.amount")}
              error={
                error && error.details && error.details.field === "amount" ? error.message : null
              }
            >
              <UI.TextInput
                id="pay-amount"
                name="amount"
                inputMode="decimal"
                autoComplete="off"
                placeholder="0,00"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </UI.Field>
            <UI.Field id="pay-currency" label={t("payments.currency")}>
              <UI.TextInput id="pay-currency" value={currency} readOnly tabIndex={-1} />
            </UI.Field>
          </div>

          <UI.Field
            id="pay-reference"
            label={t("payments.reference")}
            error={
              error && error.details && error.details.field === "reference" ? error.message : null
            }
          >
            <UI.TextInput
              id="pay-reference"
              name="reference"
              autoComplete="off"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
            />
          </UI.Field>

          <UI.Field id="pay-category" label={t("payments.categoryLabel")}>
            <select
              id="pay-category"
              className="input"
              value={category}
              onChange={(event) => setCategory(event.target.value)}
            >
              {["transfer", "groceries", "utilities", "transport", "entertainment", "other"].map(
                (key) => (
                  <option key={key} value={key}>
                    {t("payments.category." + key)}
                  </option>
                )
              )}
            </select>
          </UI.Field>

          {rail === "iban" ? (
            <label className="pay-check">
              <input
                type="checkbox"
                checked={save}
                onChange={(event) => setSave(event.target.checked)}
              />
              <span>{t("payments.savePayee")}</span>
            </label>
          ) : null}

          {mismatch ? (
            <label className="pay-check pay-warn">
              <input
                type="checkbox"
                checked={acknowledge}
                onChange={(event) => setAcknowledge(event.target.checked)}
              />
              <span>{t("payments.acknowledgeMismatch")}</span>
            </label>
          ) : null}

          <p className="text-muted pay-note">{t("payments.stepUpNote")}</p>

          <div className="dialog-actions">
            <UI.Button type="button" onClick={onDismiss}>
              {t("payments.cancel")}
            </UI.Button>
            <UI.Button type="submit" variant="primary" disabled={busy || !ready}>
              {busy ? t("payments.sending") : t("payments.continue")}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  };

  PAY.SignDialog = function SignDialog({ payment, busy, error, onDismiss, onSubmit }) {
    const [code, setCode] = useState("");
    const attemptsLeft = error && error.details ? error.details.attemptsLeft : null;

    return (
      <UI.Dialog labelledBy="sign-title" onDismiss={onDismiss}>
        <h2 id="sign-title" className="dialog-title">
          {t("payments.signTitle")}
        </h2>

        <dl className="pay-receipt">
          <dt>{t("payments.beneficiary")}</dt>
          <dd>{payment.counterparty}</dd>
          <dt>{t("payments.iban")}</dt>
          <dd className="pay-mono">{payment.iban}</dd>
          <dt>{t("payments.amount")}</dt>
          <dd>
            <UI.Money
              minorUnits={payment.amount.minorUnits}
              currency={payment.amount.currency}
            />
          </dd>
          <dt>{t("payments.reference")}</dt>
          <dd>{payment.reference}</dd>
        </dl>

        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(payment.paymentId, code);
          }}
        >
          <UI.Field
            id="sign-code"
            label={t("payments.signatureCode")}
            hint={t("payments.signatureHint")}
            error={error ? error.message : null}
          >
            <UI.TextInput
              id="sign-code"
              name="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
            />
          </UI.Field>

          {attemptsLeft !== null && attemptsLeft !== undefined ? (
            <p className="text-muted pay-note">
              {t("payments.attemptsLeft", { n: attemptsLeft })}
            </p>
          ) : null}

          <div className="dialog-actions">
            <UI.Button type="button" onClick={onDismiss}>
              {t("payments.cancel")}
            </UI.Button>
            <UI.Button type="submit" variant="primary" disabled={busy || code.length !== 6}>
              {busy ? t("payments.signing") : t("payments.signAndSend")}
            </UI.Button>
          </div>
        </form>
      </UI.Dialog>
    );
  };

  PAY.Receipt = function Receipt({ receipt, onDismiss }) {
    return (
      <UI.Dialog labelledBy="receipt-title" onDismiss={onDismiss}>
        <h2 id="receipt-title" className="dialog-title">
          {t("payments.sent")}
        </h2>
        <dl className="pay-receipt">
          <dt>{t("payments.beneficiary")}</dt>
          <dd>{receipt.counterparty}</dd>
          <dt>{t("payments.amount")}</dt>
          <dd>
            <UI.Money
              minorUnits={receipt.amount.minorUnits}
              currency={receipt.amount.currency}
            />
          </dd>
          <dt>{t("payments.reference")}</dt>
          <dd>{receipt.reference}</dd>
          <dt>{t("payments.journalRef")}</dt>
          <dd className="pay-mono">{receipt.journalTransactionId}</dd>
        </dl>
        <div className="dialog-actions">
          <UI.Button type="button" variant="primary" onClick={onDismiss}>
            {t("payments.done")}
          </UI.Button>
        </div>
      </UI.Dialog>
    );
  };
})();
