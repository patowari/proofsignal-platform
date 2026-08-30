import { RecentList } from "@/components/recent-list";
import { getRecent } from "@/lib/api/client";
import type { RecentVerification } from "@/lib/api/schemas";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Recent verifications",
};

export default async function RecentPage() {
  let items: RecentVerification[] = [];
  let unreachable = false;
  try {
    items = (await getRecent(50)).items;
  } catch {
    unreachable = true;
  }

  return (
    <div className="mx-auto max-w-4xl px-5 py-10 sm:py-16">
      <p className="section-kicker">Public archive</p>
      <h1 className="mt-2 font-serif text-4xl font-semibold tracking-tight sm:text-5xl">
        Recent verifications
      </h1>
      <p className="mt-2 text-sm text-muted">
        Every submission is public. These are the most recent.
      </p>

      <div className="mt-8">
        {unreachable ? (
          <p role="alert" className="text-sm text-muted">
            The verification service is not responding, so this list cannot be
            loaded.
          </p>
        ) : (
          <RecentList
            heading="All verifications"
            items={items}
            emptyMessage="Nothing has been verified yet."
          />
        )}
      </div>
    </div>
  );
}
