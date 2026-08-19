(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = (GEMS.onboarding = GEMS.onboarding || {});
  const UI = GEMS.ui;
  const t = GEMS.i18n.t;
  const formatDate = GEMS.format.isoToDisplayDate;
  const { useState, useRef, useEffect } = React;

  function DropZone({ id, label, required, file, onFile }) {
    const inputRef = useRef(null);
    const [dragging, setDragging] = useState(false);
    const [preview, setPreview] = useState(null);

    useEffect(() => {
      if (!file) {
        setPreview(null);
        return undefined;
      }
      const url = URL.createObjectURL(file);
      setPreview(url);
      return () => URL.revokeObjectURL(url);
    }, [file]);

    function pick(list) {
      const chosen = list && list[0];
      if (chosen) onFile(chosen);
    }

    return (
      <div>
        <button
          type="button"
          className="onb-dropzone"
          data-filled={Boolean(file)}
          data-required={Boolean(required)}
          data-dragging={dragging}
          aria-label={label}
          onClick={() => inputRef.current && inputRef.current.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            pick(event.dataTransfer.files);
          }}
        >
          {preview ? (
            <img src={preview} alt="" />
          ) : (
            <span className="onb-dropzone-label">{label}</span>
          )}
        </button>
        <input
          ref={inputRef}
          id={id}
          className="visually-hidden"
          type="file"
          accept="image/png,image/jpeg,image/webp,application/pdf"
          onChange={(event) => pick(event.target.files)}
        />
        <div className="text-muted" style={{ fontSize: 11, marginTop: 6 }}>
          {file ? file.name : required ? "" : t("document.backOptional")}
        </div>
      </div>
    );
  }

  ONB.DocumentStep = function DocumentStep({ extracted, busy, onExtract, onNext }) {
    const [front, setFront] = useState(null);
    const [back, setBack] = useState(null);

    return (
      <div className="onb-fade">
        <div className="onb-two-col">
          <DropZone
            id="id-front"
            label={t("document.front")}
            required
            file={front}
            onFile={setFront}
          />
          <DropZone id="id-back" label={t("document.back")} file={back} onFile={setBack} />
        </div>

        {extracted ? (
          <UI.Plate style={{ padding: 14, marginTop: 20, maxWidth: 660 }}>
            <UI.Kicker style={{ marginBottom: 8 }}>{t("document.extractedBy")}</UI.Kicker>
            <dl className="onb-extract-grid" style={{ margin: 0 }}>
              <dt className="text-muted">{t("document.name")}</dt>
              <dd style={{ margin: 0 }}>{extracted.fullName}</dd>
              <dt className="text-muted">{t("document.birthDate")}</dt>
              <dd style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
                <span>{formatDate(extracted.birthDate)}</span>
                <UI.Tag>{t("document.ageOk", { age: extracted.ageYears })}</UI.Tag>
              </dd>
              <dt className="text-muted">{t("document.cnp")}</dt>
              <dd style={{ margin: 0 }}>{extracted.cnpMasked}</dd>
              <dt className="text-muted">{t("document.docNumber")}</dt>
              <dd style={{ margin: 0 }}>{extracted.documentNumberMasked}</dd>
              <dt className="text-muted">{t("document.expiry")}</dt>
              <dd style={{ margin: 0 }}>{formatDate(extracted.expiresOn)}</dd>
            </dl>
            <div className="text-muted" style={{ fontSize: 11, marginTop: 10 }}>
              {t("document.syntheticNote")}
            </div>
          </UI.Plate>
        ) : null}

        <div style={{ display: "flex", gap: 8, marginTop: 18 }}>
          <UI.Button
            type="button"
            variant={extracted ? "secondary" : "primary"}
            disabled={!front || busy}
            onClick={() => onExtract(front)}
          >
            {busy ? t("document.reading") : t("document.read")}
          </UI.Button>
          {extracted ? (
            <UI.Button type="button" variant="primary" onClick={onNext}>
              {t("document.cta")}
            </UI.Button>
          ) : null}
        </div>
      </div>
    );
  };
})();
