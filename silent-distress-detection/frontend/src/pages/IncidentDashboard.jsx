import React, { useCallback, useEffect, useMemo, useState } from 'react';
import StaffAccess from '../components/StaffAccess';
import { apiRequest } from '../services/api';

const severityClass = (severity) => `severity-${(severity || 'low').toLowerCase()}`;

function formatTimestamp(value) {
    if (value === null || value === undefined) return 'Timestamp unavailable';
    const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    return Number.isNaN(date.getTime()) ? 'Timestamp unavailable' : date.toLocaleString();
}

function getEvidence(incident) {
    const details = incident.details || {};
    return ['face', 'posture', 'audio'].flatMap((modality) => {
        const signal = details[modality];
        if (!signal || typeof signal !== 'object') return [];
        const score = signal.score ?? signal.distress_score;
        const entries = [];
        if (score !== undefined && score !== null) {
            entries.push({
                label: modality,
                value: `Detector score ${Number(score).toFixed(2)}`,
            });
        }
        if (modality === 'face' && signal.impact_detected === true) {
            entries.push({ label: 'Physical impact', value: 'Impact heuristic triggered' });
        }
        if (signal.details && typeof signal.details === 'object') {
            Object.entries(signal.details).forEach(([key, value]) => {
                if (typeof value !== 'object') {
                    entries.push({ label: `${modality} ${key}`, value: String(value) });
                }
            });
        } else if (typeof signal.details === 'string') {
            entries.push({ label: `${modality} details`, value: signal.details });
        }
        return entries;
    });
}

export default function IncidentDashboard() {
    const [user, setUser] = useState(null);
    const [incidents, setIncidents] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [loading, setLoading] = useState(false);
    const [updatingId, setUpdatingId] = useState(null);
    const [error, setError] = useState('');
    const onUserChange = useCallback((activeUser) => setUser(activeUser), []);

    const loadIncidents = useCallback(async (showLoading = false) => {
        if (!user) {
            setIncidents([]);
            setSelectedId(null);
            return;
        }
        if (showLoading) setLoading(true);
        try {
            const result = await apiRequest('/api/incidents', {}, true);
            if (!Array.isArray(result)) {
                throw new Error('The incidents API returned an invalid response.');
            }
            setIncidents(result);
            setSelectedId((current) => (
                result.some((item) => item.id === current) ? current : result[0]?.id || null
            ));
            setError('');
        } catch (loadError) {
            setError(loadError.message || 'Could not load incidents.');
        } finally {
            if (showLoading) setLoading(false);
        }
    }, [user]);

    useEffect(() => {
        if (!user) {
            setIncidents([]);
            setSelectedId(null);
            setLoading(false);
            return undefined;
        }
        loadIncidents(true);
        const interval = setInterval(() => loadIncidents(false), 10000);
        return () => clearInterval(interval);
    }, [user, loadIncidents]);

    const summary = useMemo(() => ({
        total: incidents.length,
        pending: incidents.filter((incident) => (incident.status || 'pending') === 'pending').length,
        verified: incidents.filter((incident) => ['confirmed', 'resolved'].includes(incident.status)).length,
        critical: incidents.filter((incident) => incident.intelligence?.severity === 'CRITICAL').length,
    }), [incidents]);

    const selected = incidents.find((incident) => incident.id === selectedId);

    const updateStatus = async (incident, status) => {
        if (!incident?.id) return;
        setUpdatingId(incident.id);
        setError('');
        try {
            const updated = await apiRequest(
                `/api/incidents/${encodeURIComponent(incident.id)}/verification`,
                {
                    method: 'PATCH',
                    body: JSON.stringify({ status }),
                },
                true
            );
            setIncidents((current) => current.map((item) => (
                item.id === updated.id ? updated : item
            )));
        } catch (updateError) {
            setError(updateError.message || 'Could not update incident status.');
        } finally {
            setUpdatingId(null);
        }
    };

    return (
        <main className="page-container incident-dashboard">
            <header className="incident-page-header">
                <div>
                    <p className="eyebrow">ResQPay AI · Emergency operations</p>
                    <h1>Incident management</h1>
                    <p>Review detector assessments, verify incidents, and track their resolution.</p>
                </div>
                {user && (
                    <button className="btn btn-secondary" onClick={() => loadIncidents(true)} disabled={loading}>
                        {loading ? 'Refreshing…' : 'Refresh'}
                    </button>
                )}
            </header>

            <StaffAccess onUserChange={onUserChange} />

            {error && <div className="incident-error" role="alert">{error}</div>}

            {!user ? (
                <section className="incident-empty">
                    <h2>Sign in required</h2>
                    <p>Sign in with an authorized Firebase account to load and manage incidents.</p>
                </section>
            ) : loading ? (
                <section className="incident-empty" role="status" aria-live="polite">
                    <span className="loading-spinner" aria-hidden="true" />
                    <p>Loading incidents from the backend…</p>
                </section>
            ) : (
                <>
                    <section className="incident-summary" aria-label="Incident summary">
                        <article className="summary-card">
                            <span>Total incidents</span><strong>{summary.total}</strong>
                        </article>
                        <article className="summary-card summary-pending">
                            <span>Pending verification</span><strong>{summary.pending}</strong>
                        </article>
                        <article className="summary-card summary-verified">
                            <span>Verified incidents</span><strong>{summary.verified}</strong>
                        </article>
                        <article className="summary-card summary-critical">
                            <span>Critical incidents</span><strong>{summary.critical}</strong>
                        </article>
                    </section>

                    {incidents.length === 0 ? (
                        <section className="incident-empty">
                            <h2>No incidents found</h2>
                            <p>New incidents will appear here when the backend detection pipeline records them.</p>
                        </section>
                    ) : (
                        <div className="incident-workspace">
                            <section className="incident-list-panel">
                                <div className="incident-panel-heading">
                                    <h2>Incidents</h2>
                                    <span>{incidents.length} total</span>
                                </div>
                                <div className="incident-table-wrap">
                                    <table className="incident-table">
                                        <thead>
                                            <tr>
                                                <th>Incident ID</th>
                                                <th>Category</th>
                                                <th>Severity</th>
                                                <th>Detected</th>
                                                <th>Status</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {incidents.map((incident) => {
                                                const assessment = incident.intelligence || {};
                                                const status = incident.status || 'pending';
                                                return (
                                                    <tr
                                                        key={incident.id}
                                                        className={incident.id === selectedId ? 'incident-row-selected' : ''}
                                                        onClick={() => setSelectedId(incident.id)}
                                                        onKeyDown={(event) => {
                                                            if (event.key === 'Enter' || event.key === ' ') {
                                                                event.preventDefault();
                                                                setSelectedId(incident.id);
                                                            }
                                                        }}
                                                        tabIndex={0}
                                                        aria-selected={incident.id === selectedId}
                                                    >
                                                        <td data-label="Incident ID"><span className="incident-id">{incident.id}</span></td>
                                                        <td data-label="Category">{assessment.category || 'Uncertain / requires human review'}</td>
                                                        <td data-label="Severity">
                                                            <span className={`severity-badge ${severityClass(assessment.severity)}`}>
                                                                {assessment.severity || 'LOW'}
                                                            </span>
                                                        </td>
                                                        <td data-label="Detected">{formatTimestamp(assessment.timestamp || incident.timestamp)}</td>
                                                        <td data-label="Status"><span className={`incident-status status-${status}`}>{status}</span></td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </section>

                            {selected && (
                                <aside className="incident-detail-panel" aria-label="Incident details">
                                    <div className="incident-panel-heading">
                                        <div>
                                            <p className="eyebrow">Incident details</p>
                                            <h2>{selected.id}</h2>
                                        </div>
                                        <span className={`severity-badge ${severityClass(selected.intelligence?.severity)}`}>
                                            {selected.intelligence?.severity || 'LOW'}
                                        </span>
                                    </div>
                                    <dl className="incident-detail-list">
                                        <div>
                                            <dt>Category</dt>
                                            <dd>{selected.intelligence?.category || 'Uncertain / requires human review'}</dd>
                                        </div>
                                        <div>
                                            <dt>Detected</dt>
                                            <dd>{formatTimestamp(selected.intelligence?.timestamp || selected.timestamp)}</dd>
                                        </div>
                                        <div>
                                            <dt>Current status</dt>
                                            <dd><span className={`incident-status status-${selected.status || 'pending'}`}>{selected.status || 'pending'}</span></dd>
                                        </div>
                                        {selected.location && (
                                            <div><dt>Location</dt><dd>{selected.location}</dd></div>
                                        )}
                                        {selected.intelligence?.confidence !== undefined && (
                                            <div><dt>Model confidence</dt><dd>{(selected.intelligence.confidence * 100).toFixed(1)}%</dd></div>
                                        )}
                                        {selected.intelligence?.detector_score !== undefined && (
                                            <div><dt>Fusion detector score</dt><dd>{Number(selected.intelligence.detector_score).toFixed(2)}</dd></div>
                                        )}
                                    </dl>
                                    <section className="incident-assessment">
                                        <h3>AI assessment</h3>
                                        <p>{selected.intelligence?.explanation || 'No assessment is available for this incident.'}</p>
                                        <h3>Recommended response</h3>
                                        <p>{selected.intelligence?.recommended_response || 'Have a staff member review the incident.'}</p>
                                        <p className="human-review-note">Decision support only · Human verification required · No automatic response</p>
                                    </section>

                                    <section className="incident-evidence">
                                        <h3>Available detection evidence</h3>
                                        {getEvidence(selected).length > 0 ? (
                                            <ul>
                                                {getEvidence(selected).map((item, index) => (
                                                    <li key={`${item.label}-${index}`}>
                                                        <strong>{item.label}</strong><span>{item.value}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        ) : (
                                            <p>No individual sensor evidence was saved with this incident.</p>
                                        )}
                                    </section>

                                    <div className="incident-admin-actions">
                                        <h3>Admin actions</h3>
                                        {selected.status === 'resolved' || selected.status === 'dismissed' ? (
                                            <p>This incident is {selected.status}.</p>
                                        ) : (
                                            <div className="incident-action-buttons">
                                                {selected.status !== 'confirmed' && (
                                                    <button
                                                        className="btn btn-primary"
                                                        onClick={() => updateStatus(selected, 'confirmed')}
                                                        disabled={updatingId === selected.id}
                                                    >
                                                        Verify incident
                                                    </button>
                                                )}
                                                <button
                                                    className="btn btn-secondary"
                                                    onClick={() => updateStatus(selected, 'dismissed')}
                                                    disabled={updatingId === selected.id}
                                                >
                                                    Reject false alert
                                                </button>
                                                {selected.status === 'confirmed' && (
                                                    <button
                                                        className="btn btn-success"
                                                        onClick={() => updateStatus(selected, 'resolved')}
                                                        disabled={updatingId === selected.id}
                                                    >
                                                        Mark as resolved
                                                    </button>
                                                )}
                                            </div>
                                        )}
                                        {updatingId === selected.id && <p role="status">Saving incident status…</p>}
                                    </div>
                                </aside>
                            )}
                        </div>
                    )}
                </>
            )}
        </main>
    );
}
