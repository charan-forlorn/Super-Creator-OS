import { parseAiPlan, AiPlanValidationError, type AiEditPlan } from "@haios/ai-core";
import {
  AIProvider,
  ProviderRequest,
  ProviderResponse,
  ProviderKind,
  ProviderUnavailableError,
  AI_PLAN_SYSTEM_PROMPT,
} from "./types.js";

/** Extract the first balanced JSON object from arbitrary model text. */
export function extractJsonObject(text: string): string {
  const start = text.indexOf("{");
  if (start === -1) throw new AiPlanValidationError("no JSON object in model output");
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
    } else if (ch === '"') inStr = true;
    else if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  throw new AiPlanValidationError("unbalanced JSON in model output");
}

/** Shared: parse the model text into a strict AIEditPlan (never returns raw text as action). */
export function modelTextToPlan(rawText: string, _provider: ProviderKind): AiEditPlan {
  const json = extractJsonObject(rawText);
  return parseAiPlan(JSON.parse(json));
}

/* ----------------------------- Offline provider ----------------------------- */
/**
 * Deterministic, fully-offline provider used for tests, E2E, and when no model
 * is configured. Maps a small set of canonical natural-language commands to
 * plans directly (no network). This lets the whole AI pipeline run and be
 * verified without an external model.
 */
export class OfflineProvider implements AIProvider {
  readonly kind: ProviderKind = "hermes";
  async isAvailable(): Promise<boolean> {
    return true;
  }
  async generate(req: ProviderRequest): Promise<ProviderResponse> {
    const plan = routeOfflineInstruction(req.instruction, req.context.selectedClipId);
    return { plan, provider: "hermes", rawText: JSON.stringify(plan) };
  }
}

function routeOfflineInstruction(text: string, selectedClipId?: string): AiEditPlan {
  const t = text.toLowerCase();
  const target = selectedClipId
    ? { kind: "clip" as const, clipId: selectedClipId }
    : { kind: "selection" as const };
  const secMatch = t.match(/(\d+(?:\.\d+)?)\s*seconds?/);
  const sec = secMatch ? Number(secMatch[1]) : 4;

  if (t.includes("split")) {
    return { version: 1, target, operations: [{ tool: "split_clip", params: { t: sec } }] };
  }
  if (t.includes("move")) {
    return { version: 1, target, operations: [{ tool: "move_clip", params: { newStart: sec } }] };
  }
  if (t.includes("trim")) {
    return { version: 1, target, operations: [{ tool: "trim_clip", params: { newInPoint: sec } }] };
  }
  if (t.includes("delete")) {
    return { version: 1, target, operations: [{ tool: "delete_clip", params: {} }] };
  }
  if (t.includes("caption")) {
    const capMatch = text.match(/"([^"]+)"/);
    return {
      version: 1,
      target: { kind: "selection" },
      operations: [{ tool: "add_caption", params: { text: capMatch ? capMatch[1] : "Caption" } }],
    };
  }
  if (t.includes("aspect")) {
    const ratio = t.includes("vertical") || t.includes("1080x1920") ? "1080x1920" : "1920x1080";
    return {
      version: 1,
      target: { kind: "selection" },
      operations: [{ tool: "change_aspect_ratio", params: { ratio } }],
    };
  }
  throw new AiPlanValidationError(`offline provider cannot interpret: "${text}"`);
}

/* ----------------------------- Ollama provider ----------------------------- */
interface OllamaConfig {
  baseUrl: string;
  model: string;
  /** Injectable fetch for testing. */
  fetchImpl?: typeof fetch;
}
export class OllamaProvider implements AIProvider {
  readonly kind: ProviderKind = "ollama";
  constructor(private cfg: OllamaConfig) {}
  async isAvailable(): Promise<boolean> {
    try {
      const f = this.cfg.fetchImpl ?? fetch;
      const r = await f(`${this.cfg.baseUrl}/api/tags`, { signal: AbortSignal.timeout(3000) });
      return r.ok;
    } catch {
      return false;
    }
  }
  async generate(req: ProviderRequest): Promise<ProviderResponse> {
    if (req.signal?.aborted) throw new ProviderUnavailableError("ollama", "aborted");
    const f = this.cfg.fetchImpl ?? fetch;
    let res: Response;
    try {
      res = await f(`${this.cfg.baseUrl}/api/generate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          model: this.cfg.model,
          prompt: `${AI_PLAN_SYSTEM_PROMPT}\n\nUser: ${req.instruction}\nContext: ${JSON.stringify(req.context)}`,
          stream: false,
          format: "json",
        }),
        signal: req.signal,
      });
    } catch (e) {
      throw new ProviderUnavailableError("ollama", String(e));
    }
    if (!res.ok) throw new ProviderUnavailableError("ollama", `status ${res.status}`);
    const data = (await res.json()) as { response: string };
    return { plan: modelTextToPlan(data.response, "ollama"), provider: "ollama", rawText: data.response };
  }
}

/* ------------------------- OpenAI-compatible provider ----------------------- */
interface OpenAIConfig {
  baseUrl: string;
  apiKey: string;
  model: string;
  fetchImpl?: typeof fetch;
}
export class OpenAICompatibleProvider implements AIProvider {
  readonly kind: ProviderKind = "openai-compatible";
  constructor(private cfg: OpenAIConfig) {}
  async isAvailable(): Promise<boolean> {
    try {
      const f = this.cfg.fetchImpl ?? fetch;
      const r = await f(`${this.cfg.baseUrl}/models`, {
        headers: { authorization: `Bearer ${this.cfg.apiKey}` },
        signal: AbortSignal.timeout(3000),
      });
      return r.ok;
    } catch {
      return false;
    }
  }
  async generate(req: ProviderRequest): Promise<ProviderResponse> {
    if (req.signal?.aborted) throw new ProviderUnavailableError("openai-compatible", "aborted");
    const f = this.cfg.fetchImpl ?? fetch;
    let res: Response;
    try {
      res = await f(`${this.cfg.baseUrl}/chat/completions`, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${this.cfg.apiKey}` },
        body: JSON.stringify({
          model: this.cfg.model,
          messages: [
            { role: "system", content: AI_PLAN_SYSTEM_PROMPT },
            {
              role: "user",
              content: `Instruction: ${req.instruction}\nContext: ${JSON.stringify(req.context)}`,
            },
          ],
          response_format: { type: "json_object" },
        }),
        signal: req.signal,
      });
    } catch (e) {
      throw new ProviderUnavailableError("openai-compatible", String(e));
    }
    if (!res.ok) throw new ProviderUnavailableError("openai-compatible", `status ${res.status}`);
    const data = (await res.json()) as { choices: [{ message: { content: string } }] };
    return {
      plan: modelTextToPlan(data.choices[0].message.content, "openai-compatible"),
      provider: "openai-compatible",
      rawText: data.choices[0].message.content,
    };
  }
}
