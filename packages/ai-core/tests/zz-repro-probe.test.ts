import { describe, it } from "vitest";
import { createEmptyProject } from "@haios/project-model";
import { createStudioRegistry } from "@haios/command-system";
import { planToCommands } from "../src/compiler.js";

// Diagnostic probe: prints the CURRENT (pre-fix) failure text for each of the
// two production-loop payload defects so the RED evidence can be compared
// byte-for-byte against evidence/production-loop/runs/*.json.
describe("repro probe", () => {
  it("prints current failures", async () => {
    const cases: Array<[string, unknown]> = [
      ["DEFECT1 caption.place duration-as-string (run f6ff926d)", {
        version: 1, target: { kind: "selection" },
        operations: [{ tool: "add_caption", params: { text: "Hi", start: "2", duration: "3.5" } }],
      }],
      ["DEFECT2 changeAspect params.place (run abadc93c / f54fbced)", {
        version: 1, target: { kind: "selection" },
        operations: [{ tool: "change_aspect_ratio", params: { place: { ratio: "1080x1920" } } }],
      }],
    ];
    for (const [label, plan] of cases) {
      try {
        const project = createEmptyProject("x", "p");
        const cmds = planToCommands(plan as never, project, createStudioRegistry());
        console.log(`\n[${label}]\n  => COMPILED: ${JSON.stringify(cmds)}`);
        // Reproduce the FULL runtime path: the governor then does
        // bus.execute(commandType, payload) — which is where f6ff926d failed.
        const { createCommandBus } = await import("@haios/command-system");
        const bus = createCommandBus(project);
        for (const c of cmds) {
          bus.execute(c.commandType, c.payload);
        }
        console.log(`  => BUS EXECUTED OK`);
      } catch (e) {
        console.log(`  => REJECTED: ${(e as Error).message.replace(/\s+/g, " ")}`);
      }
    }
  });
});
