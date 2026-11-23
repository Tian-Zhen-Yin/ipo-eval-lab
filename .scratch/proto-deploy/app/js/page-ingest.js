/* 数据接入页（ADR-0013 修订 1；工单 04）：上传 → 校验 → 预览 → 保存 → 去测评。
   四态共用一条工作流：idle（上传）/ viol（违例清单+预填）/ prev（预览+409 覆盖确认）。
   在线改数不做（Excel 是财务的母语）；预填模板让客户只改标红格。 */

import { esc, fmtYuan } from './format.js';
import { uploadIngest, saveIngest } from './api.js';
import { showLoading, hideLoading } from './dialogs.js';

const $ = s => document.querySelector(s);

let deps = null;   // {onEnterpriseSaved}
let last = null;   // 最近一次上传响应（ok / violations）

const CID_RE = /^[a-z0-9_]+$/;

/* derived 字段的中文名（与 ingest/__main__.py 的 _DERIVED_ZH 同义，改模板科目时两处同步） */
const DERIVED_ZH = {
  'balance.minority_interests': '少数股东权益（可选，可推导）',
  'reconciliation.adjustments': '间接法调节项合计（可选，可推导）',
  'equity_roll.net_profit_attrib_parent': '权益滚动·归母净利润（恒由利润表带出）',
  'equity_roll.closing_attrib_parent': '权益滚动·期末归母权益（恒由资产负债表带出）',
  'equity_roll.opening_attrib_parent': '期初归母所有者权益（由上年期末链推）',
  'equity_roll.dividends': '本年分红（由权益恒等式残差推得）',
  'equity_roll.capital_injection': '本年增资（由权益恒等式残差推得）',
};

const AUDIT_ZH = { unqualified: '标准无保留', qualified: '保留意见', disclaimer: '无法表示意见', adverse: '否定意见' };

function setState(name) {   // idle | viol | prev
  $('#ing-idle').style.display = name === 'idle' ? '' : 'none';
  $('#ing-viol').style.display = name === 'viol' ? '' : 'none';
  $('#ing-prev').style.display = name === 'prev' ? '' : 'none';
  $('#ing-err').style.display = 'none';
  $('#ing-conflict').style.display = 'none';
  // 焦点管理（走查 P3-8）：状态切换后焦点落到该态首个操作元素，键盘用户不用从头 Tab
  const target = { idle: '#ing-drop', viol: '#ing-prefill', prev: '#ing-save' }[name];
  if (target) $(target).focus({ preventScroll: false });
}

function showErr(msg) {
  const e = $('#ing-err');
  e.textContent = msg;
  e.style.display = '';
}

async function handleFile(file) {
  if (!file) return;
  if (!/\.xlsx$/i.test(file.name)) { setState('idle'); showErr('仅接受 .xlsx 模板文件（.xls/.csv 请先另存为 .xlsx）'); return; }
  const cid = $('#ing-cid').value.trim();
  if (cid && !CID_RE.test(cid)) { setState('idle'); showErr('自定义主体 ID 仅允许小写字母、数字与下划线'); return; }
  showLoading('<b>正在校验数据…</b>', '读取模板 → 勾稽校验 → 推导未填报项');
  try {
    const out = await uploadIngest(file, cid || undefined);
    last = out;
    hideLoading();
    if (out.status === 'violations') renderViolations(out, file);
    else renderPreview(out);
  } catch (e) {
    hideLoading();
    setState('idle');
    showErr(e.message || String(e));
  }
}

/* ── 违例态：两分组——格错（带坐标，客户自己能改）/ 账不平（勾稽号）── */
function renderViolations(out, file) {
  setState('viol');
  $('#ing-viol-sub').textContent = `${file.name} · ${out.violations.length} 处违例（已一次报全，未落盘）`;
  const cell = out.violations.filter(v => v.coord);
  const acct = out.violations.filter(v => !v.coord);
  const item = v => `<li><code>${esc(v.coord ? `${v.sheet}!${v.coord}` : v.sheet)}</code>${v.label ? ` ${esc(v.label)}：` : ' '}${esc(v.reason)}</li>`;
  $('#ing-viol-groups').innerHTML = `
    ${cell.length ? `<div class="vg"><h4>格错 <span>${cell.length}</span>——模板红标格有问题，按坐标自行修改</h4><ul>${cell.map(item).join('')}</ul></div>` : ''}
    ${acct.length ? `<div class="vg vg-acct"><h4>账不平 <span>${acct.length}</span>——会计恒等式校验未过，请核对报表口径后重新填写上传</h4><ul>${acct.map(item).join('')}</ul></div>` : ''}
    <p class="vg-tip">提示：下载「预填模板」——正确值已保留、错误格清空并标红批注，填回红标格即可重新上传。</p>`;
  $('#ing-prefill').href = 'mock/prefill.xlsx';
}

/* ── 预览态：财务摘要 + derived 披露 ── */
function renderPreview(out) {
  setState('prev');
  const p = out.preview;
  $('#ing-prev-sub').textContent = `${p.display_name} · 主体 ID ${out.company_id}`;
  const row = (name, arr, f) =>
    `<tr><td>${esc(name)}</td>${p.fiscal_years.map((_, i) => `<td class="num">${f ? f(arr[i]) : esc(arr[i] ?? '—')}</td>`).join('')}</tr>`;
  $('#ing-prev-body').innerHTML = `
    <table class="t ing-tbl">
      <tr><th></th>${p.fiscal_years.map(y => `<th class="num">${y}</th>`).join('')}</tr>
      ${row('营业收入', p.revenue, fmtYuan)}
      ${row('归母净利润', p.net_profit_attrib, fmtYuan)}
      ${row('审计意见', p.audit_opinion, v => AUDIT_ZH[v] || '—')}
    </table>
    ${p.declared ? `<p class="vg-tip" style="margin-top:10px">申报口径问卷：已填 <b>${p.declared.filled} / ${p.declared.total}</b> 项，留空项按「未定」进入测评（不会默认按 0 处理）。</p>` : ''}
    ${out.derived && out.derived.length ? `
    <div class="vg vg-derived"><h4>推导字段 <span>${out.derived.length}</span>——您未填报，系统按会计恒等式推导</h4>
      <ul>${out.derived.map(d => `<li>${esc(DERIVED_ZH[d] || d)}</li>`).join('')}</ul></div>` : ''}
  `;
}

/* ── 保存（409 = 指纹确认后覆盖：对着具体数据确认，不是对着一句话）── */
async function doSave(overwrite) {
  if (!last || last.status !== 'ok') return;
  const box = $('#ing-conflict');
  box.style.display = 'none';
  showLoading('<b>正在保存主体…</b>', '写入企业主体库（enterprises/）');
  try {
    const r = await saveIngest({ company_id: last.company_id, session_dir: last.session_dir, overwrite: !!overwrite });
    hideLoading();
    if (r.ok) { await deps.onEnterpriseSaved(last.company_id); return; }
    if (r.status === 409) {
      const ex = r.data.existing || {};
      const sha = (ex.source_sha256 || '').slice(0, 8);
      box.innerHTML = `
        <b>主体已存在：${esc(last.company_id)}</b>
        <div style="margin-top:6px;font-size:12.5px">
          原数据指纹 —— 导入于 ${esc(ex.imported_at || '未知')}
          · 原件哈希 <code>${esc(sha || '未知')}</code>…${ex.display_name ? ` · ${esc(ex.display_name)}` : ''}
        </div>
        <div style="margin-top:10px;display:flex;gap:10px">
          <button class="btn btn-pri" id="ing-overwrite" type="button">覆盖替换（不可再生数据，请确认）</button>
          <button class="btn btn-ghost" id="ing-cancel-ow" type="button">取消</button>
        </div>`;
      box.style.display = '';
      $('#ing-overwrite').addEventListener('click', () => doSave(true));
      $('#ing-cancel-ow').addEventListener('click', () => { box.style.display = 'none'; });
      return;
    }
    throw new Error(r.data.error || `HTTP ${r.status}`);
  } catch (e) {
    hideLoading();
    box.textContent = e.message || String(e);
    box.style.display = '';
  }
}

/* ── init ── */
export function initIngestPage(d) {
  deps = d;
  const dz = $('#ing-drop');
  const fi = $('#ing-file');
  dz.addEventListener('click', () => fi.click());
  dz.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fi.click(); } });
  ['dragover', 'dragenter'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove('drag'); }));
  dz.addEventListener('drop', e => { const f = e.dataTransfer.files && e.dataTransfer.files[0]; if (f) handleFile(f); });
  fi.addEventListener('change', () => { if (fi.files && fi.files[0]) handleFile(fi.files[0]); fi.value = ''; });

  $('#ing-retry').addEventListener('click', () => setState('idle'));
  $('#ing-retry2').addEventListener('click', () => setState('idle'));
  $('#ing-report').addEventListener('click', () => {
    if (!last || !last.violations) return;
    const text = `企业数据接入 · 违例报告（${last.violations.length} 处，已一次报全）\n\n`
      + last.violations.map(v => `- [${v.sheet}${v.coord ? '!' + v.coord : ''}] ${v.label ? v.label + '：' : ''}${v.reason}`).join('\n')
      + '\n\n提示：下载预填模板，填回红标格后重新上传。';
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url; a.download = '违例报告.txt'; a.click();
    URL.revokeObjectURL(url);
  });
  $('#ing-save').addEventListener('click', () => doSave(false));
}
