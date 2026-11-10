# Adapter: Firebase Auth and Cloud Firestore

Use this when the audit shows Firebase Auth and Firestore. Paths and field names below are examples. Take the real ones from the audit.

## Consent fields

Add to the existing user profile document. Do not create a new collection.

- `agreed_to_terms` (boolean)
- `agreed_to_terms_at` (server timestamp, `serverTimestamp()`)
- `terms_version` (string, from the legal config)

When you read the profile, treat a missing `agreed_to_terms` as `false`. Existing users then see the agreement modal once.

## Sign-in method

Read it from the signed in user: `user.providerData[].providerId`. Common values are `password` and `google.com`. Show a readable label.

## Security rules

Tighten only what is needed. Keep the app working.

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    function isOwner(uid) { return request.auth != null && request.auth.uid == uid; }

    // Profile document. Adjust the path to the real one.
    match /users/{uid} {
      allow read, create, update: if isOwner(uid);
      allow delete: if false;      // deletion only through the Admin SDK
    }

    // User owned data stored under the profile. Users may delete single items.
    match /users/{uid}/{collection}/{doc=**} {
      allow read, write: if isOwner(uid);
    }

    match /{document=**} { allow read, write: if false; }
  }
}
```

If data lives in top level collections with a user id field, use:

```
allow read, delete: if request.auth != null && resource.data.uid == request.auth.uid;
allow create: if request.auth != null && request.resource.data.uid == request.auth.uid;
allow update: if request.auth != null && resource.data.uid == request.auth.uid
              && request.resource.data.uid == request.auth.uid;
```

If the project has a rules file, edit it. If not, add `firestore.rules` and tell the user it needs deploying.

## Export

Read client side with the Firestore SDK. Read the profile and every collection in the data inventory for the current user. Exclude fields the user listed in `data.export_exclude_fields`.

## Server side deletion

Use the Firebase Admin SDK in a server function. Never delete the profile or the Auth record from the client.

1. Accept POST only. Read the Bearer token. Verify it with `admin.auth().verifyIdToken(token)` to get `uid`. Return 401 on failure.
2. Delete the profile document and every user owned collection from the data inventory. Use `admin.firestore().recursiveDelete(ref)` for documents with subcollections. For top level collections keyed by a user id field, query by that field and delete in batches with a bulk writer. A failure here is logged and does not stop step 3.
3. Delete the Auth user with `admin.auth().deleteUser(uid)`. Return 500 if this fails.
4. Return `{ success: true }`.

Credentials: store the service account JSON in a host environment variable. Parse it with `JSON.parse(process.env.<NAME>)`. Never commit it. Ask the user for the variable name and record it in the legal config.

The client calls the function with a fresh token: `await user.getIdToken(true)`. After success, clear local state and call `signOut(auth)`.
