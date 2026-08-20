(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = GEMS.onboarding;
  const AUTH = GEMS.auth;
  const { useState } = React;

  function App() {
    const [mode, setMode] = useState("signIn");

    if (mode === "register") {
      return <ONB.RegisterPage onSwitchToSignIn={() => setMode("signIn")} />;
    }
    return <AUTH.SignInPage onSwitchToRegister={() => setMode("register")} />;
  }

  GEMS.App = App;

  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
})();
