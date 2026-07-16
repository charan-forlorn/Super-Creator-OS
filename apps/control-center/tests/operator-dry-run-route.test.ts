import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { POST } from "@/app/api/operator-dry-run/route";
import { buildDryRunRequest } from "@/lib/operator-dry-run";

describe("operator dry-run route", () => {
  it("returns deterministic DRY_RUN response without execution success implication", async () => {
    const request = new NextRequest("http://localhost/api/operator-dry-run", {
      method: "POST",
      body: JSON.stringify(buildDryRunRequest("inspect-project", { project_id: "demo-project" })),
      headers: { "content-type": "application/json" },
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.mode).toBe("DRY_RUN");
    expect(payload.status).toBe("READY");
    expect(payload.side_effects_performed).toBe(false);
    expect(payload.prohibited_actions.map((item: { action: string }) => item.action)).toContain("invoke_hvs");
  });

  it("bad JSON fails closed as INVALID", async () => {
    const request = new NextRequest("http://localhost/api/operator-dry-run", {
      method: "POST",
      body: "{not-json",
    });

    const response = await POST(request);
    const payload = await response.json();

    expect(payload.status).toBe("INVALID");
    expect(payload.reason_codes).toContain("REQUEST_MUST_BE_OBJECT");
    expect(payload.side_effects_performed).toBe(false);
  });
});
