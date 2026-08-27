-- PostgREST exposes graphql_public, so the schema must exist before PostgREST
-- builds its schema cache. The Supabase Postgres image ships pg_graphql but its
-- self-hosted Docker stack still owns the orchestration-level initialization.

CREATE SCHEMA IF NOT EXISTS graphql;
CREATE SCHEMA IF NOT EXISTS graphql_public AUTHORIZATION supabase_admin;

CREATE EXTENSION IF NOT EXISTS pg_graphql WITH SCHEMA graphql;

CREATE OR REPLACE FUNCTION graphql_public.graphql(
  "operationName" text DEFAULT NULL,
  query text DEFAULT NULL,
  variables jsonb DEFAULT NULL,
  extensions jsonb DEFAULT NULL
)
RETURNS jsonb
LANGUAGE sql
AS $$
  SELECT graphql.resolve(
    query := query,
    variables := COALESCE(variables, '{}'::jsonb),
    "operationName" := "operationName",
    extensions := extensions
  );
$$;

GRANT USAGE ON SCHEMA graphql TO postgres, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA graphql_public TO postgres, anon, authenticated, service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA graphql TO postgres, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION graphql_public.graphql(text, text, jsonb, jsonb)
  TO postgres, anon, authenticated, service_role;
