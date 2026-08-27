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

    accounts: [
      {
        id: "acc-current-ron",
        cur: "RON",
        typeKey: "current",
        minor: 4218055,
        iban: "RO49 AAAA 1B31 0075 9384 4127",
        ibanShort: "RO49 •••• 4127",
      },
      {
        id: "acc-savings-eur",
        cur: "EUR",
        typeKey: "savings",
        minor: 1194000,
        iban: "RO12 BBBB 2C44 0011 2288 8802",
        ibanShort: "RO12 •••• 8802",
      },
      {
        id: "acc-deposit-ron",
        cur: "RON",
        typeKey: "deposit",
        minor: 5541000,
        iban: "RO88 CCCC 3D55 0099 4410 6610",
        ibanShort: "RO88 •••• 6610",
      },
      {
        id: "acc-invest-usd",
        cur: "USD",
        typeKey: "invest",
        minor: 402010,
        iban: "RO31 DDDD 4E66 0044 7712 2210",
        ibanShort: "RO31 •••• 2210",
      },
    ],

    accountTypes: [
      { key: "current", creates: "account", rateBps: 0, monthlyFeeMinor: 0, minOpenMinor: 0, accessKey: "anytime" },
      { key: "savings", creates: "account", rateBps: 225, monthlyFeeMinor: 0, minOpenMinor: 10000, accessKey: "anytime" },
      { key: "deposit", creates: "deposit", depositKind: "term", monthlyFeeMinor: 0, minOpenMinor: 100000, accessKey: "maturity" },
      { key: "goal", creates: "deposit", depositKind: "goal", monthlyFeeMinor: 0, minOpenMinor: 10000, accessKey: "goalExit" },
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

    deposits: [
      { id: "dep-term-12m", kind: "term", name: "Term deposit 12M", rateBps: 610, matures: "2027-02-14", minor: 5541000, cur: "RON" },
      { id: "dep-eur-savings", kind: "savings", name: "EUR savings", rateBps: 225, matures: null, minor: 1194000, cur: "EUR" },
      { id: "dep-goal-apartment", kind: "goal", name: "Goal — apartment", rateBps: 300, matures: "2028-06-01", minor: 820000, targetMinor: 5000000, cur: "RON" },
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

    credits: [
      { id: "cr-personal", kind: "loan", nameKey: "personal", termMonths: 60, paidMonths: 24, outstandingMinor: 3410000, cur: "RON", rateBps: 890 },
      { id: "cr-line", kind: "line", nameKey: "line", limitMinor: 600000, usedMinor: 120000, cur: "RON", rateBps: 1890 },
    ],
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

    holdings: [
      { id: "h-msci", name: "MSCI World ETF", unitKey: "units", units: 20, unitPriceMinor: 45700, cur: "RON" },
      { id: "h-tlv", name: "TLV — Banca Transilvania", unitKey: "shares", units: 320, unitPriceMinor: 2100, cur: "RON" },
      { id: "h-btc", name: "BTC", unitKey: "coins", units: 0.014, unitPriceMinor: 14857143, cur: "RON" },
      { id: "h-spy", name: "S&P 500 ETF", unitKey: "units", units: 0, unitPriceMinor: 254800, cur: "RON" },
      { id: "h-aapl", name: "Apple", unitKey: "shares", units: 0, unitPriceMinor: 104650, cur: "RON" },
      { id: "h-snp", name: "OMV Petrom", unitKey: "shares", units: 0, unitPriceMinor: 50, cur: "RON" },
      { id: "h-eth", name: "Ethereum", unitKey: "coins", units: 0, unitPriceMinor: 1729000, cur: "RON" },
      { id: "h-msft", name: "Microsoft", unitKey: "shares", units: 0, unitPriceMinor: 213850, cur: "RON" },
      { id: "h-amzn", name: "Amazon", unitKey: "shares", units: 0, unitPriceMinor: 100100, cur: "RON" },
      { id: "h-googl", name: "Alphabet", unitKey: "shares", units: 0, unitPriceMinor: 86450, cur: "RON" },
      { id: "h-nvda", name: "Nvidia", unitKey: "shares", units: 0, unitPriceMinor: 61425, cur: "RON" },
      { id: "h-meta", name: "Meta", unitKey: "shares", units: 0, unitPriceMinor: 282100, cur: "RON" },
      { id: "h-tsla", name: "Tesla", unitKey: "shares", units: 0, unitPriceMinor: 118300, cur: "RON" },
      { id: "h-gld", name: "Gold", unitKey: "units", units: 0, unitPriceMinor: 113750, cur: "RON" },
      { id: "h-slv", name: "Silver", unitKey: "units", units: 0, unitPriceMinor: 13195, cur: "RON" },
      { id: "h-pplt", name: "Platinum", unitKey: "units", units: 0, unitPriceMinor: 44135, cur: "RON" },
    ],
    investCashMinor: 100000,

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
