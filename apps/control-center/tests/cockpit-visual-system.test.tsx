import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { render } from "@testing-library/react";
import { CockpitDashboard } from "@/components/cockpit/cockpit-dashboard";

describe("cockpit visual system", () => {
  it("renders a deterministic ambient layer inside the isolated cockpit shell", () => {
    const { container } = render(<CockpitDashboard />);
    const shell = container.querySelector(".cockpit-shell");
    const ambient = container.querySelector(".cockpit-ambient");

    expect(shell).toHaveClass("cockpit-shell--ambient-full");
    expect(ambient).toHaveAttribute("aria-hidden", "true");
    expect(ambient?.querySelectorAll(".cockpit-firefly")).toHaveLength(10);
  });

  it("keeps ambient motion and contrast adjustments in CSS-only accessibility guards", () => {
    const css = readFileSync("app/globals.css", "utf8");

    expect(css).toContain("isolation: isolate");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("@media (prefers-contrast: more)");
    expect(css).toContain("cockpit-firefly-drift");
  });

  it("renders Orbit as a static CSS-native mascot with no canvas or runtime image", () => {
    const { container } = render(<CockpitDashboard />);
    const mascot = container.querySelector(".orbit-briefing .cockpit-orbit");
    const css = readFileSync("app/globals.css", "utf8");
    const mascotSource = readFileSync("components/cockpit/orbit-mascot.tsx", "utf8");

    // CSS-native orbit markup is present; no canvas surface is used.
    expect(mascot).toBeInTheDocument();
    expect(mascot?.querySelector("canvas")).toBeNull();
    expect(css).toContain("grid-template-columns: 132px minmax(0, 1fr)");
    expect(css).toContain(".cockpit-orbit");
    // The re-exported mascot no longer relies on the canvas rig (drawLayer/ORBIT_ART).
    expect(mascotSource).not.toContain("drawLayer");
    expect(mascotSource).not.toContain("ORBIT_ART");
  });

  it("does not import any prohibited mascot asset in the active cockpit UI", () => {
    const sourceFiles = [
      "components/cockpit/orbit-mascot.tsx",
      "components/cockpit/orbit.tsx",
      "components/cockpit/cockpit-dashboard.tsx",
      "components/cockpit/cockpit-shell.tsx",
      "components/cockpit/cockpit-routes.tsx",
    ];
    const prohibited = [
      "design-references/orbit-robot-reference.png",
      "public/mascot/orbit-sprite.png",
      "public/mascots/orbit-reference-chroma.png",
      "orbit-reference.png",
    ];

    for (const file of sourceFiles) {
      const content = readFileSync(file, "utf8");
      for (const asset of prohibited) {
        expect(content, `${file} must not reference ${asset}`).not.toContain(asset);
      }
    }
  });

  it("disables continuous mascot motion under prefers-reduced-motion", () => {
    const css = readFileSync("app/globals.css", "utf8");
    const block = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce) { .cockpit-orbit__character"));

    // The CSS-native orbit animation guards must neutralize continuous motion.
    expect(block).toContain(".cockpit-orbit__character");
    expect(block).toContain("animation: none");
    // No canvas-based reduced-motion rig should remain.
    expect(css).not.toContain("orbit-rig-float");
    expect(css).not.toContain(".orbit-mascot__canvas");
  });
});
