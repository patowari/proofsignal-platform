import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Method — Evidence-Backed Verification",
  description:
    "How we check claims, what our verdicts mean, and what this system cannot do.",
};

export default function MethodPage() {
  return (
    <div className="mx-auto max-w-3xl px-5 py-12 sm:py-16">
      <h1 className="font-serif text-4xl font-semibold tracking-tight">
        How this works
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-muted">
        We do not ask an AI what is true. We look for evidence first, then
        report what that evidence establishes.
      </p>

      <section className="mt-12" aria-labelledby="process">
        <h2 id="process" className="font-serif text-2xl font-semibold">
          The process
        </h2>
        <ol className="mt-4 space-y-4 text-sm leading-relaxed">
          <li>
            <strong className="font-medium">Claims are separated.</strong> A
            paragraph usually contains several factual assertions. We split them
            apart and check each one independently, because a piece can be
            mostly accurate while one central detail is wrong.
          </li>
          <li>
            <strong className="font-medium">Evidence is retrieved.</strong> We
            search our indexed sources for passages that speak to each specific
            claim, not merely to its topic.
          </li>
          <li>
            <strong className="font-medium">
              Each passage is labelled.
            </strong>{" "}
            Supports, contradicts, related but inconclusive, or insufficient.
          </li>
          <li>
            <strong className="font-medium">
              Duplicates are grouped.
            </strong>{" "}
            Fifty sites republishing one wire report is one source, not fifty.
            Repetition does not raise our confidence.
          </li>
          <li>
            <strong className="font-medium">
              The verdict is computed.
            </strong>{" "}
            A fixed, published formula turns those labels into a verdict. The
            language model never chooses the outcome.
          </li>
        </ol>
      </section>

      <section className="mt-12" aria-labelledby="verdicts">
        <h2 id="verdicts" className="font-serif text-2xl font-semibold">
          What the verdicts mean
        </h2>
        <dl className="mt-4 space-y-4 text-sm leading-relaxed">
          {[
            ["Verified", "Strong, independent evidence establishes the claim."],
            ["Likely true", "Good supporting evidence, with thin sourcing or minor gaps."],
            ["Partly true", "The core holds up, but specific details are wrong or overstated."],
            ["Misleading", "The facts are real, but the framing or timing creates a false impression."],
            ["Unverified", "We could not find enough evidence either way. This is not the same as false."],
            ["Likely false", "Meaningful evidence contradicts the claim, though not conclusively."],
            ["False", "Strong, independent evidence directly contradicts the claim."],
            ["Satire", "It comes from satire or parody and is not a sincere assertion."],
            ["Opinion", "It is a value judgement or prediction, which evidence cannot settle."],
          ].map(([term, definition]) => (
            <div key={term}>
              <dt className="font-medium">{term}</dt>
              <dd className="text-muted">{definition}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-12" aria-labelledby="limits">
        <h2 id="limits" className="font-serif text-2xl font-semibold">
          What we cannot do
        </h2>
        <ul className="mt-4 space-y-3 text-sm leading-relaxed text-muted">
          <li>
            <strong className="font-medium text-[var(--foreground)]">
              We do not search the whole web.
            </strong>{" "}
            Coverage is limited to our indexed sources and any link you give us.
            Each report names what was actually checked.
          </li>
          <li>
            <strong className="font-medium text-[var(--foreground)]">
              We cannot reverse image search.
            </strong>{" "}
            We can compare a file against our own indexed material, but we
            cannot trace it across the internet. When we do not know where an
            image came from, we say so rather than guessing.
          </li>
          <li>
            <strong className="font-medium text-[var(--foreground)]">
              We cannot read private or paywalled content.
            </strong>{" "}
            We do not bypass logins, paywalls, or platform restrictions.
          </li>
          <li>
            <strong className="font-medium text-[var(--foreground)]">
              Our scoring is not calibrated.
            </strong>{" "}
            The formula is published and testable, but it has not been validated
            against a labelled dataset.
          </li>
        </ul>
      </section>

      <section className="mt-12" aria-labelledby="wrong">
        <h2 id="wrong" className="font-serif text-2xl font-semibold">
          We can be wrong
        </h2>
        <p className="mt-4 text-sm leading-relaxed text-muted">
          Evidence can be missing, mislabelled, or simply not yet published.
          Results can change as new material appears. Treat a report as a
          starting point with its sources attached — not as a final authority.
          The sources are shown precisely so you can judge them yourself.
        </p>
      </section>
    </div>
  );
}
