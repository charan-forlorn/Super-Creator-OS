import type { OrbitState } from "@/lib/cockpit-types";

export function Orbit({ state }: Readonly<{ state: OrbitState }>) {
  return (
    <div className={`cockpit-orbit cockpit-orbit--${state}`} aria-hidden="true">
      <div className="cockpit-orbit__ground" />
      <div className="cockpit-orbit__character">
        <div className="cockpit-orbit__antenna">
          <span className="cockpit-orbit__antenna-tip" />
        </div>
        <div className="cockpit-orbit__shell">
          <div className="cockpit-orbit__face">
            <span className="cockpit-orbit__eye cockpit-orbit__eye--left">
              <span className="cockpit-orbit__eye-shine" />
            </span>
            <span className="cockpit-orbit__eye cockpit-orbit__eye--right">
              <span className="cockpit-orbit__eye-shine" />
            </span>
            <span className="cockpit-orbit__cheek cockpit-orbit__cheek--left" />
            <span className="cockpit-orbit__cheek cockpit-orbit__cheek--right" />
            <span className="cockpit-orbit__smile" />
          </div>
        </div>
        <span className="cockpit-orbit__arm cockpit-orbit__arm--left" />
        <span className="cockpit-orbit__arm cockpit-orbit__arm--right" />
        <div className="cockpit-orbit__body">
          <span className="cockpit-orbit__confirmation">✓</span>
        </div>
      </div>
    </div>
  );
}
