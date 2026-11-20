/* 入口：页路由 + 数据加载（meta/rulebook/companies/results 并行）+ 页面装配。 */

import { getJSON } from './api.js';
import { buildCtx, fromResult } from './adapters.js';
import { esc } from './format.js';
import { renderResult, renderError, initResultEvents, renderRollCompare } from './page-result.js';
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

/* 结果文件加载（whenLabel = 文件选择器里该 run 的友好标签：主体 · 基准日 · 生成时间）。
   深链：?file= 同步进地址栏（push 默认开；首开恢复 / popstate 走 replace，不压历史） */
export async function openResult(file, { push = true } = {}) {
  const prev = state.file;
  state.file = file;
  try {
    const result = await getJSON('/api/results/' + encodeURIComponent(file));
    const entry = state.companies.find(c => c.id === result.run.company_id);
    const item = state.results.find(r => r.file === file);
    renderResult(fromResult(file, result, state.ctx), entry ? entry.profile : null,
      { whenLabel: item ? (item.shortLabel || item.label) : '' });
    const sel = $('#rh-file');
    sel.value = file;
    sel.title = item ? item.label : file;   // 选项文本精简后，全文靠悬浮补全
    renderRollCompare(file, result).catch(() => {});   // 窗口滚动对比（异步增强，失败不影响主结果）
    if (prev !== file) history[push ? 'pushState' : 'replaceState']({ file }, '', '?file=' + encodeURIComponent(file));
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
  return {
    full: `${name} · 基准日 ${r.run.as_of_date} · 生成于 ${ts}`,   // 悬浮全文（select title）
    opt: `${name} · ${r.run.as_of_date} · ${ts.slice(11)}`,        // 选项文本：下拉宽度有限，去掉引导词防截断
    short: `${name}（基准日 ${r.run.as_of_date}）`,                 // 面包屑用
  };
}

async function fillFileSelector() {
  const list = await getJSON('/api/results');
  list.forEach(r => { const w = whenLabel(r); r.label = w.full; r.optLabel = w.opt; r.shortLabel = w.short; });
  state.results = list;
  const sel = $('#rh-file');
  if (!list.length) {
    sel.innerHTML = '<option value="">（暂无历史结果 —— 先在新建页跑一次测评）</option>';
    return list;
  }
  sel.innerHTML = list.map(r =>
    `<option value="${encodeURIComponent(r.file)}">${esc(r.optLabel)}</option>`).join('');
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
    if (state.results.length) {
      // 缺省展示 = 基准日最新的 run（并列取生成时间新者）。
      // 不能只按文件时间：早期引擎的旧 run 可能被测试重写而时间最新，但内容不含发行条件数据。
      const best = [...state.results].sort((a, b) =>
        (b.run.as_of_date || '').localeCompare(a.run.as_of_date || '') || (b.mtime - a.mtime))[0];
      // 深链恢复：?file= 指向已存在的 run 才采用；失效/缺省回落到最新（replace，不压历史）
      const want = new URLSearchParams(location.search).get('file');
      const target = want && state.results.some(r => r.file === want) ? want : best.file;
      await openResult(target, { push: false });
      if (target === want) go('result');   // 带 ?file= 进来 = 深链分享，直达结果页
    }
  } catch (err) {
    renderError(err.message || err);
  }
}

$('#rh-file').addEventListener('change', e => { if (e.target.value) openResult(e.target.value); });
/* 后退/前进：按地址栏 ?file= 恢复结果视图（不重复压栈） */
window.addEventListener('popstate', () => {
  const f = new URLSearchParams(location.search).get('file');
  if (f && f !== state.file) openResult(f, { push: false }).then(ok => { if (ok) go('result'); });
});
/* 调整重测 → 回新建页（主体/板块预选在阶段 3 打磨） */
$('#btn-rerun').addEventListener('click', () => go('new'));

init();
