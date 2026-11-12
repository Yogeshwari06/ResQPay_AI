import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import StaffAccess from '../components/StaffAccess';
import { apiRequest } from '../services/api';

export default function Donations() {
    const [searchParams] = useSearchParams();
    const [user, setUser] = useState(null);
    const [campaigns, setCampaigns] = useState([]);
    const [campaignId, setCampaignId] = useState(searchParams.get('campaign') || '');
    const [amount, setAmount] = useState('');
    const [transactions, setTransactions] = useState([]);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    const handledOrder = useRef('');
    const onUserChange = useCallback((activeUser) => setUser(activeUser), []);

    const loadTransactions = useCallback(async () => {
        if (!user) {
            setTransactions([]);
            return;
        }
        try {
            setTransactions(await apiRequest('/api/transactions', {}, true));
        } catch (historyError) {
            setError(historyError.message);
        }
    }, [user]);

    useEffect(() => {
        apiRequest('/api/campaigns')
            .then((items) => {
                const acceptingDonations = items.filter(
                    (campaign) => campaign.status === 'APPROVED' && campaign.remaining_amount > 0
                );
                setCampaigns(acceptingDonations);
                if (!campaignId && acceptingDonations.length) {
                    setCampaignId(acceptingDonations[0].campaign_id || acceptingDonations[0].id);
                }
            })
            .catch((campaignError) => setError(campaignError.message));
    }, []);

    useEffect(() => {
        loadTransactions();
    }, [loadTransactions]);

    useEffect(() => {
        const orderId = searchParams.get('token');
        const wasCancelled = searchParams.get('cancelled') === '1';
        if (!orderId || !user || handledOrder.current === `${wasCancelled}:${orderId}`) return;
        handledOrder.current = `${wasCancelled}:${orderId}`;
        setBusy(true);
        setError('');
        if (wasCancelled) {
            apiRequest('/api/donations/cancel', {
                method: 'POST',
                body: JSON.stringify({ order_id: orderId }),
            }, true)
                .then(() => {
                    setMessage('PayPal checkout was cancelled. No donation was recorded.');
                    window.history.replaceState({}, '', '/donations?cancelled=1');
                    return loadTransactions();
                })
                .catch((cancelError) => {
                    setError(cancelError.message);
                    handledOrder.current = '';
                })
                .finally(() => setBusy(false));
            return;
        }

        apiRequest('/api/donations/capture', {
            method: 'POST',
            body: JSON.stringify({ order_id: orderId }),
        }, true)
            .then(() => {
                setMessage('Donation completed and confirmed by PayPal Sandbox.');
                window.history.replaceState({}, '', '/donations');
                return Promise.all([
                    loadTransactions(),
                    apiRequest('/api/campaigns').then(setCampaigns),
                ]);
            })
            .catch((captureError) => {
                setError(captureError.message);
                handledOrder.current = '';
            })
            .finally(() => setBusy(false));
    }, [loadTransactions, searchParams, user]);

    const createOrder = async (event) => {
        event.preventDefault();
        setBusy(true);
        setError('');
        setMessage('');
        try {
            const order = await apiRequest('/api/donations/create-order', {
                method: 'POST',
                body: JSON.stringify({
                    campaign_id: campaignId,
                    amount: Number(amount),
                }),
            }, true);
            window.location.assign(order.approval_url);
        } catch (orderError) {
            setError(orderError.message);
            setBusy(false);
        }
    };

    return (
        <div className="page-container">
            <h1>Donations and transactions</h1>
            <p>Payments are processed by PayPal Sandbox. Sign in to donate and view your transaction history.</p>
            <StaffAccess onUserChange={onUserChange} />
            {message && <p className="form-success" role="status">{message}</p>}
            {error && <p className="form-error" role="alert">{error}</p>}
            {searchParams.get('cancelled') && !searchParams.get('token') && <p className="no-data">PayPal checkout was cancelled; no donation will be recorded.</p>}

            <section className="campaign-section">
                <h2>Make a donation</h2>
                <form className="settings-card" onSubmit={createOrder}>
                    <div className="form-group">
                        <label htmlFor="donation-campaign">Approved campaign</label>
                        <select id="donation-campaign" value={campaignId} onChange={(event) => setCampaignId(event.target.value)} required>
                            <option value="" disabled>Select a campaign</option>
                            {campaigns.map((campaign) => (
                                <option value={campaign.campaign_id || campaign.id} key={campaign.campaign_id || campaign.id}>
                                    {campaign.title} — {campaign.funding_progress_percentage}% funded
                                </option>
                            ))}
                        </select>
                    </div>
                    {campaigns.find((campaign) => (campaign.campaign_id || campaign.id) === campaignId) && (
                        <div className="campaign-funding">
                            <div className="campaign-funding-values">
                                <span>Raised <strong>${Number(campaigns.find((campaign) => (campaign.campaign_id || campaign.id) === campaignId).current_funding_amount).toFixed(2)}</strong></span>
                                <span>Remaining <strong>${Number(campaigns.find((campaign) => (campaign.campaign_id || campaign.id) === campaignId).remaining_amount).toFixed(2)}</strong></span>
                            </div>
                            <div
                                className="campaign-progress-track"
                                role="progressbar"
                                aria-label="Campaign funding progress"
                                aria-valuemin="0"
                                aria-valuemax="100"
                                aria-valuenow={campaigns.find((campaign) => (campaign.campaign_id || campaign.id) === campaignId).funding_progress_percentage}
                            >
                                <span style={{ width: `${campaigns.find((campaign) => (campaign.campaign_id || campaign.id) === campaignId).funding_progress_percentage}%` }} />
                            </div>
                        </div>
                    )}
                    <div className="form-group">
                        <label htmlFor="donation-amount">Donation amount (USD)</label>
                        <input
                            id="donation-amount"
                            type="number"
                            min="0.01"
                            max={Math.min(10000000, campaigns.find((campaign) => (campaign.campaign_id || campaign.id) === campaignId)?.remaining_amount || 0)}
                            step="0.01"
                            value={amount}
                            onChange={(event) => setAmount(event.target.value)}
                            required
                        />
                    </div>
                    <button className="btn btn-primary" type="submit" disabled={!user || !campaignId || busy}>
                        {busy ? 'Processing…' : 'Continue to PayPal Sandbox'}
                    </button>
                    {!user && <small className="form-hint">Sign in above to donate.</small>}
                    {campaigns.length === 0 && <small className="form-hint">No approved campaigns are currently accepting donations.</small>}
                </form>
            </section>

            <section className="campaign-section">
                <h2>Transaction history</h2>
                {!user ? (
                    <p className="no-data">Sign in to view your transactions.</p>
                ) : transactions.length === 0 ? (
                    <p className="no-data">No completed donations yet.</p>
                ) : (
                    <div className="table-scroll">
                        <table className="data-table">
                            <thead><tr><th>Date</th><th>Campaign</th><th>Amount</th><th>Status</th><th>PayPal capture</th></tr></thead>
                            <tbody>
                                {transactions.map((transaction) => (
                                    <tr key={transaction.id}>
                                        <td>{new Date(transaction.created_at * 1000).toLocaleString()}</td>
                                        <td>{campaigns.find((item) => item.id === transaction.campaign_id)?.title || transaction.campaign_id}</td>
                                        <td>{transaction.currency} {Number(transaction.amount).toFixed(2)}</td>
                                        <td>{transaction.payment_status || transaction.status}</td>
                                        <td>{transaction.transaction_id || 'Not captured'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </section>
        </div>
    );
}
