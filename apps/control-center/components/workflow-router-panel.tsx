import React from 'react';
import { sampleDecision } from '../lib/workflow-router-mock-data';

export const WorkflowRouterPanel = () => {
    return (
        <div>
            <h2>Cross-Agent Router (Mock)</h2>
            <pre>{JSON.stringify(sampleDecision, null, 2)}</pre>
        </div>
    );
};

export default WorkflowRouterPanel;
