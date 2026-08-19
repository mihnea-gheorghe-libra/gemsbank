(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  GEMS.messages = GEMS.messages || {};

  GEMS.messages.en = {
    brand: "GEMS",
    screenTag: "SCREEN 01 — ONBOARDING & KYC",
    backToSignIn: "Back to sign in",
    signInSoon: "Sign in — coming soon",
    stepOf: "STEP {n} OF {total}",
    loading: "Preparing your session…",
    state: { done: "DONE", inProgress: "IN PROGRESS", pending: "PENDING" },
    rail: {
      document: "ID document",
      contact: "Contact",
      code: "Email signature",
      credentials: "Credentials",
    },
    document: {
      title: "Upload your ID",
      lede: "Front and back of your CI or passport. The agent reads the fields for you.",
      front: "DROP ID — FRONT",
      back: "DROP ID — BACK",
      backOptional: "optional in the demo",
      change: "Replace",
      extractedBy: "EXTRACTED BY AGENT",
      name: "Name",
      birthDate: "Date of birth",
      ageOk: "{age} years old · 18+ verified",
      cnp: "CNP",
      docNumber: "Series",
      expiry: "Expiry",
      read: "Read the document",
      reading: "Reading…",
      cta: "Confirm details",
      syntheticNote:
        "Demo system: the values below are synthetic. Nothing you upload is stored.",
    },
    contact: {
      title: "How can we reach you?",
      lede: "We use these for signatures and alerts — nothing else.",
      phone: "Phone number",
      email: "Email",
      cta: "Send code",
      sending: "Sending…",
    },
    code: {
      title: "Confirm the code",
      lede: "Six digits, valid for 5 minutes. This is your electronic signature.",
      digit: "Digit {n} of 6",
      sentTo: "Code sent to {target}",
      resendIn: "resend in {seconds}",
      resendNow: "Resend code",
      resendsLeft: "{n} resends left",
      devCode: "Dev mode — no mail provider configured. Your code is {code}.",
      cta: "Verify signature",
      verifying: "Verifying…",
    },
    credentials: {
      title: "Secure your account",
      lede: "A username, a password, and a 6-digit PIN for day-to-day access.",
      username: "Username",
      password: "Password",
      pin: "6-digit PIN",
      pinConfirm: "Confirm PIN",
      passkeyTag: "Passkey ready",
      passkeyNote: "Register Windows Hello / Touch ID after your first sign-in.",
      cta: "Open my account",
      creating: "Creating your account…",
    },
    agent: {
      header: "ONBOARDING AGENT",
      suggested: "SUGGESTED",
      whyId: "Why do you need my ID?",
      readAloud: "Read this step aloud",
      messages: {
        document:
          "I read the fields off the document and fill the form for you. If a value looks wrong, correct it — your edit wins over my reading.",
        contact:
          "Romanian numbers only for signatures at the moment. The email can be any provider.",
        code: "Nothing arrived? I can resend once the timer runs out, then we switch to a voice call.",
        credentials:
          "Pick a PIN you have never used at an ATM. After this I will offer to register your device passkey.",
        done: "That is everything. Your accounts are being opened in the background.",
      },
    },
    done: {
      title: "Welcome to GEMS, {username}",
      lede: "Your account is created and your onboarding case is closed.",
      caseLabel: "KYC CASE",
      cta: "Go to dashboard",
      comingSoon: "Dashboard — coming soon",
    },
    footer: "DEMO SYSTEM · NO LICENCE · NO REAL FUNDS · NO REAL CARD DATA",
  };
})();
