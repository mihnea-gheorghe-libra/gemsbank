(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASH = (GEMS.dashboardUi = GEMS.dashboardUi || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const { useState, useEffect, useRef, useMemo } = React;

  function accountLabel(account) {
    return t("dashboard.accountType." + account.typeKey) + " · " + account.cur + " · " + account.ibanShort;
  }

  function accountBalanceOption(account) {
    return accountLabel(account) + " — " + DASH.formatMinor(account.minor) + " " + account.cur;
  }

  const NAV_ICONS = {
    home: "LayoutGrid",
    payments: "ArrowLeftRight",
    chat: "MessageCircle",
    portfolio: "PieChart",
    cards: "CreditCard",
    analytics: "BarChart3",
    settings: "Settings",
  };

  DASH.Sidebar = function Sidebar({ screen, onNavigate, onSignOut }) {
    return (
      <nav className="dash-sidebar" aria-label={t("dashboard.navLabel")}>
        <div className="dash-sidebar-brand">{t("brand")}</div>

        {DATA.navItems.map((item) => {
          const active = item.key === screen;
          return (
            <button
              key={item.key}
              type="button"
              className={UI.classNames("dash-nav-item", active && "is-active")}
              aria-current={active ? "page" : undefined}
              onClick={() => onNavigate(item.key)}
            >
              <UI.Icon name={NAV_ICONS[item.key]} size={17} />
              <span>{t("dashboard.nav." + item.key)}</span>
              {active ? <span className="dash-nav-dot" aria-hidden="true" /> : null}
            </button>
          );
        })}

        <div className="dash-sidebar-foot">
          <div className="hr" />
          <UI.Plate style={{ padding: 11 }}>
            <UI.Kicker style={{ marginBottom: 4 }}>{t("dashboard.agentsOnline.title")}</UI.Kicker>
            <div className="text-muted" style={{ fontSize: 12 }}>{t("dashboard.agentsOnline.note")}</div>
          </UI.Plate>
          <UI.Button type="button" variant="ghost" style={{ alignSelf: "flex-start", padding: 0, gap: 6 }} onClick={onSignOut}>
            <UI.Icon name="LogOut" size={15} />
            {t("dashboard.signOut")}
          </UI.Button>
        </div>
      </nav>
    );
  };

  DASH.Topbar = function Topbar({ screen, username, me, onOpenSettings, onSignOut }) {
    const [menuOpen, setMenuOpen] = useState(false);
    const containerRef = useRef(null);

    useEffect(() => {
      if (!menuOpen) return undefined;
      function onPointerDown(event) {
        if (containerRef.current && !containerRef.current.contains(event.target)) {
          setMenuOpen(false);
        }
      }
      function onKeyDown(event) {
        if (event.key === "Escape") setMenuOpen(false);
      }
      document.addEventListener("mousedown", onPointerDown);
      document.addEventListener("keydown", onKeyDown);
      return () => {
        document.removeEventListener("mousedown", onPointerDown);
        document.removeEventListener("keydown", onKeyDown);
      };
    }, [menuOpen]);

    return (
      <header className="dash-topbar">
        <div>
          <div className="dash-topbar-title">{t("dashboard.greeting", { username })}</div>
          <div className="dash-topbar-tag">{t("dashboard.tag." + screen)}</div>
        </div>

        <div className="dash-search-wrap">
          <UI.Icon name="Search" size={16} />
          <UI.TextInput
            className="input dash-search"
            type="search"
            aria-label={t("dashboard.searchPlaceholder")}
            placeholder={t("dashboard.searchPlaceholder")}
          />
        </div>

        <div className="dash-profile" ref={containerRef}>
          <button
            type="button"
            className="dash-avatar"
            aria-haspopup="true"
            aria-expanded={menuOpen}
            aria-label={t("dashboard.profileMenu.trigger")}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {(username || "").slice(0, 2).toUpperCase()}
            <span className="dash-avatar-dot" aria-hidden="true" />
          </button>

          {menuOpen ? (
            <div className="dash-profile-menu elev-md plate" role="menu">
              <div className="dash-profile-name">{me ? me.fullName : ""}</div>
              <div className="hr" />
              <UI.Button
                type="button"
                variant="secondary"
                role="menuitem"
                style={{ justifyContent: "flex-start", gap: 8 }}
                onClick={() => { setMenuOpen(false); onOpenSettings(); }}
              >
                <UI.Icon name="Settings" size={15} />
                {t("dashboard.profileMenu.settings")}
              </UI.Button>
              <UI.Button
                type="button"
                variant="secondary"
                role="menuitem"
                style={{ justifyContent: "flex-start", gap: 8 }}
                onClick={() => { setMenuOpen(false); onSignOut(); }}
              >
                <UI.Icon name="LogOut" size={15} />
                {t("dashboard.signOut")}
              </UI.Button>
            </div>
          ) : null}
        </div>
      </header>
    );
  };

  DASH.AgentDock = function AgentDock({ open, username, onOpen, onClose, onExpand, onPrompt }) {
    if (!open) {
      return (
        <UI.Button type="button" variant="primary" className="dash-dock-fab elev-md" style={{ gap: 8 }} onClick={onOpen}>
          <UI.Icon name="Sparkles" size={16} />
          {t("dashboard.chat.askGems")}
        </UI.Button>
      );
    }
    return (
      <UI.Plate className="dash-dock elev-lg" aria-label={t("dashboard.chat.askGems")}>
        <div className="dash-dock-head">
          <span className="dash-agent-dot" aria-hidden="true" />
          <span className="kicker">{t("dashboard.nav.chat")}</span>
          <UI.Button type="button" variant="ghost" style={{ marginLeft: "auto" }} onClick={onExpand}>
            <UI.Icon name="Maximize2" size={14} />
            {t("dashboard.chat.dockExpand")}
          </UI.Button>
          <UI.Button type="button" variant="ghost" aria-label={t("dashboard.chat.dockCloseLabel")} onClick={onClose}>
            <UI.Icon name="X" size={15} />
          </UI.Button>
        </div>
        <div style={{ padding: 14 }}>
          <p style={{ fontSize: 13, lineHeight: 1.6, margin: 0 }}>
            {t("dashboard.chat.dockGreeting", { username, balance: DATA.totalBalance })}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 12 }}>
            <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8 }} onClick={() => onPrompt("pay")}>
              <UI.Icon name="Send" size={14} />
              {t("dashboard.chat.promptPay")}
            </UI.Button>
            <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start", gap: 8 }} onClick={() => onPrompt("recurring")}>
              <UI.Icon name="Repeat" size={14} />
              {t("dashboard.chat.promptRecurring")}
            </UI.Button>
          </div>
        </div>
      </UI.Plate>
    );
  };

  function BalanceLine({ account, shortfallMinor }) {
    const available = DASH.formatMinor(account.minor) + " " + account.cur;
    if (shortfallMinor == null) {
      return (
        <div className="dash-balance-line" role="status">
          {t("dashboard.payDialog.availableBalance", { amount: available })}
        </div>
      );
    }
    return (
      <div className="dash-balance-line is-short" role="alert">
        {t("dashboard.payDialog.insufficient", {
          amount: available,
          missing: DASH.formatMinor(shortfallMinor) + " " + account.cur,
        })}
      </div>
    );
  }

  DASH.NewPaymentDialog = function NewPaymentDialog({ payType, onPayType, accounts, templates, prefill, onClose, onSubmit }) {
    const [fromId, setFromId] = useState(() => (prefill && prefill.fromId) || accounts[0].id);
    const [toId, setToId] = useState("");
    const [beneficiary, setBeneficiary] = useState((prefill && prefill.beneficiary) || "");
    const [iban, setIban] = useState((prefill && prefill.iban) || "");
    const [amount, setAmount] = useState("");
    const [reference, setReference] = useState((prefill && prefill.reference) || "");
    const [saveTemplate, setSaveTemplate] = useState(false);
    const [templateName, setTemplateName] = useState("");

    const from = accounts.find((account) => account.id === fromId) || accounts[0];
    const internalTargets = accounts.filter((account) => account.id !== from.id && account.cur === from.cur);
    const to = internalTargets.find((account) => account.id === toId) || null;

    const amountMinor = DASH.parseMinor(amount);
    const shortfall = amountMinor != null && amountMinor > from.minor ? amountMinor - from.minor : null;

    const types = [
      { value: "iban", label: t("dashboard.payDialog.iban") },
      { value: "internal", label: t("dashboard.payDialog.internal") },
    ];

    const applyTemplate = (template) => {
      onPayType("iban");
      setBeneficiary(template.beneficiary);
      setIban(template.iban);
      setReference(template.reference || "");
      const match = accounts.find((account) => account.cur === template.cur);
      if (match) setFromId(match.id);
    };

    const ready = payType === "internal"
      ? Boolean(to) && amountMinor > 0 && shortfall == null
      : beneficiary.trim() !== "" && iban.trim() !== "" && amountMinor > 0 && shortfall == null;

    const submit = () => {
      onSubmit({
        payType,
        fromId: from.id,
        toId: to ? to.id : null,
        beneficiary: payType === "internal" ? accountLabel(to) : beneficiary.trim(),
        iban: payType === "internal" ? to.iban : iban.trim(),
        amountMinor,
        currency: from.cur,
        reference: reference.trim(),
        template: payType === "iban" && saveTemplate && templateName.trim()
          ? {
              id: "tpl-" + Date.now(),
              name: templateName.trim(),
              beneficiary: beneficiary.trim(),
              iban: iban.trim(),
              cur: from.cur,
              reference: reference.trim(),
            }
          : null,
      });
    };

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="pay-dialog-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="pay-dialog-title" style={{ margin: 0 }}>{t("dashboard.payDialog.title")}</h2>
          <DASH.SegmentedControl className="dash-seg-full" options={types} value={payType} onChange={onPayType} label={t("dashboard.payDialog.title")} />

          {payType === "iban" && templates.length ? (
            <div>
              <UI.Kicker style={{ marginBottom: 8 }}>{t("dashboard.payDialog.templatesTitle")}</UI.Kicker>
              <div className="dash-template-chips">
                {templates.map((template) => (
                  <button key={template.id} type="button" className="dash-template-chip" onClick={() => applyTemplate(template)}>
                    <span className="dash-template-chip-name">{template.name}</span>
                    <span className="dash-template-chip-sub">{template.beneficiary}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <UI.Field id="pay-from" label={t("dashboard.payDialog.from")}>
            <UI.Select id="pay-from" value={from.id} onChange={(event) => { setFromId(event.target.value); setToId(""); }}>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>{accountLabel(account)}</option>
              ))}
            </UI.Select>
          </UI.Field>

          <BalanceLine account={from} shortfallMinor={shortfall} />

          {payType === "internal" ? (
            <UI.Field id="pay-to" label={t("dashboard.payDialog.toOwn")} hint={t("dashboard.payDialog.sameCurrency")}>
              <UI.Select id="pay-to" value={toId} onChange={(event) => setToId(event.target.value)}>
                <option value="">{t("dashboard.payDialog.choose")}</option>
                {internalTargets.map((account) => (
                  <option key={account.id} value={account.id}>{accountBalanceOption(account)}</option>
                ))}
              </UI.Select>
            </UI.Field>
          ) : (
            <div className="dash-field-grid">
              <UI.Field id="pay-beneficiary" label={t("dashboard.payDialog.beneficiary")}>
                <UI.TextInput id="pay-beneficiary" value={beneficiary} placeholder={t("dashboard.payDialog.beneficiaryPh")} onChange={(event) => setBeneficiary(event.target.value)} />
              </UI.Field>
              <UI.Field id="pay-iban" label={t("dashboard.payDialog.ibanLabel")}>
                <UI.TextInput id="pay-iban" value={iban} placeholder={t("dashboard.payDialog.ibanPh")} onChange={(event) => setIban(event.target.value)} />
              </UI.Field>
            </div>
          )}

          <div className="dash-field-grid">
            <UI.Field id="pay-amount" label={t("dashboard.payDialog.amount")}>
              <UI.TextInput
                id="pay-amount"
                className={shortfall == null ? undefined : "is-invalid"}
                aria-invalid={shortfall == null ? undefined : "true"}
                inputMode="decimal"
                value={amount}
                placeholder="0,00"
                onChange={(event) => setAmount(event.target.value)}
              />
            </UI.Field>
            <UI.Field id="pay-currency" label={t("dashboard.payDialog.currency")}>
              <UI.TextInput id="pay-currency" value={from.cur} readOnly />
            </UI.Field>
          </div>

          <UI.Field id="pay-reference" label={t("dashboard.payDialog.reference")}>
            <UI.TextInput id="pay-reference" value={reference} placeholder={t("dashboard.payDialog.referencePh")} onChange={(event) => setReference(event.target.value)} />
          </UI.Field>

          {payType === "iban" ? (
            <div className="dash-save-template">
              <label className="dash-check">
                <input type="checkbox" checked={saveTemplate} onChange={(event) => setSaveTemplate(event.target.checked)} />
                {t("dashboard.payDialog.saveTemplate")}
              </label>
              {saveTemplate ? (
                <UI.TextInput
                  value={templateName}
                  placeholder={t("dashboard.templates.namePh")}
                  aria-label={t("dashboard.templates.name")}
                  onChange={(event) => setTemplateName(event.target.value)}
                />
              ) : null}
            </div>
          ) : null}

          <p className="text-muted" style={{ fontSize: 12, margin: 0 }}>{t("dashboard.payDialog.agentCheck")}</p>

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={submit}>{t("dashboard.payDialog.continueBtn")}</UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  DASH.SplitBillDialog = function SplitBillDialog({ accounts, onClose, onSubmit }) {
    const [accountId, setAccountId] = useState(accounts[0].id);
    const [total, setTotal] = useState("");
    const [reference, setReference] = useState("");
    const [includeMe, setIncludeMe] = useState(true);
    const [people, setPeople] = useState([
      { key: "p1", name: "", amount: "" },
      { key: "p2", name: "", amount: "" },
    ]);

    const account = accounts.find((item) => item.id === accountId) || accounts[0];
    const totalMinor = DASH.parseMinor(total);

    const allocated = useMemo(
      () => people.reduce((sum, person) => sum + (DASH.parseMinor(person.amount) || 0), 0),
      [people]
    );
    const myShare = totalMinor == null ? 0 : Math.max(totalMinor - allocated, 0);
    const overAllocated = totalMinor != null && allocated > totalMinor;

    const updatePerson = (key, patch) => {
      setPeople((list) => list.map((person) => (person.key === key ? Object.assign({}, person, patch) : person)));
    };

    const addPerson = () => {
      setPeople((list) => list.concat([{ key: "p" + Date.now(), name: "", amount: "" }]));
    };

    const removePerson = (key) => {
      setPeople((list) => (list.length > 1 ? list.filter((person) => person.key !== key) : list));
    };

    const splitEqually = () => {
      if (totalMinor == null) return;
      const shares = DASH.splitEvenly(totalMinor, people.length + (includeMe ? 1 : 0));
      setPeople((list) => list.map((person, index) => Object.assign({}, person, { amount: DASH.formatMinor(shares[index]) })));
    };

    const ready = totalMinor > 0
      && !overAllocated
      && people.every((person) => person.name.trim() !== "" && DASH.parseMinor(person.amount) > 0);

    const submit = () => {
      onSubmit({
        id: "split-" + Date.now(),
        accountId: account.id,
        currency: account.cur,
        totalMinor,
        reference: reference.trim() || t("dashboard.split.defaultReference"),
        myShareMinor: includeMe ? myShare : 0,
        participants: people.map((person) => ({
          key: person.key,
          name: person.name.trim(),
          minor: DASH.parseMinor(person.amount),
          settled: false,
        })),
      });
    };

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="split-dialog-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="split-dialog-title" style={{ margin: 0 }}>{t("dashboard.split.title")}</h2>
          <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>{t("dashboard.split.subtitle")}</p>

          <div className="dash-field-grid">
            <UI.Field id="split-total" label={t("dashboard.split.total")}>
              <UI.TextInput id="split-total" inputMode="decimal" value={total} placeholder="0,00" onChange={(event) => setTotal(event.target.value)} />
            </UI.Field>
            <UI.Field id="split-account" label={t("dashboard.split.collectInto")}>
              <UI.Select id="split-account" value={account.id} onChange={(event) => setAccountId(event.target.value)}>
                {accounts.map((item) => (
                  <option key={item.id} value={item.id}>{accountLabel(item)}</option>
                ))}
              </UI.Select>
            </UI.Field>
          </div>

          <UI.Field id="split-reference" label={t("dashboard.split.reference")}>
            <UI.TextInput id="split-reference" value={reference} placeholder={t("dashboard.split.referencePh")} onChange={(event) => setReference(event.target.value)} />
          </UI.Field>

          <div className="dash-split-toolbar">
            <label className="dash-check">
              <input type="checkbox" checked={includeMe} onChange={(event) => setIncludeMe(event.target.checked)} />
              {t("dashboard.split.includeMe")}
            </label>
            <UI.Button type="button" variant="secondary" disabled={totalMinor == null} onClick={splitEqually}>
              {t("dashboard.split.splitEqually")}
            </UI.Button>
          </div>

          <div className="dash-split-people">
            {people.map((person, index) => (
              <div className="dash-split-row" key={person.key}>
                <span className="dash-split-num" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <UI.TextInput
                  value={person.name}
                  placeholder={t("dashboard.split.personPh")}
                  aria-label={t("dashboard.split.person", { n: index + 1 })}
                  onChange={(event) => updatePerson(person.key, { name: event.target.value })}
                />
                <UI.TextInput
                  className="dash-split-amount"
                  inputMode="decimal"
                  value={person.amount}
                  placeholder="0,00"
                  aria-label={t("dashboard.split.share", { n: index + 1 })}
                  onChange={(event) => updatePerson(person.key, { amount: event.target.value })}
                />
                <UI.Button
                  type="button"
                  variant="ghost"
                  disabled={people.length === 1}
                  aria-label={t("dashboard.split.removePerson")}
                  onClick={() => removePerson(person.key)}
                >
                  ×
                </UI.Button>
              </div>
            ))}
          </div>

          <UI.Button type="button" variant="secondary" style={{ alignSelf: "flex-start" }} onClick={addPerson}>
            {t("dashboard.split.addPerson")}
          </UI.Button>

          <div className={UI.classNames("dash-balance-line", overAllocated && "is-short")} role="status">
            {totalMinor == null
              ? t("dashboard.split.enterTotal")
              : overAllocated
                ? t("dashboard.split.overAllocated", { amount: DASH.formatMinor(allocated - totalMinor) + " " + account.cur })
                : t("dashboard.split.yourShare", {
                    amount: DASH.formatMinor(myShare) + " " + account.cur,
                    others: DASH.formatMinor(allocated) + " " + account.cur,
                  })}
          </div>

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={submit}>{t("dashboard.split.send")}</UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  DASH.TemplateDialog = function TemplateDialog({ accounts, template, onClose, onSubmit }) {
    const [name, setName] = useState((template && template.name) || "");
    const [beneficiary, setBeneficiary] = useState((template && template.beneficiary) || "");
    const [iban, setIban] = useState((template && template.iban) || "");
    const [cur, setCur] = useState((template && template.cur) || accounts[0].cur);
    const [reference, setReference] = useState((template && template.reference) || "");

    const currencies = accounts
      .map((account) => account.cur)
      .filter((value, index, list) => list.indexOf(value) === index);

    const ready = name.trim() !== "" && beneficiary.trim() !== "" && iban.trim() !== "";

    const submit = () => {
      onSubmit({
        id: (template && template.id) || "tpl-" + Date.now(),
        name: name.trim(),
        beneficiary: beneficiary.trim(),
        iban: iban.trim(),
        cur,
        reference: reference.trim(),
      });
    };

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="tpl-dialog-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="tpl-dialog-title" style={{ margin: 0 }}>
            {template ? t("dashboard.templates.editTitle") : t("dashboard.templates.newTitle")}
          </h2>
          <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>{t("dashboard.templates.subtitle")}</p>

          <UI.Field id="tpl-name" label={t("dashboard.templates.name")}>
            <UI.TextInput id="tpl-name" value={name} placeholder={t("dashboard.templates.namePh")} onChange={(event) => setName(event.target.value)} />
          </UI.Field>

          <div className="dash-field-grid">
            <UI.Field id="tpl-beneficiary" label={t("dashboard.payDialog.beneficiary")}>
              <UI.TextInput id="tpl-beneficiary" value={beneficiary} placeholder={t("dashboard.payDialog.beneficiaryPh")} onChange={(event) => setBeneficiary(event.target.value)} />
            </UI.Field>
            <UI.Field id="tpl-currency" label={t("dashboard.payDialog.currency")}>
              <UI.Select id="tpl-currency" value={cur} onChange={(event) => setCur(event.target.value)}>
                {currencies.map((code) => <option key={code} value={code}>{code}</option>)}
              </UI.Select>
            </UI.Field>
          </div>

          <UI.Field id="tpl-iban" label={t("dashboard.payDialog.ibanLabel")}>
            <UI.TextInput id="tpl-iban" value={iban} placeholder={t("dashboard.payDialog.ibanPh")} onChange={(event) => setIban(event.target.value)} />
          </UI.Field>

          <UI.Field id="tpl-reference" label={t("dashboard.payDialog.reference")}>
            <UI.TextInput id="tpl-reference" value={reference} placeholder={t("dashboard.payDialog.referencePh")} onChange={(event) => setReference(event.target.value)} />
          </UI.Field>

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={submit}>{t("dashboard.templates.save")}</UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  DASH.accountLabel = accountLabel;
})();
