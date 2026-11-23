/* 历史页：results/ 索引 → 结论记录表（总体结论 + 推荐情况）。
   每 run 的 result.json 整文件即冻结快照 —— 查看即完整回放，无「叶子明细未分档」问题。
   窗口滚动对比已移至结果页（随当前主体定位，见 page-result.js renderRollCompare）。 */

import { esc, dotCls, BOARD_NAMES } from './format.js';
import { getJSON } from './api.js';

const $ = s => document.querySelector(s);

let deps = null;
let cache = null;   // [{file, mtime, run, gapSets, path}]


export function initHistory(d) {
  deps = d;
  $('#hist-table').addEventListener('click', async e => {
    const b = e.target.closest('[data-open]');
    if (!b) return;
    await deps.openResult(b.dataset.open);
    deps.go('result');
  });
}

async function loadAll() {
  const list = await getJSON('/api/results');
  cache = [];
  for (const r of list) {
    try {
      const full = await getJSON('/api/results/' + encodeURIComponent(r.file));
      cache.push({
        ...r,
        gapSets: full.layers?.gap?.sets || [],
        path: full.layers?.path || {},
      });
    } catch { /* 半截文件跳过 */ }
  }
  return cache;
}

export async function renderHistory() {
  const rows = await loadAll();
  $('#hist-sub2').textContent = `全部测评记录 · ${rows.length} 次`;
  if (!rows.length) {
    $('#hist-table').innerHTML = `<tr><td style="padding:34px 0;text-align:center;color:var(--faint);font-size:13px">暂无测评记录 —— 去「新建测评」跑第一份。</td></tr>`;
    return;
  }
  $('#hist-table').innerHTML = `
    <tr><th>测评时间</th><th>主体</th><th>报告期</th><th>总体结论</th><th title="按四轴对比与硬性条件闸门筛选后的标准推荐情况：推荐 / 前沿（互不支配、各有优势）/ 未进推荐">推荐情况</th><th class="r">操作</th></tr>
    ${rows.map((r, i) => {
      const when = new Date(r.mtime * 1000);
      const ts = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}-${String(when.getDate()).padStart(2, '0')} ${String(when.getHours()).padStart(2, '0')}:${String(when.getMinutes()).padStart(2, '0')}`;
      // 总体结论：与结果页结论带同口径（adapters buildVerdict）；逐项标准进详情看
      const cnt = { criteria_met: 0, criteria_not_met: 0, indeterminate: 0 };
      (r.gapSets || []).forEach(s => { cnt[s.outcome] = (cnt[s.outcome] || 0) + 1; });
      const total = (r.gapSets || []).length;
      let dot, tag, detail;
      if (!total) {
        dot = 'd-ind'; tag = '—'; detail = '';
      } else if (cnt.criteria_met > 0) {
        dot = 'd-met'; tag = '有达标标准';
        detail = `${total} 个标准：满足 ${cnt.criteria_met}`
          + (cnt.criteria_not_met ? ` · 未满足 ${cnt.criteria_not_met}` : '')
          + (cnt.indeterminate ? ` · 暂无法判定 ${cnt.indeterminate}` : '');
      } else if (cnt.criteria_not_met > 0) {
        dot = 'd-not'; tag = '未满足';
        detail = `${total} 个标准：未满足 ${cnt.criteria_not_met}`
          + (cnt.indeterminate ? ` · 暂无法判定 ${cnt.indeterminate}` : '');
      } else {
        dot = 'd-ind'; tag = '暂无法判定';
        detail = `${total} 个标准均数据不完整`;
      }
      const sets = `<span class="dot ${dot}"></span><b style="font-size:13px">${tag}</b>`
        + (detail ? `<div style="font-size:11px;color:var(--faint);margin-top:2px">${detail}</div>` : '');
      const pareto = new Set(r.path.pareto_frontier || []);
      const rec = r.path.recommendation || [];
      const excluded = (r.path.excluded || []).filter(x => !pareto.has(x.group_id));
      const pathTxt = [
        rec.length ? `<b style="color:var(--met)">★ 推荐·${rec.map(shortLabel).join('、')}</b>` : '',
        pareto.size ? `<b style="color:var(--brand)" title="四轴对比中不被其他标准全面优于（各有优势）">前沿·${[...pareto].map(shortLabel).join('、')}</b>` : '',
        excluded.length ? `<div style="font-size:11px;color:var(--faint)">未进推荐·${excluded.map(x => shortLabel(x.group_id)).join('、')}</div>` : '',
      ].filter(Boolean).join(' ');
      return `<tr ${i === 0 ? 'style="background:#f8faff"' : ''}>
        <td class="num">${ts}${i === 0 ? ' <span class="pill pill-b">最新</span>' : ''}</td>
        <td>${esc(displayName(r.run.company_id))}${srcBadge(r.data_source)}</td>
        <td class="num">${(r.run.report_period?.fiscal_years || ['-'])[0]}–${(r.run.report_period?.fiscal_years || ['-']).slice(-1)[0]}</td>
        <td>${sets}</td>
        <td style="font-size:12px">${pathTxt || '—'}</td>
        <td class="r"><a href="#" data-open="${esc(r.file)}">查看 ↗</a></td>
      </tr>`;
    }).join('')}`;
}

/* 主体 id → 显示名（/api/companies 已在 ctx；找不到回退 id） */
function displayName(cid) {
  const c = deps.getCtx()?.companies?.[cid];
  return c ? c.display_name : cid;
}

/* 来源徽标（工单 05）：区分 mock 跑的与客户数据跑的；字段缺失 = 旧 JSON，不显示 */
function srcBadge(ds) {
  if (ds === 'enterprise') return ' <span class="src-tag src-ent" title="本次测评来自企业接入的主体数据">企业</span>';
  if (ds === 'session') return ' <span class="src-tag src-ses" title="本次测评含 UI 补录数据">补录</span>';
  return '';
}

/* group_id → 短标签（主板标准 1；找不到组上下文时回退原 id） */
function shortLabel(gid) {
  const g = deps.getCtx().groups[gid];
  if (!g) return gid;
  const B = { 'SSE-MB': '主板', 'SZSE-MB': '主板', STAR: '科创板', ChiNext: '创业板', BSE: '北交所' };
  if (g.group_no && g.scope === 'set') return `${B[(g.boards || [])[0]] || ''}标准 ${g.group_no}`;
  return gid.replace(/_general|_g\d+$/g, '');
}
