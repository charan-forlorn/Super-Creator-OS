import { BriefStudio } from "@/components/brief-studio/brief-studio";

// Cohort 10K — dedicated plain-language Brief Studio route.
// Server component shell. The resume identity arrives only through the
// authoritative opaque `draft_id` search param; nothing is read from storage.

export const dynamic = "force-dynamic";

export default async function BriefStudioPage({
  searchParams,
}: Readonly<{ searchParams: Promise<Record<string, string | string[] | undefined>> }>) {
  const params = await searchParams;
  const raw = params.draft_id;
  const candidate = Array.isArray(raw) ? raw[0] : raw;
  const draftId = typeof candidate === "string" && /^[A-Za-z0-9-]{1,64}$/.test(candidate) ? candidate : undefined;
  return <BriefStudio initialDraftId={draftId} />;
}
