(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASH = (GEMS.dashboardUi = GEMS.dashboardUi || {});
  const UI = GEMS.ui;
  const AUTH = GEMS.auth;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const api = GEMS.api;
  const { useState, useEffect, useRef, useMemo } = React;

  function accountLabel(account) {
    const name = account.label || t("dashboard.accountType." + account.typeKey);
    return name + " · " + account.cur + " · " + account.ibanShort;
  }

  const NAV_ICONS = {
    home: "LayoutGrid",
    payments: "ArrowLeftRight",
    chat: "MessageCircle",
    accounts: "Wallet",
    portfolio: "PieChart",
    cards: "CreditCard",
    analytics: "BarChart3",
    education: "GraduationCap",
    education_health: "Activity",
    education_goals: "Target",
    education_chat: "Bot",
    education_lessons: "BookOpen",
    settings: "Settings",
  };

  const EDUCATION_SUBITEMS = [
    { key: "education_health", icon: "Activity", labelKey: "dashboard.nav.education_health" },
    { key: "education_goals", icon: "Target", labelKey: "dashboard.nav.education_goals" },
    { key: "education_chat", icon: "Bot", labelKey: "dashboard.nav.education_chat" },
  ];

  DASH.Sidebar = function Sidebar({ screen, onNavigate, onSignOut }) {
    const isEduScreen = (screen || "").startsWith("education");
    const [educationExpanded, setEducationExpanded] = useState(isEduScreen);

    useEffect(() => {
      if (isEduScreen) {
        setEducationExpanded(true);
      }
    }, [isEduScreen]);

    return (
      <nav className="dash-sidebar" aria-label={t("dashboard.navLabel")}>
        <div className="dash-sidebar-brand"><UI.Logo size={22} /></div>

        {DATA.navItems.map((item) => {
          if (item.key === "education") {
            return (
              <div
                key="education"
                className={UI.classNames("dash-nav-dropdown-group", isEduScreen && "has-active-child")}
              >
                <button
                  type="button"
                  className={UI.classNames(
                    "dash-nav-item",
                    "dash-nav-dropdown-trigger",
                    isEduScreen && "is-active",
                    educationExpanded && "is-expanded"
                  )}
                  aria-expanded={educationExpanded}
                  aria-controls="dash-education-subnav"
                  onClick={() => {
                    setEducationExpanded((prev) => !prev);
                    if (!isEduScreen) {
                      onNavigate("education_health");
                    }
                  }}
                >
                  <UI.Icon name={NAV_ICONS.education} size={17} />
                  <span className="dash-nav-item-label">{t("dashboard.nav.education")}</span>
                  <UI.Icon
                    name={educationExpanded ? "ChevronDown" : "ChevronRight"}
                    size={14}
                    className="dash-nav-chevron"
                  />
                </button>

                {educationExpanded ? (
                  <div id="dash-education-subnav" className="dash-nav-sublist" role="region">
                    {EDUCATION_SUBITEMS.map((sub) => {
                      const isSubActive =
                        screen === sub.key || (screen === "education" && sub.key === "education_health");
                      return (
                        <button
                          key={sub.key}
                          type="button"
                          className={UI.classNames("dash-nav-subitem", isSubActive && "is-active")}
                          aria-current={isSubActive ? "page" : undefined}
                          onClick={() => onNavigate(sub.key)}
                        >
                          <UI.Icon name={sub.icon} size={13} className="dash-nav-subicon" />
                          <span>{t(sub.labelKey)}</span>
                          {isSubActive ? <span className="dash-nav-dot" aria-hidden="true" /> : null}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          }

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

          <UI.Button type="button" variant="ghost" style={{ alignSelf: "flex-start", padding: 0, gap: 6 }} onClick={onSignOut}>
            <UI.Icon name="LogOut" size={15} />
            {t("dashboard.signOut")}
          </UI.Button>
        </div>
      </nav>
    );
  };

  function formatNotificationWhen(iso) {
    const moment = new Date(iso);
    if (Number.isNaN(moment.getTime())) return "";
    return moment.toLocaleString(GEMS.i18n.locale === "ro" ? "ro-RO" : "en-GB", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function notificationText(item) {
    const payload = item.payload || {};
    switch (item.type) {
      case "credit_approved":
      case "credit_rejected":
        return t("dashboard.notifications.types." + item.type, { reason: payload.reason || "" });
      case "transaction_accepted":
        return t("dashboard.notifications.types.transaction_accepted", {
          amount: DASH.formatMinor(payload.amountMinorUnits || 0) + " " + (payload.currency || ""),
        });
      case "account_frozen":
        return t("dashboard.notifications.types.account_frozen", { reason: payload.reason || "" });
      case "card_frozen":
        return t("dashboard.notifications.types.card_frozen");
      case "goal_achieved":
        return t("dashboard.notifications.types.goal_achieved", {
          name: payload.name || "",
          target: DASH.formatMinor(payload.targetMinorUnits || 0) + " " + (payload.currency || ""),
        });
      case "goal_invite_sent":
        return t("dashboard.notifications.types.goal_invite_sent", {
          inviter: payload.inviterName || "",
          goal: payload.goalName || "",
        });
      case "goal_invite_accepted":
        return t("dashboard.notifications.types.goal_invite_accepted", {
          invitee: payload.inviteeUsername || "",
          goal: payload.goalName || "",
        });
      case "goal_invite_declined":
        return t("dashboard.notifications.types.goal_invite_declined", {
          invitee: payload.inviteeUsername || "",
          goal: payload.goalName || "",
        });
      default:
        return "";
    }
  }

  function inviteShareText(payload) {
    if (!payload) return "";
    if (payload.shareKind === "fixed" && payload.shareAmountMinorUnits) {
      return DASH.formatMinor(payload.shareAmountMinorUnits) + " " + (payload.currency || "");
    }
    if (payload.shareKind === "percent" && payload.sharePercentBp) {
      return Math.round(payload.sharePercentBp / 100) + "%";
    }
    return "";
  }

  DASH.NotificationBell = function NotificationBell({ notifications, unreadCount, onOpen }) {
    const [open, setOpen] = useState(false);
    const containerRef = useRef(null);
    const [respondedIds, setRespondedIds] = useState({});
    const [busyInviteId, setBusyInviteId] = useState(null);
    const items = notifications || [];

    const respondedFromFeed = useMemo(() => {
      const set = {};
      items.forEach((item) => {
        if (item.type === "goal_invite_responded" && item.payload && item.payload.inviteId) {
          set[item.payload.inviteId] = true;
        }
      });
      return set;
    }, [items]);

    const visibleItems = items.filter((item) => item.type !== "goal_invite_responded");

    function respondToInvite(inviteId, accept) {
      setBusyInviteId(inviteId);
      api
        .respondToGoalInvite(inviteId, accept)
        .then(() => {
          setBusyInviteId(null);
          setRespondedIds((previous) => ({ ...previous, [inviteId]: true }));
        })
        .catch(() => {
          setBusyInviteId(null);
        });
    }

    useEffect(() => {
      if (!open) return undefined;
      function onPointerDown(event) {
        if (containerRef.current && !containerRef.current.contains(event.target)) {
          setOpen(false);
        }
      }
      function onKeyDown(event) {
        if (event.key === "Escape") setOpen(false);
      }
      document.addEventListener("mousedown", onPointerDown);
      document.addEventListener("keydown", onKeyDown);
      return () => {
        document.removeEventListener("mousedown", onPointerDown);
        document.removeEventListener("keydown", onKeyDown);
      };
    }, [open]);

    return (
      <div className="dash-notif" ref={containerRef}>
        <button
          type="button"
          className="dash-notif-btn"
          aria-haspopup="true"
          aria-expanded={open}
          aria-label={t("dashboard.notifications.trigger")}
          onClick={() => {
            setOpen((value) => {
              const next = !value;
              if (next) onOpen();
              return next;
            });
          }}
        >
          <UI.Icon name="Bell" size={17} />
          {unreadCount > 0 ? (
            <span className="dash-notif-badge" aria-hidden="true">{unreadCount > 9 ? "9+" : unreadCount}</span>
          ) : null}
        </button>

        {open ? (
          <div className="dash-notif-panel elev-md plate" role="menu">
            <div className="dash-notif-panel-title">{t("dashboard.notifications.title")}</div>
            {visibleItems.length === 0 ? (
              <div className="dash-notif-empty">{t("dashboard.notifications.empty")}</div>
            ) : (
              <ul className="dash-notif-list">
                {visibleItems.map((item) => {
                  const inviteId = item.payload && item.payload.inviteId;
                  const isPendingInvite =
                    item.type === "goal_invite_sent" &&
                    inviteId &&
                    !respondedFromFeed[inviteId] &&
                    !respondedIds[inviteId];
                  const share = inviteShareText(item.payload);
                  return (
                    <li
                      key={item.id}
                      className={UI.classNames("dash-notif-item", !item.read && "is-unread")}
                      role="menuitem"
                    >
                      <span className="dash-notif-item-text">{notificationText(item)}</span>
                      {item.type === "goal_invite_sent" && share ? (
                        <span className="dash-notif-item-share">{share}</span>
                      ) : null}
                      <span className="dash-notif-item-time">{formatNotificationWhen(item.occurredAt)}</span>
                      {isPendingInvite ? (
                        <div className="dash-notif-item-actions">
                          <UI.Button
                            type="button"
                            variant="primary"
                            disabled={busyInviteId === inviteId}
                            onClick={() => respondToInvite(inviteId, true)}
                          >
                            {t("dashboard.notifications.acceptInvite")}
                          </UI.Button>
                          <UI.Button
                            type="button"
                            variant="secondary"
                            disabled={busyInviteId === inviteId}
                            onClick={() => respondToInvite(inviteId, false)}
                          >
                            {t("dashboard.notifications.declineInvite")}
                          </UI.Button>
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ) : null}
      </div>
    );
  };

  DASH.Topbar = function Topbar({
    screen,
    username,
    me,
    theme,
    onTheme,
    onOpenSettings,
    onSignOut,
    notifications,
    unreadNotifications,
    onOpenNotifications,
  }) {
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

<div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 16 }}>
          <DASH.NotificationBell
            notifications={notifications}
            unreadCount={unreadNotifications}
            onOpen={onOpenNotifications}
          />

          <UI.Button type="button" onClick={() => onTheme(theme === "dark" ? "light" : "dark")}>
            <UI.Icon name={theme === "dark" ? "Sun" : "Moon"} size={16} />
          </UI.Button>

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
              <div className="dash-profile-name">{me ? GEMS.people.fullName((me.identity && me.identity.fullName) || me.fullName) : ""}</div>
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
        </div>
      </header>
    );
  };

  DASH.AgentDock = function AgentDock({ open, username, screen, onOpen, onClose, onExpand, onPrompt }) {
    if (!open) {
      return (
        <UI.Button type="button" variant="primary" className="dash-dock-fab elev-md" style={{ gap: 8 }} onClick={onOpen}>
          <UI.Icon name="Sparkles" size={16} />
          {t("dashboard.chat.askGems")}
        </UI.Button>
      );
    }
    const promptKeys = DATA.screenPrompts[screen] || DATA.screenPrompts.home;
    const greetingKey = DATA.screenGreetings[screen] || DATA.screenGreetings.home;
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
            {t("dashboard.chat." + greetingKey, { username, balance: DATA.totalBalance })}
          </p>
          <div className="kicker" style={{ marginTop: 14, marginBottom: 7 }}>{t("dashboard.chat.suggestedTitle")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {promptKeys.map((key) => {
              const prompt = DATA.chatPrompts[key];
              if (!prompt) return null;
              return (
                <UI.Button
                  key={key}
                  type="button"
                  variant="secondary"
                  style={{ justifyContent: "flex-start", gap: 8 }}
                  onClick={() => onPrompt(key)}
                >
                  <UI.Icon name={prompt.icon} size={14} />
                  {t("dashboard.chat." + prompt.labelKey)}
                </UI.Button>
              );
            })}
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

  DASH.NewPaymentDialog = function NewPaymentDialog({ payType, onPayType, accounts, templates, prefill, holderName, busy, error, onClose, onSubmit }) {
    const [fromId, setFromId] = useState(() => (prefill && prefill.fromId) || accounts[0].id);
    const [toId, setToId] = useState((prefill && prefill.toId) || "");
    const [beneficiary, setBeneficiary] = useState((prefill && prefill.beneficiary) || "");
    const [iban, setIban] = useState((prefill && prefill.iban) || "");
    const [amount, setAmount] = useState((prefill && prefill.amount) || "");
    const [reference, setReference] = useState((prefill && prefill.reference) || "");
    const [saveTemplate, setSaveTemplate] = useState(false);
    const [templateName, setTemplateName] = useState("");
    const [acknowledgeMismatch, setAcknowledgeMismatch] = useState(false);

    useEffect(() => {
      setToId("");
    }, [payType]);

    const mismatch = Boolean(error && error.details && error.details.payeeCheck === "no_match");

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

    const ready = (payType === "internal"
      ? Boolean(to) && amountMinor > 0 && shortfall == null
      : beneficiary.trim() !== "" && iban.trim() !== "" && amountMinor > 0 && shortfall == null)
      && reference.trim() !== ""
      && (!mismatch || acknowledgeMismatch)
      && !busy;

    const submit = () => {
      onSubmit({
        payType,
        fromId: from.id,
        toId: to ? to.id : null,
        beneficiary: payType === "internal" ? (holderName || accountLabel(to)) : beneficiary.trim(),
        iban: payType === "internal" ? null : iban.trim(),
        amountMinor,
        currency: from.cur,
        reference: reference.trim(),
        acknowledgeMismatch,
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
            <React.Fragment>
              <UI.Field id="pay-to" label={t("dashboard.payDialog.toOwn")} hint={t("dashboard.payDialog.sameCurrency")}>
                <UI.Select id="pay-to" value={toId} onChange={(event) => setToId(event.target.value)}>
                  <option value="">{t("dashboard.payDialog.choose")}</option>
                  {internalTargets.map((account) => (
                    <option key={account.id} value={account.id}>{accountLabel(account)}</option>
                  ))}
                </UI.Select>
              </UI.Field>
              {to ? <BalanceLine account={to} shortfallMinor={null} /> : null}
            </React.Fragment>
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

          {mismatch ? (
            <label className="dash-check">
              <input type="checkbox" checked={acknowledgeMismatch} onChange={(event) => setAcknowledgeMismatch(event.target.checked)} />
              {t("dashboard.payDialog.acknowledgeMismatch")}
            </label>
          ) : null}

          {error ? (
            <div className="dash-balance-line is-short" role="alert">{error.message}</div>
          ) : null}

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={submit}>
              {busy ? t("dashboard.payDialog.sending") : t("dashboard.payDialog.continueBtn")}
            </UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  DASH.SignPaymentDialog = function SignPaymentDialog({ payment, busy, error, onClose, onSubmit }) {
    const [pin, setPin] = useState("");

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="sign-payment-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="sign-payment-title" style={{ margin: 0 }}>{t("dashboard.signDialog.title")}</h2>
          <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>
            {t("dashboard.signDialog.subtitle", {
              who: payment.counterparty,
              amount: DASH.formatMinor(payment.amount.minorUnits) + " " + payment.amount.currency,
            })}
          </p>

          <AUTH.DigitGroup
            label={t("dashboard.signDialog.codeLabel")}
            length={6}
            value={pin}
            onChange={setPin}
            autoFocus
          />

          {error ? (
            <div className="dash-balance-line is-short" role="alert">{error.message}</div>
          ) : null}

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={busy || pin.length !== 6} onClick={() => onSubmit(payment.paymentId, pin)}>
              {busy ? t("dashboard.signDialog.signing") : t("dashboard.signDialog.confirm")}
            </UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  DASH.AddFundsDialog = function AddFundsDialog({ account, busy, error, onClose, onSubmit }) {
    const [amount, setAmount] = useState("");
    const amountMinor = DASH.parseMinor(amount);
    const ready = Boolean(account) && amountMinor > 0 && !busy;

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="add-funds-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="add-funds-title" style={{ margin: 0 }}>{t("dashboard.addFunds.title")}</h2>

          {account ? (
            <UI.Field id="add-funds-amount" label={t("dashboard.addFunds.amount", { currency: account.cur })}>
              <UI.TextInput
                id="add-funds-amount"
                inputMode="decimal"
                value={amount}
                placeholder="0,00"
                onChange={(event) => setAmount(event.target.value)}
              />
            </UI.Field>
          ) : (
            <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>{t("dashboard.addFunds.noAccount")}</p>
          )}

          {error ? (
            <div className="dash-balance-line is-short" role="alert">{error.message}</div>
          ) : null}

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={() => onSubmit(amountMinor)}>
              {busy ? t("dashboard.payDialog.sending") : t("dashboard.addFunds.submit")}
            </UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  function statementRange(period, customFrom, customTo) {
    const today = new Date();
    const toIso = (d) => d.toISOString().slice(0, 10);
    if (period === "month") {
      const from = new Date(today);
      from.setMonth(from.getMonth() - 1);
      return { from: toIso(from), to: toIso(today) };
    }
    if (period === "fiscal") {
      return { from: toIso(new Date(today.getFullYear(), 0, 1)), to: toIso(today) };
    }
    if (period === "all") {
      return { from: null, to: null };
    }
    if (!customFrom || !customTo || customFrom > customTo) return null;
    return { from: customFrom, to: customTo };
  }

  DASH.StatementDialog = function StatementDialog({ account, accounts, busy, error, onClose, onSubmit }) {
    const [accountId, setAccountId] = useState(account ? account.id : (accounts[0] ? accounts[0].id : ""));
    const [format, setFormat] = useState("pdf");
    const [period, setPeriod] = useState("month");
    const [customFrom, setCustomFrom] = useState("");
    const [customTo, setCustomTo] = useState("");

    const selectedAccount = accounts.find((item) => item.id === accountId) || null;

    const formatOptions = [
      { value: "pdf", label: t("dashboard.statement.formatPdf") },
      { value: "csv", label: t("dashboard.statement.formatCsv") },
    ];
    const periodOptions = [
      { value: "month", label: t("dashboard.statement.periodMonth") },
      { value: "fiscal", label: t("dashboard.statement.periodFiscal") },
      { value: "all", label: t("dashboard.statement.periodAll") },
      { value: "custom", label: t("dashboard.statement.periodCustom") },
    ];

    const range = statementRange(period, customFrom, customTo);
    const ready = Boolean(selectedAccount) && Boolean(range) && !busy;

    const submit = () => {
      if (!range || !selectedAccount) return;
      onSubmit({ accountId: selectedAccount.id, format, from: range.from, to: range.to });
    };

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="statement-dialog-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="statement-dialog-title" style={{ margin: 0 }}>{t("dashboard.statement.title")}</h2>

          <UI.Field id="statement-account" label={t("dashboard.statement.account")}>
            <UI.Select id="statement-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
              {accounts.map((item) => (
                <option key={item.id} value={item.id}>{accountLabel(item)}</option>
              ))}
            </UI.Select>
          </UI.Field>

          <DASH.SegmentedControl
            className="dash-seg-full"
            options={formatOptions}
            value={format}
            onChange={setFormat}
            label={t("dashboard.statement.format")}
          />

          <UI.Field id="statement-period" label={t("dashboard.statement.period")}>
            <UI.Select id="statement-period" value={period} onChange={(event) => setPeriod(event.target.value)}>
              {periodOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </UI.Select>
          </UI.Field>

          {period === "custom" ? (
            <div className="dash-field-grid">
              <UI.Field id="statement-from" label={t("dashboard.statement.from")}>
                <UI.TextInput id="statement-from" type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} />
              </UI.Field>
              <UI.Field id="statement-to" label={t("dashboard.statement.to")}>
                <UI.TextInput id="statement-to" type="date" value={customTo} onChange={(event) => setCustomTo(event.target.value)} />
              </UI.Field>
            </div>
          ) : null}

          {period === "custom" && !range ? (
            <div className="dash-balance-line is-short" role="alert">{t("dashboard.statement.invalidRange")}</div>
          ) : null}

          {error ? (
            <div className="dash-balance-line is-short" role="alert">{error.message}</div>
          ) : null}

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.statement.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={submit}>
              {busy ? t("dashboard.statement.downloading") : t("dashboard.statement.download")}
            </UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  const EXCHANGE_TARGETS = ["EUR", "USD"];
  const RATE_SCALE = 1000000;

  DASH.ExchangeDialog = function ExchangeDialog({ accounts, busy, error, onClose, onSubmit }) {
    const ronAccounts = accounts.filter((account) => account.cur === "RON");
    const [sourceId, setSourceId] = useState(ronAccounts.length ? ronAccounts[0].id : "");
    const [targetCurrency, setTargetCurrency] = useState(EXCHANGE_TARGETS[0]);
    const [amount, setAmount] = useState("");
    const [rates, setRates] = useState({});
    const [rateLoading, setRateLoading] = useState(false);
    const [rateError, setRateError] = useState(null);

    const source = ronAccounts.find((account) => account.id === sourceId) || ronAccounts[0] || null;
    const amountMinor = DASH.parseMinor(amount);
    const shortfall = source && amountMinor != null && amountMinor > source.minor ? amountMinor - source.minor : null;

    useEffect(() => {
      let cancelled = false;
      setRateLoading(true);
      setRateError(null);
      Promise.all(EXCHANGE_TARGETS.map((code) => api.exchangeRate("RON", code)))
        .then((responses) => {
          if (cancelled) return;
          const byCurrency = {};
          EXCHANGE_TARGETS.forEach((code, index) => { byCurrency[code] = responses[index]; });
          setRates(byCurrency);
        })
        .catch((err) => {
          if (!cancelled) setRateError(err);
        })
        .finally(() => {
          if (!cancelled) setRateLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }, []);

    const rate = rates[targetCurrency] || null;

    const targetAmountMinor = rate && amountMinor > 0
      ? Math.round((amountMinor * rate.rateMicro) / RATE_SCALE)
      : null;

    const ready = Boolean(source) && amountMinor > 0 && shortfall == null && Boolean(rate) && !busy;

    const submit = () => {
      onSubmit({ sourceAccountId: source.id, targetCurrency, amountMinor });
    };

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="exchange-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="exchange-title" style={{ margin: 0 }}>{t("dashboard.exchange.title")}</h2>
          <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>{t("dashboard.exchange.subtitle")}</p>

          {!ronAccounts.length ? (
            <div className="dash-balance-line is-short" role="alert">{t("dashboard.exchange.noRonAccount")}</div>
          ) : (
            <React.Fragment>
              <UI.Field id="exchange-from" label={t("dashboard.exchange.from")}>
                <UI.Select id="exchange-from" value={source.id} onChange={(event) => setSourceId(event.target.value)}>
                  {ronAccounts.map((account) => (
                    <option key={account.id} value={account.id}>{accountLabel(account)}</option>
                  ))}
                </UI.Select>
              </UI.Field>

              <BalanceLine account={source} shortfallMinor={shortfall} />

              <UI.Field id="exchange-to" label={t("dashboard.exchange.to")}>
                <UI.Select id="exchange-to" value={targetCurrency} onChange={(event) => setTargetCurrency(event.target.value)}>
                  {EXCHANGE_TARGETS.map((code) => <option key={code} value={code}>{code}</option>)}
                </UI.Select>
              </UI.Field>

              <UI.Field id="exchange-amount" label={t("dashboard.exchange.amount", { currency: "RON" })}>
                <UI.TextInput
                  id="exchange-amount"
                  className={shortfall == null ? undefined : "is-invalid"}
                  aria-invalid={shortfall == null ? undefined : "true"}
                  inputMode="decimal"
                  value={amount}
                  placeholder="0,00"
                  onChange={(event) => setAmount(event.target.value)}
                />
              </UI.Field>

              <div className="dash-balance-line" role="status">
                {rateLoading
                  ? t("dashboard.exchange.rateLoading")
                  : rateError
                    ? t("dashboard.exchange.rateUnavailable")
                    : EXCHANGE_TARGETS.filter((code) => rates[code]).map((code) =>
                        t("dashboard.exchange.rateNote", {
                          source: "RON",
                          rate: (rates[code].rateMicro / RATE_SCALE).toFixed(4).replace(".", ","),
                          target: code,
                        })
                      ).join(" · ")}
              </div>

              {targetAmountMinor != null ? (
                <div className="dash-balance-line" role="status">
                  {t("dashboard.exchange.youReceive", {
                    amount: DASH.formatMinor(targetAmountMinor) + " " + targetCurrency,
                  })}
                </div>
              ) : null}
            </React.Fragment>
          )}

          {error ? (
            <div className="dash-balance-line is-short" role="alert">{error.message}</div>
          ) : null}

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={submit}>
              {busy ? t("dashboard.payDialog.sending") : t("dashboard.exchange.submit")}
            </UI.Button>
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

  DASH.IssueCardDialog = function IssueCardDialog({ kind, onKind, accounts, onClose, onCreate, creating }) {
    const options = [
      { value: "virtual", label: t("dashboard.cards.issueDialog.virtual") },
      { value: "physical", label: t("dashboard.cards.issueDialog.physical") },
    ];
    const [accountId, setAccountId] = useState(accounts.length ? accounts[0].id : "");
    const ready = Boolean(accountId) && !creating;

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate
          className="dash-dialog elev-lg"
          role="dialog"
          aria-modal="true"
          aria-labelledby="issue-card-dialog-title"
          onClick={(event) => event.stopPropagation()}
        >
          <h2 id="issue-card-dialog-title" style={{ margin: 0 }}>{t("dashboard.cards.issueDialog.title")}</h2>
          <DASH.SegmentedControl className="dash-seg-full" options={options} value={kind} onChange={onKind} label={t("dashboard.cards.issueDialog.title")} />

          <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>
            {kind === "physical" ? t("dashboard.cards.issueDialog.physicalNote") : t("dashboard.cards.issueDialog.virtualNote")}
          </p>

          {accounts.length ? (
            <UI.Field id="issue-card-account" label={t("dashboard.cards.issueDialog.linkedAccount")}>
              <UI.Select id="issue-card-account" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>{accountLabel(account)}</option>
                ))}
              </UI.Select>
            </UI.Field>
          ) : (
            <div className="dash-balance-line is-short" role="alert">{t("dashboard.cards.issueDialog.noAccount")}</div>
          )}

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.cards.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" disabled={!ready} onClick={() => onCreate(accountId)}>
              {creating ? t("dashboard.cards.issuing") : t("dashboard.cards.issueDialog.create")}
            </UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  DASH.CardHistoryDialog = function CardHistoryDialog({ cards, onClose }) {
    const sortedCards = [...(cards || [])].sort((a, b) => {
      const dateA = a.deletedAt || a.updatedAt || a.createdAt || "";
      const dateB = b.deletedAt || b.updatedAt || b.createdAt || "";
      return dateB.localeCompare(dateA);
    });

    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate
          className="dash-dialog elev-lg"
          role="dialog"
          aria-modal="true"
          aria-labelledby="card-history-dialog-title"
          onClick={(event) => event.stopPropagation()}
        >
          <h2 id="card-history-dialog-title" style={{ margin: 0 }}>{t("dashboard.cards.historyDialog.title")}</h2>

          {sortedCards.length === 0 ? (
            <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>{t("dashboard.cards.historyDialog.empty")}</p>
          ) : (
            <div className="dash-history-list">
              {sortedCards.map((card) => {
                const rawDate = card.deletedAt || card.updatedAt;
                const formattedDate = rawDate && GEMS.i18n ? GEMS.i18n.isoToDisplayDate(rawDate.slice(0, 10)) : "";
                return (
                  <div key={card.cardId} className="dash-history-row">
                    <span style={{ fontFamily: "var(--font-mono)", letterSpacing: "0.1em" }}>
                      {DASH.mockFullNumber(card.cardId, card.numberMasked.slice(-4), card.kind)}
                    </span>
                    {formattedDate ? (
                      <span className="text-muted" style={{ fontSize: 13, fontFamily: "var(--font-mono)", letterSpacing: "normal", whiteSpace: "nowrap" }}>
                        {t("dashboard.cards.historyDialog.deletedOn", { date: formattedDate })}
                      </span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.cards.historyDialog.close")}</UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };

  DASH.TemplateDialog = function TemplateDialog({ accounts, template, busy, error, onClose, onSubmit }) {
    const [name, setName] = useState((template && template.name) || "");
    const [beneficiary, setBeneficiary] = useState((template && template.beneficiary) || "");
    const [iban, setIban] = useState((template && template.iban) || "");
    const [cur, setCur] = useState((template && template.cur) || accounts[0].cur);
    const [reference, setReference] = useState((template && template.reference) || "");

    const currencies = accounts
      .map((account) => account.cur)
      .filter((value, index, list) => list.indexOf(value) === index);

    const ready = name.trim() !== "" && beneficiary.trim() !== "" && iban.trim() !== "" && !busy;

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

          {error ? (
            <div className="dash-balance-line is-short" role="alert">{error.message}</div>
          ) : null}

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
