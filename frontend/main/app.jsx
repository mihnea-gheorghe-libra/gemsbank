(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  const ONB = GEMS.onboarding;
  const AUTH = GEMS.auth;
  const PAY = GEMS.payments;
  const { useState } = React;

  function App() {
    const [mode, setMode] = useState("signIn");
    const [username, setUsername] = useState("");

    if (mode === "payments") {
      return (
        <PAY.PaymentsPage
          username={username}
          onSignOut={() => {
            setUsername("");
            setMode("signIn");
          }}
        />
      );
    }
    if (mode === "register") {
      return <ONB.RegisterPage onSwitchToSignIn={() => setMode("signIn")} />;
    }
    return (
      <AUTH.SignInPage
        onSwitchToRegister={() => setMode("register")}
        onSignedIn={(name) => {
          setUsername(name);
          setMode("payments");
        }}
      />
    );
  }

  GEMS.App = App;

  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
})();
