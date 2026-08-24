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
      { key: "portfolio", num: "04" },
      { key: "cards", num: "05" },
      { key: "analytics", num: "06" },
      { key: "settings", num: "07" },
    ],

    totalBalance: "128.470,55",

    accounts: [
      { cur: "RON", typeKey: "current", amount: "42.180,55", iban: "RO49 •••• 4127" },
      { cur: "EUR", typeKey: "savings", amount: "11.940,00", iban: "RO12 •••• 8802" },
      { cur: "RON", typeKey: "deposit", amount: "55.410,00", iban: "RO88 •••• 6610" },
    ],
    accountsFull: [
      { cur: "RON", typeKey: "current", amount: "42.180,55", iban: "RO49 AAAA 1B31 0075 9384 4127" },
      { cur: "EUR", typeKey: "savings", amount: "11.940,00", iban: "RO12 BBBB 2C44 0011 2288 8802" },
      { cur: "RON", typeKey: "deposit", amount: "55.410,00", iban: "RO88 CCCC 3D55 0099 4410 6610" },
      { cur: "USD", typeKey: "invest", amount: "4.020,10", iban: "RO31 DDDD 4E66 0044 7712 2210" },
    ],

    transactions: [
      { date: "16.08.2026", who: "Kaufland Băneasa", ref: "POS 4127", categoryKey: "groceries", statusKey: "booked", amount: "214,80", direction: "out" },
      { date: "15.08.2026", who: "Enel Energie", ref: "Direct debit", categoryKey: "utilities", statusKey: "booked", amount: "187,40", direction: "out" },
      { date: "15.08.2026", who: "Salary — Nexo SRL", ref: "AUG 2026", categoryKey: "income", statusKey: "booked", amount: "9.400,00", direction: "in" },
      { date: "14.08.2026", who: "Ionescu Maria", ref: "Split — dinner", categoryKey: "transfer", statusKey: "booked", amount: "120,00", direction: "out" },
      { date: "13.08.2026", who: "Netflix", ref: "Subscription", categoryKey: "entertainment", statusKey: "booked", amount: "67,99", direction: "out" },
      { date: "12.08.2026", who: "Revolut top-up", ref: "SEPA out", categoryKey: "transfer", statusKey: "pending", amount: "500,00", direction: "out" },
      { date: "11.08.2026", who: "OMV Petrom", ref: "POS 4127", categoryKey: "transport", statusKey: "booked", amount: "320,15", direction: "out" },
      { date: "10.08.2026", who: "Digi Communications", ref: "Direct debit", categoryKey: "utilities", statusKey: "booked", amount: "59,00", direction: "out" },
    ],

    pending: [
      { num: "01", who: "Revolut top-up", noteKey: "revolut", amount: "500,00" },
      { num: "02", who: "Chirie august", noteKey: "rent", amount: "2.400,00" },
    ],

    deposits: [
      { name: "Term deposit 12M", rate: "6,10%", due: "14.02.2027", value: "55.410,00" },
      { name: "EUR savings", rate: "2,25%", due: "—", value: "11.940,00" },
      { name: "Goal — apartment", rate: "3,00%", due: "01.06.2028", value: "8.200,00" },
    ],
    credits: [
      { name: "Personal loan · 24 of 60 months", left: "34.100 RON left", pct: 40 },
      { name: "Card credit line", left: "1.200 of 6.000 used", pct: 20 },
    ],
    holdings: [
      { name: "MSCI World ETF", qty: "12 units", value: "9.140,00" },
      { name: "TLV — Banca Transilvania", qty: "320 shares", value: "6.720,20" },
      { name: "BTC", qty: "0,014", value: "2.080,00" },
      { name: "Cash to invest", qty: "—", value: "1.000,00" },
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
