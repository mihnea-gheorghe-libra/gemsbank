(function () {
  const GEMS = (window.GEMS = window.GEMS || {});

  const LOCALE = "ro-RO";

  function titleCase(value) {
    return String(value || "")
      .trim()
      .toLocaleLowerCase(LOCALE)
      .replace(/(^|[\s\-'])(\S)/g, function (match, boundary, letter) {
        return boundary + letter.toLocaleUpperCase(LOCALE);
      });
  }

  function parts(value) {
    return String(value || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
  }

  GEMS.people = {
    fullName(value) {
      return titleCase(value);
    },
    firstName(value) {
      const tokens = parts(value);
      if (tokens.length === 0) return "";
      if (tokens.length === 1) return titleCase(tokens[0]);
      return titleCase(tokens.slice(1).join(" "));
    },
    initials(value) {
      const tokens = parts(value);
      if (tokens.length === 0) return "";
      if (tokens.length === 1) return tokens[0].slice(0, 2).toLocaleUpperCase(LOCALE);
      return (tokens[0][0] + tokens[1][0]).toLocaleUpperCase(LOCALE);
    },
  };
})();
