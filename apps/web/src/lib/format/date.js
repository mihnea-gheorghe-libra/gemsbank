(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const format = (GEMS.format = GEMS.format || {});

  format.isoToDisplayDate = function isoToDisplayDate(iso) {
    if (typeof iso !== "string") return "";
    const parts = iso.split("-");
    if (parts.length !== 3) return iso;
    return parts[2] + "." + parts[1] + "." + parts[0];
  };
})();
