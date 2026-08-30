# Frontend rules

Next.js App Router + TypeScript (strict) + Tailwind + shadcn/ui + TanStack Query
+ Zod. Package manager: **pnpm**.

## Visual direction

Credible editorial newsroom / research tool. Serious typography, strong
information hierarchy, restrained neutral palette, generous whitespace.

Explicitly avoid: neon gradients, glassmorphism, glowing AI orbs, robot mascots,
"AI magic" language, dashboard-card soup, decorative animation that delays
information.

## Evidence-first UI

The verdict is never presented as a bare number. Every result screen shows what
was found, what supports, what contradicts, and what is unresolved. Contradicting
evidence is never hidden because the verdict is positive. Never render a fake
percentage — confidence is `LOW | MEDIUM | HIGH`.

Progress UI reflects **real backend stages** polled from the API. Never animate a
fake sequence of steps unrelated to actual job state.

## Data

All API responses are parsed through Zod schemas in `lib/api/schemas.ts` before
use; a shape mismatch surfaces an error state rather than crashing on `undefined`.
Server components fetch directly; client interactivity uses TanStack Query.
Verdict/stage enums are derived from one shared source, not restated per file.

## Accessibility

Semantic landmarks, real headings order, labelled controls, visible focus rings,
keyboard-operable everything. Verdict is never communicated by color alone —
always pair with an icon and text. Target WCAG AA contrast. Respect
`prefers-reduced-motion`.

## Quality

`pnpm typecheck`, `pnpm lint`, and `pnpm test` must pass. No `any` in component
props. Loading, empty, error, and partial-failure states are designed, not
afterthoughts.
