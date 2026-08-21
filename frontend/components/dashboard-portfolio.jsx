(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASH = (GEMS.dashboardUi = GEMS.dashboardUi || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const { useState } = React;

  const ACCOUNT_TYPES = ["current", "savings", "deposit", "invest"];
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

  function accountLine(account) {
    return DASH.accountLabel(account) + " — " + DASH.formatMinor(account.minor) + " " + account.cur;
  }

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
    const [typeKey, setTypeKey] = useState("current");
    const [cur, setCur] = useState("RON");
    const [fundFromId, setFundFromId] = useState("");
    const [amount, setAmount] = useState("");

    const sources = accounts.filter((account) => account.cur === cur);
    const from = sources.find((account) => account.id === fundFromId) || null;
    const amountMinor = DASH.parseMinor(amount);
    const shortfall = from && amountMinor != null && amountMinor > from.minor ? amountMinor - from.minor : null;
    const ready = shortfall == null && (!from || amountMinor == null || amountMinor > 0);

    const submit = () => {
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
        subtitle={t("dashboard.openAccount.subtitle")}
        onClose={onClose}
        action={t("dashboard.openAccount.submit")}
        actionDisabled={!ready}
        onAction={submit}
      >
        <div className="dash-field-grid">
          <UI.Field id="open-type" label={t("dashboard.openAccount.type")}>
            <UI.Select id="open-type" value={typeKey} onChange={(event) => setTypeKey(event.target.value)}>
              {ACCOUNT_TYPES.map((key) => (
                <option key={key} value={key}>{t("dashboard.accountType." + key)}</option>
              ))}
            </UI.Select>
          </UI.Field>
          <UI.Field id="open-currency" label={t("dashboard.payDialog.currency")}>
            <UI.Select id="open-currency" value={cur} onChange={(event) => { setCur(event.target.value); setFundFromId(""); }}>
              {CURRENCIES.map((code) => <option key={code} value={code}>{code}</option>)}
            </UI.Select>
          </UI.Field>
        </div>

        <UI.Field id="open-fund" label={t("dashboard.openAccount.fundFrom")} hint={t("dashboard.openAccount.fundHint")}>
          <UI.Select id="open-fund" value={fundFromId} onChange={(event) => setFundFromId(event.target.value)}>
            <option value="">{t("dashboard.openAccount.noFunding")}</option>
            {sources.map((account) => (
              <option key={account.id} value={account.id}>{accountLine(account)}</option>
            ))}
          </UI.Select>
        </UI.Field>

        {from ? (
          <AmountField
            id="open-amount"
            label={t("dashboard.payDialog.amount")}
            value={amount}
            onChange={setAmount}
            account={from}
            shortfall={shortfall}
          />
        ) : null}
      </Dialog>
    );
  };

  DASH.NewDepositDialog = function NewDepositDialog({ accounts, onClose, onSubmit }) {
    const [kind, setKind] = useState("term");
    const [name, setName] = useState("");
    const [fromId, setFromId] = useState(accounts[0].id);
    const [amount, setAmount] = useState("");
    const [months, setMonths] = useState(String(DATA.depositTerms[2].months));
    const [target, setTarget] = useState("");

    const from = accounts.find((account) => account.id === fromId) || accounts[0];
    const amountMinor = DASH.parseMinor(amount);
    const targetMinor = DASH.parseMinor(target);
    const shortfall = amountMinor != null && amountMinor > from.minor ? amountMinor - from.minor : null;

    const term = DATA.depositTerms.find((option) => String(option.months) === months) || DATA.depositTerms[2];
    const rateBps = kind === "term" ? term.rateBps : kind === "savings" ? 225 : 300;

    const ready = name.trim() !== ""
      && amountMinor > 0
      && shortfall == null
      && (kind !== "goal" || targetMinor > 0);

    const submit = () => {
      onSubmit({
        deposit: {
          id: "dep-" + Date.now(),
          kind,
          name: name.trim(),
          rateBps,
          matures: kind === "savings" ? null : DASH.addMonths(new Date(), kind === "term" ? term.months : 24),
          minor: amountMinor,
          targetMinor: kind === "goal" ? targetMinor : null,
          cur: from.cur,
        },
        fromId: from.id,
        amountMinor,
      });
    };

    const kinds = [
      { value: "term", label: t("dashboard.deposit.kind.term") },
      { value: "savings", label: t("dashboard.deposit.kind.savings") },
      { value: "goal", label: t("dashboard.deposit.kind.goal") },
    ];

    return (
      <Dialog
        labelledBy="new-deposit-title"
        title={t("dashboard.portfolio.newDeposit")}
        subtitle={t("dashboard.deposit.subtitle")}
        onClose={onClose}
        action={t("dashboard.deposit.submit")}
        actionDisabled={!ready}
        onAction={submit}
      >
        <DASH.SegmentedControl className="dash-seg-full" options={kinds} value={kind} onChange={setKind} label={t("dashboard.deposit.kindLabel")} />

        <UI.Field id="deposit-name" label={t("dashboard.deposit.name")}>
          <UI.TextInput id="deposit-name" value={name} placeholder={t("dashboard.deposit.namePh")} onChange={(event) => setName(event.target.value)} />
        </UI.Field>

        <UI.Field id="deposit-from" label={t("dashboard.deposit.fundFrom")}>
          <UI.Select id="deposit-from" value={from.id} onChange={(event) => setFromId(event.target.value)}>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>{DASH.accountLabel(account)}</option>
            ))}
          </UI.Select>
        </UI.Field>

        <AmountField
          id="deposit-amount"
          label={t("dashboard.deposit.openingAmount")}
          value={amount}
          onChange={setAmount}
          account={from}
          shortfall={shortfall}
        />

        {kind === "term" ? (
          <UI.Field id="deposit-term" label={t("dashboard.deposit.term")}>
            <UI.Select id="deposit-term" value={months} onChange={(event) => setMonths(event.target.value)}>
              {DATA.depositTerms.map((option) => (
                <option key={option.months} value={String(option.months)}>
                  {t("dashboard.deposit.months", { n: option.months }) + " — " + DASH.formatRate(option.rateBps)}
                </option>
              ))}
            </UI.Select>
          </UI.Field>
        ) : null}

        {kind === "goal" ? (
          <UI.Field id="deposit-target" label={t("dashboard.deposit.target")}>
            <UI.TextInput id="deposit-target" inputMode="decimal" value={target} placeholder="0,00" onChange={(event) => setTarget(event.target.value)} />
          </UI.Field>
        ) : null}

        <div className="dash-balance-line" role="status">
          {t("dashboard.deposit.rateNote", { rate: DASH.formatRate(rateBps) })}
        </div>
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
                <option key={item.id} value={item.id}>{accountLine(item)}</option>
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
              <option key={item.id} value={item.id}>
                {item.name + " — " + DASH.formatMinor(item.unitPriceMinor) + " " + item.cur}
              </option>
            ))}
          </UI.Select>
        </UI.Field>

        <UI.Field id="invest-account" label={buying ? t("dashboard.deposit.fundFrom") : t("dashboard.deposit.payInto")}>
          <UI.Select id="invest-account" value={account.id} onChange={(event) => setAccountId(event.target.value)}>
            {accounts.map((item) => (
              <option key={item.id} value={item.id}>{accountLine(item)}</option>
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
    const [productId, setProductId] = useState(DATA.creditProducts[0].id);
    const [amount, setAmount] = useState("");
    const [months, setMonths] = useState(String(DATA.creditProducts[0].terms[4]));
    const [purpose, setPurpose] = useState("");
    const [payoutId, setPayoutId] = useState(accounts[0].id);

    const product = DATA.creditProducts.find((item) => item.id === productId) || DATA.creditProducts[0];
    const payout = accounts.find((account) => account.id === payoutId) || accounts[0];
    const amountMinor = DASH.parseMinor(amount);
    const overMax = amountMinor != null && amountMinor > product.maxMinor ? amountMinor - product.maxMinor : null;
    const ready = amountMinor > 0 && overMax == null;

    const selectProduct = (id) => {
      const next = DATA.creditProducts.find((item) => item.id === id) || DATA.creditProducts[0];
      setProductId(id);
      setMonths(next.terms.length ? String(next.terms[next.terms.length - 1]) : "");
    };

    const submit = () => {
      onSubmit({
        id: "app-" + Date.now(),
        productId: product.id,
        kind: product.kind,
        amountMinor,
        termMonths: product.terms.length ? Number(months) : null,
        rateBps: product.rateBps,
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
              <option key={item.id} value={item.id}>
                {t("dashboard.credit.name." + item.id) + " — " + DASH.formatRate(item.rateBps)}
              </option>
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
          <UI.Field id="credit-term" label={t("dashboard.credit.term")}>
            <UI.Select id="credit-term" value={months} onChange={(event) => setMonths(event.target.value)}>
              {product.terms.map((option) => (
                <option key={option} value={String(option)}>{t("dashboard.deposit.months", { n: option })}</option>
              ))}
            </UI.Select>
          </UI.Field>
        ) : null}

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
