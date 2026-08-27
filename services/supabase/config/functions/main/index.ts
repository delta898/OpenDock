console.log("OpenDock Supabase Edge Functions gateway started");

const jwtSecret = Deno.env.get("JWT_SECRET") ?? "";
const verifyJwt = Deno.env.get("VERIFY_JWT") === "true";

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

Deno.serve(async (request: Request) => {
  if (request.method !== "OPTIONS" && verifyJwt) {
    const authorization = request.headers.get("authorization") ?? "";
    const [scheme, token] = authorization.split(" ", 2);
    if (scheme !== "Bearer" || !(await validLegacyJwt(token ?? ""))) {
      return Response.json({ message: "Invalid or missing JWT" }, { status: 401 });
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
