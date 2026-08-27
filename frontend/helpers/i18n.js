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

  function countFor(n) {
    const value = Number(n) || 0;
    if (state.locale === "ro" && Math.abs(value) >= 20) return value + " de";
    return String(value);
  }

  function tError(message) {
    if (!message) return message;
    const value = state.dictionary.serverErrors && state.dictionary.serverErrors[message];
    if (typeof value === "string") return value;
    return message;
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

  GEMS.i18n = { 
    locale: state.locale, 
    t, 
    countFor,
    tError, // Păstrat de pe branch-ul main
    dictionary: state.dictionary, 
    isoToDisplayDate, 
    setLocale // Păstrat de pe branch-ul tău
  };
  document.documentElement.lang = state.locale;
})();
