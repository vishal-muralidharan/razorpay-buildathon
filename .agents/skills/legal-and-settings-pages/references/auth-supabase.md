# Adapter: Supabase Auth and Postgres

Use this when the audit shows Supabase. Table and column names are examples. Take the real ones from the audit.

## Consent fields

Add columns to the existing profile table. Use the project's own migration process.

- `agreed_to_terms boolean not null default false`
- `agreed_to_terms_at timestamptz`
- `terms_version text`

Existing rows then read as `false`.

## Sign-in method

Read `user.app_metadata.provider` (for example `email` or `google`). Show a readable label.

## Row Level Security

Keep RLS on for every user owned table.

- Profile table: policies for select, insert and update where `auth.uid() = id`. Add no delete policy for the client role. With RLS on, a missing policy means denied.
- Other user owned tables: select, insert, update and delete where `auth.uid() = user_id`, with the same condition in `with check` for insert and update. Users keep the right to delete their own single items.

## Export

Run client side selects scoped by RLS. Read the profile and each table in the data inventory. Exclude fields the user listed in `data.export_exclude_fields`.

## Server side deletion

Use a server function with the service role key. Never put that key in client code.

1. Accept POST only. Read the Bearer token. Call `supabase.auth.getUser(token)` with a server client to get the user id. Return 401 on failure.
2. Delete user owned rows. If foreign keys to `auth.users` use `on delete cascade`, step 3 removes them. If not, delete from each table in the data inventory first. A failure here is logged and does not stop step 3.
3. Delete the user with `supabase.auth.admin.deleteUser(uid)`. Return 500 if this fails.
4. Return `{ success: true }`.

Store the service role key in a host environment variable. Ask the user for its name and record it in the legal config. Do not commit it.

Storage buckets: if the app stores files per user, remove those objects in step 2 too.
