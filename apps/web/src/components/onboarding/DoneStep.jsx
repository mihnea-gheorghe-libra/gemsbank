(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;

  ONB.DoneStep = function DoneStep({ result }) {
    return (
      <div className="onb-fade">
        <UI.Plate style={{ padding: 20, maxWidth: 560, background: "var(--color-surface)" }}>
          <UI.Kicker style={{ marginBottom: 8 }}>{t("done.caseLabel")}</UI.Kicker>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 14 }}>
            {result.kycCaseId}
          </div>
          <UI.Tag>{t("credentials.passkeyTag")}</UI.Tag>
        </UI.Plate>

        <UI.Button type="button" variant="primary" style={{ marginTop: 20 }} disabled>
          {t("done.comingSoon")}
        </UI.Button>
      </div>
    );
  };
})();
