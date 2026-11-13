/* 入口：页路由 + 数据加载（meta/rulebook/companies/results 并行）+ 结果页装配。 */

import { getJSON } from './api.js';
import { buildCtx, fromResult } from './adapters.js';
import { renderResult, renderError, initResultEvents } from './page-result.js';
import { initDialogs } from './dialogs.js';

const $ = s => document.querySelector(s);

const state = {
  ctx: null,          // {items, laws, groups, companies, meta}
  companies: [],      // /api/companies 原始列表（含 profile）
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

/* ── 结果文件加载 ── */
export async function openResult(file) {
  state.file = file;
  try {
    const result = await getJSON('/api/results/' + encodeURIComponent(file));
    const entry = state.companies.find(c => c.id === result.run.company_id);
    renderResult(fromResult(file, result, state.ctx), entry ? entry.profile : null);
    $('#rh-file').value = file;
    return true;
  } catch (err) {
    renderError(err.message || err);
    return false;
  }
}

async function fillFileSelector() {
  const list = await getJSON('/api/results');
  const sel = $('#rh-file');
  if (!list.length) {
    sel.innerHTML = '<option value="">（results/ 为空——先在新建页跑一次测评）</option>';
    return [];
  }
  sel.innerHTML = list.map(r =>
    `<option value="${encodeURIComponent(r.file)}">${r.file} · ${r.run.company_id} @${r.run.as_of_date}</option>`).join('');
  return list;
}

/* ── init ── */
async function init() {
  initNav();
  initDialogs();
  initResultEvents(() => state.companies);

  try {
    const [rulebook, companies] = await Promise.all([getJSON('/api/rulebook'), getJSON('/api/companies')]);
    state.companies = companies;
    state.ctx = buildCtx(rulebook, companies);

    const list = await fillFileSelector();
    if (list.length) await openResult(list[0].file);   // 缺省 = 最新一份
  } catch (err) {
    renderError(err.message || err);
  }
}

$('#rh-file').addEventListener('change', e => { if (e.target.value) openResult(e.target.value); });

init();
