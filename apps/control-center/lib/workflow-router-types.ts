export type AgentName = 'chatgpt' | 'claude_code' | 'codex' | 'hermes' | 'operator';

export interface RoutingDecision {
    decisionId: string;
    sessionId: string;
    sourcePacketId?: string;
    sourceAgent: AgentName;
    targetAgent: AgentName;
    nextPacketType: string;
    requiresOperatorReview: boolean;
    decisionStatus: string;
}
