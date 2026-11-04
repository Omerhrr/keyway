/**
 * Keyway LLM extraction mini-service (port 8001).
 *
 * Assistive interpretation layer only (per PRD): parses messy WhatsApp vendor
 * messages into structured JSON. It never creates orders or ledger entries -
 * the FastAPI backend validates everything and keeps rules-based fallback.
 */
import ZAI from 'z-ai-web-dev-sdk';

const PORT = Number(process.env.LLM_PORT || 8001);

const SYSTEM_PROMPT = `You are the order-intake parser for Keyway, a Nigerian WhatsApp-first logistics platform (currency: NGN, naira).
Vendors send informal messages. Extract structured data. Respond with ONLY valid JSON, no markdown, no commentary.

JSON schema:
{
  "intent": one of ["NEW_ORDER","ORDER_UPDATE","ORDER_CANCELLATION_REQUEST","ORDER_STATUS_ENQUIRY","INVENTORY_ENQUIRY","PAYMENT_ENQUIRY","SETTLEMENT_ENQUIRY","GENERAL_MESSAGE","UNKNOWN_INTENT"],
  "customer_name": string|null,
  "customer_phone": string|null (Nigerian format 0XXXXXXXXXX),
  "quantity": number|null,
  "unit_price": number|null (amount in NAIRA mentioned by the vendor; never invent one),
  "state": string|null (Nigerian state),
  "city": string|null,
  "street": string|null,
  "product_query": string|null (the product wording to search in the vendor catalog),
  "order_ref": string|null (like KW-1234 if mentioned),
  "confidence": number 0-1
}

Rules:
- Only use information present in the message. Never fabricate names, phones or prices.
- "product_query" must be matched against the provided catalog if possible; pick the closest catalog item name.
- If the message references changing/cancelling a previous order, keep intent as ORDER_UPDATE / ORDER_CANCELLATION_REQUEST.
- Confidence reflects how sure you are that the order fields are correct.`;

interface ExtractBody {
  text: string;
  catalog?: { product_id: number; sku: string; name: string }[];
}

interface TranscribeBody {
  file_base64: string;
  mime?: string;
}

interface VisionBody {
  image_base64: string;   // raw base64 (no data: prefix) or full data URL
  mime?: string;
  question?: string;
  catalog?: { product_id: number; sku: string; name: string }[];
}

let zaiPromise: Promise<any> | null = null;
async function getZAI() {
  if (!zaiPromise) zaiPromise = ZAI.create();
  return zaiPromise;
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    p,
    new Promise<T>((_, rej) => setTimeout(() => rej(new Error('LLM timeout')), ms)),
  ]);
}

async function extract(body: ExtractBody) {
  const text = (body.text || '').slice(0, 1200);
  const catalog = (body.catalog || []).slice(0, 80);
  const catalogLine = catalog.length
    ? `\nVendor catalog: ${catalog.map((c) => `${c.name} (sku ${c.sku})`).join('; ')}`
    : '';
  const zai = await getZAI();
  const completion = await withTimeout(
    zai.chat.completions.create({
      messages: [
        { role: 'assistant', content: SYSTEM_PROMPT },
        { role: 'user', content: `Parse this vendor message:${catalogLine}\n\nMessage: """${text}"""` },
      ],
      thinking: { type: 'disabled' },
    }),
    15000,
  );
  const raw = completion?.choices?.[0]?.message?.content || '';
  const match = raw.match(/\{[\s\S]*\}/);
  if (!match) throw new Error('No JSON in LLM response');
  const parsed = JSON.parse(match[0]);
  return {
    intent: parsed.intent || 'UNKNOWN_INTENT',
    customer_name: parsed.customer_name ?? null,
    customer_phone: parsed.customer_phone ?? null,
    quantity: parsed.quantity ?? null,
    unit_price: parsed.unit_price ?? null,
    state: parsed.state ?? null,
    city: parsed.city ?? null,
    street: parsed.street ?? null,
    product_query: parsed.product_query ?? null,
    order_ref: parsed.order_ref ?? null,
    confidence: Math.min(Math.max(Number(parsed.confidence) || 0.3, 0), 0.99),
    llm: 'glm',
  };
}

async function transcribe(body: TranscribeBody) {
  const raw = (body.file_base64 || '').replace(/^data:[^,]*,/, '');
  if (!raw) throw new Error('file_base64 is required');
  const zai = await getZAI();
  const result = await withTimeout(
    zai.audio.asr.create({ file_base64: raw }),
    40000,
  );
  const text = (result?.text || '').trim();
  if (!text) throw new Error('Empty transcription');
  return { text, engine: 'zai-asr' };
}

const VISION_PROMPT = `You are the product-vision assistant for Keyway, a Nigerian WhatsApp-first logistics platform.
Look at the image from a vendor (likely a product photo or a handwritten/scanned order list).
Respond with ONLY valid JSON, no markdown:
{
  "description": string (concise description of what is shown),
  "items": [{ "name": string, "quantity": number|null }],
  "suggested_product_query": string|null (best catalog search phrase),
  "confidence": number 0-1
}
Only describe what is actually visible; never invent prices or brands.`;

async function vision(body: VisionBody) {
  let raw = (body.image_base64 || '').replace(/^data:[^,]*,/, '');
  if (!raw) throw new Error('image_base64 is required');
  if (raw.length > 8_000_000) throw new Error('Image too large (max ~6MB)');
  const mime = body.mime || 'image/jpeg';
  const catalog = (body.catalog || []).slice(0, 80);
  const catalogLine = catalog.length
    ? `\nVendor catalog to match against: ${catalog.map((c) => c.name).join('; ')}`
    : '';
  const question = (body.question || '').slice(0, 400);
  const zai = await getZAI();
  const completion = await withTimeout(
    zai.chat.completions.createVision({
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: VISION_PROMPT + catalogLine + (question ? `\nExtra instruction: ${question}` : '') },
            { type: 'image_url', image_url: { url: `data:${mime};base64,${raw}` } },
          ],
        },
      ],
      thinking: { type: 'disabled' },
    }),
    85000,
  );
  const rawText = completion?.choices?.[0]?.message?.content || '';
  const match = rawText.match(/\{[\s\S]*\}/);
  if (!match) throw new Error('No JSON in vision response');
  const parsed = JSON.parse(match[0]);
  return {
    description: String(parsed.description || '').slice(0, 600),
    items: Array.isArray(parsed.items) ? parsed.items.slice(0, 20) : [],
    suggested_product_query: parsed.suggested_product_query ?? null,
    confidence: Math.min(Math.max(Number(parsed.confidence) || 0.4, 0), 0.99),
    engine: 'glm-vision',
  };
}

Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);
    try {
      if (url.pathname === '/health') {
        return Response.json({ ok: true, service: 'keyway-llm', port: PORT });
      }
      if (url.pathname === '/v1/extract' && req.method === 'POST') {
        const body = (await req.json()) as ExtractBody;
        const result = await extract(body);
        return Response.json(result);
      }
      if (url.pathname === '/v1/transcribe' && req.method === 'POST') {
        const body = (await req.json()) as TranscribeBody;
        const result = await transcribe(body);
        return Response.json(result);
      }
      if (url.pathname === '/v1/vision' && req.method === 'POST') {
        const body = (await req.json()) as VisionBody;
        const result = await vision(body);
        return Response.json(result);
      }
      return new Response('Not found', { status: 404 });
    } catch (err: any) {
      return Response.json({ error: err?.message || 'LLM failed' }, { status: 502 });
    }
  },
});

console.log(`[keyway-llm] listening on :${PORT}`);
