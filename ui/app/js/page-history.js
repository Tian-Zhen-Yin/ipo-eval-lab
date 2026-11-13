/* 历史页：results/ 索引 → 结论记录表（套终态逐套 + 路径输出）。
   每 run 的 result.json 整文件即冻结快照 —— 查看即完整回放，无「叶子明细未分档」问题。
   窗口滚动图：同一主体需要跨报告期的多份 run 才有可比序列；数据稀疏时降级为
   占位说明（不编造数据，设计 0010 §3）。 */

import { esc, dotCls, BOARD_NAMES } from './format.js';
import { getJSON } from './api.js';

const $ = s => document.querySelector(s);

let deps = null;
let cache = null;   // [{file, mtime, run, gapSets, path}]

const OUTCOME_DOT = { criteria_met: 'd-met', criteria_not_met: 'd-not', indeterminate: 'd-ind' };
const OUTCOME_TXT = { criteria_met: '满足', criteria_not_met: '未满足', indeterminate: '不可判' };

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
  $('#hist-sub2').textContent = `results/ 全部 run · ${rows.length} 份`;
  if (!rows.length) {
    $('#hist-table').innerHTML = `<tr><td style="padding:34px 0;text-align:center;color:var(--faint);font-size:13px">暂无测评记录 —— 去「新建测评」跑第一份。</td></tr>`;
    renderRoll(rows);
    return;
  }
  $('#hist-table').innerHTML = `
    <tr><th>测评时间</th><th>主体</th><th>报告期</th><th>套终态（逐套）</th><th>路径输出</th><th>结果文件</th><th class="r">操作</th></tr>
    ${rows.map((r, i) => {
      const when = new Date(r.mtime * 1000);
      const ts = `${when.getFullYear()}-${String(when.getMonth() + 1).padStart(2, '0')}-${String(when.getDate()).padStart(2, '0')} ${String(when.getHours()).padStart(2, '0')}:${String(when.getMinutes()).padStart(2, '0')}`;
      const sets = r.gapSets.map(s =>
        `<span class="dot ${OUTCOME_DOT[s.outcome] || 'd-ind'}"></span><span style="font-size:12px">${esc(shortLabel(s.group_id))} ${OUTCOME_TXT[s.outcome] || s.outcome}</span>`).join(' &nbsp;');
      const pareto = new Set(r.path.pareto_frontier || []);
      const rec = r.path.recommendation || [];
      const excluded = (r.path.excluded || []).filter(x => !pareto.has(x.group_id));
      const pathTxt = [
        rec.length ? `<b style="color:var(--met)">★ 推荐·${rec.map(shortLabel).join('、')}</b>` : '',
        pareto.size ? `<b style="color:var(--brand)">前沿·${[...pareto].map(shortLabel).join('、')}</b>` : '',
        excluded.length ? `<div style="font-size:11px;color:var(--faint)">排除·${excluded.map(x => shortLabel(x.group_id)).join('、')}</div>` : '',
      ].filter(Boolean).join(' ');
      return `<tr ${i === 0 ? 'style="background:#f8faff"' : ''}>
        <td class="num">${ts}${i === 0 ? ' <span class="pill pill-b">最新</span>' : ''}</td>
        <td>${esc(r.run.company_id)}</td>
        <td class="num">${(r.run.report_period?.fiscal_years || ['-'])[0]}–${(r.run.report_period?.fiscal_years || ['-']).slice(-1)[0]}</td>
        <td style="white-space:nowrap">${sets}</td>
        <td style="font-size:12px;white-space:nowrap">${pathTxt || '—'}</td>
        <td style="font-size:12px;color:var(--faint)">${esc(r.file)}</td>
        <td class="r"><a href="#" data-open="${esc(r.file)}">查看 ↗</a></td>
      </tr>`;
    }).join('')}`;
  renderRoll(rows);
}

/* group_id → 短标签（主板标准 1 等；找不到组上下文时回退原 id） */
function shortLabel(gid) {
  const g = deps.getCtx().groups[gid];
  if (!g) return gid;
  const B = { 'SSE-MB': '主板', 'SZSE-MB': '主板', STAR: '科创', ChiNext: '创业', BSE: '北交' };
  if (g.group_no && g.scope === 'set') return `${B[(g.boards || [])[0]] || ''}标${g.group_no}`;
  return gid.replace(/_general|_g\d+$/g, '');
}

/* 窗口滚动图：可比序列要求同一主体存在「不同报告期窗口」的多份 run。
   当前 results/ 的多份 run 若底层 profile 相同（同窗口同数值），图无信息量 ——
   如实降级为说明，不编造对比柱（设计 0010 §3）。 */
function renderRoll(rows) {
  const note = $('#roll-note');
  const chart = $('#rollchart');
  const byCompany = {};
  for (const r of rows) (byCompany[r.run.company_id] = byCompany[r.run.company_id] || []).push(r);
  const varying = Object.entries(byCompany).filter(([, rs]) => {
    const wins = new Set(rs.map(x => (x.run.report_period?.fiscal_years || []).join('-')));
    return wins.size > 1;   // 报告期窗口确有差异才可画
  });
  if (!varying.length) {
    chart.innerHTML = '';
    note.innerHTML = `当前 results/ 中<b>还没有跨报告期窗口的同一主体序列</b>（现有 run 的底层报告期相同，画对比柱只是同一数字的重复）。构造不同申报时点的变体（如窗口滑至 2023–2025）后，此处将呈现 window_roll 的结论反转可视化 —— 该值是确定性重算（阈值 − 窗口剩余年值合计），不是预测。`;
    return;
  }
  const [cid, rs] = varying[0];
  const MAX_YEARS = rs.map(x => Math.max(...(x.run.report_period?.fiscal_years || [0])));
  note.innerHTML = '';   // 有序列时再实现对比柱（等真数据；暂不渲染）
  chart.innerHTML = `<div style="padding:20px 0;color:var(--faint);font-size:13px">${esc(cid)} 存在 ${new Set(MAX_YEARS).size} 个申报时点 —— 对比柱待多窗口数据就位后渲染。</div>`;
}
