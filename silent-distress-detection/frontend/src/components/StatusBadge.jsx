import React from 'react';

const StatusBadge = ({ status }) => {
    let colorClass = 'badge-gray';

    if (status === 'Active') colorClass = 'badge-green';
    if (status === 'Idle' || status === 'Connecting' || status === 'Stopping') colorClass = 'badge-yellow';
    if (status === 'Error') colorClass = 'badge-red';

    // Alert statuses
    if (status === 'pending') colorClass = 'badge-red-blink';
    if (status === 'confirmed') colorClass = 'badge-blue';
    if (status === 'dismissed') colorClass = 'badge-gray';

    return (
        <span className={`status-badge ${colorClass}`}>
            {status}
        </span>
    );
};

export default StatusBadge;
