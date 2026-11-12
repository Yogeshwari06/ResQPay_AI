import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import StaffAccess from '../components/StaffAccess';
import { apiRequest } from '../services/api';

const money = (amount) => `$${Number(amount || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
})}`;

function CampaignFunding({ campaign }) {
    const progress = Math.min(Number(campaign.funding_progress_percentage || 0), 100);
    return (
        <div className="campaign-funding">
            <div className="campaign-funding-values">
                <span>Raised <strong>{money(campaign.current_funding_amount)}</strong></span>
                <span>Goal <strong>{money(campaign.target_funding_amount)}</strong></span>
            </div>
            <div
                className="campaign-progress-track"
                role="progressbar"
                aria-label="Campaign funding progress"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={progress}
            >
                <span style={{ width: `${progress}%` }} />
            </div>
            <div className="campaign-funding-values">
                <span>{progress.toFixed(1)}% funded</span>
                <span>{money(campaign.remaining_amount)} remaining</span>
            </div>
        </div>
    );
}

export default function Campaigns() {
    const [user, setUser] = useState(null);
    const [campaigns, setCampaigns] = useState([]);
    const [adminCampaigns, setAdminCampaigns] = useState([]);
    const [verifiedIncidents, setVerifiedIncidents] = useState([]);
    const [isAdmin, setIsAdmin] = useState(false);
    const [loading, setLoading] = useState(true);
    const [submitting, setSubmitting] = useState(false);
    const [incidentId, setIncidentId] = useState('');
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [emergencyCategory, setEmergencyCategory] = useState('');
    const [location, setLocation] = useState('');
    const [targetAmount, setTargetAmount] = useState('');
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const onUserChange = useCallback((activeUser) => setUser(activeUser), []);

    const loadCampaigns = useCallback(async (showLoading = false) => {
        if (showLoading) setLoading(true);
        try {
            const approved = await apiRequest('/api/campaigns');
            setCampaigns(Array.isArray(approved) ? approved : []);
            if (user) {
                try {
                    const [allCampaigns, incidents] = await Promise.all([
                        apiRequest('/api/admin/campaigns', {}, true),
                        apiRequest('/api/incidents', {}, true),
                    ]);
                    setAdminCampaigns(allCampaigns);
                    setVerifiedIncidents(incidents.filter((incident) => incident.status === 'confirmed'));
                    setIsAdmin(true);
                } catch (adminError) {
                    if (adminError.message.includes('Administrator access required')) {
                        setAdminCampaigns([]);
                        setVerifiedIncidents([]);
                        setIsAdmin(false);
                    } else {
                        throw adminError;
                    }
                }
            } else {
                setAdminCampaigns([]);
                setVerifiedIncidents([]);
                setIsAdmin(false);
            }
            setError('');
        } catch (loadError) {
            setError(loadError.message);
        } finally {
            if (showLoading) setLoading(false);
        }
    }, [user]);

    useEffect(() => {
        loadCampaigns(true);
    }, [loadCampaigns]);

    const submitCampaign = async (event) => {
        event.preventDefault();
        setSubmitting(true);
        setMessage('');
        setError('');
        try {
            const draft = await apiRequest('/api/campaigns', {
                method: 'POST',
                body: JSON.stringify({
                    incident_id: incidentId,
                    title,
                    description,
                    emergency_category: emergencyCategory,
                    location,
                    target_funding_amount: Number(targetAmount),
                    currency: 'USD',
                }),
            }, true);
            await apiRequest(`/api/campaigns/${encodeURIComponent(draft.id)}/submit`, {
                method: 'POST',
            }, true);
            setIncidentId('');
            setTitle('');
            setDescription('');
            setEmergencyCategory('');
            setLocation('');
            setTargetAmount('');
            setMessage('Campaign submitted for administrator approval.');
            await loadCampaigns();
        } catch (submitError) {
            setError(submitError.message);
        } finally {
            setSubmitting(false);
        }
    };

    const submitForApproval = async (campaignId) => {
        setError('');
        try {
            await apiRequest(`/api/campaigns/${encodeURIComponent(campaignId)}/submit`, {
                method: 'POST',
            }, true);
            await loadCampaigns();
        } catch (submitError) {
            setError(submitError.message);
        }
    };

    const reviewCampaign = async (campaignId, approved) => {
        setError('');
        try {
            await apiRequest(
                `/api/campaigns/${encodeURIComponent(campaignId)}/approval?approved=${approved}`,
                { method: 'PATCH' },
                true
            );
            await loadCampaigns();
        } catch (reviewError) {
            setError(reviewError.message);
        }
    };

    return (
        <div className="page-container">
            <header className="incident-page-header">
                <div>
                    <p className="eyebrow">ResQPay AI · Verified emergency relief</p>
                    <h1>Relief campaigns</h1>
                    <p>Campaigns are linked to human-verified incidents and require approval before accepting donations.</p>
                </div>
                <button className="btn btn-secondary" onClick={() => loadCampaigns(true)} disabled={loading}>
                    {loading ? 'Loading…' : 'Refresh'}
                </button>
            </header>
            <StaffAccess onUserChange={onUserChange} />
            {message && <p className="form-success" role="status">{message}</p>}
            {error && <p className="form-error" role="alert">{error}</p>}

            <section className="campaign-section">
                <h2>Active and completed campaigns</h2>
                {loading ? (
                    <p role="status">Loading campaigns…</p>
                ) : campaigns.length === 0 ? (
                    <p className="no-data">No approved relief campaigns are available.</p>
                ) : (
                    <div className="campaign-grid">
                        {campaigns.map((campaign) => (
                            <article className="campaign-card" key={campaign.campaign_id || campaign.id}>
                                <div className="alert-header">
                                    <h3>{campaign.title}</h3>
                                    <span className={`campaign-status campaign-status-${campaign.status?.toLowerCase()}`}>{campaign.status}</span>
                                </div>
                                {campaign.is_demo && <span className="demo-label">DEMO CAMPAIGN</span>}
                                <p>{campaign.description}</p>
                                <p><strong>Category:</strong> {campaign.emergency_category}</p>
                                <p><strong>Location:</strong> {campaign.location}</p>
                                <CampaignFunding campaign={campaign} />
                                {campaign.status === 'APPROVED' && campaign.remaining_amount > 0 ? (
                                    <Link className="btn btn-primary" to={`/donations?campaign=${encodeURIComponent(campaign.campaign_id || campaign.id)}`}>
                                        Donate
                                    </Link>
                                ) : (
                                    <p className="campaign-closed">
                                        {campaign.status === 'COMPLETED' ? 'Funding goal reached.' : 'Donations are closed.'}
                                    </p>
                                )}
                            </article>
                        ))}
                    </div>
                )}
            </section>

            {isAdmin && (
                <>
                    <section className="campaign-section">
                        <h2>Create a campaign for a verified emergency</h2>
                        {verifiedIncidents.length === 0 ? (
                            <p className="no-data">No confirmed incidents are available. Verify an incident before creating its campaign.</p>
                        ) : (
                            <form className="settings-card campaign-form" onSubmit={submitCampaign}>
                                <div className="form-group">
                                    <label htmlFor="campaign-incident">Verified incident</label>
                                    <select id="campaign-incident" value={incidentId} onChange={(event) => setIncidentId(event.target.value)} required>
                                        <option value="" disabled>Select a confirmed incident</option>
                                        {verifiedIncidents.map((incident) => (
                                            <option key={incident.id} value={incident.id}>
                                                {incident.id} · {incident.intelligence?.category || 'Uncertain'} · {incident.location || 'Location unavailable'}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label htmlFor="campaign-title">Title</label>
                                    <input id="campaign-title" value={title} onChange={(event) => setTitle(event.target.value)} minLength="3" maxLength="120" required />
                                </div>
                                <div className="form-group">
                                    <label htmlFor="campaign-description">Description</label>
                                    <textarea id="campaign-description" rows="4" value={description} onChange={(event) => setDescription(event.target.value)} minLength="10" maxLength="2000" required />
                                </div>
                                <div className="form-group">
                                    <label htmlFor="campaign-category">Emergency category</label>
                                    <input id="campaign-category" value={emergencyCategory} onChange={(event) => setEmergencyCategory(event.target.value)} minLength="3" maxLength="80" placeholder="e.g. Flood recovery" required />
                                </div>
                                <div className="form-group">
                                    <label htmlFor="campaign-location">Location</label>
                                    <input id="campaign-location" value={location} onChange={(event) => setLocation(event.target.value)} minLength="2" maxLength="200" required />
                                </div>
                                <div className="form-group">
                                    <label htmlFor="campaign-target">Target funding amount (USD)</label>
                                    <input id="campaign-target" type="number" min="0.01" max="10000000" step="0.01" value={targetAmount} onChange={(event) => setTargetAmount(event.target.value)} required />
                                </div>
                                <button className="btn btn-primary" type="submit" disabled={submitting}>
                                    {submitting ? 'Submitting…' : 'Create and submit for approval'}
                                </button>
                                <small className="form-hint">Creates a DRAFT and submits it for administrator approval. No campaign is generated automatically from detector output.</small>
                            </form>
                        )}
                    </section>

                    <section className="campaign-section">
                        <h2>Administrator campaign review</h2>
                        {adminCampaigns.length === 0 ? (
                            <p className="no-data">No campaigns are awaiting review.</p>
                        ) : (
                            <div className="campaign-grid">
                                {adminCampaigns.map((campaign) => (
                                    <article className="campaign-card" key={campaign.campaign_id || campaign.id}>
                                        <div className="alert-header">
                                            <h3>{campaign.title}</h3>
                                            <span className={`campaign-status campaign-status-${campaign.status?.toLowerCase()}`}>{campaign.status}</span>
                                        </div>
                                        {campaign.is_demo && <span className="demo-label">DEMO CAMPAIGN</span>}
                                        <p>{campaign.description}</p>
                                        <p><strong>Emergency:</strong> {campaign.emergency_category} · {campaign.location}</p>
                                        <p><strong>Verified incident:</strong> {campaign.incident_id}</p>
                                        <CampaignFunding campaign={campaign} />
                                        {campaign.status === 'DRAFT' && (
                                            <button className="btn btn-secondary" onClick={() => submitForApproval(campaign.id)}>Submit for approval</button>
                                        )}
                                        {campaign.status === 'PENDING_APPROVAL' && (
                                            <div className="alert-actions">
                                                <button className="btn btn-primary" onClick={() => reviewCampaign(campaign.id, true)}>Approve</button>
                                                <button className="btn btn-secondary" onClick={() => reviewCampaign(campaign.id, false)}>Reject</button>
                                            </div>
                                        )}
                                    </article>
                                ))}
                            </div>
                        )}
                    </section>
                </>
            )}
            {user && !isAdmin && <p className="form-hint">Administrator access is required to create, submit, or review campaigns.</p>}
        </div>
    );
}
