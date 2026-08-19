(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const t = GEMS.i18n.t;

  ONB.STEPS = [
    { key: "document", num: "01" },
    { key: "contact", num: "02" },
    { key: "code", num: "03" },
    { key: "credentials", num: "04" },
  ];

  ONB.StepRail = function StepRail({ current }) {
    return (
      <nav className="onb-rail" aria-label={t("screenTag")}>
        <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {ONB.STEPS.map((step, index) => {
            const position = index + 1;
            const state =
              position < current
                ? t("state.done")
                : position === current
                  ? t("state.inProgress")
                  : t("state.pending");
            return (
              <li
                key={step.key}
                className="onb-rail-item"
                data-state={state}
                aria-current={position === current ? "step" : undefined}
              >
                <span className="onb-rail-num" aria-hidden="true">
                  {step.num}
                </span>
                <span>
                  <span className="onb-rail-title">{t("rail." + step.key)}</span>
                  <span className="onb-rail-state" style={{ display: "block" }}>
                    {state}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      </nav>
    );
  };
})();
