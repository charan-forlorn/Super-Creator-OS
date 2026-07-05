import { RoutingDecision } from './workflow-router-types';

export const sampleDecision: RoutingDecision = {
    decisionId: 'dec-1',
    sessionId: 's1',
    sourceAgent: 'chatgpt',
    targetAgent: 'claude_code',
    nextPacketType: 'implementation_prompt',
    requiresOperatorReview: true,
    decisionStatus: 'review_required',
};
