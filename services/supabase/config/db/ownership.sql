-- The Supabase Postgres image seeds placeholder objects as supabase_admin.
-- Auth and Storage run their own migrations with narrower service roles, so
-- those roles must own any objects that their migrations replace or alter.

CREATE OR REPLACE FUNCTION pg_temp.reassign_schema_objects(
  target_schema name,
  target_owner name
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  item record;
  object_kind text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = target_schema) THEN
    RETURN;
  END IF;

  EXECUTE format('ALTER SCHEMA %I OWNER TO %I', target_schema, target_owner);

  FOR item IN
    SELECT c.relname, c.relkind
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = target_schema
      AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
  LOOP
    object_kind := CASE item.relkind
      WHEN 'S' THEN 'SEQUENCE'
      WHEN 'v' THEN 'VIEW'
      WHEN 'm' THEN 'MATERIALIZED VIEW'
      WHEN 'f' THEN 'FOREIGN TABLE'
      ELSE 'TABLE'
    END;

    EXECUTE format(
      'ALTER %s %I.%I OWNER TO %I',
      object_kind,
      target_schema,
      item.relname,
      target_owner
    );
  END LOOP;

  FOR item IN
    SELECT p.oid::regprocedure AS identity, p.prokind
    FROM pg_proc AS p
    JOIN pg_namespace AS n ON n.oid = p.pronamespace
    WHERE n.nspname = target_schema
      AND p.prokind IN ('f', 'p')
  LOOP
    object_kind := CASE item.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END;
    EXECUTE format('ALTER %s %s OWNER TO %I', object_kind, item.identity, target_owner);
  END LOOP;
END;
$$;

SELECT pg_temp.reassign_schema_objects('auth', 'supabase_auth_admin');
SELECT pg_temp.reassign_schema_objects('storage', 'supabase_storage_admin');

GRANT ALL ON SCHEMA auth TO supabase_auth_admin;
GRANT ALL ON ALL TABLES IN SCHEMA auth TO supabase_auth_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA auth TO supabase_auth_admin;
GRANT ALL ON ALL ROUTINES IN SCHEMA auth TO supabase_auth_admin;

GRANT ALL ON SCHEMA storage TO supabase_storage_admin;
GRANT ALL ON ALL TABLES IN SCHEMA storage TO supabase_storage_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA storage TO supabase_storage_admin;
GRANT ALL ON ALL ROUTINES IN SCHEMA storage TO supabase_storage_admin;
