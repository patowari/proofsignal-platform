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
    <div className="mx-auto max-w-5xl px-5 py-12 sm:py-16">
      <section className="mx-auto max-w-3xl text-center">
        <h1 className="font-serif text-4xl font-semibold tracking-tight sm:text-5xl">
          What does the evidence say?
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-muted sm:text-lg">
          Submit a claim, article, image, or video. We find what evidence
          exists, show you what supports it and what contradicts it, and tell
          you plainly when we cannot establish an answer.
        </p>
      </section>

      <section className="mx-auto mt-8 max-w-3xl" aria-label="Submit content for verification">
        <Composer />
      </section>

      <section className="mx-auto mt-6 max-w-3xl">
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
