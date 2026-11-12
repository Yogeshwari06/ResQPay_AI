import React, { useCallback, useEffect, useState } from 'react';
import AlertCard from '../components/AlertCard';
import StaffAccess from '../components/StaffAccess';
import { apiRequest } from '../services/api';
const Alerts = () => {
    const [alerts, setAlerts] = useState([]);
    const [user, setUser] = useState(null);
    const [error, setError] = useState('');
    const onUserChange = useCallback((activeUser) => setUser(activeUser), []);

    const fetchAlerts = useCallback(async () => {
        if (!user) {
            setAlerts([]);
            return;
        }
        try {
            setAlerts(await apiRequest('/api/incidents', {}, true));
            setError('');
        } catch (err) {
            setError(err.message);
        }
    }, [user]);

    useEffect(() => {
        fetchAlerts();
        const interval = setInterval(fetchAlerts, 3000); // Poll every 3 seconds
        return () => clearInterval(interval);
    }, [fetchAlerts]);

    const handleVerification = async (id, status) => {
        try {
            await apiRequest(`/api/incidents/${encodeURIComponent(id)}/verification`, {
                method: 'PATCH',
                body: JSON.stringify({ status }),
            }, true);
            await fetchAlerts();
        } catch (verificationError) {
            setError(verificationError.message);
        }
    };

    return (
        <div className="page-container">
            <h1>Emergency incidents</h1>
            <p>Detector output is decision support; a staff member must verify each incident.</p>
            <StaffAccess onUserChange={onUserChange} />
            {error && <p className="form-error" role="alert">{error}</p>}
            <div className="alerts-grid">
                {!user ? (
                    <p className="no-data">Sign in to review incidents.</p>
                ) : alerts.length === 0 ? (
                    <p className="no-data">No alerts detected yet.</p>
                ) : (
                    alerts.map(alert => (
                        <AlertCard
                            key={alert.id}
                            alert={alert}
                            onConfirm={(id) => handleVerification(id, 'confirmed')}
                            onDismiss={(id) => handleVerification(id, 'dismissed')}
                        />
                    ))
                )}
            </div>
        </div>
    );
};

export default Alerts;
