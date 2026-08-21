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
    depositTerms: [
      { months: 3, rateBps: 480 },
      { months: 6, rateBps: 540 },
      { months: 12, rateBps: 610 },
      { months: 24, rateBps: 665 },
    ],

    credits: [
      { id: "cr-personal", kind: "loan", nameKey: "personal", termMonths: 60, paidMonths: 24, outstandingMinor: 3410000, cur: "RON", rateBps: 890 },
      { id: "cr-line", kind: "line", nameKey: "line", limitMinor: 600000, usedMinor: 120000, cur: "RON", rateBps: 1890 },
    ],
    creditProducts: [
      { id: "personal", kind: "loan", rateBps: 890, maxMinor: 15000000, terms: [12, 24, 36, 48, 60] },
      { id: "line", kind: "line", rateBps: 1890, maxMinor: 2000000, terms: [] },
      { id: "mortgage", kind: "loan", rateBps: 590, maxMinor: 90000000, terms: [120, 180, 240, 300, 360] },
    ],

    holdings: [
      { id: "h-msci", name: "MSCI World ETF", unitKey: "units", units: 20, unitPriceMinor: 45700, cur: "RON" },
      { id: "h-tlv", name: "TLV — Banca Transilvania", unitKey: "shares", units: 320, unitPriceMinor: 2100, cur: "RON" },
      { id: "h-btc", name: "BTC", unitKey: "coins", units: 0.014, unitPriceMinor: 14857143, cur: "RON" },
    ],
    investCashMinor: 100000,

    categories: [
      { key: "groceries", value: "1.180 RON · 32%" },
      { key: "utilities", value: "840 RON · 23%" },
      { key: "transport", value: "690 RON · 19%" },
      { key: "entertainment", value: "510 RON · 14%" },
      { key: "other", value: "430 RON · 12%" },
    ],
    groceryBars: [
      { label: "MAR", pct: 68 },
      { label: "APR", pct: 82 },
      { label: "MAY", pct: 74 },
      { label: "JUN", pct: 90 },
      { label: "JUL", pct: 80 },
      { label: "AUG", pct: 62 },
    ],
    yearBars: [
      { label: "S", inc: 72, out: 48 },
      { label: "O", inc: 68, out: 55 },
      { label: "N", inc: 80, out: 62 },
      { label: "D", inc: 92, out: 74 },
      { label: "J", inc: 64, out: 40 },
      { label: "F", inc: 70, out: 52 },
      { label: "M", inc: 76, out: 58 },
      { label: "A", inc: 74, out: 50 },
      { label: "M", inc: 82, out: 66 },
      { label: "J", inc: 78, out: 60 },
      { label: "J", inc: 88, out: 71 },
      { label: "A", inc: 84, out: 57 },
    ],

    recurring: [
      { name: "Netflix", next: "13.09.2026", amount: "67,99" },
      { name: "Digi internet", next: "10.09.2026", amount: "59,00" },
      { name: "Spotify Family", next: "02.09.2026", amount: "44,99" },
      { name: "Gym — World Class", next: "01.09.2026", amount: "199,00" },
      { name: "iCloud 200GB", next: "21.08.2026", amount: "41,99" },
    ],
  };
})();
