export async function onRequestPost(context) {
  const { request, env } = context;

  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID || !env.ALERT_API_KEY) {
    return Response.json(
      { error: "Telegram is not configured. Add its credentials and ALERT_API_KEY as Pages secrets." },
      { status: 503 },
    );
  }
  if (request.headers.get("authorization") !== `Bearer ${env.ALERT_API_KEY}`) {
    return Response.json({ error: "Alert access is unauthorized." }, { status: 401 });
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "Request body must be valid JSON." }, { status: 400 });
  }

  if (typeof payload.message !== "string" || !payload.message.trim()) {
    return Response.json({ error: "A non-empty alert message is required." }, { status: 400 });
  }
  if (payload.message.length > 4096) {
    return Response.json({ error: "Telegram messages cannot exceed 4096 characters." }, { status: 400 });
  }

  const telegramResponse = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        chat_id: env.TELEGRAM_CHAT_ID,
        text: payload.message,
        disable_web_page_preview: true,
      }),
    },
  );

  if (!telegramResponse.ok) {
    return Response.json({ error: "Telegram rejected the alert. Check the Pages secrets and bot chat access." }, { status: 502 });
  }

  return Response.json({ status: "sent" });
}
