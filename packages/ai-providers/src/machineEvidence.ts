export interface OllamaObservedModel {
  readonly modelId: string;
  readonly modelVersion?: string;
}

export interface OllamaMachineEvidence {
  readonly observedAt: string;
  readonly providerId: "ollama";
  readonly providerReachable: boolean;
  readonly health: "HEALTHY" | "UNHEALTHY";
  readonly models: readonly OllamaObservedModel[];
  readonly evidenceRefs: readonly string[];
}

export interface OllamaMachineEvidenceOptions {
  readonly baseUrl: string;
  readonly observedAt: string;
  readonly evidenceRef: string;
  readonly fetchImpl?: typeof fetch;
}

interface OllamaTagsResponse {
  models?: Array<{
    name?: string;
    digest?: string;
  }>;
}

export async function probeOllamaMachineEvidence(
  options: OllamaMachineEvidenceOptions,
): Promise<OllamaMachineEvidence> {
  const fetchImpl = options.fetchImpl ?? fetch;
  try {
    const response = await fetchImpl(`${options.baseUrl}/api/tags`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) return unreachable(options);
    const body = (await response.json()) as OllamaTagsResponse;
    const models = (body.models ?? [])
      .filter((model) => typeof model.name === "string" && model.name.length > 0)
      .map((model) => ({ modelId: model.name as string, modelVersion: model.digest }));
    return {
      observedAt: options.observedAt,
      providerId: "ollama",
      providerReachable: true,
      health: "HEALTHY",
      models,
      evidenceRefs: [options.evidenceRef],
    };
  } catch {
    return unreachable(options);
  }
}

function unreachable(options: OllamaMachineEvidenceOptions): OllamaMachineEvidence {
  return {
    observedAt: options.observedAt,
    providerId: "ollama",
    providerReachable: false,
    health: "UNHEALTHY",
    models: [],
    evidenceRefs: [options.evidenceRef],
  };
}

export function toMachineCapabilityEvidence(
  evidence: OllamaMachineEvidence,
): readonly import("./routing.js").MachineCapabilityEvidence[] {
  return evidence.models.map((model) => ({
    observedAt: evidence.observedAt,
    providerId: evidence.providerId,
    providerReachable: evidence.providerReachable,
    modelId: model.modelId,
    modelVersion: model.modelVersion,
    modelPresent: true,
    health: evidence.health,
    evidenceRefs: evidence.evidenceRefs,
  }));
}
