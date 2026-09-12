function marketServiceUrl(baseUrl, symbol) {
  const url = new URL("/api/options-signals", baseUrl);
  url.searchParams.set("symbol", symbol);
  return url;
}

export async function onRequestGet(context) {
  const { request, env } = context;
  const requestUrl = new URL(request.url);
  const symbol = requestUrl.searchParams.get("symbol") || "NIFTY 50";

  if (!env.MARKET_API_BASE) {
    return Response.json(
      { status: "error", message: "Market API is not configured. Add MARKET_API_BASE as a Pages secret." },
      { status: 503 },
    );
  }

  let upstream;
  try {
    upstream = await fetch(marketServiceUrl(env.MARKET_API_BASE, symbol), {
      headers: { accept: "application/json" },
    });
  } catch {
    return Response.json(
      { status: "error", message: "The market service could not be reached." },
      { status: 502 },
    );
  }

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") || "application/json",
      "cache-control": "no-store",
    },
  });
}
