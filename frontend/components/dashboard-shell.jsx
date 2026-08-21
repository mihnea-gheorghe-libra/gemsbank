(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const DASH = (GEMS.dashboardUi = GEMS.dashboardUi || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const DATA = GEMS.dashboardData;
  const { useState, useEffect, useRef } = React;

  function deriveDisplayId(fullName, userId) {
    const parts = (fullName || "").trim().split(/\s+/).filter(Boolean);
    const surname = (parts[0] || "").toUpperCase();
    const given = (parts[1] || "").split("-")[0].toUpperCase();
    const initials = (surname.slice(0, 2) + given.slice(0, 2)).padEnd(4, "X");
    const seed = String(userId || "");
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
      hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
    }
    const digits = String(hash % 1000000).padStart(6, "0");
    return initials + digits;
  }
  DASH.deriveDisplayId = deriveDisplayId;

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
              <span className="dash-nav-num" aria-hidden="true">{item.num}</span>
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
          <UI.Button type="button" variant="ghost" style={{ alignSelf: "flex-start", padding: 0 }} onClick={onSignOut}>
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

        <UI.TextInput
          className="input dash-search"
          type="search"
          aria-label={t("dashboard.searchPlaceholder")}
          placeholder={t("dashboard.searchPlaceholder")}
        />

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
              <div className="dash-profile-id">
                {t("dashboard.profileMenu.idPrefix")}: {me ? deriveDisplayId(me.fullName, me.userId) : "…"}
              </div>
              <div className="hr" />
              <UI.Button
                type="button"
                variant="secondary"
                role="menuitem"
                style={{ justifyContent: "flex-start" }}
                onClick={() => { setMenuOpen(false); onOpenSettings(); }}
              >
                {t("dashboard.profileMenu.settings")}
              </UI.Button>
              <UI.Button
                type="button"
                variant="secondary"
                role="menuitem"
                style={{ justifyContent: "flex-start" }}
                onClick={() => { setMenuOpen(false); onSignOut(); }}
              >
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
        <UI.Button type="button" variant="primary" className="dash-dock-fab elev-md" onClick={onOpen}>
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
            {t("dashboard.chat.dockExpand")}
          </UI.Button>
          <UI.Button type="button" variant="ghost" aria-label={t("dashboard.chat.dockCloseLabel")} onClick={onClose}>
            {t("dashboard.chat.dockClose")}
          </UI.Button>
        </div>
        <div style={{ padding: 14 }}>
          <p style={{ fontSize: 13, lineHeight: 1.6, margin: 0 }}>
            {t("dashboard.chat.dockGreeting", { username, balance: DATA.totalBalance })}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 12 }}>
            <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start" }} onClick={() => onPrompt("pay")}>
              {t("dashboard.chat.promptPay")}
            </UI.Button>
            <UI.Button type="button" variant="secondary" style={{ justifyContent: "flex-start" }} onClick={() => onPrompt("recurring")}>
              {t("dashboard.chat.promptRecurring")}
            </UI.Button>
          </div>
        </div>
      </UI.Plate>
    );
  };

  DASH.NewPaymentDialog = function NewPaymentDialog({ payType, onPayType, onClose, onContinue }) {
    const types = [
      { value: "iban", label: t("dashboard.payDialog.iban") },
      { value: "internal", label: t("dashboard.payDialog.internal") },
      { value: "split", label: t("dashboard.payDialog.split") },
    ];
    return (
      <div className="dash-dialog-backdrop" onClick={onClose}>
        <UI.Plate className="dash-dialog elev-lg" role="dialog" aria-modal="true" aria-labelledby="pay-dialog-title" onClick={(event) => event.stopPropagation()}>
          <h2 id="pay-dialog-title" style={{ margin: 0 }}>{t("dashboard.payDialog.title")}</h2>
          <DASH.SegmentedControl options={types} value={payType} onChange={onPayType} label={t("dashboard.payDialog.title")} />

          <div className="dash-field-grid">
            <UI.Field id="pay-beneficiary" label={t("dashboard.payDialog.beneficiary")}>
              <UI.TextInput id="pay-beneficiary" placeholder={t("dashboard.payDialog.beneficiaryPh")} />
            </UI.Field>
            <div />
            <UI.Field id="pay-iban" label={t("dashboard.payDialog.ibanLabel")}>
              <UI.TextInput id="pay-iban" placeholder={t("dashboard.payDialog.ibanPh")} />
            </UI.Field>
            <div />
            <UI.Field id="pay-amount" label={t("dashboard.payDialog.amount")}>
              <UI.TextInput id="pay-amount" inputMode="decimal" placeholder="0,00" />
            </UI.Field>
            <UI.Field id="pay-currency" label={t("dashboard.payDialog.currency")}>
              <UI.TextInput id="pay-currency" defaultValue="RON" />
            </UI.Field>
            <UI.Field id="pay-reference" label={t("dashboard.payDialog.reference")}>
              <UI.TextInput id="pay-reference" placeholder={t("dashboard.payDialog.referencePh")} />
            </UI.Field>
          </div>

          <p className="text-muted" style={{ fontSize: 12, margin: 0 }}>{t("dashboard.payDialog.agentCheck")}</p>

          <div className="dash-dialog-actions">
            <UI.Button type="button" variant="secondary" onClick={onClose}>{t("dashboard.payDialog.cancel")}</UI.Button>
            <UI.Button type="button" variant="primary" onClick={onContinue}>{t("dashboard.payDialog.continueBtn")}</UI.Button>
          </div>
        </UI.Plate>
      </div>
    );
  };
})();
