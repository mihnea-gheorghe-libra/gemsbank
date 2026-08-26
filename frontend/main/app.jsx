(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = GEMS.onboarding;
  const AUTH = GEMS.auth;
  const PAY = GEMS.payments;
  const { useState, useEffect } = React;

  function App() {
    const [mode, setMode] = useState("signIn");
    const [username, setUsername] = useState("");
    
    const [theme, setTheme] = useState(() => window.localStorage.getItem("gems.theme") || "light");
    const [lang, setLang] = useState(GEMS.i18n.locale);

    useEffect(() => {
      if (theme === "dark") document.documentElement.setAttribute("data-theme", "dark");
      else document.documentElement.setAttribute("data-theme", "light");
      window.localStorage.setItem("gems.theme", theme);
    }, [theme]);

    const handleThemeChange = (newTheme) => {
      setTheme(newTheme);
      if (username) {
        GEMS.api.updatePreferences({ theme: newTheme, lang }).catch(() => {});
      }
    };

    const handleLangChange = (newLang) => {
      GEMS.i18n.setLocale(newLang);
      setLang(newLang);
      if (username) {
        GEMS.api.updatePreferences({ theme, lang: newLang }).catch(() => {});
      }
    };

    if (mode === "dashboard") {
      return (
        <GEMS.dashboard.Dashboard
          username={username}
          theme={theme}
          onTheme={handleThemeChange}
          lang={lang}
          onLang={handleLangChange}
          onSignOut={() => {
            setUsername("");
            setMode("signIn");
          }}
        />
      );
    }
    if (mode === "register") {
      return (
        <ONB.RegisterPage
          theme={theme}
          onTheme={handleThemeChange}
          lang={lang}
          onLang={handleLangChange}
          onSwitchToSignIn={() => setMode("signIn")}
          onRegistered={(name, prefs) => {
            setUsername(name);
            if (prefs) {
              // We intentionally do not overwrite the local theme with prefs.theme
              // so that the user's choice on the login page is preserved.
              if (prefs.lang && prefs.lang !== lang) {
                GEMS.i18n.setLocale(prefs.lang);
                setLang(prefs.lang);
              }
            }
            setMode("dashboard");
          }}
        />
      );
    }
    return (
      <AUTH.SignInPage
        theme={theme}
        onTheme={handleThemeChange}
        lang={lang}
        onLang={handleLangChange}
        onSwitchToRegister={() => setMode("register")}
        onSignedIn={(name, prefs) => {
          setUsername(name);
          if (prefs) {
            // We intentionally do not overwrite the local theme with prefs.theme
            // so that the user's choice on the login page is preserved.
            if (prefs.lang && prefs.lang !== lang) {
              GEMS.i18n.setLocale(prefs.lang);
              setLang(prefs.lang);
            }
          }
          setMode("dashboard");
        }}
      />
    );
  }

  GEMS.App = App;

  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
})();
