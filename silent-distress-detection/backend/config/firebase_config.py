import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from dotenv import load_dotenv
import os
import time

load_dotenv()

# Check for service account key
# You should place your 'serviceAccountKey.json' in the root or backend folder
cred_path = os.getenv("FIREBASE_CREDENTIALS", "serviceAccountKey.json")

class MockDocumentSnapshot:
    def __init__(self, data, doc_id, exists=True):
        self._data = data
        self.id = doc_id
        self.exists = exists
    
    def to_dict(self):
        return self._data.copy()


class MockDocumentReference:
    def __init__(self, collection, doc_id):
        self._collection = collection
        self.id = doc_id

    def get(self):
        for document in self._collection._docs:
            if document.id == self.id:
                return document
        return MockDocumentSnapshot({}, self.id, exists=False)

    def update(self, data):
        for document in self._collection._docs:
            if document.id == self.id:
                document._data.update(data)
                return None
        raise KeyError(f"Document {self.id} does not exist.")

    def set(self, data):
        for document in self._collection._docs:
            if document.id == self.id:
                document._data = data.copy()
                return None
        self._collection._docs.append(
            MockDocumentSnapshot(data.copy(), self.id)
        )
        return None

class MockCollectionReference:
    def __init__(self, name):
        self.name = name
        self._docs = [] # In-memory store for the session
    
    def add(self, data):
        # Mock add
        doc_id = f"mock_id_{len(self._docs) + 1}"
        print(f"[MOCK FIRESTORE] Added to {self.name}: {data}")
        self._docs.append(MockDocumentSnapshot(data, doc_id))
        return (None, MockDocumentReference(self, doc_id))

    def document(self, doc_id):
        return MockDocumentReference(self, doc_id)

    def stream(self):
        # Return what we have stored in memory
        return self._docs

class MockFirestore:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = MockCollectionReference(name)
        return self._collections[name]

try:
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("[FIREBASE] Initialized successfully.")
    else:
        raise FileNotFoundError(f"Credential file {cred_path} not found.")
except Exception as e:
    print(f"[FIREBASE] Warning: Could not initialize Firebase ({e}). Using Mock Firestore.")
    db = MockFirestore()
