import type { OrbitState } from "@/lib/cockpit-types";
import { Orbit } from "@/components/cockpit/orbit";

/**
 * CSS-native Orbit mascot (no canvas, no runtime image, reduced-motion safe).
 * `size` is retained in the signature for call-site compatibility only; the
 * committed CSS-native `.cockpit-orbit` renders at a fixed intrinsic size.
 */
export function OrbitMascot({ state }: Readonly<{ state: OrbitState; size?: number }>) {
  return <Orbit state={state} />;
}
