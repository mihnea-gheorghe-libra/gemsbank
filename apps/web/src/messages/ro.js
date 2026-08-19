(function () {
  const GEMS = (window.GEMS = window.GEMS || {});
  GEMS.messages = GEMS.messages || {};

  GEMS.messages.ro = {
    brand: "GEMS",
    screenTag: "ECRAN 01 — ÎNROLARE & KYC",
    backToSignIn: "Înapoi la autentificare",
    signInSoon: "Autentificare — în curând",
    stepOf: "PASUL {n} DIN {total}",
    loading: "Îți pregătim sesiunea…",
    state: { done: "GATA", inProgress: "ÎN CURS", pending: "URMEAZĂ" },
    rail: {
      document: "Act de identitate",
      contact: "Date de contact",
      code: "Semnătură pe email",
      credentials: "Credențiale",
    },
    document: {
      title: "Încarcă actul de identitate",
      lede: "Fața și verso-ul cărții de identitate sau al pașaportului. Agentul citește câmpurile pentru tine.",
      front: "TRAGE ACTUL — FAȚĂ",
      back: "TRAGE ACTUL — VERSO",
      backOptional: "opțional în demo",
      change: "Înlocuiește",
      extractedBy: "EXTRAS DE AGENT",
      name: "Nume",
      birthDate: "Data nașterii",
      ageOk: "{age} ani · 18+ verificat",
      cnp: "CNP",
      docNumber: "Serie",
      expiry: "Expiră",
      read: "Citește documentul",
      reading: "Se citește…",
      cta: "Confirmă datele",
      syntheticNote:
        "Sistem demo: valorile de mai jos sunt sintetice. Nimic din ce încarci nu se stochează.",
    },
    contact: {
      title: "Cum te putem contacta?",
      lede: "Le folosim pentru semnături și alerte — nimic altceva.",
      phone: "Număr de telefon",
      email: "Email",
      cta: "Trimite codul",
      sending: "Se trimite…",
    },
    code: {
      title: "Confirmă codul",
      lede: "Șase cifre, valabile 5 minute. Aceasta este semnătura ta electronică.",
      digit: "Cifra {n} din 6",
      sentTo: "Cod trimis către {target}",
      resendIn: "retrimitere în {seconds}",
      resendNow: "Retrimite codul",
      resendsLeft: "{n} retrimiteri rămase",
      devCode: "Mod dev — niciun furnizor de email configurat. Codul tău este {code}.",
      cta: "Verifică semnătura",
      verifying: "Se verifică…",
    },
    credentials: {
      title: "Securizează-ți contul",
      lede: "Un nume de utilizator, o parolă și un PIN de 6 cifre pentru accesul zilnic.",
      username: "Nume utilizator",
      password: "Parolă",
      pin: "PIN de 6 cifre",
      pinConfirm: "Confirmă PIN-ul",
      passkeyTag: "Passkey disponibil",
      passkeyNote: "Înregistrează Windows Hello / Touch ID după prima autentificare.",
      cta: "Deschide-mi contul",
      creating: "Îți creăm contul…",
    },
    agent: {
      header: "AGENT DE ÎNROLARE",
      suggested: "SUGESTII",
      whyId: "De ce aveți nevoie de actul meu?",
      readAloud: "Citește pasul cu voce tare",
      messages: {
        document:
          "Citesc câmpurile de pe document și completez formularul pentru tine. Dacă o valoare pare greșită, corectează-o — modificarea ta are prioritate.",
        contact:
          "Momentan acceptăm doar numere românești pentru semnături. Emailul poate fi de la orice furnizor.",
        code: "Nu a ajuns nimic? Pot retrimite după ce expiră cronometrul, apoi trecem la un apel vocal.",
        credentials:
          "Alege un PIN pe care nu l-ai folosit niciodată la bancomat. După asta îți propun să înregistrezi passkey-ul dispozitivului.",
        done: "Asta e tot. Conturile tale se deschid în fundal.",
      },
    },
    done: {
      title: "Bine ai venit în GEMS, {username}",
      lede: "Contul tău este creat, iar dosarul de înrolare este închis.",
      caseLabel: "DOSAR KYC",
      cta: "Mergi la dashboard",
      comingSoon: "Dashboard — în curând",
    },
    footer: "SISTEM DEMO · FĂRĂ LICENȚĂ · FĂRĂ FONDURI REALE · FĂRĂ DATE REALE DE CARD",
  };
})();
