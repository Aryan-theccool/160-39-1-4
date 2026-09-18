# BIS Standards AI — web frontend

Part 6. Next.js 14 + TypeScript + TailwindCSS + shadcn/ui in front of the
`bis_api` service, in an Indian tricolour theme.

```bash
# terminal 1 — the API
cd ../bis_scraper && export PYTHONPATH=src
uvicorn bis_api.main:app --reload --port 8000

# terminal 2 — this app
npm install
npm run dev            # http://localhost:3000
```

---

## The six pages

| Page | Route | What it does |
|---|---|---|
| **Home** | `/` | The search bar, and nothing competing with it. Example queries are real and clickable. |
| **Search results** | `/search?q=` | IS code cards with match strength, the clause that matched, the retrievers that found it, and an **AI answer** tab for the cited summary. Filters for division, result count and superseded editions. |
| **Tender analysis** | `/upload` | Drag & drop a tender PDF. Every IS code the document cites is extracted and then looked up, so you see which are in the corpus and which are not. |
| **Compliance** | `/compliance` | Product description + the standards you hold → score gauge, grade, action items, superseded editions to replace, and a link to the printable gap report. |
| **Standards browser** | `/standards` | All 197 standards as a filterable table — free text, division, year, edition, QCO-mandatory — with CSV export. |
| **Dashboard** | `/dashboard` | Standards by division, by decade, by committee, current vs superseded, plus the live retrieval configuration the API is actually running on. |

## Stack

Next.js 14 (App Router) · TypeScript (strict) · TailwindCSS 3 · shadcn/ui ·
Radix primitives · Recharts · axios · lucide-react · Vitest.

```
src/
├── app/                    one directory per page, plus layout and not-found
├── components/
│   ├── ui/                 shadcn primitives (button, card, table, select, …)
│   ├── site-nav.tsx        header, nav, the API health pill
│   ├── standard-card.tsx   the result card
│   ├── match-meter.tsx     match strength — see the note below
│   ├── score-gauge.tsx     the compliance dial
│   ├── answer-panel.tsx    RAG answer + citations + warnings
│   ├── upload-dropzone.tsx drag & drop with client-side validation
│   └── api-status.tsx      live /health pill in the header
├── lib/
│   ├── api.ts              typed client for every endpoint
│   ├── format.ts           presentation + aggregation helpers
│   └── utils.ts            cn()
└── hooks/use-api.ts        useAsync (race-safe) and useDebounced
```

### Theme

Saffron `#FF9933` is `primary`, India green `#138808` is `secondary`, and the
Ashoka Chakra navy `#000080` is a chart colour. The two decorative pieces:

- `.tricolor-bar` — a 3px saffron/white/navy/white/green rule under the header
  and above the footer. The navy stripe is what makes it read as the flag rather
  than as three arbitrary bands.
- `.tricolor-text` — a saffron→green gradient on the two headline words.

Both are plain CSS in `globals.css`, so no page repeats a hex value.

---

## How the browser reaches the API

**The client calls `/api/v1/*` on its own origin, and Next.js proxies that to
`http://127.0.0.1:8000`** (`next.config.mjs`).

The brief said `axios → http://localhost:8000/api/v1`, which is the right address
on a laptop where both processes run side by side — and wrong everywhere else.
When the browser is not on the same host as the API, `localhost` means *the
user's* machine, and every request fails with a connection error that reads like
the API is down. It is also the single most common way a working local build
breaks on first deploy.

A relative URL works in both cases, so that is the default. Set
`NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` to talk to the API directly —
correct whenever browser and API really are on the same machine.

```
NEXT_PUBLIC_API_URL   unset → relative, proxied by Next   (default)
API_PROXY_TARGET      where Next proxies to  (default http://127.0.0.1:8000)
```

---

## Two things this UI deliberately does not do

**1. It does not print a confidence percentage on search results.**

The brief asked for "IS code cards with confidence scores". The API does not
return one, and it would be easy to fake: `score` is a reciprocal-rank-fusion
value that depends on how many retrievers fired and on the result-set size, so
`0.041` is not "4% confident". A card reading “94% confident” next to an IS code
would be the most misleading element in the app, because nothing computed it.

What the cards show instead is **match strength relative to the best hit**
(`43% of best`) plus the evidence behind the ranking: which retrievers returned
it, and the clause that matched. That is checkable. The distinction is stated in
the UI, not just here.

**2. It does not hide how an answer was produced.**

The RAG service answers in `extractive` mode with no LLM key and `llm` mode with
one. Those deserve different trust, so the badge says which ran. Citations the
corpus could not verify are listed separately, in warning colours, with the
codes named.

---

## Tests

```bash
npm test          # 42 tests, vitest, no network
npm run typecheck # tsc --noEmit
npm run build     # production build, also type-checks and lints
```

| File | Covers |
|---|---|
| `src/lib/__tests__/format.test.ts` | match strength (including the divide-by-zero and out-of-order cases), retriever labels, the count/decade aggregations that feed the charts, grade colours, formatters |
| `src/lib/__tests__/api.test.ts` | the relative base URL, error mapping for 404/500/503/network failure, POST bodies, gap-report URL encoding |
| `src/components/__tests__/render.test.tsx` | server-rendered output of the gauge, the meter, the card and the answer panel — the numbers, the accessible label, and the "never say confidence" rule |

Four of these found real problems:

- A local `const health = healthState.data` **shadowed the imported `health()`
  function** in the dashboard, so the fetch called `null` and the page rendered
  nothing. `tsc` caught it; nothing else would have until someone opened the page.
- The axios stub in `api.test.ts` returned a 404 response object instead of
  rejecting. Real adapters call `settle`, so the stub made axios treat a 404 as
  success and the client's error mapping was never exercised. The tests were
  passing a code path they never entered.
- `tsconfig.json` had no `target`, so `tsc` defaulted to ES5 and rejected `[...map]`.
- JSX in Vitest needs the automatic runtime configured explicitly; the default is
  the classic one, which demands `import React` in every file.

> **Not covered:** anything requiring a browser. There is no headless Chromium
> available in the environment this was built in, so hydration, drag & drop and
> the Recharts rendering are verified by the production build and by the
> server-rendered markup of the components, not by a real browser session.

## On the "197 standards"

The brief's 197 is the corpus on the machine this was built for. **Every count
in the UI comes from `GET /api/v1/health`**, never from a hardcoded number, so
the pages are correct against whatever dataset the API is serving — including
the 12-standard fixture used for the development screenshots.

## shadcn/ui

`components.json` is a real shadcn config (`new-york`, zinc, CSS variables,
`@/components`). The registry at `ui.shadcn.com` was unreachable from the
environment this was built in, so the primitives in `src/components/ui/` were
written by hand in the same style with the same dependencies — which is what
shadcn does anyway: the components are source files vendored into your repo, not
a package. On a machine with network access, `npx shadcn@2.1.8 add <name>` will
work normally and either match or replace them.
