import React from 'react';

export const AgentRouteFlow: React.FC<{ steps?: Array<Record<string, unknown>> }> = ({ steps }) => {
    return (
        <div>
            <h4>Route Steps</h4>
            <ul>
                {steps && steps.map((s: Record<string, unknown>, index: number) => (
                    <li key={(s["step_id"] as string) || index}> {(s["source_agent"] as string) || ''} → {(s["target_agent"] as string) || ''} ({(s["packet_type"] as string) || ''})</li>
                ))}
            </ul>
        </div>
    );
};

export default AgentRouteFlow;
