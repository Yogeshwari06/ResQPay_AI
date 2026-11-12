import React, { useState, useEffect, useCallback } from 'react';
import StatusBadge from '../components/StatusBadge';
import { getSystemStatus, getVideoFeedUrl, startMonitoring, stopMonitoring } from '../services/api';

const Dashboard = () => {
    const [status, setStatus] = useState({
        is_running: false,
        camera_status: 'Idle',
        active_alerts_count: 0,
        last_alert: null,
        camera_error: null
    });
    const [isStarting, setIsStarting] = useState(false);
    const [isStopping, setIsStopping] = useState(false);
    const [systemError, setSystemError] = useState('');
    const [streamError, setStreamError] = useState('');

    // State for Emergency Popup
    const [showPopup, setShowPopup] = useState(false);
    const [popupData, setPopupData] = useState(null);
    const [lastProcessedAlertTime, setLastProcessedAlertTime] = useState(0);

    const fetchStatus = useCallback(async () => {
        try {
            const data = await getSystemStatus();
            setStatus(data);
            setSystemError('');

            // Checks for Critical Alert
            if (data.last_alert && data.last_alert.time > lastProcessedAlertTime) {
                // User Requirement: Start Popup ONLY if confidence is 100% (or Impact Triggered which sets it to 1.0)
                const isCritical = data.last_alert.score >= 0.99 ||
                    (data.last_alert.details && data.last_alert.details.trigger === "IMPACT_DETECTED");

                if (isCritical) {
                    setPopupData(data.last_alert);
                    setShowPopup(true);
                    setLastProcessedAlertTime(data.last_alert.time);
                }
            }
        } catch (error) {
            setSystemError(error.message);
        }
    }, [lastProcessedAlertTime]);

    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 1000); // Faster polling for alerts
        return () => clearInterval(interval);
    }, [fetchStatus]);

    const handleStart = async () => {
        setIsStarting(true);
        setSystemError('');
        setStreamError('');
        try {
            await startMonitoring();
            await fetchStatus();
        } catch (error) {
            setSystemError(error.message);
            await fetchStatus();
        } finally {
            setIsStarting(false);
        }
    };

    const handleStop = async () => {
        setIsStopping(true);
        setSystemError('');
        try {
            await stopMonitoring();
            await fetchStatus();
        } catch (error) {
            setSystemError(error.message);
        } finally {
            setIsStopping(false);
        }
    };

    const closePopup = () => setShowPopup(false);

    return (
        <div className="page-container">
            {/* EMERGENCY POPUP MODAL */}
            {showPopup && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, width: '100%', height: '100%',
                    backgroundColor: 'rgba(255,0,0,0.5)', zIndex: 9999,
                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}>
                    <div style={{
                        background: '#fff', padding: '40px', borderRadius: '12px',
                        boxShadow: '0 0 50px rgba(255,0,0,0.8)',
                        textAlign: 'center', maxWidth: '500px', border: '5px solid red',
                        animation: 'pulse 1s infinite'
                    }}>
                        <h1 style={{ color: 'red', fontSize: '3rem', margin: 0 }}>⚠️ WARNING ⚠️</h1>
                        <h2 style={{ fontSize: '2rem' }}>PHYSICAL IMPACT DETECTED</h2>
                        <p style={{ fontSize: '1.2rem', margin: '20px 0' }}>
                            High confidence distress signal received.<br />
                            <strong>Confidence: {popupData ? (popupData.score * 100).toFixed(1) : 0}%</strong>
                        </p>
                        <button
                            className="btn btn-danger btn-lg"
                            style={{ fontSize: '1.5rem', padding: '15px 40px' }}
                            onClick={closePopup}
                        >
                            ACKNOWLEDGE
                        </button>
                    </div>
                    <style>
                        {`@keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }`}
                    </style>
                </div>
            )}

            <h1>ResQPay AI Dashboard</h1>

            <div className="status-panel">
                <div className="status-item">
                    <h3>System State</h3>
                    <StatusBadge status={
                        status.is_running
                            ? "Active"
                            : ["Connecting", "Stopping", "Error"].includes(status.camera_status)
                                ? status.camera_status
                                : "Idle"
                    } />
                </div>
                <div className="status-item">
                    <h3>Camera</h3>
                    <StatusBadge status={status.camera_status} />
                    {status.camera_error && <p className="form-error">{status.camera_error}</p>}
                </div>
                <div className="status-item">
                    <h3>Active Alerts</h3>
                    <span className="count-badge">{status.active_alerts_count}</span>
                    {status.last_alert && (
                        <p className="latest-alert">
                            Latest detection: {Math.round(Number(status.last_alert.score || 0) * 100)}%
                            {status.last_alert.details?.trigger
                                ? ` · ${status.last_alert.details.trigger.replace(/_/g, ' ')}`
                                : ''}
                        </p>
                    )}
                </div>
            </div>

            {systemError && <p className="form-error" role="alert">{systemError}</p>}
            <div className="control-panel">
                <div className="video-feed-container">
                    {status.is_running && !streamError ? (
                        <img
                            src={getVideoFeedUrl()}
                            alt="Live camera feed"
                            onLoad={() => setStreamError('')}
                            onError={() => setStreamError('The camera is active but the live video stream could not be loaded.')}
                        />
                    ) : isStarting || status.camera_status === 'Connecting' ? (
                        <p className="camera-message" role="status">Connecting to camera…</p>
                    ) : streamError ? (
                        <p className="form-error camera-message" role="alert">{streamError}</p>
                    ) : status.camera_error ? (
                        <p className="form-error camera-message" role="alert">{status.camera_error}</p>
                    ) : (
                        <p className="camera-message">Camera is idle. Start monitoring to connect to the available camera.</p>
                    )}
                </div>

                {status.camera_status === 'Connecting' ? (
                    <button className="btn btn-danger btn-lg" onClick={handleStop} disabled={isStarting || isStopping}>
                        {isStarting ? 'Connecting…' : isStopping ? 'Cancelling…' : 'Cancel Connection'}
                    </button>
                ) : status.is_running || status.camera_status === 'Stopping' ? (
                    <button className="btn btn-danger btn-lg" onClick={handleStop} disabled={isStopping || status.camera_status === 'Stopping'}>
                        {isStopping || status.camera_status === 'Stopping' ? 'Stopping…' : 'Stop Monitoring'}
                    </button>
                ) : (
                    <button className="btn btn-primary btn-lg" onClick={handleStart} disabled={isStarting}>
                        {isStarting ? 'Starting…' : 'Start Monitoring'}
                    </button>
                )}
            </div>
        </div>
    );
};

export default Dashboard;
