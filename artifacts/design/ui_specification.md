# UI Specification — CD-5: Dogwatch web dashboard shell

Source of truth: `artifacts/planning/frozen_spec.md` ("FS"). Every decision below cites an FS section, FR, AS or SC. Prior research this design depends on: CD-2 §2.4 (untrusted rendering, CSP), at `/Users/iliaglushkov/Documents/sandbox/contractor/.am/reports/9c37b285-b35d-4dc2-be1c-2347272422e0-research-paper.md`.

**Workspace check.** The repository contains only `.am/` and `.playwright-mcp/`. There is no existing design system, token file or component library to reuse. All tokens in §7 are therefore **new**. Each one is justified, and they are all defined in the single token file that FR-078 requires.

---

## 1. Summary

The CD-5 web app is the **empty dashboard shell** for Dogwatch operators (FS §1, US-5).

**Who it is for.** At this stage the only real audience is Dogwatch developers who run the app locally to confirm the shell builds and can reach the API (US-5, A-8). The eventual audience is authenticated operators who will review scanner reports once CD-2 ingestion exists (FR-071 rationale).

**What it must prove, and nothing more:**
- client-side rendering (CSR) works (FR-071);
- the same-origin API consumption contract works (FR-073, FR-073a);
- the accessibility, performance and token foundations are in place (FR-074–FR-081).

**What that means for the design:**
- It has one honest piece of live information: the API status indicator.
- It has three places to land: Home, Not Found, and the error fallback.
- It has no data views, forms, auth, storage or third-party assets (FR-043, FR-045, FR-081, FR-075).

The design is deliberately minimal and token-driven, so later tickets (CD-2 report views) can add screens without reworking the shell, the tokens or the accessibility baseline.

---

## 2. Information Architecture

### 2.1 Hierarchy

```
Document (lang="en", <title> per view)
├── Shell
│   ├── <header>  — product wordmark "Dogwatch" (A-1)
│   └── <main>    — exactly one view at a time
│        ├── Home view          (path "/")            FR-072
│        └── Not Found view     (any other path)      FR-072, AS-5.3
└── Error fallback (replaces the whole Shell on an uncaught render error)  FR-076
```

### 2.2 Navigation model

- **Primary navigation: none in CD-5.** There are two views, and the only route between them is the Not Found → Home link (FR-072). There is no nav bar, menu or breadcrumbs. Adding them now would be speculative scope.
- **URLs are path-based (history), never hash fragments** (FR-072).
- **Routing rule:**
  - `/` resolves to Home.
  - Every other path, including deep links on static hosting, resolves to Not Found (FR-072, Edge Case "deep link").
- **The Not Found → Home link is a plain `<a href="/">` (full document navigation).** Reloading the document re-runs Home's single health check. That is the intended behaviour, because the indicator is terminal until reload (FS §4, API status indicator).
- **The header wordmark is plain text, not a link.** Home is always one action away from Not Found, and there are no other screens. Keeping the wordmark non-interactive also leaves the Home view with zero tab stops (§5.1). This can be revisited when a second real screen arrives.

### 2.3 Named screens and relationships

| Screen | Path / trigger | Reachable from | Leads to | FS anchor |
|---|---|---|---|---|
| Home | `/` | Direct load; Not Found link; reload from error fallback (when on `/`) | (nothing) | FR-072, FR-073, AS-5.1, AS-5.2 |
| Not Found | any path other than `/` | Direct load / deep link | Home (link) | FR-072, AS-5.3 |
| Error fallback | uncaught render error anywhere in the view tree | Any screen | Same URL, reloaded | FR-076 |

### 2.4 Document titles (WCAG 2.2 SC 2.4.2 Page Titled, required by FR-079's AA target)

| Screen | `<title>` |
|---|---|
| Home | `Dogwatch` |
| Not Found | `Page not found · Dogwatch` |
| Error fallback | `Something went wrong · Dogwatch` |

All title strings live in the strings module (FR-080).

---

## 3. Screens & States

All visible copy below lives in the single strings module (FR-080). Copy marked *(proposed)* is not fixed by the FS and is listed in OQ-U1.

### 3.1 Shell (wraps Home and Not Found)

- **Purpose:** gives every view a stable frame, the landmark structure and the product identity (FR-079 landmarks, AS-5.1 "shows the product name").
- **Content:**
  - `<header>`: the wordmark "Dogwatch" (A-1). It is not a heading, so each view owns the page's single `h1` (FR-079).
  - `<main>`: the current view.
- **States:** none. It renders synchronously from static assets, needs no data, and appears at first paint.
- **Constraints:**
  - No inline scripts or handlers (FR-075).
  - System font stack only, with no external origin (FR-075).
  - Nothing is written to cookies or storage (FR-081).

### 3.2 Home (`/`)

- **Purpose:** show the product name and whether the API can be reached (AS-5.1, AS-5.2, FR-073).
- **Content, in reading order:**
  1. `h1`: "Dashboard" *(proposed, OQ-U1)*.
  2. **API status indicator**: a decorative status dot (`aria-hidden`) followed by the status text, inside a polite live region (§5.3).
- **Data:** exactly one `GET {base}/health` per load. The base defaults to same-origin `/api/v1` (FR-073, FR-073a).

**States.** This is the API status indicator state machine (FS §4):

| State | Entry condition | Visible text | Dot token | Exit |
|---|---|---|---|---|
| **Loading**: `checking` | Initial render, before the response | "Checking API…" (FR-073) | `--color-status-neutral` | → `available` or `unavailable` |
| **Success**: `available` | 2xx **and** the body parses as JSON **and** `status === "ok"` (FS §4, Edge Cases) | "API available" (AS-5.1) | `--color-status-ok` | Terminal until reload |
| **Error**: `unavailable` | Non-2xx, non-JSON body, `status ≠ "ok"`, network error, or the 5 s timeout (FR-073, Edge Cases) | "API unavailable" (AS-5.2) | `--color-status-error` | Terminal until reload; a late success is ignored (Edge Case "API slow") |
| **Empty** | Not applicable. CD-5 has no report data or endpoints (FR-043). No "no reports yet" placeholder is shown (OQ-U2). | — | — | — |

**Content rules:**
- **No response text is ever rendered.** The indicator shows only one of the three fixed strings. Response fields (including `version`) are not displayed. This follows FR-073a and CD-2 §2.4: API responses are untrusted.
- **No error detail, HTTP code or retry button is shown.** FS defines the state as terminal until reload. A retry control would add an interaction the FS does not ask for (OQ-U3).

**Layout-stability rule** (supports SC-008 CLS ≤ 0.1):
- The indicator is in the DOM from the first render, in the `checking` state.
- Moving between states changes only the text and the dot colour, inside a box whose height is fixed by line-height and padding tokens, so no content is inserted above it.

**Entry and exit transitions:**
- **Entry:** document load at `/`.
- **Exit:** navigating away or reloading.
- **No animated transitions between states** (§4.5).

### 3.3 Not Found (any other path)

- **Purpose:** handle unknown routes gracefully and lead the user back (AS-5.3, FR-072).
- **Content:**
  1. `h1`: "Page not found" (AS-5.3).
  2. Link: "Back to home" *(proposed wording, OQ-U1)*, pointing to `/`.
- **The requested path is not echoed back.** There is no need for it, and it avoids rendering URL-controlled text (CD-2 §2.4 posture).
- **States:** a single static state. No loading, empty or error variants, because it makes no data request (FR-073 scopes the health request to Home).
- **Entry:** any non-`/` path, including direct deep links. The dev and preview servers serve `index.html` for unknown paths (Edge Case "deep link").
- **Exit:** activating the link loads Home.

### 3.4 Error fallback

- **Purpose:** never show a blank page after an uncaught render error (FR-076, AS-5.2 "does not crash or show a blank screen").
- **Content:** a static `<header>` with the wordmark, plus `<main>` containing:
  1. `h1`: "Something went wrong" (FR-076).
  2. Button: "Reload page" *(proposed wording, OQ-U1)*. It reloads the current URL (FR-076 "reload action").
- **Static by design:**
  - No error message, stack trace or component name is shown (FR-051 posture applied to the client; CD-2 §2.4).
  - It uses no data, no strings derived from the error, and no lazy-loaded code. Token CSS is already loaded with the entry stylesheet.
- **The header and main landmarks are kept,** so the fallback stays landmark-complete (FR-079).
- **States:** a single static state.
- **Entry:** the top-level error boundary catches a render error.
- **Exit:** a reload. Focus is **not** moved programmatically; the page title change and the `h1` give the context.

### 3.5 Out of scope (deliberately not designed)

None of these appear in CD-5:
- report list or detail screens (FR-043);
- login or session screens (FR-045, FR-082);
- settings;
- offline or service-worker states (FR-076);
- a consent banner (FR-081);
- a theme switcher (FR-078, light theme only);
- a locale switcher (FR-080).

---

## 4. Interaction Patterns

| # | Pattern | Screens | Behaviour | FS anchor |
|---|---|---|---|---|
| IP-1 | **Passive status feedback** | Home | The indicator changes text and dot colour once, with no user action, and is announced politely (§5.3). Colour is never the only cue: the text carries the meaning (WCAG 2.2 SC 1.4.1). | FR-073, FR-079 (SC 4.1.3) |
| IP-2 | **Text link navigation** | Not Found | Native `<a href>`. Underlined by default, using the accent colour token. Hover thickens the underline. Focus shows the focus ring (§5.2). | FR-072, AS-5.3 |
| IP-3 | **Recovery button** | Error fallback | Native `<button type="button">`, which works with Enter and Space. Its visual is a solid accent fill with inverse text, and a 44×44 CSS px minimum hit area (exceeds WCAG 2.2 SC 2.5.8 Target Size (Minimum), 24×24). | FR-076 |
| IP-4 | **Timeout feedback** | Home | After 5 s with no response, the state becomes `unavailable` with no intermediate "slow" message. A late response does not change the state. | FR-073, Edge Case "API slow" |
| IP-5 | **No motion** | All | No transitions or animations in CD-5, including the `checking` state (static neutral dot, no spinner). This avoids motion-sensitivity concerns and CLS risk. | FR-079, SC-008 |

**Not present in CD-5, by design:**
- **Forms and validation surfaces: none.** No screen accepts input (FR-043, FR-045). Inline validation patterns are deferred to the ticket that adds the first input.
- **Custom keyboard shortcuts: none.** Only native browser and assistive-technology keys apply.
- **Gestures: none.** Standard browser scrolling and zoom only, and zoom is never disabled (§6.4).
- **Toasts, modals and dialogs: none.** No FS requirement calls for one.

---

## 5. Accessibility

**Target: WCAG 2.2 Level AA** (FR-079).
**Automated gate (SC-009):** 0 axe-core violations for the tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` on Home and Not Found. It runs in the web test suite (Vitest + jsdom + axe-core) on every CI run. Throttling profile: not applicable (static DOM analysis).
**Recommended addition:** run the same axe check on the error fallback, so the AA promise covers all three screens.

### 5.1 Keyboard navigation and focus order

| Screen | Tab stops, in DOM order | Notes |
|---|---|---|
| Home | **none** | The status indicator is not focusable. Making it focusable would add a meaningless stop. Screen-reader users reach it with virtual-cursor or landmark navigation. |
| Not Found | 1. "Back to home" link | — |
| Error fallback | 1. "Reload page" button | — |

- Focus order always matches visual order: a single column with no CSS reordering (SC 2.4.3 Focus Order, SC 1.3.2 Meaningful Sequence).
- **No skip link.** The header contains no interactive elements, so there is nothing to bypass. The `header` and `main` landmarks satisfy SC 2.4.1 Bypass Blocks. A skip link becomes mandatory when the header gains navigation.
- No keyboard traps (SC 2.1.2). No focus is moved programmatically on load. Every view change is a full document load, so focus starts at the top of the document.

### 5.2 Visible focus

- `:focus-visible` shows a 2 px solid `--color-focus` outline with a 2 px offset on every interactive element. Outlines are never removed (FR-079, SC 2.4.7 Focus Visible).
- `--color-focus` (#1F5FBF) has 6.1:1 contrast against `--color-bg` and 5.7:1 against `--color-surface`, which is ≥ 3:1 (SC 1.4.11 Non-text Contrast).
- The focus ring is never covered by other content (SC 2.4.11 Focus Not Obscured (Minimum)). There is no sticky UI in CD-5.

### 5.3 ARIA roles, landmarks and screen-reader semantics

| Element | Semantics | FS / WCAG |
|---|---|---|
| `<html lang="en">` | Document language | FR-079, FR-080, SC 3.1.1 |
| `<header>` | Implicit `banner` landmark (top level) | FR-079, SC 1.3.1 |
| `<main>` | Implicit `main` landmark; exactly one per document | FR-079, SC 1.3.1 |
| `h1` | Exactly one per screen (Home, Not Found, fallback) | FR-079, SC 2.4.6 |
| Status indicator container | `role="status"` (implicit `aria-live="polite"`, `aria-atomic="true"`). It is present at first render with "Checking API…", so the later change to "API available" / "API unavailable" is announced once. | FR-079, SC 4.1.3 Status Messages |
| Status dot | `aria-hidden="true"`; purely decorative | SC 1.1.1 (no alt needed for decoration) |
| Not Found link | Native link; accessible name "Back to home" | SC 2.4.4 Link Purpose |
| Reload control | Native `<button>`; accessible name "Reload page" | SC 4.1.2 Name, Role, Value |

- The live region contains **only** the status text, so the heading is not re-announced.
- A visually hidden prefix such as "API status:" is **not** used, because the status strings are already self-describing.

### 5.4 Contrast targets (verified token pairs; ratios computed with the WCAG relative-luminance formula)

| Foreground token | Background token | Ratio | Requirement |
|---|---|---|---|
| `--color-text` #1A1D23 | `--color-bg` #FFFFFF | 16.9:1 | ≥ 4.5:1 text (SC 1.4.3) |
| `--color-text` | `--color-surface` #F6F7F9 | 15.8:1 | ≥ 4.5:1 |
| `--color-text-muted` #4A5260 | `--color-bg` | 7.9:1 | ≥ 4.5:1 |
| `--color-text-muted` | `--color-surface` | 7.3:1 | ≥ 4.5:1 |
| `--color-link` #1F5FBF | `--color-bg` | 6.1:1 | ≥ 4.5:1 |
| `--color-text-inverse` #FFFFFF | `--color-accent` #1F5FBF (button fill) | 6.1:1 | ≥ 4.5:1 |
| `--color-status-ok` #1B7F3B | `--color-surface` | 4.7:1 | ≥ 3:1 non-text (SC 1.4.11) |
| `--color-status-error` #B42318 | `--color-surface` | 6.1:1 | ≥ 3:1 |
| `--color-status-neutral` #4A5260 | `--color-surface` | 7.3:1 | ≥ 3:1 |
| `--color-focus` #1F5FBF | `--color-bg` / `--color-surface` | 6.1 / 5.7:1 | ≥ 3:1 (SC 1.4.11) |

**How these ratios are kept and checked:**
- They are recorded as comments next to each pair in the token file (architecture §6.27).
- axe in jsdom cannot evaluate SC 1.4.3 (it reports the result as incomplete). Contrast is therefore confirmed by the Lighthouse accessibility audit at acceptance (see OQ-U4, which mirrors architecture OQ-5).
- Status text is drawn in `--color-text`, not in the status colour. This keeps text contrast trivially high and leaves the colour as a redundant cue.

### 5.5 Further AA safeguards

- **Resize text (SC 1.4.4):**
  - All type sizes are in `rem`.
  - The viewport meta is `width=device-width, initial-scale=1`, with no `maximum-scale` and no `user-scalable=no`.
- **Text spacing (SC 1.4.12):**
  - No fixed heights on text containers.
  - The status box height comes from line-height and padding, so it grows with user spacing overrides.
- **Reflow (SC 1.4.10):** see §6.
- **Forced-colors mode** (Edge on Windows, a supported browser per FR-070):
  - Meaning is carried by text, so state is still conveyed when system colours override the dot.
  - Focus outlines use `outline`, not `box-shadow`, so they survive forced colours.

---

## 6. Responsive Behaviour

### 6.1 Breakpoints (exactly the three that FR-077 names)

| Name | Range | Media query (mobile-first) |
|---|---|---|
| compact | < 640 px | base styles |
| medium | 640–1023 px | `@media (min-width: 640px)` |
| wide | ≥ 1024 px | `@media (min-width: 1024px)` |

- Media-query values are literals. Custom properties cannot be used inside media queries, and the strict-value lint rule ignores media parameters (architecture §6.26).
- No other breakpoints are introduced.

### 6.2 Layout adaptations

| Element | compact | medium | wide |
|---|---|---|---|
| Page inline padding | `--space-4` (16 px) | `--space-6` (24 px) | `--space-8` (32 px) |
| Content container | Full width | Full width | Centred, `max-width: --layout-max-width` (64 rem) |
| Header | One row; wordmark at `--font-size-lg` | Same | Same; aligned to the content container |
| `h1` size | `--font-size-xl` | `--font-size-2xl` | `--font-size-2xl` |
| Status indicator | Block, full width of the content column | Inline-flex, sized to content | Same as medium |
| Not Found / fallback block | Single column; link or button on its own line below the `h1` | Same | Same |

### 6.3 Content reflow rules

- **No horizontal scrolling at 320 CSS px width** (FR-077, WCAG 2.2 SC 1.4.10 Reflow). This is equivalent to 1280 px viewed at 400 % zoom.
- Single column at every breakpoint. Nothing is hidden or truncated at smaller widths; breakpoints only change spacing and size.
- Text uses `overflow-wrap: anywhere` as a safety net for long unbroken strings (relevant once real data arrives; harmless now).
- Layout uses CSS logical properties (`margin-inline`, `padding-block`), so a later RTL locale needs no layout rewrite (FR-080, i18n readiness).
- The button and link keep a ≥ 44 px block size at every breakpoint (IP-3).

### 6.4 Viewport and zoom

- `<meta name="viewport" content="width=device-width, initial-scale=1">` is set (supports SC 1.4.4 and SC 1.4.10).
- Pinch-zoom is never disabled.

---

## 7. Visual System

**No design system exists yet** (empty workspace). The tokens below are the first and only definitions.
- They are CSS custom properties on `:root` in the single token file (FR-078).
- Every other stylesheet references them. A literal colour, spacing, font-size or radius value outside the token file is a lint error (FR-078, architecture §6.27).
- `:root` declares `color-scheme: light`. The light theme is the only one (FR-078).
- A later dark theme overrides the **same token names** under a theme selector such as `[data-theme="dark"]`. No consumer code changes are needed.

### 7.1 Typography

- **Family token:** `--font-family-sans`: `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`.
  - The system stack means no external font origin (FR-075), zero font bytes against the CSS budget (FR-074), and no font-swap layout shift (SC-008 CLS).

| Token | Value | Used for |
|---|---|---|
| `--font-size-sm` | 0.875rem | Reserved for secondary text (not used by CD-5 screens) |
| `--font-size-md` | 1rem | Body, status text, link, button |
| `--font-size-lg` | 1.25rem | Header wordmark |
| `--font-size-xl` | 1.5rem | `h1` (compact) |
| `--font-size-2xl` | 2rem | `h1` (medium, wide) |
| `--font-weight-regular` | 400 | Body |
| `--font-weight-semibold` | 600 | Wordmark, `h1`, status text, button |
| `--line-height-tight` | 1.25 | Headings, wordmark |
| `--line-height-body` | 1.5 | Body, status, link, button |

`--font-size-sm` is included now so the scale is complete for CD-2 screens. It costs nothing at runtime.

### 7.2 Colour tokens

| Token | Value | Role |
|---|---|---|
| `--color-bg` | #FFFFFF | Page background |
| `--color-surface` | #F6F7F9 | Header background, status indicator background |
| `--color-border` | #D0D5DD | Header bottom border, status box border (decorative only) |
| `--color-text` | #1A1D23 | Primary text, including status text |
| `--color-text-muted` | #4A5260 | Secondary text (reserved) |
| `--color-text-inverse` | #FFFFFF | Text on accent fills (button) |
| `--color-accent` | #1F5FBF | Button fill |
| `--color-accent-hover` | #194E9E | Button hover fill. Darker than accent, so text contrast is higher than 6.1:1. |
| `--color-link` | #1F5FBF | Links |
| `--color-focus` | #1F5FBF | Focus outline |
| `--color-status-ok` | #1B7F3B | "API available" dot |
| `--color-status-error` | #B42318 | "API unavailable" dot |
| `--color-status-neutral` | #4A5260 | "Checking API…" dot |

All contrast ratios for these pairs are in §5.4.

**Why semantic names:**
- `--color-link` and `--color-focus` share a value but have separate names, so a dark theme or brand change can split them without touching component styles (FR-078 "structured so a dark theme can override").
- The three status tokens are named by meaning (ok / error / neutral) rather than hue, so the CD-2 finding-severity colours can reuse or extend them later.

### 7.3 Spacing scale (4 px base)

| Token | Value |
|---|---|
| `--space-1` | 0.25rem (4 px) |
| `--space-2` | 0.5rem (8 px) |
| `--space-3` | 0.75rem (12 px) |
| `--space-4` | 1rem (16 px) |
| `--space-6` | 1.5rem (24 px) |
| `--space-8` | 2rem (32 px) |
| `--space-12` | 3rem (48 px) |

**Layout token:** `--layout-max-width: 64rem`. This is a new token category. FR-078 lists colour, spacing, typography and radius; a container width is effectively a spacing/size value. It is defined as a token so the "no hard-coded values" rule holds (OQ-U5 confirms the category).

### 7.4 Radius

| Token | Value | Used for |
|---|---|---|
| `--radius-sm` | 4px | Button, focus-outline corners |
| `--radius-md` | 8px | Status indicator box |
| `--radius-full` | 9999px | Status dot |

### 7.5 Component motifs (visual intent only; implementation detail belongs to the contracts stage)

| Motif | Description | Tokens |
|---|---|---|
| **Shell header** | Full-bleed `--color-surface` band with a 1 px `--color-border` bottom edge. Wordmark in semibold `--font-size-lg`. Block padding `--space-4`. | surface, border, text, font-size-lg, space-4 |
| **Page heading** | `h1`, semibold, tight line-height. Top margin `--space-8`, bottom margin `--space-6`. | font-size-xl/2xl, space-8, space-6 |
| **Status indicator** | Rounded box: `--color-surface` fill, 1 px `--color-border`, `--radius-md`, padding `--space-3` / `--space-4`. A 0.75 rem `--radius-full` dot, then `--space-2` gap, then the status text in semibold `--color-text`. | surface, border, radius-md, radius-full, space-2/3/4, status-* |
| **Text link** | `--color-link`, always underlined; underline thickens on hover; focus ring on `:focus-visible`. | link, focus |
| **Primary button** (fallback only) | `--color-accent` fill, `--color-text-inverse` text, `--radius-sm`, minimum 44 px block size, inline padding `--space-4`; hover uses `--color-accent-hover`; focus ring. | accent, accent-hover, text-inverse, radius-sm, space-4, focus |

No icons, illustrations or images in CD-5. This keeps the JS and CSS budgets clear (FR-074) and avoids external assets (FR-075).

### 7.6 Budget-linked visual constraints

- **CSS ≤ 20 KB gzip, total (FR-074, SC-007).** The token file plus the four motifs is expected to be well under 2 KB gzip.
- **Initial JS ≤ 100 KB gzip for the Home route (FR-074, SC-007).** The design adds no UI library, icon set, router or animation library.
- **Core Web Vitals (SC-008):**
  - **LCP ≤ 2.5 s:** the LCP element is the `h1` text, which paints with system fonts and needs no image.
  - **CLS ≤ 0.1:** the status box is reserved at first paint.
  - **TBT ≤ 200 ms:** a lab proxy for INP ≤ 200 ms.
  - Measured with Lighthouse, mobile preset, simulated throttling (Slow 4G, 4× CPU slowdown), median of 3 runs against `vite preview`.

---

## 8. Open Questions

**OQ-U1 — Proposed UI copy.**
- The FS fixes these strings: "Checking API…", "API available", "API unavailable", "Page not found", "Something went wrong", and the product name "Dogwatch".
- It does not fix: Home's `h1` (proposed "Dashboard"), the Not Found link label (proposed "Back to home"), the fallback button label (proposed "Reload page"), or the document titles in §2.4.
- **Question:** confirm the proposed copy, or supply alternatives. All of it lives in the strings module (FR-080), so changing it costs nothing.

**OQ-U2 — Home empty state.**
- FR-043 excludes report endpoints, and the FS is silent on whether Home should say anything about reports (for example, "Reports will appear here once ingestion is available").
- **Default:** no placeholder copy.
- **Question:** should Home carry an explanatory empty-state line for CD-5?

**OQ-U3 — Retry affordance.**
- FS §4 makes `unavailable` terminal until reload, so no retry control is designed.
- **Question:** confirm that a developer reloading the page is acceptable, rather than an in-page "Check again" button. A button would add one interaction and its own tests.

**OQ-U4 — Real-browser checks for contrast and reflow.**
- axe in jsdom cannot evaluate SC 1.4.3 contrast or SC 1.4.10 reflow at 320 px (FR-077 has no SC of its own).
- **Default:** verify both at acceptance, using:
  - the Lighthouse accessibility audit (mobile preset, simulated Slow 4G + 4× CPU);
  - Chrome DevTools device mode at 320 × 640 CSS px with no throttling, checking `scrollWidth ≤ clientWidth`.
- **Question:** is acceptance-time verification enough, or should CI add a Playwright/Chromium check? That adds about 1–2 runner-minutes against FR-095's 25-minute budget (same trade-off as architecture OQ-5).

**OQ-U5 — Layout token category.**
- FR-078 enumerates colour, spacing, typography and radius. This design adds `--layout-max-width`.
- **Question:** confirm that size/layout tokens belong in the same token file and under the same lint rule.

**OQ-U6 — Header wordmark as home link.**
- **Default:** plain text, which leaves zero tab stops on Home.
- **Question:** should it become a link to `/` now, or only when a second real screen exists?

**OQ-U7 — Favicon.**
- The FS is silent. Without one, browsers request `/favicon.ico`, and the SPA fallback answers it with `index.html`.
- **Question:** add a self-hosted SVG favicon, which is same-origin and so compatible with FR-075, or leave it until branding exists?

---

## Appendix A — Traceability (UI decision → FS)

| UI element / decision | FS anchor |
|---|---|
| Two views plus Not Found routing, history URLs | FR-072, AS-5.3, Edge Case "deep link" |
| Error fallback with reload | FR-076, AS-5.2 |
| Status indicator states, 5 s timeout, late success ignored, plain-text only | FR-073, FR-073a, FS §4, Edge Cases |
| Same-origin `/api/v1`, dev proxy, build-time override variable | FR-073a |
| CSR static SPA | FR-071 |
| No inline script, no external origins, system fonts | FR-075 |
| Breakpoints 640 / 1024, 320 px reflow | FR-077 |
| Tokens as CSS custom properties, light theme, dark-ready | FR-078 |
| WCAG 2.2 AA, landmarks, single `h1`, focus, contrast, live region, axe | FR-079, SC-009 |
| English, `lang="en"`, single strings module | FR-080 |
| No analytics, cookies or storage | FR-081 |
| JS ≤ 100 KB gzip initial, CSS ≤ 20 KB gzip | FR-074, SC-007 |
| LCP / CLS / TBT targets | SC-008 |
| Supported browsers (latest 2 of Chrome, Edge, Firefox, Safari macOS/iOS) | FR-070 |

## Appendix B — Bundle section coverage

The Web Development bundle requires every listed section to be addressed. Sections with no UI surface in CD-5 are handled by the FS and the architecture. They are restated here only to confirm the UI's dependency on them, or that it has none.

**Frontend sections (designed above):**

| Bundle section | Where addressed / UI position |
|---|---|
| target_browsers_and_versions | Latest two stable majors of Chrome, Edge, Firefox, Safari (macOS + iOS). The design uses only CSS features supported across that set (custom properties, logical properties, `:focus-visible`), so no fallbacks are needed. FR-070. |
| routing_and_navigation_model | §2.2. FR-072. |
| rendering_strategy | **CSR**, statically built SPA. SSR, SSG, ISR and RSC are not used. FR-071. |
| state_management_and_data_fetching | View-local state only, one health request per Home load, no global store. §3.2. FR-073. |
| api_consumption_contract | Same-origin `/api/v1/health`; only `status === "ok"` is read; responses are rendered as nothing beyond fixed strings. §3.2. FR-073a, CD-2 §2.4. |
| auth_session_and_csrf_model | No session, cookies or state-changing calls, so no login screen or CSRF UI. Recorded target: `HttpOnly; Secure; SameSite=Lax` session cookies plus a CSRF token or same-origin header check, designed by the auth ticket. FR-082. |
| responsive_breakpoints_and_layout | §6. FR-077. |
| design_tokens_and_theming | §7. FR-078. |
| accessibility_wcag_level | §5: **WCAG 2.2 AA**, SC IDs cited. FR-079, SC-009. |
| i18n_and_locale_strategy | English only, strings module, logical properties for later RTL. §6.3. FR-080. |
| performance_budget | **Initial JS ≤ 100 KB gzip (Home route)**, CSS ≤ 20 KB gzip, checked by the build size check in the web CI job on every run (SC-007; throttling n/a for build-time checks). **LCP ≤ 2.5 s, CLS ≤ 0.1, TBT ≤ 200 ms (proxy for INP ≤ 200 ms)**, measured with Lighthouse mobile preset, Slow 4G + 4× CPU, median of 3 (SC-008). §7.6. |
| analytics_and_consent_model | None collected, no banner. FR-081. |
| error_boundary_and_offline_strategy | §3.4. No service worker. FR-076. |
| asset_pipeline_and_code_splitting | Content-hashed static assets; no route splitting in CD-5; later views lazy-loaded to protect the Home budget; no images, icons or fonts added by the design. FR-074, FR-075. |

**Backend sections (no UI surface; shell depends only on health):**

| Bundle section | Where addressed / UI position |
|---|---|
| api_surface_and_versioning | The UI consumes only `GET /api/v1/health`. Versioning uses the URL prefix (`/api/v1/`, with breaking changes going to `/api/v2/`). FR-040–FR-042. |
| auth_and_identity_model | No UI auth in CD-5. Recorded target for uploads: **GitHub Actions OIDC (JWT, RS256, JWKS-verified, audience-bound)** or a hashed, revocable **project-scoped API key**. Operator auth is undecided. FR-045, FR-046. |
| data_model_and_storage | No database; the UI holds only the transient indicator state. FR-055, FS §4. |
| migration_and_schema_evolution | Report schema follows **expand-contract**. Future DB migrations are **zero-downtime expand-contract** (add, backfill, switch reads, remove). No UI impact. FR-056, FR-057. |
| background_jobs_and_scheduling | None; no job-status UI. FR-058. |
| event_and_messaging_contract | None; no real-time UI channel. FR-058. |
| rate_limiting_and_quotas | None. A future `rate-limited` (429) maps to "API unavailable" in the indicator (any non-2xx). FR-059, FR-073. |
| observability_and_slo | The API writes structured request logs. **SC-006: `GET /api/v1/health` p95 ≤ 50 ms and p99 ≤ 100 ms at 20 concurrent clients sustained for 60 s, 0 errors, measured with Locust (headless), dataset: none (stateless endpoint), environment: one GitHub-hosted ubuntu-24.04 runner with a single uvicorn process.** The UI's 5 s timeout sits far above this SLO. |
| error_taxonomy_and_codes | API problem codes `not-found` 404, `method-not-allowed` 405, `validation-failed` 422, `internal-error` 500 (reserved: 400, 409, 413, 422, 429). Every non-2xx response maps to "API unavailable"; problem text is never displayed. FR-050, FR-051, FR-073a. |
| deployment_topology_and_envs | Local development (macOS/Linux) and CI only. Web dev server on `127.0.0.1:5173`, proxying `/api` to `127.0.0.1:8000`. FR-090, FR-073a. |
| scaling_and_resource_limits | Single local API process; no UI impact. FR-094. |
| secrets_and_config_management | No secrets. The only web config is the optional build-time API base URL variable, documented in `.env.example`. FR-091, FR-073a. |
| data_retention_and_compliance | No user data collected or stored by the UI. FR-081, FR-096. |
| backup_and_disaster_recovery | The repository is the system of record; recovery is clone, install, test. FR-097. |

**DevOps sections (no UI surface):**

| Bundle section | Where addressed / UI position |
|---|---|
| target_environments | Local development plus GitHub-hosted CI runners. FR-090. |
| infrastructure_as_code_strategy | No IaC in CD-5. Provisional direction: **Terraform**, provider chosen with the hosting target. FR-090. |
| ci_cd_pipeline_topology | GitHub Actions; the `web` job runs format, lint, type check, tests (including axe) and the build budget check on every PR and every push to `main`. FR-085, FR-086. **SC-005 (DORA lead time for changes, pre-deployment proxy): median ≤ 10 min, p95 ≤ 15 min from push to `main` until all checks are green, over the first 30 days after merge, measured from GitHub Actions run timestamps (GitHub Actions analytics) for every push to `main`.** |
| container_and_orchestration_model | None built. Provisional: API as an OCI image, web as static assets on the same origin; orchestrator undecided. FR-090. |
| secrets_and_credentials_management | None needed. Provisional model: **GitHub Actions OIDC** federation for CI-to-cloud access, and a **cloud-provider secret manager** (for example AWS Secrets Manager or GCP Secret Manager) for runtime secrets. FR-092. |
| observability_stack | The UI emits no telemetry (FR-081). Provisional service stack: **OpenTelemetry** SDK for logs, metrics and traces, exported over OTLP to an OpenTelemetry Collector, which forwards **metrics → Prometheus**, **logs → Grafana Loki** and **traces → Grafana Tempo**. FR-062. |
| rollout_and_rollback_strategy | CD-5 rollback is reverting the merge commit (it must pass CI). Provisional target: **blue-green** releases with traffic switched back to the previous colour, plus a **feature-flag kill-switch** for new ingestion behaviour. FR-093. |
| cost_and_resource_budget | USD 0/month; CI ≤ 25 runner-minutes and ≤ 10 min wall-clock per run. The axe and build checks fit inside the web job. FR-095. |
| disaster_recovery_runbook | Re-clone, install from lockfiles, `make test`. FR-097. |
| compliance_and_audit_trails | Git history plus Actions logs; branch protection recommended. No personal data processed by the UI. FR-098. |
