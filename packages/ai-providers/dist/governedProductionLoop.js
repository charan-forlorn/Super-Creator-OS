import { randomUUID } from "node:crypto";
import { planToCommands } from "@haios/ai-core";
import { CommandBus, createStudioRegistry } from "@haios/command-system";
import { createEmptyProject } from "@haios/project-model";
import { OllamaProvider } from "./providers.js";
import { AI_PLAN_SYSTEM_PROMPT } from "./types.js";
import { probeOllamaMachineEvidence, toMachineCapabilityEvidence } from "./machineEvidence.js";
import { routeCapability } from "./routing.js";
import { loadProductionHistory, sha256, summarizeModelHistory, writeProductionEvidence, } from "./productionTelemetry.js";
function candidateFor(modelId, digest, observedRows, priority, contractRevision) {
    const history = summarizeModelHistory(observedRows, "ollama", modelId, contractRevision);
    return {
        capability: "generate_text",
        providerId: "ollama",
        modelId,
        modelVersion: digest,
        capabilityId: "scos.ai.generate_text.ollama." + modelId.replace(/[^a-zA-Z0-9]+/g, "-"),
        capabilityVersion: "r1",
        capabilityKind: "ai_generation",
        authorityScope: "plan_generation_only",
        costClass: "local_zero_inference_cost",
        availability: "READY",
        currentness: "CURRENT",
        health: "HEALTHY",
        qualification: "QUALIFIED",
        licence: "ALLOWED",
        hardware: "FIT",
        evidenceComplete: true,
        priority,
        observedSuccessRate: history.successRate,
        observedLatencyMs: history.observedLatencyMs,
    };
}
export async function runGovernedProductionLoop(input) {
    const loopRunId = randomUUID();
    const routeDecisionId = randomUUID();
    const observedAt = new Date().toISOString();
    const contractRevision = sha256(AI_PLAN_SYSTEM_PROMPT);
    const qualificationModelIds = Object.keys(input.qualification.models).sort();
    const machineProbe = await probeOllamaMachineEvidence({
        baseUrl: input.baseUrl,
        observedAt,
        evidenceRef: "ollama-machine-probe:" + loopRunId,
        fetchImpl: input.fetchImpl,
    });
    const machineFacts = toMachineCapabilityEvidence(machineProbe);
    const history = await loadProductionHistory(input.evidenceDir);
    const candidates = [];
    for (const modelId of qualificationModelIds) {
        const binding = input.qualification.models[modelId];
        const observedModel = machineProbe.models.find((model) => model.modelId === modelId);
        if (!observedModel || !observedModel.modelVersion)
            continue;
        if (observedModel.modelVersion !== binding.digest)
            continue;
        const priority = input.modelOverride === modelId ? 100 : 0;
        candidates.push(candidateFor(modelId, binding.digest, history, priority, contractRevision));
    }
    const governanceEvidence = {};
    for (const candidate of candidates) {
        governanceEvidence[candidate.providerId + ":" + candidate.modelId] = {
            currentness: "CURRENT",
            qualification: "QUALIFIED",
            licence: "ALLOWED",
            hardware: "FIT",
            allowedCostClasses: ["local_zero_inference_cost"],
            evidenceComplete: true,
            evidenceRefs: [
                input.qualification.sourceRepo,
                input.qualification.sourceCommit,
                input.qualification.sourcePath,
                input.qualification.sourceSha256,
                "ollama-machine-probe:" + loopRunId,
            ],
        };
    }
    const routeDecision = routeCapability({
        capability: "generate_text",
        candidates,
        routeDecisionId,
        loopRunId,
        machineEvidence: machineFacts,
        governanceEvidence,
    });
    if (routeDecision.kind === "DENIED") {
        const evidence = await writeProductionEvidence(input.evidenceDir, {
            schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1",
            loopRunId,
            routeDecisionId,
            observedAt,
            routeDecision,
            qualification: {
                sourceRepo: input.qualification.sourceRepo,
                sourceCommit: input.qualification.sourceCommit,
                sourcePath: input.qualification.sourcePath,
                sourceSha256: input.qualification.sourceSha256,
                modelDigest: "",
            },
            telemetry: null,
            verification: {
                status: "NOT_RUN",
                planSchemaValidated: false,
                reason: "route_denied_fail_closed",
            },
        });
        return {
            status: "DENIED",
            loopRunId,
            routeDecisionId,
            evidencePath: evidence.path,
            evidenceSha256: evidence.evidenceSha256,
            telemetry: null,
            error: "no eligible route",
        };
    }
    const selected = routeDecision.candidate;
    const selectedBinding = input.qualification.models[selected.modelId];
    if (!selectedBinding || selected.modelVersion !== selectedBinding.digest) {
        const evidence = await writeProductionEvidence(input.evidenceDir, {
            schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1",
            loopRunId,
            routeDecisionId,
            observedAt,
            routeDecision,
            qualification: {
                sourceRepo: input.qualification.sourceRepo,
                sourceCommit: input.qualification.sourceCommit,
                sourcePath: input.qualification.sourcePath,
                sourceSha256: input.qualification.sourceSha256,
                modelDigest: selected.modelVersion ?? "",
            },
            telemetry: null,
            verification: {
                status: "FAIL",
                planSchemaValidated: false,
                reason: "qualification_digest_mismatch",
            },
        });
        return {
            status: "FAILED",
            loopRunId,
            routeDecisionId,
            evidencePath: evidence.path,
            evidenceSha256: evidence.evidenceSha256,
            telemetry: null,
            selectedModel: selected.modelId,
            error: "qualification digest mismatch",
        };
    }
    const provider = new OllamaProvider({
        baseUrl: input.baseUrl,
        model: selected.modelId,
        fetchImpl: input.fetchImpl,
    });
    const startedAt = new Date().toISOString();
    const startMono = performance.now();
    const requestBody = JSON.stringify({
        instruction: input.instruction,
        context: input.context ?? {},
    });
    const requestSha256 = sha256(requestBody);
    try {
        const response = await provider.generate({
            instruction: input.instruction,
            context: {
                clipIds: [...(input.context?.clipIds ?? [])],
                selectedClipId: input.context?.selectedClipId,
                projectSummary: input.context?.projectSummary,
            },
        });
        const rawText = response.rawText ?? JSON.stringify(response.plan);
        const projectBefore = createEmptyProject("Governed Production E2E", "loop-" + loopRunId);
        const projectBeforeSha256 = sha256(JSON.stringify(projectBefore));
        const executionStarted = performance.now();
        try {
            const registry = createStudioRegistry();
            const bus = new CommandBus(registry, projectBefore);
            const commands = planToCommands(response.plan, projectBefore, registry);
            for (const command of commands) {
                bus.execute(command.commandType, command.payload);
            }
            const projectAfter = bus.project;
            const projectAfterSha256 = sha256(JSON.stringify(projectAfter));
            const executionDurationMs = Math.round(performance.now() - executionStarted);
            const completedAt = new Date().toISOString();
            const durationMs = Math.round(performance.now() - startMono);
            const telemetry = {
                schemaVersion: "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1",
                loopRunId,
                routeDecisionId,
                observedAt,
                startedAt,
                completedAt,
                durationMs,
                capabilityId: selected.capabilityId ?? "unknown",
                providerId: selected.providerId,
                modelId: selected.modelId,
                modelVersion: selected.modelVersion,
                status: "COMPLETED",
                generationStatus: "COMPLETED",
                executionStatus: "COMPLETED",
                executedCommandTypes: commands.map((command) => command.commandType),
                projectBeforeSha256,
                projectAfterSha256,
                executionDurationMs,
                responseBytes: Buffer.byteLength(rawText, "utf8"),
                responseSha256: sha256(rawText),
                contractRevision,
                requestSha256,
                fallbackUsed: false,
                evidenceRefs: routeDecision.evidenceRefs,
            };
            const evidence = await writeProductionEvidence(input.evidenceDir, {
                schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1",
                loopRunId,
                routeDecisionId,
                observedAt,
                routeDecision,
                qualification: {
                    sourceRepo: input.qualification.sourceRepo,
                    sourceCommit: input.qualification.sourceCommit,
                    sourcePath: input.qualification.sourcePath,
                    sourceSha256: input.qualification.sourceSha256,
                    modelDigest: selectedBinding.digest,
                },
                telemetry,
                verification: {
                    status: "PASS",
                    planSchemaValidated: true,
                    operationCount: commands.length,
                },
            });
            return {
                status: "COMPLETED",
                loopRunId,
                routeDecisionId,
                evidencePath: evidence.path,
                evidenceSha256: evidence.evidenceSha256,
                selectedModel: selected.modelId,
                telemetry,
                plan: response.plan,
            };
        }
        catch (executionError) {
            const completedAt = new Date().toISOString();
            const durationMs = Math.round(performance.now() - startMono);
            const executionDurationMs = Math.round(performance.now() - executionStarted);
            const message = executionError instanceof Error ? executionError.message : String(executionError);
            const telemetry = {
                schemaVersion: "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1",
                loopRunId,
                routeDecisionId,
                observedAt,
                startedAt,
                completedAt,
                durationMs,
                capabilityId: selected.capabilityId ?? "unknown",
                providerId: selected.providerId,
                modelId: selected.modelId,
                modelVersion: selected.modelVersion,
                status: "FAILED",
                generationStatus: "COMPLETED",
                executionStatus: "FAILED",
                projectBeforeSha256,
                executionDurationMs,
                responseBytes: Buffer.byteLength(rawText, "utf8"),
                responseSha256: sha256(rawText),
                contractRevision,
                requestSha256,
                fallbackUsed: false,
                error: "governed execution failed: " + message,
                evidenceRefs: routeDecision.evidenceRefs,
            };
            const evidence = await writeProductionEvidence(input.evidenceDir, {
                schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1",
                loopRunId,
                routeDecisionId,
                observedAt,
                routeDecision,
                qualification: {
                    sourceRepo: input.qualification.sourceRepo,
                    sourceCommit: input.qualification.sourceCommit,
                    sourcePath: input.qualification.sourcePath,
                    sourceSha256: input.qualification.sourceSha256,
                    modelDigest: selectedBinding.digest,
                },
                telemetry,
                verification: {
                    status: "FAIL",
                    planSchemaValidated: true,
                    operationCount: response.plan.operations.length,
                    reason: message,
                },
            });
            return {
                status: "FAILED",
                loopRunId,
                routeDecisionId,
                evidencePath: evidence.path,
                evidenceSha256: evidence.evidenceSha256,
                selectedModel: selected.modelId,
                telemetry,
                plan: response.plan,
                error: message,
            };
        }
    }
    catch (error) {
        const completedAt = new Date().toISOString();
        const durationMs = Math.round(performance.now() - startMono);
        const message = error instanceof Error ? error.message : String(error);
        const telemetry = {
            schemaVersion: "SCOS_PRODUCTION_EXECUTION_TELEMETRY_R1",
            loopRunId,
            routeDecisionId,
            observedAt,
            startedAt,
            completedAt,
            durationMs,
            capabilityId: selected.capabilityId ?? "unknown",
            providerId: selected.providerId,
            modelId: selected.modelId,
            modelVersion: selected.modelVersion,
            status: "FAILED",
            generationStatus: "FAILED",
            executionStatus: "NOT_RUN",
            contractRevision,
            requestSha256,
            fallbackUsed: false,
            error: message,
            evidenceRefs: routeDecision.evidenceRefs,
        };
        const evidence = await writeProductionEvidence(input.evidenceDir, {
            schemaVersion: "SCOS_GOVERNED_PRODUCTION_LOOP_R1",
            loopRunId,
            routeDecisionId,
            observedAt,
            routeDecision,
            qualification: {
                sourceRepo: input.qualification.sourceRepo,
                sourceCommit: input.qualification.sourceCommit,
                sourcePath: input.qualification.sourcePath,
                sourceSha256: input.qualification.sourceSha256,
                modelDigest: selectedBinding.digest,
            },
            telemetry,
            verification: {
                status: "FAIL",
                planSchemaValidated: false,
                reason: message,
            },
        });
        return {
            status: "FAILED",
            loopRunId,
            routeDecisionId,
            evidencePath: evidence.path,
            evidenceSha256: evidence.evidenceSha256,
            selectedModel: selected.modelId,
            telemetry,
            error: message,
        };
    }
}
