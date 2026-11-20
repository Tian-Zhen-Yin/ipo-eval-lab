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

/* 数据接入（ADR-0013 修订 1）：上传走原始字节流，文件名/主体 id 在请求头（非 ASCII 需编码） */
export async function uploadIngest(file, companyId) {
  const headers = { 'X-Filename': encodeURIComponent(file.name) };
  if (companyId) headers['X-Company-Id'] = encodeURIComponent(companyId);
  const r = await fetch('/api/ingest/upload', {
    method: 'POST', headers, body: await file.arrayBuffer(),
  });
  const j = await r.json().catch(() => ({ error: `非 JSON 响应（HTTP ${r.status}）` }));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

/* 保存：409（已存在，带指纹）不抛错——覆盖确认是页面交互，不是异常路径 */
export async function saveIngest(body) {
  const r = await fetch('/api/ingest/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({ error: `非 JSON 响应（HTTP ${r.status}）` }));
  if (!r.ok && r.status !== 409) throw new Error(j.error || `HTTP ${r.status}`);
  return { ok: r.ok, status: r.status, data: j };
}
