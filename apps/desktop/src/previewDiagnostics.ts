// ROOT_CAUSE_3 / TEST3 — playback diagnostics.
//
// The preview must expose and record the WebView2 media lifecycle so a decode
// or source error is never silently swallowed. This is a pure, framework-free
// recorder that the <Preview> component feeds from the <video> element's events.

export type PlaybackEventType =
  | "loadedmetadata"
  | "canplay"
  | "canplaythrough"
  | "play"
  | "playing"
  | "pause"
  | "ended"
  | "waiting"
  | "seeking"
  | "seeked"
  | "error"
  | "stalled";

export interface MediaErrorInfo {
  /** HTMLMediaElement error code: 1=ABORTED, 2=NETWORK, 3=DECODE, 4=SRC_NOT_SUPPORTED. */
  code: number;
  message: string;
}

export interface PlaybackEvent {
  type: PlaybackEventType;
  at: number;
  code?: number;
  message?: string;
  mediaError?: MediaErrorInfo;
}

const DECODE_CODES = new Set([3, 4]);

export class PlaybackDiagnostics {
  private events: PlaybackEvent[] = [];

  record(ev: Omit<PlaybackEvent, "at">): void {
    this.events.push({ ...ev, at: Date.now() });
  }

  recordError(error: { code: number; message?: string }): void {
    this.record({
      type: "error",
      code: error.code,
      message: error.message,
      mediaError: { code: error.code, message: error.message ?? `media error ${error.code}` },
    });
  }

  get lastEvent(): PlaybackEvent | undefined {
    return this.events[this.events.length - 1];
  }

  get hasError(): boolean {
    return this.events.some((e) => e.type === "error");
  }

  get isDecodeError(): boolean {
    return this.events.some(
      (e) => e.type === "error" && e.mediaError != null && DECODE_CODES.has(e.mediaError.code),
    );
  }

  get isReady(): boolean {
    return this.events.some((e) => e.type === "canplay" || e.type === "canplaythrough");
  }

  log(): PlaybackEvent[] {
    return this.events;
  }

  /** Stable snapshot for review / debug telemetry. */
  toJSON(): { events: PlaybackEvent[]; hasError: boolean; isDecodeError: boolean; isReady: boolean } {
    return {
      events: this.events,
      hasError: this.hasError,
      isDecodeError: this.isDecodeError,
      isReady: this.isReady,
    };
  }

  summary(): string {
    const last = this.lastEvent;
    if (!last) return "no-playback-events";
    if (last.type === "error" && last.mediaError) {
      const kind =
        last.mediaError.code === 4
          ? "source-not-supported"
          : last.mediaError.code === 3
            ? "decode-error"
            : last.mediaError.code === 2
              ? "network-error"
              : "playback-error";
      return `${kind}: ${last.mediaError.message}`;
    }
    return last.type;
  }

  reset(): void {
    this.events = [];
  }
}
