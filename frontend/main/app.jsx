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
      window.localStorage.setItem("gems.lang", newLang);
      if (username) {
        GEMS.api.updatePreferences({ theme, lang: newLang }).catch(() => {}).finally(() => {
          window.location.reload();
        });
      } else {
        window.location.reload();
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
            if (prefs.theme && prefs.theme !== theme) setTheme(prefs.theme);
            if (prefs.lang && prefs.lang !== lang) {
              window.localStorage.setItem("gems.lang", prefs.lang);
              window.location.reload();
              return;
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
