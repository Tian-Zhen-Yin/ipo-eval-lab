/* 新建页：真实数据驱动的向导。
   - 套卡由 /api/rulebook 36 组摘要驱动（V16 关闭：无「仅铺沪主板」占位）
   - 依法无套组合来自 meta.declared_no_sets（套级裁定的可见化）
   - 报告期来自主体 profile（契约下不可虚构报告期）
   - 补录 → overrides → POST /api/run（会话 profile，fixtures 零改动） */

import { esc, BOARD_NAMES, TYPE_NAMES, FILTER_OP_ZH, fmtYuan } from './format.js';
import { postJSON } from './api.js';
import { openMask, closeMask, showLoading, hideLoading } from './dialogs.js';

const $ = s => document.querySelector(s);

let deps = null;                       // {getCtx, getCompanies, getResults, openResult, go, refreshResults}
let selB = 'SSE-MB', selC = 'general';
let supCtx = null;                     // 补录上下文（公司 id + base profile）

/* ── 表单填充 ── */
function fillForm() {
  const ctx = deps.getCtx();
  const companies = deps.getCompanies();
  $('#f-entity').innerHTML = companies.map(c =>
    `<option value="${esc(c.id)}">${esc(c.display_name)}</option>`).join('');
  $('#f-board').innerHTML = ctx.meta.boards.map(b =>
    `<option value="${esc(b)}">${esc(BOARD_NAMES[b] || b)}</option>`).join('');
  $('#f-ctype').innerHTML = ctx.meta.company_types.map(t =>
    `<option value="${esc(t)}" ${t === selC ? 'selected' : ''}>${esc(TYPE_NAMES[t] || t)}</option>`).join('');
  const today = new Date().toISOString().slice(0, 10);
  $('#f-asof').value = today;
  syncAll();
}

/* ── 联动 ── */
function syncAll() {
  const ctx = deps.getCtx();
  $('#f-board').value = selB;
  $('#f-ctype').value = selC;
  const noSets = (ctx.meta.declared_no_sets || []).some(([b, t]) => b === selB && t === selC);
  const nSets = setGroupsFor().length;
  $('#f-board-note').textContent = `${BOARD_NAMES[selB] || selB} · 适用企业类型 ${typeCountFor(selB)} 类`;
  $('#f-ctype-note').textContent = noSets
    ? '该「板块 × 类型」组合在规则层面不设上市标准套（套级裁定明确记录，非遗漏）——发行条件与板块定位仍适用'
    : `本组合适用官方标准 ${nSets} 套`;
  renderPeriod();
  renderBoardPos(noSets);
  renderStdCards(noSets);
  renderHist();
}

function typeCountFor(board) {
  const ctx = deps.getCtx();
  const declared = new Set((ctx.meta.declared_no_sets || []).filter(([b]) => b === board).map(([, t]) => t));
  return ctx.meta.company_types.filter(t => !declared.has(t)).length;
}

function setGroupsFor() {
  const ctx = deps.getCtx();
  return ctx.groups_list.filter(g => g.scope === 'set'
    && (g.boards || []).includes(selB) && g.company_type === selC);
}

function company() {
  return deps.getCompanies().find(c => c.id === $('#f-entity').value);
}

function renderPeriod() {
  const c = company();
  const ys = c && c.fiscal_years && c.fiscal_years.length ? c.fiscal_years : [];
  const stub = c && c.profile && c.profile.stub_period;
  const stubOn = $('#f-stub') && $('#f-stub').checked;
  const stubTxt = stub && stubOn ? ` + ${esc(stub.period_label)}（中期，仅作定位展示，不进窗口计算）` : '';
  $('#f-period').textContent = ys.length
    ? `${ys[0]}–${ys[ys.length - 1]} 年度（${ys.length} 个完整年度）${stubTxt}`
    : '—';
  const stubField = $('#f-stub-field');
  if (stubField) stubField.style.display = stub ? '' : 'none';
  if (stub && !stubOn) { /* 未勾选不显示 */ }
}

/* ── 板块定位卡（真实 positioning 组：条款 display + 硬筛） ── */
function renderBoardPos(noSets) {
  const ctx = deps.getCtx();
  const pos = ctx.groups_list.filter(g => g.scope === 'positioning' && (g.boards || []).includes(selB));
  $('#bp-title').textContent = `${BOARD_NAMES[selB] || selB} · 板块定位`;
  const clauseLines = [];
  for (const g of pos) {
    for (const b of g.branches || []) {
      for (const c of b.clauses || []) if (c.display) clauseLines.push(c.display);
      for (const c of g.shared_clauses || []) if (c.display) clauseLines.push(c.display);
    }
  }
  const hf = pos.flatMap(g => g.hard_filters || []);
  $('#bp-desc').innerHTML = clauseLines.length
    ? clauseLines.map(l => `· ${esc(l)}`).join('<br>')
    : '该板块暂无定位条款（覆盖范围见规则库定位组）。';
  $('#bp-meta').innerHTML = `
    <span>适用标准 <b>${setGroupsFor().length}</b> 套</span>
    <span class="bp-sep"></span>
    <span>企业类型 <b>${esc(TYPE_NAMES[selC] || selC)}</b></span>
    <span class="bp-sep"></span>
    <span>定位组 <b>${pos.length}</b></span>`;
  $('#bp-kw').innerHTML = hf.map(h =>
    `<span data-tip="${esc(h.note || `${h.field} ${FILTER_OP_ZH[h.op] || h.op} ${(h.values || []).join('、')}`)}">行业负面清单：${esc(h.field)} ${FILTER_OP_ZH[h.op] || h.op} ${(h.values || []).slice(0, 3).map(esc).join('、')}${(h.values || []).length > 3 ? '…' : ''}</span>`).join('')
    || (noSets ? '<span style="color:var(--faint)">该组合不设标准套</span>' : '');
}

/* ── 上市标准套卡（28 套真数据；as_of 未生效标记） ── */
function renderStdCards(noSets) {
  const ctx = deps.getCtx();
  const asOf = $('#f-asof').value || '';
  const list = setGroupsFor();
  $('#std-sub').textContent = `${BOARD_NAMES[selB] || selB} · ${TYPE_NAMES[selC] || selC} · ${list.length} 个官方套`;
  if (noSets) {
    $('#stdcards').innerHTML = `<div style="padding:26px;text-align:center;color:var(--faint);font-size:13px">该「板块 × 类型」组合<b>依法不设标准套</b>（套级裁定记录可查）。发行条件与板块定位仍适用。</div>`;
    return;
  }
  if (!list.length) {
    $('#stdcards').innerHTML = `<div style="padding:26px;text-align:center;color:var(--faint);font-size:13px">规则库中暂无该组合的套。</div>`;
    return;
  }
  $('#stdcards').innerHTML = list.map((g, i) => {
    const notYet = asOf && g.effective_from > asOf;
    const clauses = [
      ...(g.shared_clauses || []),
      ...((g.branches || []).flatMap(b => b.clauses || [])),
    ];
    const lawRefs = [...new Set((g.law_refs || []).map(l => l.split('#')[1] || l))].join(' / ');
    const nLeaves = clauses.reduce((n, c) => n + (c.leaves || []).length, 0);
    const isFirst = i === 0;
    return `
    <div class="stdcard ${isFirst ? 'open' : ''}" data-std="${i}">
      <button class="sc-hd" aria-expanded="${isFirst}" aria-controls="stdbody-${i}" type="button">
        <span class="sc-arrow" aria-hidden="true">▶</span>
        <div class="sc-name">
          <h5>${g.group_no ? `第 ${g.group_no} 套` : esc(g.display)}${notYet ? '<span class="pill pill-w">基准日前未生效</span>' : ''}</h5>
          <div class="sc-sub">生效于 ${esc(g.effective_from)} · ${clauses.length} 条文 / ${nLeaves} 条件项</div>
        </div>
      </button>
      <div class="sc-body" id="stdbody-${i}">
        ${clauses.map(c => {
          const leafNames = (c.leaves || []).map(l => {
            const item = ctx.items[l.item_ref];
            return esc(item ? item.display : l.item_ref);
          }).join('；');
          // 单叶条文名与条款名几乎重复，不重复罗列；多叶才列细项
          const detail = (c.leaves || []).length > 1 ? ` <span class="sc-thr-sub">${leafNames}</span>` : '';
          const logic = c.logic === 'any' ? ' <span class="logic-or">或 · 任一满足</span>' : '';
          return `<div class="sc-thr"><b>${esc(c.display || c.clause_id)}</b>${logic}${detail}</div>`;
        }).join('')}
        <div class="sc-law">条文依据：${esc(lawRefs)}</div>
      </div>
    </div>`;
  }).join('');
}

/* ── 历史测评卡（results/ 按主体过滤） ── */
function renderHist() {
  const c = company();
  const list = (deps.getResults() || []).filter(r => r.run.company_id === (c ? c.id : ''));
  $('#hist-sub').textContent = c ? `${c.display_name} · ${list.length} 次测评` : '当前主体最近记录';
  $('#histlist').innerHTML = list.length ? list.slice(0, 5).map((r, i) => {
    const d = new Date(r.mtime * 1000);
    const ts = `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    return `
    <button class="histcard" type="button" data-hist="${esc(r.file)}">
      <div class="hicon" aria-hidden="true">${i === 0 ? '今' : '历'}</div>
      <div class="hmain"><b>基准日 ${esc(r.run.as_of_date)} 的测评</b><span>生成于 ${ts} · 适用标准 ${((r.run.applied_rule_versions || []).length)} 套</span></div>
      <div class="hscore">查看 ↗</div>
    </button>`;
  }).join('')
    : '<div style="padding:16px 4px;color:var(--faint);font-size:12.5px">该主体暂无测评记录 —— 点「开始测评」跑第一份。</div>';
}

/* ── 补录弹窗 ── */
function openSup() {
  const c = company();
  if (!c) return;
  supCtx = { id: c.id, doc: (c.profile && c.profile.documentary) || {} };
  const doc = supCtx.doc;
  const mkt = doc.mktcap_self_estimate;
  const fields = [
    { key: 'mktcap', n: '市值 / 预计市值', ph: mkt && mkt.value ? fmtYuan(mkt.value) : '未填报', d: '上市标准中的市值类条件使用；结果一律带「企业自估」限定。底表值：' + (mkt && mkt.value ? fmtYuan(mkt.value) : '无（留空则该项暂无法判定）') },
    { key: 'operating_years', n: '经营年限（年）', ph: doc.operating_years ?? '未填报', d: '持续经营时间，整数年。底表值：' + (doc.operating_years ?? '无') },
    { key: 'public_float_ratio', n: '公开发行比例（%）', ph: doc.public_float_ratio != null ? (doc.public_float_ratio * 100).toFixed(2) : '未填报', d: '0–100，可两位小数。底表值：' + (doc.public_float_ratio != null ? (doc.public_float_ratio * 100).toFixed(2) + '%' : '无') },
    { key: 'total_shares_after_ipo', n: '发行后股本总额（股）', ph: doc.total_shares_after_ipo ?? '未填报', d: '整数股。底表值：' + (doc.total_shares_after_ipo != null ? doc.total_shares_after_ipo.toLocaleString('zh-CN') + ' 股' : '无') },
  ];
  $('#sup-fields').innerHTML = fields.map(f => `
    <div class="field">
      <label>${f.n} <span data-tip="${esc(f.d)}" style="cursor:help;border-bottom:1px dashed var(--faint);color:var(--faint);font-weight:400">说明</span></label>
      ${f.key === 'mktcap' ? `
      <div class="amt-row">
        <input type="text" id="sup-mkt" value="" placeholder="${esc(f.ph)}" inputmode="decimal">
        <select id="sup-mkt-unit"><option value="100000000">亿元</option><option value="10000">万元</option><option value="1">元</option></select>
        <label style="margin:0;font-weight:400;white-space:nowrap"><input type="checkbox" id="sup-mkt-clear"> 清空自估</label>
      </div>` : `
      <input type="text" id="sup-${f.key}" value="" placeholder="${esc(String(f.ph))}" data-key="${f.key}" inputmode="decimal">`}
      <div class="note">${esc(f.d)}</div>
    </div>`).join('');
  const echo = document.getElementById('sup-mkt-echo-holder');
  if (echo) echo.remove();
  $('#sup-err').style.display = 'none';
  bindMktEcho();
  openMask('mask-sup');
}

function bindMktEcho() {
  const inp = document.getElementById('sup-mkt');
  const unit = document.getElementById('sup-mkt-unit');
  if (!inp) return;
  const holder = document.createElement('div');
  holder.className = 'note';
  holder.id = 'sup-mkt-echo-holder';
  inp.closest('.field').appendChild(holder);
  const upd = () => {
    const clear = document.getElementById('sup-mkt-clear').checked;
    const raw = inp.value.trim().replace(/,/g, '');
    if (clear) { holder.innerHTML = '已勾选清空 → 市值按<b>暂无法判定</b>进入测评'; return; }
    if (!raw) { holder.innerHTML = '留空 = 沿用底表值'; return; }
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) { holder.innerHTML = '<span style="color:var(--notmet)">请输入正数金额</span>'; return; }
    holder.innerHTML = `折合 <b class="num">${esc(fmtYuan(n * Number(unit.value)))}</b>`;
  };
  inp.addEventListener('input', upd);
  unit.addEventListener('change', upd);
  document.getElementById('sup-mkt-clear').addEventListener('change', upd);
  upd();
}

function collectOverrides() {
  const o = { documentary: {}, declared: {} };
  const num = id => {
    const el = document.getElementById(id);
    if (!el) return undefined;
    const raw = el.value.trim().replace(/,/g, '');
    return raw === '' ? undefined : Number(raw);
  };
  const mktClear = document.getElementById('sup-mkt-clear')?.checked;
  const mktRaw = num('sup-mkt');
  if (mktClear) o.documentary.mktcap_self_estimate = null;              // 显式清空
  else if (mktRaw !== undefined) {
    const unit = Number(document.getElementById('sup-mkt-unit').value);
    o.documentary.mktcap_self_estimate = { value: Math.round(mktRaw * unit), note: 'UI 补录（webui 会话）' };
  }
  const oy = num('sup-operating_years');
  if (oy !== undefined) o.documentary.operating_years = Math.round(oy);
  const pf = num('sup-public_float_ratio');
  if (pf !== undefined) o.documentary.public_float_ratio = pf / 100;    // % → 小数（契约约定）
  const ts = num('sup-total_shares_after_ipo');
  if (ts !== undefined) o.documentary.total_shares_after_ipo = Math.round(ts);
  if (!Object.keys(o.documentary).length && !Object.keys(o.declared).length) return null;
  return o;
}

async function runEval() {
  const errBox = $('#sup-err');
  errBox.style.display = 'none';
  const asOf = $('#f-asof').value.trim();
  if (asOf && !/^\d{4}-\d{2}-\d{2}$/.test(asOf)) {
    errBox.textContent = '基准日格式应为 YYYY-MM-DD';
    errBox.style.display = '';
    return;
  }
  const body = {
    company: $('#f-entity').value,
    as_of: asOf || undefined,
    boards: [selB],
    overrides: collectOverrides() || undefined,
  };
  closeMask('mask-sup');
  showLoading('<b>正在执行测评…</b>', '读取主体底表 → 逐项比对规则 → 汇总结论');
  try {
    const out = await postJSON('/api/run', body);
    await deps.refreshResults();
    await deps.openResult(out.file);
    hideLoading();
    deps.go('result');
  } catch (e) {
    hideLoading();
    errBox.textContent = e.message || String(e);
    errBox.style.display = '';
    openMask('mask-sup');
  }
}

/* ── init（事件委托） ── */
export function initNewPage(d) {
  deps = d;
  fillForm();
  $('#f-board').addEventListener('change', e => { selB = e.target.value; syncAll(); });
  $('#f-ctype').addEventListener('change', e => { selC = e.target.value; syncAll(); });
  $('#f-entity').addEventListener('change', () => { renderPeriod(); renderHist(); });
  $('#f-stub').addEventListener('change', renderPeriod);
  $('#f-asof').addEventListener('change', () => renderStdCards(
    (deps.getCtx().meta.declared_no_sets || []).some(([b, t]) => b === selB && t === selC)));
  $('#btn-start').addEventListener('click', openSup);
  $('#sup-go').addEventListener('click', () => { runEval(); });
  $('#stdcards').addEventListener('click', e => {
    const c = e.target.closest('.stdcard');
    if (!c) return;
    const on = c.classList.toggle('open');
    const hd = c.querySelector('.sc-hd');
    if (hd) hd.setAttribute('aria-expanded', on ? 'true' : 'false');
  });
  $('#histlist').addEventListener('click', async e => {
    const b = e.target.closest('[data-hist]');
    if (!b) return;
    await deps.openResult(b.dataset.hist);
    deps.go('result');
  });
}

/* 结果列表刷新后重画历史卡（main.js 在 run 完成后调） */
export function refreshNewPage() {
  if (!deps.getCtx()) return;
  renderHist();
}
