import { notFound } from "next/navigation";
import { VerificationPage } from "@/components/verification-page";
import { ApiError, getStatus, getVerification } from "@/lib/api/client";
import type {
  VerificationReport,
  VerificationStatusResponse,
} from "@/lib/api/schemas";

export const dynamic = "force-dynamic";

export default async function VerifyPage({
  params,
}: {
  params: Promise<{ publicId: string }>;
}) {
  const { publicId } = await params;

  // Fetch on the server so the page has real content on first paint rather
  // than a skeleton: a completed report renders immediately, and an in-flight
  // one shows its actual stages before client polling takes over.
  let initial: VerificationReport | null = null;
  let initialStatus: VerificationStatusResponse | undefined;
  let unreachable = false;
  try {
    initial = await getVerification(publicId);
    if (initial.status === "QUEUED" || initial.status === "RUNNING") {
      initialStatus = await getStatus(publicId);
    }
  } catch (error) {
    if (error instanceof ApiError && error.isNotFound) notFound();
    unreachable = true;
  }

  return (
    <div className="mx-auto max-w-3xl px-5 py-10 sm:py-14">
      <VerificationPage
        publicId={publicId}
        initialReport={initial}
        initialStatus={initialStatus}
        unreachable={unreachable}
      />
    </div>
  );
}
