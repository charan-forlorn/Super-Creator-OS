/**
 * R2.1 GUI E2E — REAL rendered-editor gesture proof.
 *
 * WebDriver drives the actual Tauri/WebView2 DOM. No CommandBus/store functions
 * are imported or called here: all state changes come from real key and pointer
 * actions, and assertions observe rendered clip elements/selection readouts.
 */
import { expect, $, browser } from "@wdio/globals";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

const clipSel = (id: string) => $(`[data-testid="clip-${id}"]`);
const startOf = async (id: string): Promise<number> =>
  Number(await clipSel(id).getAttribute("data-start"));
const selectedOf = async (id: string): Promise<boolean> =>
  (await clipSel(id).getAttribute("data-selected")) === "true";
const clipCount = async (): Promise<number> => (await $$('[data-testid^="clip-"]')).length;

async function selectedCount(): Promise<number> {
  const text = await $('[data-testid="selection-count"]').getText();
  const match = /(\d+)\s+selected/.exec(text);
  return match ? Number(match[1]) : -1;
}

/** Sends a real Control-modified pointer click, then releases Control. */
async function ctrlClick(id: string): Promise<void> {
  const el = await clipSel(id);
  await browser.action("key").down("Control").perform();
  await el.click();
  await browser.action("key").up("Control").perform();
}

async function selectC0C1(): Promise<void> {
  await browser.keys("Escape");
  await ctrlClick("c0");
  await ctrlClick("c1");
  expect(await selectedOf("c0")).toBe(true);
  expect(await selectedOf("c1")).toBe(true);
  expect(await selectedCount()).toBe(2);
}

/** Real pointer drag of c0; positions are relative to the rendered clip. */
async function dragC0By(seconds: number): Promise<void> {
  const el = await clipSel("c0");
  const duration = Number(await el.getAttribute("data-duration"));
  const size = await el.getSize();
  const pxPerSec = size.width / duration;
  await el.dragAndDrop({ x: Math.round(seconds * pxPerSec), y: 0 });
}

describe("R2.1 timeline — actual WebView2 GUI interaction", () => {
  before(async () => {
    const documentState = await browser.execute(() => ({
      href: window.location.href,
      title: document.title,
      body: document.body.innerHTML,
    }));
    await mkdir(join(process.cwd(), "e2e", "artifacts"), { recursive: true });
    await writeFile(
      join(process.cwd(), "e2e", "artifacts", "initial-document.json"),
      JSON.stringify(documentState, null, 2),
      "utf8",
    );
  });

  it("proves every pointer/keyboard gate in one deterministic fixture session", async () => {
    // 1–2. Seeded fixture must be visibly rendered, not merely present in state.
    for (const id of ["c0", "c1", "c2"]) {
      await browser.waitUntil(async () => (await clipSel(id)).isDisplayed(), {
        timeout: 15000,
        timeoutMsg: `${id} was not visibly rendered by the E2E app`,
      });
    }
    expect(await clipCount()).toBe(3); // GUI_CLIPS_VISIBLE

    // 3. Ctrl-click selects multiple distinct rendered clips.
    await selectC0C1(); // GUI_MULTI_SELECT

    // 4. Drag selected group, then observe both start attributes and preserved gap.
    const c0BeforeDrag = await startOf("c0");
    const c1BeforeDrag = await startOf("c1");
    const spacingBeforeDrag = c1BeforeDrag - c0BeforeDrag;
    await dragC0By(2);
    const c0AfterDrag = await startOf("c0");
    const c1AfterDrag = await startOf("c1");
    expect(Math.abs(c0AfterDrag - (c0BeforeDrag + 2))).toBeLessThan(0.25);
    expect(Math.abs(c1AfterDrag - (c1BeforeDrag + 2))).toBeLessThan(0.25);
    expect(Math.abs((c1AfterDrag - c0AfterDrag) - spacingBeforeDrag)).toBeLessThan(1e-6);
    // GUI_GROUP_DRAG + GUI_GROUP_SPACING_PRESERVED

    // 5–6. One undo/redo must act on the whole atomic group command.
    await browser.keys(["Control", "z"]);
    expect(Math.abs((await startOf("c0")) - c0BeforeDrag)).toBeLessThan(1e-6);
    expect(Math.abs((await startOf("c1")) - c1BeforeDrag)).toBeLessThan(1e-6);
    // GUI_GROUP_UNDO
    await browser.keys(["Control", "y"]);
    expect(Math.abs((await startOf("c0")) - c0AfterDrag)).toBeLessThan(1e-6);
    expect(Math.abs((await startOf("c1")) - c1AfterDrag)).toBeLessThan(1e-6);
    // GUI_GROUP_REDO

    // 7–8. Ctrl+A + arrow nudge moves the entire selected group by exactly 0.5s.
    await browser.keys(["Control", "a"]);
    expect(await selectedCount()).toBe(3); // GUI_SELECT_ALL
    const c0BeforeNudge = await startOf("c0");
    const c1BeforeNudge = await startOf("c1");
    const c2BeforeNudge = await startOf("c2");
    await browser.keys("ArrowRight");
    for (const [id, before] of [["c0", c0BeforeNudge], ["c1", c1BeforeNudge], ["c2", c2BeforeNudge]] as const) {
      expect(Math.abs((await startOf(id)) - (before + 0.5))).toBeLessThan(0.1);
    }
    // GUI_KEYBOARD_NUDGE

    // 9–10. Delete all through GUI, then one undo restores exact visible clips.
    await browser.keys("Delete");
    await browser.waitUntil(async () => (await clipCount()) === 0, { timeout: 5000 });
    expect(await clipCount()).toBe(0); // GUI_GROUP_DELETE
    await browser.keys(["Control", "z"]);
    await browser.waitUntil(async () => (await clipCount()) === 3, { timeout: 5000 });
    expect(await clipCount()).toBe(3); // GUI_GROUP_DELETE_UNDO

    // 11. Select 2 then Ctrl+D; both original and two duplicates are rendered.
    await selectC0C1();
    await browser.keys(["Control", "d"]);
    await browser.waitUntil(async () => (await clipCount()) === 5, { timeout: 5000 });
    expect(await clipCount()).toBe(5); // GUI_GROUP_DUPLICATE

    // 12. Use a real track click to place the playhead at 2s, then split c0/c1.
    const track = await $(".track-video");
    const trackSize = await track.getSize();
    await track.click({ x: Math.round(2 * 80), y: Math.round(trackSize.height / 2) });
    await selectC0C1();
    const countBeforeSplit = await clipCount();
    await browser.keys("s");
    await browser.waitUntil(async () => (await clipCount()) === countBeforeSplit + 2, { timeout: 5000 });
    expect(await clipCount()).toBe(countBeforeSplit + 2); // GUI_MULTI_SPLIT

    // 13. Escape clears the rendered selection readout.
    await browser.keys("Escape");
    expect(await selectedCount()).toBe(0); // GUI_CLEAR_SELECTION
  });
});
