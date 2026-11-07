export default defineEventHandler(async (event) => {
  const req = event.node.req
  const url = req.url || ''
  const base = process.env.KEYWAY_API_URL || 'http://127.0.0.1:8000'
  const target = `${base}${url}`
  const { proxyRequest } = await import('h3')
  try {
    return await proxyRequest(event, target)
  } catch (e: any) {
    return new Response(JSON.stringify({ detail: `Keyway API unreachable (${e?.message || e})` }), {
      status: 502,
      headers: { 'content-type': 'application/json' },
    })
  }
})
