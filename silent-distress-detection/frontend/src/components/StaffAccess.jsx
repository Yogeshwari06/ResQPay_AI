import React, { useEffect, useState } from 'react';

const hasFirebaseConfig = Boolean(
    process.env.REACT_APP_FIREBASE_API_KEY &&
    process.env.REACT_APP_FIREBASE_AUTH_DOMAIN &&
    process.env.REACT_APP_FIREBASE_PROJECT_ID &&
    process.env.REACT_APP_FIREBASE_APP_ID
);

export default function StaffAccess({ onUserChange }) {
    const [user, setUser] = useState(null);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [firebaseAuth, setFirebaseAuth] = useState(null);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isSigningOut, setIsSigningOut] = useState(false);

    useEffect(() => {
        if (!hasFirebaseConfig) {
            setError('Firebase sign-in is not configured. Add the REACT_APP_FIREBASE_* values from your Firebase project to frontend/.env, then restart the frontend.');
            return undefined;
        }

        let unsubscribe;
        let isMounted = true;
        import('../services/firebase')
            .then(({ auth }) => {
                if (!isMounted) return;
                setFirebaseAuth(auth);
                import('firebase/auth').then(({ onAuthStateChanged }) => {
                    if (!isMounted) return;
                    unsubscribe = onAuthStateChanged(auth, (activeUser) => {
                        setUser(activeUser);
                        onUserChange?.(activeUser);
                    });
                }).catch((authError) => {
                    if (isMounted) setError(authError.message);
                });
            })
            .catch((authError) => {
                if (isMounted) setError(authError.message);
            });

        return () => {
            isMounted = false;
            unsubscribe?.();
        };
    }, [onUserChange]);

    const signIn = async (event) => {
        event.preventDefault();
        setError('');
        setIsSubmitting(true);
        try {
            const { signInWithEmailAndPassword } = await import('firebase/auth');
            await signInWithEmailAndPassword(firebaseAuth, email.trim(), password);
        } catch (authError) {
            const messages = {
                'auth/invalid-email': 'Enter a valid email address.',
                'auth/invalid-credential': 'Email or password is incorrect, or this account is not registered.',
                'auth/user-not-found': 'No Firebase account exists for this email.',
                'auth/wrong-password': 'The password is incorrect.',
                'auth/too-many-requests': 'Too many sign-in attempts. Wait a few minutes and try again.',
                'auth/network-request-failed': 'Could not reach Firebase Authentication. Check your internet connection.',
                'auth/operation-not-allowed': 'Email/password sign-in is disabled. Enable it in Firebase Console > Authentication > Sign-in method.',
            };
            setError(messages[authError.code] || authError.message || 'Firebase sign-in failed.');
        } finally {
            setIsSubmitting(false);
        }
    };

    const signOut = async () => {
        if (firebaseAuth) {
            setIsSigningOut(true);
            setError('');
            try {
                const { signOut: firebaseSignOut } = await import('firebase/auth');
                await firebaseSignOut(firebaseAuth);
            } catch (authError) {
                setError(authError.message || 'Could not sign out.');
            } finally {
                setIsSigningOut(false);
            }
        }
    };

    return (
        <section className="settings-card staff-access">
            {user ? (
                <>
                    <p>Signed in as <strong>{user.email}</strong></p>
                    <button className="btn btn-secondary" onClick={signOut} disabled={isSigningOut}>
                        {isSigningOut ? 'Signing out…' : 'Sign out'}
                    </button>
                </>
            ) : (
                <form onSubmit={signIn}>
                    <h2>Staff sign in</h2>
                    <div className="form-group">
                        <label htmlFor="staff-email">Email</label>
                        <input id="staff-email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
                    </div>
                    <div className="form-group">
                        <label htmlFor="staff-password">Password</label>
                        <input id="staff-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
                    </div>
                    <button className="btn btn-primary" type="submit" disabled={!firebaseAuth || isSubmitting}>
                        {isSubmitting ? 'Signing in…' : 'Sign in'}
                    </button>
                </form>
            )}
            {error && <p className="form-error" role="alert">{error}</p>}
        </section>
    );
}
