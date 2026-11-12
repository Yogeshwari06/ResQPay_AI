const isLocalDevelopment =
    typeof window !== 'undefined' &&
    ['localhost', '127.0.0.1'].includes(window.location.hostname);

export const API_URL = process.env.REACT_APP_API_URL || (
    isLocalDevelopment
        ? 'http://localhost:8000'
        : 'https://silent-distress-detection.onrender.com'
);

async function fetchJson(path, options = {}) {
    let response;
    try {
        response = await fetch(`${API_URL}${path}`, options);
    } catch (error) {
        if (error instanceof TypeError) {
            throw new Error(
                `Cannot reach the ResQPay backend at ${API_URL}. Start the FastAPI backend and try again.`
            );
        }
        throw error;
    }

    const result = await response.json().catch(() => null);
    if (!response.ok) {
        throw new Error(result?.detail || `Request failed (${response.status}).`);
    }
    return result;
}

export async function apiRequest(path, options = {}, authenticated = false) {
    const requestOptions = { ...options };
    const headers = { ...(requestOptions.headers || {}) };
    delete requestOptions.headers;

    if (requestOptions.body && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    if (authenticated) {
        const { auth } = await import("./firebase");
        const user = auth.currentUser;
        if (!user) {
            throw new Error("Sign in with Firebase before continuing.");
        }
        headers.Authorization = `Bearer ${await user.getIdToken()}`;
    }

    return fetchJson(path, {
        ...requestOptions,
        headers,
    });
}

export const getVideoFeedUrl = () => `${API_URL}/video_feed`;

export const getSystemStatus = () => fetchJson('/status');

export const startMonitoring = () => fetchJson('/start', { method: 'POST' });

export const stopMonitoring = () => fetchJson('/stop', { method: 'POST' });
