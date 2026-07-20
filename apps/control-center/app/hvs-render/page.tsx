import { HvsRenderPanel } from "@/components/hvs-render-panel";

export const dynamic = "force-dynamic";

export default async function HvsRenderPage({
  searchParams,
}: Readonly<{ searchParams: Promise<{ projectId?: string }> }>) {
  const { projectId } = await searchParams;
  const pid = projectId && /^spp-[a-f0-9]{12}$/.test(projectId) ? projectId : null;
  return (
    <main style={{ padding: "1.5rem", maxWidth: "72rem", margin: "0 auto" }}>
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.75rem" }}>
        HVS Project Render
      </h1>
      {pid ? <HvsRenderPanel projectId={pid} /> : <p>Valid projectId is required.</p>}
    </main>
  );
}
