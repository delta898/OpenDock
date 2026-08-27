console.log("OpenDock Supabase Edge Functions gateway started");

const jwtSecret = Deno.env.get("JWT_SECRET") ?? "";
const jwks = parseJson<{ keys: JsonWebKey[] }>(
  Deno.env.get("SUPABASE_JWKS"),
  { keys: [] },
);
const publishableKeys = Object.values(
  parseJson<Record<string, string>>(Deno.env.get("SUPABASE_PUBLISHABLE_KEYS"), {}),
);
const secretKeys = Object.values(
  parseJson<Record<string, string>>(Deno.env.get("SUPABASE_SECRET_KEYS"), {}),
);
const verifyJwt = Deno.env.get("VERIFY_JWT") === "true";

function parseJson<T>(raw: string | undefined, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function decodeBase64Url(value: string): Uint8Array {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(
    Math.ceil(value.length / 4) * 4,
    "=",
  );
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

async function validLegacyJwt(token: string): Promise<boolean> {
  const parts = token.split(".");
  if (parts.length !== 3 || !jwtSecret) return false;

  try {
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(jwtSecret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"],
    );
    const verified = await crypto.subtle.verify(
      "HMAC",
      key,
      decodeBase64Url(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
    const payload = JSON.parse(new TextDecoder().decode(decodeBase64Url(parts[1])));
    return verified && (!payload.exp || payload.exp > Math.floor(Date.now() / 1000));
  } catch {
    return false;
  }
}

async function validAsymmetricJwt(token: string): Promise<boolean> {
  const parts = token.split(".");
  if (parts.length !== 3) return false;

  try {
    const header = JSON.parse(
      new TextDecoder().decode(decodeBase64Url(parts[0])),
    );
    if (header.alg !== "ES256" || !header.kid) return false;
    const jwk = jwks.keys.find((candidate: JsonWebKey) =>
      candidate.kty === "EC" && candidate.kid === header.kid
    );
    if (!jwk) return false;

    const key = await crypto.subtle.importKey(
      "jwk",
      jwk,
      { name: "ECDSA", namedCurve: "P-256" },
      false,
      ["verify"],
    );
    const verified = await crypto.subtle.verify(
      { name: "ECDSA", hash: "SHA-256" },
      key,
      decodeBase64Url(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
    const payload = JSON.parse(
      new TextDecoder().decode(decodeBase64Url(parts[1])),
    );
    return verified && (!payload.exp || payload.exp > Math.floor(Date.now() / 1000));
  } catch {
    return false;
  }
}

async function validJwt(token: string): Promise<boolean> {
  try {
    const header = JSON.parse(
      new TextDecoder().decode(decodeBase64Url(token.split(".")[0] ?? "")),
    );
    if (header.alg === "HS256") return await validLegacyJwt(token);
    if (header.alg === "ES256") return await validAsymmetricJwt(token);
  } catch {
    // Invalid tokens are rejected below.
  }
  return false;
}

async function authorized(request: Request): Promise<boolean> {
  const apiKey = request.headers.get("apikey") ?? "";
  const authorization = request.headers.get("authorization") ?? "";
  const [scheme, bearer] = authorization.split(" ", 2);
  const configuredOpaqueKeys = [...publishableKeys, ...secretKeys];

  if (apiKey && configuredOpaqueKeys.includes(apiKey)) return true;
  if (scheme === "Bearer" && configuredOpaqueKeys.includes(bearer ?? "")) {
    return Boolean(apiKey) && apiKey === bearer;
  }
  return scheme === "Bearer" && await validJwt(bearer ?? "");
}

Deno.serve(async (request: Request) => {
  if (request.method !== "OPTIONS" && verifyJwt) {
    if (!(await authorized(request))) {
      return Response.json(
        { message: "Invalid or missing API key/JWT" },
        { status: 401 },
      );
    }
  }

  const functionName = new URL(request.url).pathname.split("/")[1];
  if (!functionName || !/^[a-zA-Z0-9_-]+$/.test(functionName)) {
    return Response.json({ message: "Missing or invalid function name" }, { status: 400 });
  }

  try {
    const worker = await EdgeRuntime.userWorkers.create({
      servicePath: `/home/deno/functions/${functionName}`,
      memoryLimitMb: 150,
      workerTimeoutMs: 60_000,
      noModuleCache: false,
      importMapPath: null,
      envVars: Object.entries(Deno.env.toObject()),
    });
    return await worker.fetch(request);
  } catch (error) {
    console.error(error);
    return Response.json({ message: String(error) }, { status: 500 });
  }
});
