const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
};

Deno.serve((request: Request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  return Response.json(
    { message: "Hello from OpenDock Supabase Edge Functions!" },
    { headers: corsHeaders },
  );
});
