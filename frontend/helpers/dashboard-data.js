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

    cards: [
      { kindKey: "physicalDebit", num: "•••• •••• •••• 4127", owner: "A. POP", exp: "09/29", state: "active" },
      { kindKey: "virtualMastercard", num: "•••• •••• •••• 3319", owner: "A. POP", exp: "04/28", state: "active" },
      { kindKey: "virtualSingleUse", num: "•••• •••• •••• 7740", owner: "A. POP", exp: "08/26", state: "frozen" },
      { kindKey: "physicalMetal", num: "•••• •••• •••• 1002", owner: "A. POP", exp: "12/30", state: "active" },
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
