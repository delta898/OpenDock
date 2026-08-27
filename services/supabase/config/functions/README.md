# Edge Functions

Add each function under its own directory, for example `hello/index.ts`.
OpenDock ships the `main` dispatcher and a `hello` smoke-test function.

Invoke a function through the public gateway:

```sh
curl https://supabase.example.com/functions/v1/hello \
  -H "Authorization: Bearer $SUPABASE_ANON_KEY"
```
