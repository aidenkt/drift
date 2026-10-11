// Timeline of changes that touch a model's assumptions. Web-only for now; propose it as a
// schema addition once the engine can produce it.
//
// Case study timeline for data/case_study_aug2026.xlsx (Calder & Finch Home). Every value,
// date and source comes from data/ground_truth.md; impacts are one at a time, US$ millions.

export type Source = {
  publisher: string;
  title: string;
  url: string;
  date: string;
  via: "FRED" | "Bright Data" | "Workbook";
  quote?: string;
  value?: string; // the number this source gives, in the cell's units
  image?: string; // the article's preview image: saved under public/sources, or the page's og:image
};

/** One thing we watch for before calling an assumption changed. */
export type Signal = {
  look_for: string;
  observed: string;
  met: boolean;
};

export type TimelineEvent = {
  id: string;
  date: string;
  title: string;
  kind: "drift" | "news" | "check" | "baseline" | "edit";
  // updated, kept and gone are a stale assumption that has since been dealt with
  // checking: the engine has found or relabeled it and its check is still running
  status: "stale" | "watching" | "current" | "edited" | "updated" | "kept" | "gone" | "checking";
  busy?: boolean; // an edit whose cells the engine is still labeling or checking
  resolution?: { note: string; at?: string; by?: string }; // how, when and by whom
  cells: string[];
  driver: string | null;
  state?: {
    label: string;
    unit: string;
    model: number;
    live: number | null;
    change: string | null; // "+3.7%", "−2 bps"
    as_of: string;
    history: { date: string; value: number }[]; // since the model was built
  };
  signals: Signal[];
  sources: Source[];
  impact: { output: string; label: string; delta: number }[];
  edit?: { before: string; after: string }; // kind "edit" only
  at?: string; // ISO time the change was made, for edits made in Since
  by?: string; // who made it
};

const EBITDA = { output: "P&L!C27", label: "EBITDA" };
const EV = { output: "DCF!B38", label: "Enterprise value" };
const NI = { output: "P&L!C39", label: "Net income" };

export const SAMPLE_TIMELINE: TimelineEvent[] = [
  {
    id: "freight-2026-10-08",
    date: "2026-10-08",
    title: "Shanghai–LA container rates surge",
    kind: "drift",
    status: "stale",
    cells: ["P&L!C18"],
    driver: "freight_feu",
    state: {
      label: "Ocean freight, Shanghai–Los Angeles",
      unit: "$/FEU",
      model: 5739,
      live: 7624,
      change: "+32.8%",
      as_of: "2026-10-08",
      history: [
        { date: "2026-07-30", value: 5739 },
        { date: "2026-10-08", value: 7624 },
      ],
    },
    signals: [
      { look_for: "Latest weekly assessment more than 10% above the model", observed: "$7,624 on 2026-10-08, +32.8%", met: true },
      { look_for: "Number is buried in a formula, not an input cell", observed: "=C17*5739/1000000", met: true },
    ],
    sources: [
      {
        publisher: "Daily Cargo News",
        title: "World Container Index, 8 October 2026",
        url: "https://thedcn.com.au/news/world-container-index-8-october-2026",
        image: "/sources/dcn-wci.jpg",
        date: "2026-10-08",
        via: "Bright Data",
        value: "$7,624",
      },
      {
        publisher: "Shipping Telegraph",
        title: "Drewry World Container Index, week 31 2026",
        url: "https://shippingtelegraph.com/freight-news/drewry-the-world-container-index-decreased-3-this-week-31-2026/",
        image: "/sources/shippingtelegraph-wci.jpg",
        date: "2026-07-30",
        via: "Bright Data",
        value: "$5,739 (in model)",
      },
    ],
    impact: [
      { ...EBITDA, delta: -18.5 },
      { ...EV, delta: -212.0 },
    ],
  },
  {
    id: "ust10y-2026-10-08",
    date: "2026-10-08",
    title: "10-year Treasury yield climbs",
    kind: "drift",
    status: "stale",
    cells: ["DCF!B6"],
    driver: "ust10y",
    state: {
      label: "Risk-free rate, 10-year US Treasury",
      unit: "%",
      model: 0.0475,
      live: 0.0522,
      change: "+47 bps",
      as_of: "2026-10-08",
      history: [
        { date: "2026-07-31", value: 0.0475 },
        { date: "2026-10-08", value: 0.0522 },
      ],
    },
    signals: [
      { look_for: "Move of more than 25 bps from the model value", observed: "+47 bps", met: true },
    ],
    sources: [
      {
        publisher: "Federal Reserve Bank of St. Louis",
        title: "Market Yield on U.S. Treasury Securities at 10-Year (DGS10)",
        url: "https://fred.stlouisfed.org/series/DGS10",
        image: "https://fred.stlouisfed.org/graph/fredgraph.png?id=DGS10&cosd=2026-06-17&coed=2026-10-08",
        date: "2026-10-08",
        via: "FRED",
        value: "5.22%",
      },
    ],
    impact: [{ ...EV, delta: -41.5 }],
  },
  {
    id: "brent-2026-10-06",
    date: "2026-10-06",
    title: "Brent crude spikes",
    kind: "drift",
    status: "stale",
    cells: ["Assumptions!B20"],
    driver: "brent",
    state: {
      label: "Brent crude oil",
      unit: "$/bbl",
      model: 96.95,
      live: 125.44,
      change: "+29.4%",
      as_of: "2026-10-06",
      history: [
        { date: "2026-07-31", value: 96.95 },
        { date: "2026-10-06", value: 125.44 },
      ],
    },
    signals: [
      { look_for: "Spot price more than 10% from the model value", observed: "$125.44, +29.4%", met: true },
      { look_for: "Front-month future agrees with spot", observed: "$104.72 on 2026-10-09, +8.0%", met: false },
    ],
    sources: [
      {
        publisher: "Federal Reserve Bank of St. Louis",
        title: "Crude Oil Prices: Brent - Europe (DCOILBRENTEU)",
        url: "https://fred.stlouisfed.org/series/DCOILBRENTEU",
        image: "https://fred.stlouisfed.org/graph/fredgraph.png?id=DCOILBRENTEU&cosd=2026-06-17&coed=2026-10-08",
        date: "2026-10-06",
        via: "FRED",
        value: "$125.44",
      },
      {
        publisher: "Investing.com",
        title: "Brent Oil Futures historical data",
        url: "https://www.investing.com/commodities/brent-oil-historical-data",
        date: "2026-10-09",
        via: "Bright Data",
        value: "$104.72 front month",
      },
    ],
    impact: [
      { ...EBITDA, delta: -12.0 },
      { ...EV, delta: -137.3 },
    ],
  },
  {
    id: "eurusd-2026-10-02",
    date: "2026-10-02",
    title: "Euro weakens against the dollar",
    kind: "drift",
    status: "stale",
    cells: ["Assumptions!B21"],
    driver: "eurusd",
    state: {
      label: "EUR/USD exchange rate",
      unit: "USD per EUR",
      model: 1.1519,
      live: 1.1259,
      change: "−2.3%",
      as_of: "2026-10-02",
      history: [
        { date: "2026-07-31", value: 1.1519 },
        { date: "2026-10-02", value: 1.1259 },
        { date: "2026-10-09", value: 1.1206 },
      ],
    },
    signals: [
      { look_for: "Move of more than 2% from the model value", observed: "−2.3%", met: true },
      { look_for: "Market close confirms the official print", observed: "1.1206 on 2026-10-09", met: true },
    ],
    sources: [
      {
        publisher: "Federal Reserve Bank of St. Louis",
        title: "U.S. Dollars to Euro Spot Exchange Rate (DEXUSEU)",
        url: "https://fred.stlouisfed.org/series/DEXUSEU",
        image: "https://fred.stlouisfed.org/graph/fredgraph.png?id=DEXUSEU&cosd=2026-06-17&coed=2026-10-08",
        date: "2026-10-02",
        via: "FRED",
        value: "1.1259",
      },
      {
        publisher: "Yahoo Finance",
        title: "EUR/USD historical data",
        url: "https://finance.yahoo.com/quote/EURUSD=X/history/",
        date: "2026-10-09",
        via: "Bright Data",
        value: "1.1206",
      },
    ],
    impact: [
      { ...EBITDA, delta: 1.9 },
      { ...EV, delta: 22.1 },
    ],
  },
  {
    id: "sofr-2026-09-16",
    date: "2026-09-16",
    title: "Fed raises rates 25 bp",
    kind: "drift",
    status: "stale",
    cells: ["P&L!C35"],
    driver: "sofr",
    state: {
      label: "SOFR, floating base rate on the term loan",
      unit: "%",
      model: 0.0366,
      live: 0.0387,
      change: "+21 bps",
      as_of: "2026-10-08",
      history: [
        { date: "2026-07-31", value: 0.0366 },
        { date: "2026-10-08", value: 0.0387 },
      ],
    },
    signals: [
      { look_for: "Policy rate decision since the model was built", observed: "target range raised 25 bp to 3.75–4.00% on 2026-09-16", met: true },
      { look_for: "Move of more than 10 bps from the model value", observed: "+21 bps", met: true },
      { look_for: "Number is buried in a formula, not an input cell", observed: "=0.0366+Assumptions!$B$29", met: true },
    ],
    sources: [
      {
        publisher: "Federal Reserve Bank of New York",
        title: "Secured Overnight Financing Rate (SOFR)",
        url: "https://fred.stlouisfed.org/series/SOFR",
        image: "https://fred.stlouisfed.org/graph/fredgraph.png?id=SOFR&cosd=2026-06-17&coed=2026-10-08",
        date: "2026-10-08",
        via: "FRED",
        value: "3.87%",
      },
      {
        publisher: "Federal Reserve Bank of St. Louis",
        title: "Federal Funds Target Range - Upper Limit (DFEDTARU)",
        url: "https://fred.stlouisfed.org/series/DFEDTARU",
        image: "https://fred.stlouisfed.org/graph/fredgraph.png?id=DFEDTARU&cosd=2026-06-17&coed=2026-10-08",
        date: "2026-09-16",
        via: "FRED",
        value: "4.00%",
      },
    ],
    impact: [
      { ...EBITDA, delta: 0 },
      { ...NI, delta: -0.5 },
      { ...EV, delta: -5.1 },
    ],
  },
  {
    id: "canada-tariff-2026-09-15",
    date: "2026-09-15",
    title: "CBP adds furniture to the 50% Canada tariff",
    kind: "news",
    status: "stale",
    cells: ["Assumptions!B23"],
    driver: "tariff",
    state: {
      label: "Tariff on Canada-origin furniture",
      unit: "%",
      model: 0,
      live: 0.5,
      change: "+50 pp",
      as_of: "2026-09-15",
      history: [],
    },
    signals: [
      { look_for: "A new duty covering the model's import country", observed: "Section 338, 50%, in force 2026-08-22", met: true },
      { look_for: "The model's product category is on the covered list", observed: "seating and furniture added 2026-09-15", met: true },
    ],
    sources: [
      {
        publisher: "U.S. Customs and Border Protection",
        title: "CSMS #69606660",
        url: "https://content.govdelivery.com/accounts/USDHSCBP/bulletins/4261d04",
        date: "2026-09-15",
        via: "Bright Data",
        value: "50%",
      },
      {
        publisher: "Zonos",
        title: "Section 338 Canada tariffs",
        url: "https://zonos.com/docs/guides/country-guides/united-states/section-338-canada-tariffs",
        date: "2026-09-15",
        via: "Bright Data",
      },
    ],
    impact: [
      { ...EBITDA, delta: -48.1 },
      { ...EV, delta: -552.4 },
    ],
  },
  {
    id: "vietnam-tariff-check",
    date: "2026-09-30",
    title: "Section 301 probe brings no new Vietnam tariff",
    kind: "check",
    status: "current",
    cells: ["Assumptions!B22"],
    driver: "tariff",
    state: {
      label: "Tariff on Vietnam-origin furniture",
      unit: "%",
      model: 0.125,
      live: 0.125,
      change: "0.0 pp",
      as_of: "2026-09-30",
      history: [],
    },
    signals: [
      { look_for: "A new or changed duty on Vietnam-origin furniture", observed: "Section 301 excess-capacity probe: no tariff yet", met: false },
    ],
    sources: [
      {
        publisher: "C.H. Robinson",
        title: "New Section 301 forced-labor tariffs now in effect",
        url: "https://www.chrobinson.com/en-us/resources/insights-and-advisories/client-advisories/2026q3/07-24-26-client-advisory-new-section-301-forced-labor-tariffs-now-in-effect/",
        date: "2026-07-24",
        via: "Bright Data",
        value: "12.5%",
      },
      {
        publisher: "DFDL",
        title: "US Section 301 tariffs: ASEAN implications",
        url: "https://www.dfdl.com/insights/legal-and-tax-updates/us-section-301-tariffs-asean-implications/",
        image: "/sources/dfdl-301.jpg",
        date: "2026-09-30",
        via: "Bright Data",
      },
    ],
    impact: [],
  },
  {
    id: "tax-rate-check",
    date: "2026-09-30",
    title: "No change to the corporate tax code",
    kind: "check",
    status: "current",
    cells: ["Assumptions!B24"],
    driver: "tax",
    state: {
      label: "US federal corporate income tax rate",
      unit: "%",
      model: 0.21,
      live: 0.21,
      change: "0.0 pp",
      as_of: "2026-10-10",
      history: [],
    },
    signals: [{ look_for: "Change to 26 U.S.C. § 11(b)", observed: "none", met: false }],
    sources: [
      {
        publisher: "Cornell Law School LII",
        title: "26 U.S. Code § 11, Tax imposed",
        url: "https://www.law.cornell.edu/uscode/text/26/11",
        date: "2026-10-10",
        via: "Bright Data",
        value: "21%",
      },
    ],
    impact: [],
  },
  {
    id: "baseline-2026-08-01",
    date: "2026-08-01",
    title: "Assumptions set",
    kind: "baseline",
    status: "current",
    cells: ["P&L!C18", "DCF!B6", "Assumptions!B20", "Assumptions!B21", "P&L!C35", "Assumptions!B23", "Assumptions!B22", "Assumptions!B24"],
    driver: null,
    signals: [],
    sources: [
      {
        publisher: "Workbook",
        title: "case_study_aug2026.xlsx",
        url: "",
        date: "2026-08-01",
        via: "Workbook",
      },
    ],
    impact: [],
  },
];
