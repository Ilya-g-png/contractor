
# Component Contracts — CD-5: Dogwatch web dashboard shell

**Sources**
- **UI specification ("UI"):** `artifacts/design/ui_specification.md`. Every component below traces to a screen, state or interaction pattern in it.
- **Architecture ("ARCH"):** `artifacts/design/architecture.md` §3.4, §4.6, §6.21–§6.33.
- **Architecture contracts ("AC"):** `artifacts/design/architecture_contracts.md`:
  - IC-5.1 `fetchHealth`
  - IC-5.2 `resolveView`
  - IC-5.3 DOM contract
  - DC-9 `ApiStatusState`
  - DC-10 strings
  - DC-11 tokens
  - INV-W1–W12
- **Frozen spec ("FS"):** FR-070–FR-081 and the "API status indicator" Key Entity.
- **Prior research:** CD-2 §2.4 (untrusted rendering, CSP), at `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/9c37b285-b35d-4dc2-be1c-2347272422e0-research-paper.md`.

**Workspace check.** The repository holds only `.am/` and `.playwright-mcp/`, so there is no component library or naming convention to reuse. Component names follow ARCH §3.4. `Shell` and `ErrorFallback` are the UI's own screen names (UI §2.1, §3.1, §3.4), split out so the error fallback can reuse the exact landmark frame.

**Stack (fixed upstream):** React 19 function components, plus one class component for the error boundary. TypeScript strict. Plain CSS files that reference `styles/tokens.css`. No router library, no UI library, no global store (ARCH §2.4, FR-073).

**Notation**
- **MUST**: required.
- **SHOULD**: recommended by the UI; it becomes a MUST unless the related open question is answered otherwise.
- **Invariant IDs** are local to this document: `APP-n`, `SHL-n`, `HOME-n`, `STS-n`, `NF-n`, `EB-n`, `EF-n`, `X-n` (cross-component).
- **"Checked by"** says where each invariant runs:
  - **unit**: Vitest + Testing Library + jsdom, in the `web` CI job on every run;
  - **axe**: axe-core in the same suite;
  - **static**: a grep or lint over `web/src`, in the `web` CI job;
  - **Acc**: checked once at acceptance.

---

## 0. Component inventory and composition

| # | Component | File | Kind | UI anchor | ARCH / AC anchor |
|---|---|---|---|---|---|
| C-1 | `App` | `web/src/App.tsx` | function | §2.2 routing rule, §2.3 | ARCH §3.4 `App` + `router.ts`; AC IC-5.2 |
| C-2 | `Shell` | `web/src/Shell.tsx` | function, presentational | §2.1, §3.1, §7.5 "Shell header" | ARCH §3.4 `App` (shell role); AC IC-5.3 "Document" |
| C-3 | `HomeView` | `web/src/views/HomeView.tsx` | function | §3.2 | ARCH §3.4; AC IC-5.3 "Views" |
| C-4 | `ApiStatus` | `web/src/components/ApiStatus.tsx` | function, stateful | §3.2 state table, IP-1, IP-4, §5.3 | ARCH §4.6; AC DC-9, IC-5.1, IC-5.3 |
| C-5 | `NotFoundView` | `web/src/views/NotFoundView.tsx` | function | §3.3, IP-2 | ARCH §3.4; AC IC-5.2 |
| C-6 | `ErrorBoundary` | `web/src/ErrorBoundary.tsx` | class | §3.4 (entry condition) | ARCH §3.4, §6.32; AC INV-W8 |
| C-7 | `ErrorFallback` | `web/src/ErrorFallback.tsx` | function | §3.4 (screen), IP-3 | ARCH §3.4 (fallback); AC IC-5.3 "Error boundary fallback" |

File paths are proposals inside the `web/src` layout from ARCH §3.4. Moving a file is not a contract change; renaming a component is.

**Non-component modules these contracts consume.** They are specified elsewhere and not re-specified here:

| Module | Contract |
|---|---|
| `api/health.ts` | `fetchHealth(baseUrl, signal): Promise<"available" \| "unavailable">`. It never rejects (AC IC-5.1). |
| `router.ts` | `resolveView(pathname): "home" \| "not-found"` (AC IC-5.2). |
| `strings.ts` | The single `strings` object (AC DC-10, plus the additions in X-1). |
| `config.ts` (proposed, OQ-C3) | `export const API_BASE_URL = import.meta.env.VITE_DOGWATCH_API_BASE_URL ?? "/api/v1"` (AC DC-8, IC-5.1). |
| `styles/tokens.css` | The design tokens (AC DC-11, UI §7). |

**Composition** (mounted by `main.tsx`):

```
<StrictMode>                       (dev double-effect is harmless; ARCH §6.24)
  <ErrorBoundary>                  C-6  — exactly one instance, the outermost app component
    <App />                        C-1
      └─ <Shell>                   C-2  — <header> wordmark + <main>{children}
           ├─ <HomeView />         C-3  (resolveView === "home")
           │    └─ <ApiStatus />   C-4
           └─ <NotFoundView />     C-5  (resolveView === "not-found")
    ── on render error ──▶ <ErrorFallback />   C-7
                              └─ <Shell> h1 + reload button </Shell>
  </ErrorBoundary>
</StrictMode>
```

---

## C-1 `App`

**Purpose.** Resolves the current URL path to exactly one view and renders it inside `Shell`. This is the only routing logic in CD-5 (UI §2.2).

### Props / Inputs

| Name | Type | Required | Default | Validation |
|---|---|---|---|---|
| `pathname` | `string` | optional | `window.location.pathname`, read once per render | Any string. It is passed unchanged to `resolveView`. There is no normalisation: `/index.html`, `/x/` and `""` resolve to Not Found (AC IC-5.2). |

`pathname` exists so tests can render each view without touching `window.location` (it is used by the axe checks in INV-W4). Production code never passes it.

### Events / Outputs
None. Navigation is native full document loads (UI §2.2), so `App` emits nothing and listens to nothing. It does not handle `popstate`, call `pushState`/`replaceState`, or intercept link clicks.

### State machine
Stateless. The view is a pure function of `pathname`:

| `resolveView(pathname)` | Rendered |
|---|---|
| `"home"` | `<Shell><HomeView /></Shell>` |
| `"not-found"` | `<Shell><NotFoundView /></Shell>` |

### Slots / Content surfaces
None exposed. `App` fills `Shell`'s `children` slot with the resolved view.

### Invariants

| ID | Predicate | Checked by |
|---|---|---|
| APP-1 | `render(<App pathname="/" />)` contains `getByRole("heading", { level: 1, name: strings.home.title })`, and the query for `strings.notFound.title` returns null. | unit |
| APP-2 | For every `p` in `{"/x", "/index.html", "/a/b", "/x/", ""}`, `render(<App pathname={p} />)` contains the `h1` `strings.notFound.title` and no `role="status"` element. | unit (mirrors INV-W9) |
| APP-3 | For every route, exactly one `banner` landmark, one `main` landmark and one `h1` are present. | unit |
| APP-4 | `web/src` contains no `history.pushState`, `history.replaceState`, `addEventListener("popstate"` or hash-route parsing (`location.hash`). | static |
| APP-5 | `App` imports no router package. `package.json` `dependencies` lists only `react` and `react-dom`. | static (ARCH §2.4; protects the FR-074 budget) |

---

## C-2 `Shell`

**Purpose.** Provides the landmark frame (`header` holding the product wordmark, plus `main`) shared by every screen, including the error fallback (UI §3.1, §3.4).

### Props / Inputs

| Name | Type | Required | Default | Validation |
|---|---|---|---|---|
| `children` | `React.ReactNode` | required | — | It MUST contain exactly one `h1` (the view's heading). `Shell` does not add one. |

### Events / Outputs
None.

### State machine
Stateless. It has no hooks or effects and reads no data, so it can only fail through a coding error. This is required because `ErrorFallback` reuses it (EF-6).

### Slots / Content surfaces

| Slot | Content type | Layout role |
|---|---|---|
| `children` | One view's content: an `h1` followed by view body elements | Rendered inside `<main>`, within the content container. Single column at all breakpoints (UI §6.2–§6.3). |

**Fixed (non-slot) content.** `<header>` contains the wordmark `strings.productName` in a non-heading, non-interactive element (`<span>`). It is plain text, not a link (UI §2.2, OQ-U6 default).

**DOM shape:**
```html
<header class="shell-header">
  <div class="shell-container"><span class="shell-wordmark">Dogwatch</span></div>
</header>
<main class="shell-main">
  <div class="shell-container">{children}</div>
</main>
```
`<header>` and `<main>` are siblings at the top level of `#root`, never nested inside `section`, `article` or `main`, so `header` maps to `banner` (UI §5.3).

**Layout** (UI §6.2, §7.5; tokens only):

| Element | compact (< 640 px) | medium (640–1023 px) | wide (≥ 1024 px) |
|---|---|---|---|
| `.shell-container` inline padding | `var(--space-4)` | `var(--space-6)` | `var(--space-8)` |
| `.shell-container` width | full | full | `max-width: var(--layout-max-width)`, `margin-inline: auto` |
| `.shell-header` | `var(--color-surface)` background; bottom border `1px solid var(--color-border)`; block padding `var(--space-4)` | same | same |
| `.shell-wordmark` | `var(--font-size-lg)`, `var(--font-weight-semibold)`, `var(--line-height-tight)`, `var(--color-text)` | same | same |

### Invariants

| ID | Predicate | Checked by |
|---|---|---|
| SHL-1 | `render(<Shell><h1>t</h1></Shell>)`: `getAllByRole("banner").length === 1`, `getAllByRole("main").length === 1`, and `getByRole("banner").textContent === strings.productName`. | unit |
| SHL-2 | The banner contains no element matching `h1,h2,h3,h4,h5,h6,a,button,[tabindex]`. | unit |
| SHL-3 | `children` are rendered as descendants of the `main` landmark and of no other landmark. | unit |
| SHL-4 | `Shell.tsx` contains no `use[A-Z]` hook call and no `useEffect`. | static |
| SHL-5 | At 320 CSS px viewport width on Home and Not Found, `document.documentElement.scrollWidth <= 320` (WCAG 2.2 SC 1.4.10). Tool: Chrome DevTools device mode or a Playwright trace; desktop cable, no CPU throttle. | Acc (INV-W11) |

---

## C-3 `HomeView`

**Purpose.** Renders the Home screen at `/`: the page heading and the API status indicator (UI §3.2, AS-5.1, AS-5.2).

### Props / Inputs
None. The API base URL is taken from `ApiStatus`'s default; `HomeView` never overrides it.

### Events / Outputs

| Output | When | Effect |
|---|---|---|
| Document title | On mount (`useEffect`, empty deps) | `document.title = strings.productName` ("Dogwatch", UI §2.4) |

### State machine
Stateless. All live state belongs to `ApiStatus`.

### Slots / Content surfaces
None exposed. Fixed content in reading order:
1. `<h1 class="page-heading">{strings.home.title}</h1>` ("Dashboard", OQ-U1).
2. `<ApiStatus />`.

There is no empty-state copy (UI §3.2 Empty row; OQ-U2 default).

### Invariants

| ID | Predicate | Checked by |
|---|---|---|
| HOME-1 | After render, the `h1` precedes the `role="status"` element in document order (`compareDocumentPosition` reports `FOLLOWING`). | unit |
| HOME-2 | `document.title === strings.productName` after mount. | unit |
| HOME-3 | Home contains zero focusable elements: `container.querySelectorAll("a[href],button,input,select,textarea,[tabindex]").length === 0` (UI §5.1). | unit |
| HOME-4 | `axe.run` with tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` on `<App pathname="/" />` reports `violations.length === 0` in each of the three `ApiStatus` states. WCAG 2.2 AA; SC 1.3.1, 2.4.2, 3.1.1, 4.1.3. Throttling: not applicable (static DOM). | axe (INV-W4) |
| HOME-5 | The `role="status"` element is present in the **first** committed render, synchronously after `render()` and before any `await` (supports CLS ≤ 0.1, UI §3.2 layout-stability rule). | unit |

---

## C-4 `ApiStatus`

**Purpose.** Owns the API status indicator state machine. It makes exactly one health check per mount and announces the result politely, showing only fixed strings (UI §3.2, IP-1, IP-4; ARCH §4.6; AC DC-9).

### Props / Inputs

| Name | Type | Required | Default | Validation |
|---|---|---|---|---|
| `baseUrl` | `string` | optional | `API_BASE_URL` (`VITE_DOGWATCH_API_BASE_URL ?? "/api/v1"`) | It must be non-empty. Trailing slashes are trimmed by `fetchHealth`, not here. It is read at mount. A later change does not restart a terminal state (STS-6). |

`baseUrl` exists so tests can assert the URL used; production callers pass nothing. There is no `timeoutMs` prop: the 5 s timeout is fixed inside `fetchHealth` (AC IC-5.1).

### Events / Outputs
**No callbacks.** No consumer needs the result in CD-5, so any callback prop would be speculative. The outputs are:

| Output | Payload | When |
|---|---|---|
| Visible and announced text | Exactly one of `strings.apiStatus.checking` / `.available` / `.unavailable` | Each state entry |
| `data-state` attribute | `"checking" \| "available" \| "unavailable"` | Each state entry. It is the styling hook for the dot colour and a stable test hook. |
| One HTTP request | `GET {baseUrl}/health` via `fetchHealth` | Once per mount |

### State machine (AC DC-9; type `ApiStatusState = "checking" | "available" | "unavailable"`)

```
          mount
            │  side effect: controller = new AbortController();
            │               fetchHealth(baseUrl, controller.signal)
            ▼
       ┌──────────┐ resolve("available") ∧ active  ┌───────────┐
       │ checking │ ──────────────────────────────▶│ available │ (terminal)
       └──────────┘                                └───────────┘
            │ resolve("unavailable") ∧ active      ┌─────────────┐
            └─────────────────────────────────────▶│ unavailable │ (terminal)
                                                   └─────────────┘
  unmount (any state): active = false; controller.abort(); any later resolution is discarded
```

| From | Trigger | Guard | To | Side effects |
|---|---|---|---|---|
| — | mount | — | `checking` | Render the checking text. The effect creates an `AbortController` and calls `fetchHealth(baseUrl, signal)` exactly once. |
| `checking` | `fetchHealth` resolves `"available"` | `active === true` | `available` | `setState("available")`. The live region announces "API available". |
| `checking` | `fetchHealth` resolves `"unavailable"` (non-2xx, non-JSON, `status ≠ "ok"`, network error, 5 s timeout) | `active === true` | `unavailable` | `setState("unavailable")`. The live region announces "API unavailable". |
| `available` / `unavailable` | any resolution | — | unchanged | None. The setter is guarded: `s => s === "checking" ? r : s`. |
| any | unmount (effect cleanup) | — | (gone) | `active = false; controller.abort()`. The resolution that follows the abort is discarded. |

**Notes**
- **No retry and no "slow" intermediate state** (IP-4, OQ-U3 default).
- **StrictMode in development:** mount, cleanup (abort) and mount again create two requests. The first is aborted and discarded, so only one result is ever applied. The "one request per mount" invariant is asserted without StrictMode.

### Slots / Content surfaces
None exposed. Fixed DOM (AC IC-5.3, UI §5.3):

```html
<p class="api-status" role="status" aria-live="polite" aria-atomic="true" data-state="checking">
  <span class="api-status__dot" aria-hidden="true"></span>
  <span class="api-status__text">Checking API…</span>
</p>
```

- The dot is empty and `aria-hidden`, so the live region's accessible text is only the status string. There is no visually hidden prefix (UI §5.3).
- `aria-live="polite"` is explicit, as AC IC-5.3 requires; `role="status"` already implies it.

**Styling** (UI §7.5 "Status indicator", §6.2):

| Part | Rule |
|---|---|
| Box | `background: var(--color-surface)`; `border: 1px solid var(--color-border)`; `border-radius: var(--radius-md)`; `padding-block: var(--space-3)`; `padding-inline: var(--space-4)`; `gap: var(--space-2)`; `align-items: center`; no fixed `height` (SC 1.4.12) |
| Box display | compact: `display: flex` (full column width). `@media (min-width: 640px)`: `display: inline-flex`. |
| Dot | `inline-size` and `block-size` `var(--space-3)` (0.75 rem); `border-radius: var(--radius-full)`; `flex: none` |
| Dot colour by `data-state` | `checking` → `var(--color-status-neutral)`, `available` → `var(--color-status-ok)`, `unavailable` → `var(--color-status-error)` |
| Text | `var(--color-text)` (never the status colour); `var(--font-size-md)`; `var(--font-weight-semibold)`; `var(--line-height-body)` |
| Motion | None: no `transition`, `animation` or spinner (IP-5) |

### Invariants

| ID | Predicate | Checked by |
|---|---|---|
| STS-1 | On first render, before `fetch` settles: `getByRole("status").textContent === strings.apiStatus.checking` and `data-state === "checking"`. | unit |
| STS-2 | With `fetch` stubbed as each of {200 `{"status":"ok"}`, 200 `{"status":"degraded"}`, 200 `"not json"`, 503, rejected promise, a never-resolving request aborted by the 5 s timeout}, the final text is `strings.apiStatus.available` for the first case and `strings.apiStatus.unavailable` for every other. `data-state` matches the text. | unit (INV-W1) |
| STS-3 | `fetch` is called exactly once per mount (no StrictMode), with URL `"/api/v1/health"` by default and `` `${baseUrl}/health` `` (trailing slashes trimmed) when `baseUrl` is given. | unit (INV-W2) |
| STS-4 | `unmount()` before settlement aborts the signal passed to `fetch` (`signal.aborted === true`), and no React "state update on unmounted component" warning or `act` warning is emitted. | unit (INV-W2) |
| STS-5 | After reaching `available` or `unavailable`, a further resolution with `{"status":"ok"}` (for example a late stub) leaves both `textContent` and `data-state` unchanged. | unit (INV-W1) |
| STS-6 | `rerender(<ApiStatus baseUrl="/other" />)` after a terminal state leaves the text unchanged. | unit |
| STS-7 | A stubbed body `{"status":"<img src=x onerror=alert(1)>","version":"<b>x</b>"}` never appears in `container.innerHTML`, and no `img` or `b` element is created. | unit (INV-W3) |
| STS-8 | `textContent` of the `role="status"` element is always a member of `{checking, available, unavailable}` from `strings.apiStatus`. | unit |
| STS-9 | `getByRole("status").querySelector('[aria-hidden="true"]')` exists and has `textContent === ""`. | unit |
| STS-10 | `ApiStatus.tsx` contains no `dangerouslySetInnerHTML`, `innerHTML`, `setInterval`, `setTimeout` or retry loop. | static |
| STS-11 | The CSS source maps each `data-state` value to the matching `--color-status-*` token, and contains no `transition` or `animation` declarations for `.api-status`. | static (grep over `web/src/**/*.css`) |
| STS-12 | Across the `checking → terminal` change, Home CLS ≤ 0.1. Tool: Lighthouse mobile preset, simulated Slow 4G + 4× CPU slowdown, median of 3 runs against `vite preview`. | Acc (INV-W10) |

**Test note for STS-2 (timeout case).**
- `vi.useFakeTimers()` does not reliably fake `AbortSignal.timeout`.
- The timeout case SHOULD stub `AbortSignal.timeout` with `vi.spyOn(AbortSignal, "timeout")` and return a controller's signal that the test aborts with a `TimeoutError` `DOMException`, rather than waiting 5 real seconds.

---

## C-5 `NotFoundView`

**Purpose.** Renders the Not Found screen for any path other than `/`, with one link back to Home (UI §3.3, AS-5.3, FR-072).

### Props / Inputs
None. It deliberately does **not** receive the requested path. URL-controlled text is never rendered (UI §3.3, CD-2 §2.4).

### Events / Outputs

| Output | When | Effect |
|---|---|---|
| Document title | Mount (`useEffect`, empty deps) | `document.title = strings.notFound.documentTitle` ("Page not found · Dogwatch") |
| Navigation | User activates the link (click, or Enter on focus) | Native full document load of `/`, which re-runs Home's single health check (UI §2.2) |

### State machine
Stateless. It has a single static state, makes no data request, and has no loading or error variants.

### Slots / Content surfaces
None exposed. Fixed content:
1. `<h1 class="page-heading">{strings.notFound.title}</h1>`
2. `<p><a class="text-link" href="/">{strings.notFound.homeLink}</a></p>`. The link sits on its own line below the `h1` at every breakpoint.

**Link styling** (UI §7.5 "Text link", IP-2):
- `color: var(--color-link)`; always underlined; the underline gets thicker on `:hover`.
- Focus ring from X-3.
- `min-block-size` of 2.75 rem (44 CSS px) via `display: inline-flex; align-items: center` (UI §6.3).

### Invariants

| ID | Predicate | Checked by |
|---|---|---|
| NF-1 | `getByRole("link", { name: strings.notFound.homeLink }).getAttribute("href") === "/"`. The link has no `onClick` handler and no `target` attribute. | unit |
| NF-2 | Rendered via `<App pathname="/does-not-exist-<random>" />`, `container.textContent` does not include `does-not-exist`. | unit |
| NF-3 | `document.title === strings.notFound.documentTitle` after mount. | unit |
| NF-4 | Exactly one focusable element exists, and it is the link (UI §5.1). | unit |
| NF-5 | `axe.run` (tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`) on `<App pathname="/x" />` reports 0 violations. WCAG 2.2 AA; SC 2.4.4 Link Purpose, 1.3.1, 2.4.2. Throttling: not applicable. | axe (INV-W4) |
| NF-6 | No `fetch` call occurs while Not Found is mounted. | unit |

---

## C-6 `ErrorBoundary`

**Purpose.** Catches any uncaught render error in the view tree and replaces the whole app with `ErrorFallback`, so the user never sees a blank page (UI §3.4, FR-076).

### Props / Inputs

| Name | Type | Required | Default | Validation |
|---|---|---|---|---|
| `children` | `React.ReactNode` | required | — | In production this is always `<App />`. |

There is no `fallback` prop: the fallback is fixed to `ErrorFallback`. Injecting one is unnecessary with a single boundary.

### Events / Outputs
- No callbacks.
- `componentDidCatch` does **not** send telemetry (FR-081). It also adds no console logging, because React 19's default `onCaughtError` already reports to the console.
- Visible output: `ErrorFallback` replaces `children`.

### State machine

| From | Trigger | To | Side effects |
|---|---|---|---|
| — | mount | `ok` (`{ hasError: false }`) | Render `children`. |
| `ok` | a descendant throws during render, a lifecycle method, or a constructor (`static getDerivedStateFromError`) | `failed` (`{ hasError: true }`) | Unmount `children` and render `<ErrorFallback />`. |
| `failed` | any | `failed` | None. It is terminal until a document reload, with no reset API. |

**Out of scope by React design:** errors in event handlers and async code are not caught. CD-5 has no event handlers that can throw, and `fetchHealth` never rejects (AC IC-5.1).

### Slots / Content surfaces

| Slot | Content type | Layout role |
|---|---|---|
| `children` | The app tree | Rendered as-is while in `ok` |

### Invariants

| ID | Predicate | Checked by |
|---|---|---|
| EB-1 | `render(<ErrorBoundary><Thrower /></ErrorBoundary>)`, where `Thrower` throws `new Error("boom-<uuid>")` during render, shows `getByRole("heading", { level: 1, name: strings.error.title })` and `getByRole("button", { name: strings.error.reload })`, and `getByRole("main")` is non-empty. | unit (INV-W8) |
| EB-2 | In EB-1, `container.textContent` does not include `boom-` or `Error`, and contains no stack-frame text (`at `). | unit |
| EB-3 | Without a throwing child, `render(<ErrorBoundary><p>ok</p></ErrorBoundary>)` renders `ok` and no fallback. | unit |
| EB-4 | `main.tsx` renders exactly one `ErrorBoundary`, wrapping `<App />`, and no other `ErrorBoundary` exists in `web/src`. | static |
| EB-5 | `ErrorBoundary.tsx` contains no `fetch`, `navigator.sendBeacon`, `console.` or storage access. | static |

---

## C-7 `ErrorFallback`

**Purpose.** Renders the static, landmark-complete "Something went wrong" screen with a single reload action (UI §3.4, IP-3, FR-076).

### Props / Inputs

| Name | Type | Required | Default | Validation |
|---|---|---|---|---|
| `reload` | `() => void` | optional | `() => window.location.reload()` | Test seam only. `ErrorBoundary` never passes it. jsdom's `location.reload` cannot be spied on, so FR-076's "reload action" is verified through this prop. |

It receives **no** error object, message or component stack (UI §3.4, CD-2 §2.4).

### Events / Outputs

| Event | Payload | When |
|---|---|---|
| `reload()` | none | The native `<button type="button">` is activated by click, Enter or Space. Called exactly once per activation. |
| Document title | — | On mount: `document.title = strings.error.documentTitle` ("Something went wrong · Dogwatch") |

### State machine
Stateless. It has a single static state. Exit is a document reload. Focus is **not** moved programmatically (UI §3.4).

### Slots / Content surfaces
None exposed. It composes `Shell` with fixed children:

```html
<Shell>
  <h1 class="page-heading">Something went wrong</h1>
  <p><button type="button" class="button-primary">{strings.error.reload}</button></p>
</Shell>
```

**Button styling** (UI §7.5 "Primary button", IP-3):
- `background: var(--color-accent)`, `color: var(--color-text-inverse)`.
- `border-radius: var(--radius-sm)`, `padding-inline: var(--space-4)`.
- `min-block-size: 2.75rem` (44 CSS px; exceeds WCAG 2.2 SC 2.5.8).
- `font: var(--font-size-md) / var(--line-height-body)`, `var(--font-weight-semibold)`.
- `:hover` → `var(--color-accent-hover)`.
- Focus ring from X-3.
- No transition.

**Allowed dependencies:**
- MAY import: `Shell`, `strings`, and the entry stylesheet (already loaded).
- MUST NOT: use `React.lazy`, dynamic `import()`, data fetching, or anything derived from the error.

### Invariants

| ID | Predicate | Checked by |
|---|---|---|
| EF-1 | `render(<ErrorFallback reload={spy} />)`, then `user.click(getByRole("button", { name: strings.error.reload }))`, gives `spy` called exactly once. `user.keyboard("{Enter}")` and `user.keyboard(" ")` while focused each add exactly one call. | unit |
| EF-2 | The button has `type="button"`, and it is the only focusable element (UI §5.1). | unit |
| EF-3 | Exactly one `banner`, one `main` and one `h1` exist. The banner text is `strings.productName`. | unit |
| EF-4 | `document.title === strings.error.documentTitle` after mount. | unit |
| EF-5 | `document.activeElement` after mount is not the button. No `.focus()` is called (UI §3.4). | unit |
| EF-6 | `ErrorFallback.tsx` contains no `import(`, `lazy(`, `fetch` or `error` prop. | static |
| EF-7 (SHOULD, UI §5 recommendation) | `axe.run` (tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa`) on `<ErrorFallback />` reports 0 violations. WCAG 2.2 AA; SC 4.1.2, 2.4.2. Throttling: not applicable. | axe |

---

## Cross-Component Conventions

### X-1 Strings (FR-080, AC DC-10)
Every user-visible string, including document titles, comes from `strings.ts`. No JSX text literal or title literal appears in any component.

| Key | Value | Used by | Status |
|---|---|---|---|
| `productName` | `Dogwatch` | `Shell`, `HomeView` (document title) | DC-10 |
| `home.title` | `Dashboard` | `HomeView` | DC-10 (OQ-U1) |
| `notFound.title` | `Page not found` | `NotFoundView` | DC-10 |
| `notFound.homeLink` | `Back to home` | `NotFoundView` | DC-10 (OQ-U1) |
| `notFound.documentTitle` | `Page not found · Dogwatch` | `NotFoundView` | **new, adds to DC-10** (UI §2.4; OQ-C2) |
| `apiStatus.checking` / `.available` / `.unavailable` | `Checking API…` (U+2026) / `API available` / `API unavailable` | `ApiStatus` | DC-10 |
| `error.title` | `Something went wrong` | `ErrorFallback` | DC-10 |
| `error.reload` | `Reload page` | `ErrorFallback` | **conflict: DC-10 says `Reload`** (OQ-C1) |
| `error.documentTitle` | `Something went wrong · Dogwatch` | `ErrorFallback` | **new, adds to DC-10** (UI §2.4; OQ-C2) |

- **X-1a (static):** no `.tsx` file under `web/src` contains a JSX text child matching `/>\s*[A-Za-z][^<{]*</`. Tests MUST query by `strings.*` values, never by literals, so copy changes from OQ-U1 never break tests.
- **Allowed exception:** `index.html`'s pre-script `<title>Dogwatch</title>` is outside view code. It is the only duplicate of `strings.productName`.

### X-2 Tokens and styling motifs (FR-078, AC DC-11, UI §7)
- **Token-only values.** Colour, spacing (margin, padding, gap), font-size and border-radius declarations use `var(--…)` from `tokens.css` only. Stylelint `stylelint-declaration-strict-value` enforces this.
- **Literals allowed** only in: media-query parameters (`640px`, `1024px`), border and outline widths (`1px`, `2px`), and the 44 px `min-block-size` (`2.75rem`).
- **Required new token:** `--layout-max-width: 64rem` (UI §7.3; OQ-U5).
- **Shared motif classes.** These are CSS classes, not components, since the UI defines them as visual motifs (§7.5):
  - `.page-heading` (`h1`): `--font-size-xl` on compact and `--font-size-2xl` at 640 px and up; `--font-weight-semibold`; `--line-height-tight`; `margin-block: var(--space-8) var(--space-6)`.
  - `.text-link`: see C-5.
  - `.button-primary`: see C-7.
  - `.api-status`: see C-4.
- **Breakpoints:** mobile-first, with `@media (min-width: 640px)` and `@media (min-width: 1024px)` only (FR-077). No component adds another breakpoint or uses `display: none` to hide content at any width.
- **Text safety and RTL readiness:** `overflow-wrap: anywhere` on the `body` text container. Logical properties (`margin-inline`, `padding-block`, `inline-size`) only; no `left`/`right` physical properties.
- **No inline styles:** `style={` does not occur in `web/src` (static).

### X-3 Focus management (WCAG 2.2 AA; UI §5.1–§5.2)
- **Focus ring:** every interactive element (`a`, `button`) gets `:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }`, which survives forced-colours mode.
  - `outline: none` / `outline: 0` does not occur in `web/src/**/*.css` (static).
  - Satisfies SC 2.4.7 Focus Visible; 6.1:1 contrast for SC 1.4.11.
- **No programmatic focus:** no `tabIndex`/`tabindex`, `autoFocus`, or `.focus(` in `web/src` (static).
- **Tab stops per screen:** Home 0, Not Found 1 (link), Error fallback 1 (button), all in DOM order (SC 2.4.3).
- **No skip link** while the banner holds no interactive element (SHL-2). One becomes mandatory in the same change that adds navigation to `Shell` (UI §5.1).
- **No sticky or fixed positioning,** so focus is never obscured (SC 2.4.11).

### X-4 Error-surface conventions
| Failure | Surface | Copy | Detail shown |
|---|---|---|---|
| API unreachable, slow (> 5 s), non-2xx, non-JSON, or `status ≠ "ok"` | `ApiStatus` `unavailable` (inline, polite live region) | `strings.apiStatus.unavailable` | None: no HTTP code, problem `code`/`detail`, or retry (UI §3.2, OQ-U3) |
| Uncaught render error | `ErrorBoundary` → `ErrorFallback` (whole page) | `strings.error.title` + reload | None: no message, stack or component name |
| Unknown path | `NotFoundView` | `strings.notFound.title` + home link | None: path not echoed |

There are no toasts, modals, dialogs or form-validation surfaces in CD-5 (UI §4). The first ticket that adds input defines inline validation.

### X-5 Untrusted data (FR-073a, CD-2 §2.4)
- **No raw HTML:** `dangerouslySetInnerHTML`, `.innerHTML`, `insertAdjacentHTML` and `document.write` do not occur in `web/src` (static).
- **No response data is rendered:** no component stores or renders any API response field. Only `fetchHealth`'s two-value result crosses into React state.
- **No URL-controlled text is rendered:** `pathname`, `search` and `hash` are never rendered.

### X-6 Navigation
- All navigation is native full document loads (`<a href>` or `location.reload()`). There is no client-side history manipulation (APP-4).
- **Back/forward cache:** a page restored from the bfcache keeps its previous terminal `ApiStatus` state. This is consistent with "terminal until reload" (FS Key Entity), so CD-5 adds no `pageshow` handler.

### X-7 Privacy, storage and telemetry (FR-081)
- No component reads or writes `document.cookie`, `localStorage`, `sessionStorage` or `indexedDB`, or calls `navigator.sendBeacon`. ESLint `no-restricted-globals` / `no-restricted-properties` enforce this (INV-W7).
- No service worker is registered (FR-076).

### X-8 Performance contribution (FR-074, SC-007, SC-008)
- **No new runtime dependencies:** components add none beyond `react` and `react-dom` (APP-5). They add no icons, images, web fonts or animation libraries.
- **Budgets:** **Initial JS for the Home route ≤ 100 KB gzip**; **total CSS ≤ 20 KB gzip**. Both are checked by `check-build.mjs` (gzip level 9) in the CI `web` job on every run. Throttling: not applicable (build-time size).
- **Core Web Vitals:** **LCP ≤ 2.5 s** (the LCP element is the `h1` in the system font), **CLS ≤ 0.1** (status box reserved at first paint, HOME-5), **INP ≤ 200 ms** using **TBT ≤ 200 ms** as the lab proxy.
  - Tool: Lighthouse mobile preset, simulated Slow 4G + 4× CPU slowdown, median of 3 runs against `vite preview` at acceptance.
- **Lazy loading:** views added after CD-5 MUST use `React.lazy` inside `App`. `ErrorFallback` and `ApiStatus` stay eagerly bundled.

### X-9 Test harness conventions
- **No real network.** Tests stub global `fetch` with `vi.stubGlobal` and restore it after each test (A-8).
- **Routes are rendered** through `<App pathname=… />`, never by mutating `window.location`.
- **Shared axe configuration:** every axe check uses `{ runOnly: { type: "tag", values: ["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"] } }`. The "incomplete" result for SC 1.4.3 is expected in jsdom; contrast is verified by the Lighthouse accessibility audit at acceptance (UI OQ-U4).
- **`document.title` is reset** in `afterEach` so the title invariants (HOME-2, NF-3, EF-4) are independent.

---

## Open Questions

**OQ-C1 — Reload button label conflict.**
- The values disagree:
  - UI §3.4 and §5.3 use "Reload page".
  - AC DC-10 `error.reload` and INV-W8 use "Reload".
- **Default:** `strings.error.reload = "Reload page"` (the UI is the newer, user-facing decision). AC DC-10 and INV-W8 should be updated to that value.
- Either way, tests query `strings.error.reload` (X-1), so the decision is a one-line string change.

**OQ-C2 — Document-title keys.**
- UI §2.4 requires per-screen titles from the strings module, but DC-10 has no keys for them.
- **Default:** add `notFound.documentTitle` and `error.documentTitle`. Home reuses `productName`.

**OQ-C3 — Location of `API_BASE_URL`.**
- ARCH/AC define the expression but not the module.
- **Default:** `web/src/config.ts`, imported by `ApiStatus` as its default `baseUrl`.

**Inherited from the UI, with defaults applied in these contracts:**
- OQ-U1: proposed copy.
- OQ-U2: no Home empty-state line.
- OQ-U3: no retry button.
- OQ-U4: contrast and reflow checked at acceptance only.
- OQ-U5: `--layout-max-width` token.
- OQ-U6: wordmark is not a link.
- OQ-U7: no favicon.

Changing OQ-U3 or OQ-U6 adds a state or transition to `ApiStatus`, or an interactive element to `Shell`. That would require amending STS-*, SHL-2, HOME-3 and X-3.

---

## Appendix A — Traceability (contract → UI specification)

| Contract | UI screen / interaction |
|---|---|
| C-1 `App` | §2.1 hierarchy, §2.2 routing rule, §2.3 screens table |
| C-2 `Shell` | §3.1 Shell, §5.3 landmarks, §6.2 layout, §7.5 Shell header |
| C-3 `HomeView` | §3.2 Home, §2.4 titles, §5.1 (Home: no tab stops) |
| C-4 `ApiStatus` | §3.2 state table and layout-stability rule, IP-1, IP-4, IP-5, §5.3 status row, §7.5 Status indicator |
| C-5 `NotFoundView` | §3.3 Not Found, IP-2, §7.5 Text link |
| C-6 `ErrorBoundary` | §3.4 entry condition, §2.3 Error fallback row |
| C-7 `ErrorFallback` | §3.4 content and exit, IP-3, §7.5 Primary button |
| X-1 … X-9 | §2.4, §4, §5, §6, §7, Appendix B |

## Appendix B — Bundle section coverage

These are component contracts, so most bundle sections have no component surface. Each row states that position and points to the authoritative source.

**Frontend sections**

| Section | Component-level position |
|---|---|
| target_browsers_and_versions | Latest 2 stable Chrome, Edge, Firefox and Safari (macOS + iOS) (FR-070). Components use only custom properties, logical properties, `:focus-visible` and `AbortSignal.any`/`.timeout`, all available across that set. |
| routing_and_navigation_model | C-1, X-6: history paths, `/` → Home, everything else → Not Found, full document loads. |
| rendering_strategy | **CSR**: a statically built SPA mounted by `main.tsx`. No SSR, SSG, ISR or RSC (FR-071). |
| state_management_and_data_fetching | View-local `useState` in `ApiStatus` only. One request per mount. No store or cache (C-4). |
| api_consumption_contract | `GET {API_BASE_URL}/health` via `fetchHealth`. Only the two-value result is used. Nothing from the response is rendered (C-4, X-5). |
| auth_session_and_csrf_model | No auth UI in CD-5. Target for the auth ticket: `HttpOnly; Secure; SameSite=Lax` session cookie plus a CSRF token or same-origin header check (FR-082). |
| responsive_breakpoints_and_layout | compact < 640, medium 640–1023, wide ≥ 1024. Reflow at 320 px (C-2, C-4, X-2). |
| design_tokens_and_theming | X-2. Light theme only. A dark theme overrides the same names under `[data-theme="dark"]`. |
| accessibility_wcag_level | **WCAG 2.2 Level AA**. SC IDs are cited per invariant. axe gate HOME-4 / NF-5 (EF-7 SHOULD). |
| i18n_and_locale_strategy | English, `lang="en"`, every string in `strings.ts` (X-1), logical properties for later RTL. |
| performance_budget | **Initial JS ≤ 100 KB gzip (Home route)**; CSS ≤ 20 KB gzip; **LCP ≤ 2.5 s, CLS ≤ 0.1, INP ≤ 200 ms (TBT ≤ 200 ms proxy)**. Lighthouse mobile, Slow 4G + 4× CPU, median of 3 (X-8). |
| analytics_and_consent_model | None collected, no banner (X-7). |
| error_boundary_and_offline_strategy | C-6 / C-7. No service worker. Network loss surfaces only as `ApiStatus` `unavailable`. |
| asset_pipeline_and_code_splitting | Content-hashed Vite assets. No route splitting in CD-5. Later views use `React.lazy` (X-8). |

**Backend sections**

| Section | Component-level position |
|---|---|
| api_surface_and_versioning | Only `GET /api/v1/health` is consumed. Versioning is by URL prefix (`/api/v2/` for breaking changes). |
| auth_and_identity_model | No component auth. Recorded upload target: **GitHub Actions OIDC JWT** (RS256, JWKS-verified, audience-bound) or a hashed, revocable **project-scoped API key** (FR-045, FR-046). |
| data_model_and_storage | No persistence. The only state is the transient `ApiStatusState`. |
| migration_and_schema_evolution | The report schema evolves **expand-contract**. Future DB migrations are **zero-downtime expand-contract**. The UI is affected only through the health shape, which is read as `status === "ok"` alone. |
| background_jobs_and_scheduling | None. No job UI. |
| event_and_messaging_contract | None. No real-time channel. |
| rate_limiting_and_quotas | None. A future 429 `rate-limited` maps to `unavailable`. |
| observability_and_slo | **SC-006:** `GET /api/v1/health` **p95 ≤ 50 ms, p99 ≤ 100 ms**, 0 failures. **20 concurrent users sustained 60 s**, **Locust** headless, dataset: none (stateless). Environment: **1× GitHub-hosted ubuntu-24.04 runner, 1 uvicorn worker, no DB tier**. The UI's 5 s timeout is far above this. |
| error_taxonomy_and_codes | API problem codes `not-found` 404, `method-not-allowed` 405, `validation-failed` 422, `internal-error` 500 (reserved: 400, 409, 413, 429). Every non-2xx → `unavailable`; problem text is never shown (X-4). |
| deployment_topology_and_envs | Local dev (Vite `127.0.0.1:5173`, proxy `/api` → `127.0.0.1:8000`; preview `127.0.0.1:4173`) and CI only. |
| scaling_and_resource_limits | Single local API process. No component impact. |
| secrets_and_config_management | No secrets. Only `VITE_DOGWATCH_API_BASE_URL` (build-time, optional), documented in `web/.env.example`. |
| data_retention_and_compliance | Components collect and store no user data (X-7). |
| backup_and_disaster_recovery | The repository is the system of record. Recovery: clone, install from lockfiles, `make test`. |

**DevOps sections**

| Section | Component-level position |
|---|---|
| target_environments | Local dev plus GitHub-hosted CI runners. |
| infrastructure_as_code_strategy | No IaC in CD-5. Provisional: **Terraform**. |
| ci_cd_pipeline_topology | GitHub Actions `web` job: format, lint (ESLint, stylelint), type check, Vitest including axe, build budget check. Every static and unit invariant above runs there. **SC-005 DORA lead time for changes (pre-deployment proxy): median ≤ 10 min, p95 ≤ 15 min, from push to `main` until all checks pass, over a rolling 30-day window after merge, for every push to `main`, measured via GitHub Actions analytics run timestamps.** |
| container_and_orchestration_model | None built. Provisional: the API as an OCI image, and the web app as same-origin static assets. |
| secrets_and_credentials_management | None needed. Provisional: **GitHub Actions OIDC** for CI-to-cloud access, plus a **cloud-provider secret manager** (AWS Secrets Manager or GCP Secret Manager) for runtime secrets. |
| observability_stack | Components emit no telemetry (FR-081). Provisional service stack: **OpenTelemetry** SDK → OTLP → Collector, with **Prometheus** (metrics), **Grafana Loki** (logs) and **Grafana Tempo** (traces). |
| rollout_and_rollback_strategy | CD-5 rollback is reverting the merge commit (it must pass CI). Provisional: **blue-green** with traffic switch-back, plus a **feature-flag kill-switch** for new ingestion behaviour. |
| cost_and_resource_budget | USD 0/month. CI ≤ 25 runner-minutes and ≤ 10 min wall-clock per run (GitHub Actions timing API, every PR and `main` push). The component tests fit in the `web` job. |
| disaster_recovery_runbook | Re-clone, install from lockfiles, `make test`. |
| compliance_and_audit_trails | Git history plus Actions logs. Branch protection recommended. The UI processes no personal data. |
