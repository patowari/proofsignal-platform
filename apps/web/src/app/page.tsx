import Link from "next/link";
import { Composer } from "@/components/composer";
import { RecentList } from "@/components/recent-list";
import { getRecent } from "@/lib/api/client";
import type { RecentVerification } from "@/lib/api/schemas";

// Always current: a cached homepage would show stale verification states.
export const dynamic = "force-dynamic";

export default async function HomePage() {
  // Real data only. If the API is unreachable we show an honest empty state
  // rather than inventing activity to fill the page.
  let recent: RecentVerification[] = [];
  let apiReachable = true;
  try {
    recent = (await getRecent(12)).items;
  } catch {
    apiReachable = false;
  }

  const completed = recent.filter((r) => r.status === "COMPLETED");
  const inProgress = recent.filter(
    (r) => r.status === "QUEUED" || r.status === "RUNNING",
  );

  return (
    <div className="mx-auto max-w-6xl px-5 py-10 sm:py-16">
      <section className="hero-grid">
        <div className="hero-copy">
          <div className="eyebrow"><span aria-hidden="true" /> Independent public-interest verification</div>
          <h1 className="mt-5 font-serif text-5xl font-semibold leading-[0.98] tracking-tight sm:text-6xl lg:text-7xl">
            Check the claim.<br /><em>See the evidence.</em>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
          Submit a claim, article, or a captioned image or video. We find what evidence
          exists, show you what supports it and what contradicts it, and tell
          you plainly when we cannot establish an answer.
          </p>
          <div className="mt-7 flex flex-wrap gap-x-6 gap-y-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--green)]">
            <span>Sources shown</span><span>Verdicts explained</span><span>No account</span>
          </div>
        </div>
        <aside className="hero-note" aria-label="Our purpose">
          <p className="brand-bangla text-3xl font-bold leading-tight">গুজব নয়,<br />প্রমাণ দেখুন।</p>
          <div className="my-5 h-px bg-white/25" />
          <p className="text-sm leading-relaxed text-white/75">Built for the stories, posts, images and conversations that shape Bangladesh.</p>
        </aside>
      </section>

      <section className="mx-auto mt-12 max-w-4xl" aria-label="Submit content for verification">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div><p className="section-kicker">Start a check</p><h2 className="mt-1 font-serif text-2xl font-semibold">What would you like to verify?</h2></div>
          <span className="hidden text-xs text-muted sm:block">Private details? Remove them before submitting.</span>
        </div>
        <Composer />
      </section>

      <section className="mx-auto mt-5 max-w-4xl">
        <p className="text-center text-xs leading-relaxed text-muted">
          We do not search the entire web and we cannot do reverse image search.
          Every report names the sources we actually checked.{" "}
          <Link href="/method" className="underline">
            Read the method
          </Link>
          .
        </p>
      </section>

      {!apiReachable ? (
        <section className="mx-auto mt-16 max-w-3xl">
          <div className="rounded-lg border border-amber-300 bg-amber-50 px-5 py-4 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-50">
            <p className="font-medium">
              The verification service is not responding.
            </p>
            <p className="mt-1 opacity-90">
              Recent verifications cannot be shown right now. Submitting will
              not work until the service is back.
            </p>
          </div>
        </section>
      ) : (
        <div className="mt-16 space-y-12">
          {inProgress.length > 0 ? (
            <RecentList
              heading="In progress"
              description="Submissions currently being checked."
              items={inProgress}
            />
          ) : null}

          <RecentList
            heading="Recently checked"
            description="Public verifications, newest first."
            items={completed}
            emptyMessage="No verifications yet. Submit something above to create the first one."
          />
        </div>
      )}
    </div>
  );
}
