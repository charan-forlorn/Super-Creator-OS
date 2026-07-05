import React from 'react';

export const RoutingDecisionCard: React.FC<{ decision: Record<string, unknown> }> = ({ decision }) => {
    const id = decision?.decisionId as string | undefined;
    return (
        <div className="routing-decision-card">
            <strong>Decision:</strong> {id}
        </div>
    );
};

export default RoutingDecisionCard;
