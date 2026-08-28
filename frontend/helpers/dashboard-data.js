(function () {
  const GEMS = (window.GEMS = window.GEMS || {});

  // Static demo data for the post-login dashboard mockup. Mirrors the shape
  // a real read model would return (accounts, transactions, cards…) but is
  // hand-authored, not fetched — the dashboard has no backend yet (README).
  GEMS.dashboardData = {
    navItems: [
      { key: "home", num: "01" },
      { key: "payments", num: "02" },
      { key: "chat", num: "03" },
      { key: "accounts", num: "04" },
      { key: "portfolio", num: "05" },
      { key: "cards", num: "06" },
      { key: "analytics", num: "07" },
      { key: "education", num: "08" },
      { key: "settings", num: "09" },
    ],

    totalBalance: "128.470,55",

    accountTypes: [
      { key: "current", creates: "account", rateBps: 0, monthlyFeeMinor: 0, minOpenMinor: 0, accessKey: "anytime" },
      { key: "savings", creates: "account", rateBps: 225, monthlyFeeMinor: 0, minOpenMinor: 10000, accessKey: "anytime" },
      { key: "deposit", creates: "deposit", depositKind: "term", monthlyFeeMinor: 0, minOpenMinor: 100000, accessKey: "maturity" },
      { key: "invest", creates: "account", rateBps: 0, monthlyFeeMinor: 0, minOpenMinor: 0, accessKey: "anytime" },
    ],

    templates: [
      {
        id: "tpl-rent",
        name: "Chirie",
        beneficiary: "Popescu Andrei",
        iban: "RO21 BTRL 0000 1234 5678 9012",
        cur: "RON",
        reference: "Chirie luna curenta",
      },
      {
        id: "tpl-mama",
        name: "Mama",
        beneficiary: "Ionescu Maria",
        iban: "RO12 INGB 0099 8877 6655 4433",
        cur: "RON",
        reference: "Transfer",
      },
      {
        id: "tpl-gym",
        name: "Sala",
        beneficiary: "World Class Romania SA",
        iban: "RO77 RNCB 0044 1122 3344 5566",
        cur: "RON",
        reference: "Abonament",
      },
    ],

    transactions: [
      { date: "16.08.2026", who: "Kaufland Băneasa", ref: "POS 4127", categoryKey: "groceries", statusKey: "booked", minor: 21480, direction: "out", channel: "card", accountId: "acc-current-ron" },
      { date: "15.08.2026", who: "Enel Energie", ref: "Direct debit", categoryKey: "utilities", statusKey: "booked", minor: 18740, direction: "out", channel: "transfer", accountId: "acc-current-ron" },
      { date: "15.08.2026", who: "Salary — Nexo SRL", ref: "AUG 2026", categoryKey: "income", statusKey: "booked", minor: 940000, direction: "in", channel: "transfer", accountId: "acc-current-ron" },
      { date: "14.08.2026", who: "Ionescu Maria", ref: "Split — dinner", categoryKey: "transfer", statusKey: "booked", minor: 12000, direction: "out", channel: "transfer", accountId: "acc-current-ron" },
      { date: "13.08.2026", who: "Netflix", ref: "Subscription", categoryKey: "entertainment", statusKey: "booked", minor: 6799, direction: "out", channel: "card", accountId: "acc-current-ron" },
      { date: "12.08.2026", who: "Revolut top-up", ref: "SEPA out", categoryKey: "transfer", statusKey: "pending", minor: 50000, direction: "out", channel: "transfer", accountId: "acc-current-ron" },
      { date: "11.08.2026", who: "OMV Petrom", ref: "POS 4127", categoryKey: "transport", statusKey: "booked", minor: 32015, direction: "out", channel: "card", accountId: "acc-current-ron" },
      { date: "10.08.2026", who: "Digi Communications", ref: "Direct debit", categoryKey: "utilities", statusKey: "booked", minor: 5900, direction: "out", channel: "transfer", accountId: "acc-current-ron" },
    ],

    pending: [
      { num: "01", who: "Revolut top-up", noteKey: "revolut", minor: 50000 },
      { num: "02", who: "Chirie august", noteKey: "rent", minor: 240000 },
    ],

    depositProducts: {
      term: {
        defaultMonths: 12,
        terms: [
          { months: 1, rateBps: 375 },
          { months: 3, rateBps: 480 },
          { months: 6, rateBps: 540 },
          { months: 9, rateBps: 575 },
          { months: 12, rateBps: 610 },
          { months: 18, rateBps: 640 },
          { months: 24, rateBps: 665 },
          { months: 36, rateBps: 690 },
        ],
      },
      goal: {
        defaultMonths: 24,
        terms: [
          { months: 12, rateBps: 260 },
          { months: 24, rateBps: 300 },
          { months: 36, rateBps: 330 },
          { months: 60, rateBps: 360 },
        ],
      },
    },

    creditProducts: [
      {
        id: "personal",
        kind: "loan",
        rateBps: 890,
        maxMinor: 15000000,
        terms: [
          { months: 12, rateBps: 790 },
          { months: 24, rateBps: 830 },
          { months: 36, rateBps: 890 },
          { months: 48, rateBps: 940 },
          { months: 60, rateBps: 990 },
        ],
      },
      { id: "line", kind: "line", rateBps: 1890, maxMinor: 2000000, terms: [] },
      {
        id: "mortgage",
        kind: "loan",
        rateBps: 590,
        maxMinor: 90000000,
        terms: [
          { months: 120, rateBps: 520 },
          { months: 180, rateBps: 560 },
          { months: 240, rateBps: 590 },
          { months: 300, rateBps: 635 },
          { months: 360, rateBps: 670 },
        ],
      },
    ],

    groceryBars: [
      { label: "MAR", pct: 68 },
      { label: "APR", pct: 82 },
      { label: "MAY", pct: 74 },
      { label: "JUN", pct: 90 },
      { label: "JUL", pct: 80 },
      { label: "AUG", pct: 62 },
    ],

    recurring: [
      { name: "Netflix", next: "13.09.2026", amount: "67,99" },
      { name: "Digi internet", next: "10.09.2026", amount: "59,00" },
      { name: "Spotify Family", next: "02.09.2026", amount: "44,99" },
      { name: "Gym — World Class", next: "01.09.2026", amount: "199,00" },
      { name: "iCloud 200GB", next: "21.08.2026", amount: "41,99" },
    ],

    // Ask-GEMS suggested prompts: which ones show up in the floating dock
    // depends on the screen the user has open (dashboard.jsx picks the list,
    // AgentDock renders it).
    chatPrompts: {
      pay: { icon: "Send", labelKey: "promptPay" },
      recurring: { icon: "Repeat", labelKey: "promptRecurring" },
      pendingSign: { icon: "FileSignature", labelKey: "promptPendingSign" },
      portfolioGrowth: { icon: "TrendingUp", labelKey: "promptPortfolioGrowth" },
      portfolioMove: { icon: "PiggyBank", labelKey: "promptPortfolioMove" },
      cardFreeze: { icon: "Snowflake", labelKey: "promptCardFreeze" },
      cardLimit: { icon: "Gauge", labelKey: "promptCardLimit" },
      groceries: { icon: "ShoppingCart", labelKey: "promptGroceries" },
      spendingTrend: { icon: "TrendingDown", labelKey: "promptSpendingTrend" },
      settingsPin: { icon: "KeyRound", labelKey: "promptSettingsPin" },
      settings2fa: { icon: "ShieldCheck", labelKey: "promptSettings2fa" },
    },
    screenPrompts: {
      home: ["pay", "recurring"],
      payments: ["pendingSign", "recurring"],
      portfolio: ["portfolioGrowth", "portfolioMove"],
      cards: ["cardFreeze", "cardLimit"],
      analytics: ["groceries", "spendingTrend"],
      settings: ["settingsPin", "settings2fa"],
    },
    screenGreetings: {
      home: "dockGreeting",
      payments: "dockGreetingPayments",
      portfolio: "dockGreetingPortfolio",
      cards: "dockGreetingCards",
      analytics: "dockGreetingAnalytics",
      settings: "dockGreetingSettings",
    },
  };
})();
