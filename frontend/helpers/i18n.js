(function () {
  const GEMS = (window.GEMS = window.GEMS || {});

  const DEFAULT_LOCALE = "en";

  function resolveLocale() {
    const fromQuery = new URLSearchParams(window.location.search).get("lang");
    if (fromQuery && GEMS.messages[fromQuery]) return fromQuery;
    const stored = window.localStorage.getItem("gems.lang");
    if (stored && GEMS.messages[stored]) return stored;
    return DEFAULT_LOCALE;
  }

  const locale = resolveLocale();
  const dictionary = GEMS.messages[locale] || GEMS.messages[DEFAULT_LOCALE];

  function lookup(key) {
    return key.split(".").reduce((node, part) => (node == null ? null : node[part]), dictionary);
  }

  function t(key, params) {
    const value = lookup(key);
    if (typeof value !== "string") return key;
    if (!params) return value;
    return value.replace(/\{(\w+)\}/g, (match, name) =>
      Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match
    );
  }

  function isoToDisplayDate(iso) {
    if (typeof iso !== "string") return "";
    const parts = iso.split("-");
    if (parts.length !== 3) return iso;
    return parts[2] + "." + parts[1] + "." + parts[0];
  }

  GEMS.i18n = { locale, t, dictionary, isoToDisplayDate };
  document.documentElement.lang = locale;
})();
