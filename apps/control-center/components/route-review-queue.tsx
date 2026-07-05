import React from 'react';

export const RouteReviewQueue: React.FC<{ items?: Array<Record<string, unknown>> }> = ({ items }) => {
    const count = (items || []).length;
    return (
        <div>
            <h4>Route Review Queue</h4>
            <div>{count} items</div>
        </div>
    );
};

export default RouteReviewQueue;
