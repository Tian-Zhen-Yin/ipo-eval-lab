/* fetch 封装：webui API 的唯一出口；错误统一抛 Error（message 来自 {error}） */
export async function getJSON(path) {
  const r = await fetch(path);
  const j = await r.json().catch(() => ({ error: `非 JSON 响应（HTTP ${r.status}）` }));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

export async function postJSON(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({ error: `非 JSON 响应（HTTP ${r.status}）` }));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
