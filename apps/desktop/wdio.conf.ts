import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

declare global {
  namespace WebdriverIO {
    interface Capabilities {
      "tauri:options"?: {
        application: string;
        args?: string[];
      };
    }
  }
}

/**
 * TEST-ONLY direct WebDriver configuration for the official Tauri 2 driver.
 *
 * `tauri-driver` runs separately on 127.0.0.1:4444 and translates the
 * `tauri:options.application` capability to Microsoft Edge WebDriver/WebView2.
 * This config contains no Tauri service, no Appium layer, and no test control
 * surface in the product. The binary is built via tauri.e2e.conf.json, whose
 * frontend is dist-e2e/ rather than normal production dist/.
 */
export const config: WebdriverIO.Config = {
  runner: "local",
  hostname: "127.0.0.1",
  port: 4444,
  path: "/",
  logLevel: "debug",
  specs: ["./e2e/**/*.e2e.ts"],
  maxInstances: 1,
  capabilities: [
    {
      // tauri-driver 2.0.6 maps `tauri:options` only from W3C alwaysMatch.
      alwaysMatch: {
        browserName: "webview2",
        "tauri:options": {
          application: join(here, "src-tauri", "target", "release", "haios-video-studio.exe"),
          args: [],
        },
      },
      firstMatch: [{}],
    },
  ],
  framework: "mocha",
  reporters: ["spec"],
  mochaOpts: { ui: "bdd", timeout: 60000 },
};
