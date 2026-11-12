import { getApp, getApps, initializeApp } from 'firebase/app'
import { getFirestore, collection, query, orderBy, onSnapshot, doc, updateDoc } from 'firebase/firestore'
import { getAuth, signInWithEmailAndPassword, onAuthStateChanged } from 'firebase/auth'

const firebaseConfig = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.REACT_APP_FIREBASE_APP_ID
}

const app = getApps().length ? getApp() : initializeApp(firebaseConfig)
export const db = getFirestore(app)
export const auth = getAuth(app)

export function listenAlerts(onChange){
  const q = query(collection(db, 'alerts'), orderBy('timestamp', 'desc'))
  return onSnapshot(q, (snapshot) => {
    const list = snapshot.docs.map(d => ({ id: d.id, ...d.data() }))
    onChange(list)
  })
}

export async function updateAlertStatus(id, status, reviewer){
  const ref = doc(db, 'alerts', id)
  await updateDoc(ref, { status, reviewer })
}
