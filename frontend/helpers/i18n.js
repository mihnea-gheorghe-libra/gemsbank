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

  const state = {
    locale: resolveLocale(),
  };
  state.dictionary = GEMS.messages[state.locale] || GEMS.messages[DEFAULT_LOCALE];

  function lookup(key) {
    return key
      .split(".")
      .reduce((node, part) => (node == null ? null : node[part]), state.dictionary);
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

  function setLocale(next) {
    if (!GEMS.messages[next] || next === state.locale) return;
    state.locale = next;
    state.dictionary = GEMS.messages[next];
    GEMS.i18n.locale = next;
    GEMS.i18n.dictionary = state.dictionary;
    document.documentElement.lang = next;
    window.localStorage.setItem("gems.lang", next);
  }

  GEMS.i18n = { locale: state.locale, t, dictionary: state.dictionary, isoToDisplayDate, setLocale };
  document.documentElement.lang = state.locale;
})();
