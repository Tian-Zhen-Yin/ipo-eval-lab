/* 入口：页路由 + 数据加载（meta/rulebook/companies/results 并行）+ 页面装配。 */

import { getJSON } from './api.js';
import { buildCtx, fromResult } from './adapters.js';
import { esc } from './format.js';
import { renderResult, renderError, initResultEvents } from './page-result.js';
import { initNewPage, refreshNewPage } from './page-new.js';
import { initHistory, renderHistory } from './page-history.js';
import { initDialogs } from './dialogs.js';

const $ = s => document.querySelector(s);

const state = {
  ctx: null,          // {items, laws, groups, groups_list, companies, meta}
  companies: [],      // /api/companies 原始列表（含 profile）
  results: [],        // /api/results 索引
  file: null,         // 当前展示的结果文件
};

/* ── 键盘模态 + 焦点环（自原型 v0.4 迁移：渲染器不支持 :focus-visible 的回退） ── */
(function kbFocus() {
  let kbMode = false, lastEl = null;
  const paint = el => {
    if (lastEl && lastEl !== el) lastEl.classList.remove('kb-ring');
    lastEl = el;
    if (kbMode && el && el !== document.body) el.classList.add('kb-ring');
    else if (el) el.classList.remove('kb-ring');
  };
  document.addEventListener('keydown', e => {
    if (e.key === 'Tab' || e.key.indexOf('Arrow') === 0 || e.key === 'Enter' || e.key === ' ') kbMode = true;
    paint(document.activeElement);
  }, true);
  document.addEventListener('mousedown', () => { kbMode = false; paint(null); }, true);
  document.addEventListener('focusin', e => paint(e.target));
  document.addEventListener('focusout', e => { if (e.target === lastEl) { e.target.classList.remove('kb-ring'); lastEl = null; } });
})();

/* ── 页路由（委托） ── */
function go(p) {
  document.querySelectorAll('.nav button').forEach(b => b.classList.toggle('on', b.dataset.go === p));
  document.querySelectorAll('.page').forEach(x => x.classList.toggle('on', x.id === 'page-' + p));
  window.scrollTo({ top: 0 });
  if (p === 'history' && state.ctx) renderHistory().catch(() => {});   // 历史页懒加载
}
function initNav() {
  document.querySelector('.nav').addEventListener('click', e => {
    const b = e.target.closest('button[data-go]');
    if (b) go(b.dataset.go);
  });
  document.querySelector('.subtabs').addEventListener('click', e => {
    const b = e.target.closest('button[data-rt]');
    if (!b) return;
    document.querySelectorAll('.subtabs button').forEach(x => x.classList.toggle('on', x === b));
    document.querySelectorAll('.rtab').forEach(x => x.classList.toggle('on', x.id === 'rtab-' + b.dataset.rt));
  });
}

/* 结果文件加载（whenLabel = 文件选择器里该 run 的友好标签：主体 · 基准日 · 生成时间） */
export async function openResult(file) {
  state.file = file;
  try {
    const result = await getJSON('/api/results/' + encodeURIComponent(file));
    const entry = state.companies.find(c => c.id === result.run.company_id);
    const item = state.results.find(r => r.file === file);
    renderResult(fromResult(file, result, state.ctx), entry ? entry.profile : null,
      { whenLabel: item ? item.label : '' });
    $('#rh-file').value = file;
    return true;
  } catch (err) {
    renderError(err.message || err);
    return false;
  }
}

function whenLabel(r) {
  const d = new Date(r.mtime * 1000);
  const ts = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  const cid = r.run.company_id;
  const c = state.companies.find(x => x.id === cid);
  const name = c ? c.display_name : cid;
  return `${name} · 基准日 ${r.run.as_of_date} · 生成于 ${ts}`;
}

async function fillFileSelector() {
  const list = await getJSON('/api/results');
  list.forEach(r => { r.label = whenLabel(r); });
  state.results = list;
  const sel = $('#rh-file');
  if (!list.length) {
    sel.innerHTML = '<option value="">（暂无历史结果 —— 先在新建页跑一次测评）</option>';
    return list;
  }
  sel.innerHTML = list.map(r =>
    `<option value="${encodeURIComponent(r.file)}">${esc(r.label)}</option>`).join('');
  return list;
}

/* ── init ── */
async function init() {
  initNav();
  initDialogs();
  initResultEvents(() => state.companies);

  const deps = {
    getCtx: () => state.ctx,
    getCompanies: () => state.companies,
    getResults: () => state.results,
    openResult,
    go,
    refreshResults: async () => { await fillFileSelector(); refreshNewPage(); },
  };

  try {
    const [rulebook, companies] = await Promise.all([getJSON('/api/rulebook'), getJSON('/api/companies')]);
    state.companies = companies;
    state.ctx = buildCtx(rulebook, companies);

    initNewPage(deps);
    initHistory(deps);
    await fillFileSelector();
    refreshNewPage();   // 历史卡要等 results 索引就位后重画
    if (state.results.length) await openResult(state.results[0].file);   // 缺省 = 最新一份
  } catch (err) {
    renderError(err.message || err);
  }
}

$('#rh-file').addEventListener('change', e => { if (e.target.value) openResult(e.target.value); });
/* 调整重测 → 回新建页（主体/板块预选在阶段 3 打磨） */
$('#btn-rerun').addEventListener('click', () => go('new'));

init();
