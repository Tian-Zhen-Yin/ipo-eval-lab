/* 结果页渲染：消费 adapters 的视图模型，不触碰契约键名。
   交互沿原型 v0.4：事件委托（无内联 onclick）、ⓘ/溯源/口径弹窗、五态筛选。 */

import { esc, badge, dotCls, fmtYuan, fmtPct, fmtThr, ST, NATURE_NAMES } from './format.js';
import { openMask, showModal } from './dialogs.js';

const $ = s => document.querySelector(s);

let vm = null;            // 当前视图模型（fromResult 产物）
let profile = null;       // 当前公司 profile（溯源解析用）
let factsAudit = null;    // facts.audit（审计溯源用）
let curTab = null;        // 层① 当前套页签
let mxSel = {};           // 矩阵列选择
let mxFilter = 'all';

/* ── 溯源：source_ref → 真值（profile / facts.audit） ── */
function resolveRef(ref) {
  if (!profile) return { path: ref, val: null, note: '无 profile 上下文' };
  const parts = String(ref).split('.');
  if (parts[0] === 'statements') {
    const year = Number(parts[1]);
    const stmt = (profile.statements || []).find(s => s.fiscal_year === year);
    if (!stmt) return { path: ref, val: null, note: `${year} 年度无报表` };
    let node = stmt;
    for (const p of parts.slice(2)) { node = node?.[p]; }
    const aud = stmt.audit || {};
    return { path: ref, val: node, note: `${year} 年度 · 审计 ${aud.opinion || aud.status || '—'}${aud.report_id ? `（${aud.report_id}）` : ''}` };
  }
  if (parts[0] === 'documentary') {
    let node = profile.documentary;
    for (const p of parts.slice(1)) node = node?.[p];
    return { path: ref, val: node, note: '底稿填报项（documentary · worksheet）' };
  }
  if (parts[0] === 'declared') {
    let node = profile.declared;
    for (const p of parts.slice(1)) node = node?.[p];
    return { path: ref, val: node, note: '企业声明项（judgment 证据，永不判 met）' };
  }
  if (/^AUD-/.test(ref)) {
    const year = (ref.match(/AUD-(\d{4})/) || [])[1];
    const a = factsAudit && factsAudit[year];
    return { path: ref, val: a ? `${a.status}/${a.opinion || '—'}` : null, note: a ? `${year} 年度审计` : '审计档案' };
  }
  return { path: ref, val: null, note: '' };
}

function showVal(v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? '✓ 是' : '✗ 否';
  if (typeof v === 'number') return Number.isInteger(v) && Math.abs(v) >= 10000 ? esc(fmtYuan(v)) : esc(String(v));
  if (typeof v === 'object') return esc(JSON.stringify(v));
  return esc(String(v));
}

function showSrc(row) {
  const refs = row.refs || [];
  const body = refs.length
    ? `<table class="t"><tr><th>source_ref</th><th>值</th><th>期间 / 审计</th></tr>${
      refs.map(ref => {
        const r = resolveRef(ref);
        return `<tr><td style="font-family:ui-monospace,monospace;font-size:12px">${esc(ref)}</td><td><b class="num">${showVal(r.val)}</b></td><td style="font-size:12.5px;color:var(--muted)">${esc(r.note)}</td></tr>`;
      }).join('')}</table>
      <p style="margin-top:12px;color:var(--faint);font-size:12.5px">C2 source_ref：报表行项目带年度与审计意见；底稿/声明项带来源段。下钻 DWD 工作底稿属后续接入。</p>`
    : `<p style="color:var(--muted)">该行无数据来源（${esc(row.reason || '待填报/待专业意见')}）。</p>
       <p style="margin-top:10px"><span class="pill pill-w">pending</span> ${(row.pending || []).map(esc).join('；') || '补齐动作见补录弹窗'}</p>`;
  document.getElementById('ms-body').innerHTML = body;
  openMask('mask-src');
}

function showInfo(row) {
  const logicNote = row.clauseLogic === 'any'
    ? '本条为 any（或）：条文内任一支路满足即满足；旧 AND 模型会因单支路差一点而错杀整套。'
    : '本条为 all（并）：条文内各叶须全部满足。';
  showModal('测评项说明 · ' + row.name.replace(/<[^>]+>/g, ''), `
    <p style="margin-bottom:10px"><b>条件型：</b>${esc(row.q || '—')} · 阈值 ${esc(row.reqText)} · ${esc(NATURE_NAMES[row.nature] || row.nature || '')}</p>
    <p style="margin-bottom:10px"><b>判定逻辑：</b>实测值与阈值同量纲比对；百分比存小数、金额存元（契约 v0.2 §3.3）。五态：满足 / 未满足 / 不可判（缺数据 ≠ 0）/ 不适用（画像不符）/ 待核查（judgment 项，永不判 met）。</p>
    <p style="margin-bottom:10px">${esc(logicNote)}</p>
    ${row.reason ? `<p style="margin-bottom:10px"><b>本行判定说明：</b>${esc(row.reason)}</p>` : ''}
    ${row.pending.length ? `<p style="margin-bottom:10px"><b>待补证据：</b>${row.pending.map(esc).join('；')}</p>` : ''}
    <p style="color:var(--faint);font-size:12.5px">条文与阈值来自正式规则库 YAML（唯一权威源，AR1）。</p>`);
}

function showBasis(b) {
  const common = {
    '归母': [['口径定义', '归属于母公司所有者的净利润（合并利润表行项目）'], ['取值期间', '按叶量词窗口取值：sum 累计 / latest 最近一年']],
    '扣非孰低': [
      ['规则', '同一年度取「归母净利润」与「扣非归母净利润」孰低作为实测值'],
      ['逐年孰低', '按年逐期取孰低后再做量词聚合（sum / allpos），不是先合计再取孰低'],
      ['缺数处理', '任一年度扣非缺失 → 整叶转 indeterminate（不静默回退、不按 0 参与）'],
      ['依据', '设计 0005 E3「measures 逐年孰低」'],
    ],
    '自估': [
      ['规则', '市值类条件无财报来源，取值依赖企业自估（worksheet / documentary）'],
      ['限定', '一切市值类结论必须带「企业自估」限定语；缺依据 → indeterminate'],
      ['依据', 'ADR-0003（缺数据 ≠ 0）'],
    ],
    '审计意见': [['规则', '审计形态量词（audit_clean）：逐年审计意见全部为标准无保留才判满足；未审计 → indeterminate，非标 → 待核查']],
  }[b];
  if (!common) return;
  showModal('口径取值过程 · ' + b, `<table class="t">${common.map(([k, v]) => `<tr><th style="width:110px">${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</table>`);
}

/* ── 各区块渲染 ── */

function renderHeader(h) {
  $('#rh-name').innerHTML = `${h.name} <span style="color:var(--faint);font-weight:500">· ${esc(h.companyId)}</span>`;
  $('#rh-meta').innerHTML = `
    ${esc(h.boards)} · ${esc(h.type)}${h.industry ? ` · ${esc(h.industry)}` : ''} · 报告期 <b class="num">${esc(h.yearsLabel)}</b> · 审计 ${esc(h.audit)}<br>
    as_of <b class="num">${esc(h.asOf)}</b> · 规则 <span class="pill pill-b">${esc(h.rbVersion)}</span>
    <span class="pill">生效 ${h.effectiveCount} 组 · 适用套 ${h.setsCount}</span>
    <span class="pill">叶计数 满足 ${h.counts.met} · 未满足 ${h.counts.not_met} · 不可判 ${h.counts.indeterminate} · 待核查 ${h.counts.needs_review}</span>`;
  $('#run-no').textContent = h.fileLabel;
}

function renderVerdict(v) {
  const el = $('#verdict');
  if (!v) { el.style.display = 'none'; return; }
  const toneColor = v.tone === 'met' ? '#34d399' : v.tone === 'not_met' ? '#f43f5e' : '#94a3b8';
  const tagBg = v.tone === 'met' ? 'rgba(16,185,129,.12)' : v.tone === 'not_met' ? 'rgba(244,63,94,.12)' : 'rgba(148,163,184,.12)';
  const tagBd = v.tone === 'met' ? 'rgba(52,211,153,.35)' : v.tone === 'not_met' ? 'rgba(244,63,94,.35)' : 'rgba(148,163,184,.35)';
  const tagCol = v.tone === 'met' ? '#6ee7b7' : v.tone === 'not_met' ? '#fda4af' : '#cbd5e1';
  el.style.display = '';
  el.innerHTML = `
    <span class="vtag" style="background:${tagBg};border-color:${tagBd};color:${tagCol}"><span class="dot" style="background:${toneColor}"></span>${esc(v.tag)}</span>
    <h2>${v.headline}</h2>
    ${v.detail ? `<p>${esc(v.detail)}</p>` : ''}
    <span class="qual">判定措辞限定：「满足/未满足」仅指指标层面（基于所提供数据与规则版本），不构成对发行条件或上市资格的认定 —— ${esc(v.qual)}</span>`;
}

function progColor(st) {
  return { met: 'var(--met)', not_met: 'var(--notmet)', indeterminate: 'var(--indet)', needs_review: 'var(--review)' }[st] || 'var(--indet)';
}

function renderSetCards(cards) {
  $('#setcards').innerHTML = cards.map(c => `
    <div class="card setcard ${c.front ? 'front' : ''}">
      <div class="rk" ${c.excludedTip ? `data-tip="${c.excludedTip}"` : ''}>${esc(c.pathMark)}</div>
      <h4>${esc(c.label)}</h4>
      <div class="desc">${esc(c.boardsText)}${c.lawHtml ? ' · ' + c.lawHtml : ''}</div>
      <div>${badge(c.outcomeSt)}</div>
      <div class="prog">
        <div class="bar"><span style="width:${c.progress}%;background:${progColor(c.outcomeSt)}"></span></div>
        <span class="pnum num">${c.progress} 分</span>
        <span class="cover ${c.coverage < 100 ? 'low' : ''}">${c.coverage < 100 ? '⚠ ' : ''}数据覆盖 ${c.coverage}%</span>
      </div>
      <div class="counts" style="margin-top:8px">
        <span class="count"><span class="dot d-met"></span>满足 <b>${c.counts.met}</b></span>
        <span class="count"><span class="dot d-not"></span>未满足 <b>${c.counts.not_met}</b></span>
        <span class="count"><span class="dot d-ind"></span>不可判 <b>${c.counts.indeterminate}</b></span>
        ${c.counts.needs_review ? `<span class="count"><span class="dot d-rev"></span>待核查 <b>${c.counts.needs_review}</b></span>` : ''}
      </div>
      <div class="summary">${c.summaryHTML}</div>
      <div class="bline">
        ${c.bindingHTML ? `卡点：${c.bindingHTML}` : ''}
        ${c.nextHTML ? `<span class="nextline">次弱：${c.nextHTML}</span>` : ''}
      </div>
    </div>`).join('');
}

function renderSetTabs(vmData) {
  const ids = vmData.gapSets.map(s => s.group_id);
  if (!curTab || !ids.includes(curTab)) curTab = ids[0];
  $('#set-tabs').innerHTML = ids.map(gid => {
    const c = vmData.setCards.find(x => x.groupId === gid);
    return `<button class="fbtn ${gid === curTab ? 'on' : ''}" data-tab="${esc(gid)}" type="button">${esc(c ? c.label : gid)}</button>`;
  }).join('');
}

function renderLeaves(vmData) {
  const secs = (vmData.leafSectionsByGroup[curTab] || []);
  const logicPill = l => l === 'any'
    ? `<span class="pill pill-b">或 · 任一支路满足即满足</span>`
    : `<span class="pill">并 · 须全部满足</span>`;
  $('#leaf-table').innerHTML = secs.length ? `
    <table class="t">
      <tr><th style="width:29%">测评项（条件型 · 量词）</th><th style="width:13%">上市要求</th><th style="width:16%">公司数据</th><th style="width:11%" class="r">差距</th><th style="width:9%">状态</th><th style="width:22%">口径与依据</th></tr>
      ${secs.map(sec => {
        if (sec.kind === 'branch') {
          return `<tr class="secrow"><td colspan="6">${esc(sec.title)}${sec.setId ? ` <span style="font-weight:400;color:var(--faint)">${esc(sec.setId)}</span>` : ''}</td></tr>`;
        }
        return `<tr class="clrow"><td colspan="6">${esc(sec.title)} ${logicPill(sec.logic)} ${sec.lawHtml || ''}</td></tr>${
          sec.rows.map(rowLeaf).join('')}`;
      }).join('')}
    </table>` : '<p class="loadslot">该套无可展示叶子。</p>';
}

function rowLeaf(l) {
  return `<tr>
    <td><div class="leaf-name">${esc(l.name)} <span class="info-dot" data-leaf="${esc(l.leafId)}" role="button" tabindex="0">ⓘ</span></div><small>${esc(l.q)}</small></td>
    <td><b class="num">${esc(l.reqText)}</b></td>
    <td>${l.refs.length ? `<span class="val val-link num" data-src="${esc(l.leafId)}" role="button" tabindex="0" title="查看数据溯源">${l.valText}</span>` : `<span class="val num">${l.valText}</span>`}${l.ratio !== null ? `
      <div class="gapbar-wrap"><div class="gapbar"><span style="width:${Math.max(4, Math.round((1 - l.ratio) * 100))}%;background:${l.ratio > 0.5 ? 'var(--notmet)' : l.ratio > 0.25 ? '#f59e0b' : 'var(--met)'}"></span></div><small class="num gap-ratio">gap_ratio ${l.ratio.toFixed(2)}</small></div>` : ''}</td>
    <td class="r gapcell">${l.diffText ? `<b style="color:var(--notmet)">${esc(l.diffText)}</b>` : (l.state === 'met' ? '—' : (l.state === 'indeterminate' ? 'n/a' : '—'))}</td>
    <td>${badge(l.state)}</td>
    <td style="font-size:12.5px;color:var(--muted)">
      ${l.basis.map(b => `<span class="pill basis-pill ${b === '自估' ? 'pill-w' : b === '归母' ? 'pill-b' : ''}" data-basis="${esc(b)}">${esc(b)} ⓘ</span>`).join(' ')}
      ${(l.reason || l.pending.length) ? `<span class="note-tail" data-note="${esc(l.leafId)}">${esc(((l.reason || l.pending.join('；')) + '').slice(0, 18))}…</span>` : ''}
    </td>
  </tr>`;
}

function renderScen(cards) {
  const block = $('#scen-block');
  if (!cards.length) { block.style.display = 'none'; return; }
  block.style.display = '';
  $('#scen-cards').innerHTML = cards.map(s => `
    <div class="sc ${s.tone}">
      <h5><span class="dot ${s.tone === 'warn' ? 'd-not' : s.tone === 'ok' ? 'd-met' : 'd-ind'}"></span>${s.title}</h5>
      ${s.lines.map(t => `<p style="margin-top:${t === s.lines[0] ? '0' : '8px'}">${t}</p>`).join('')}
      <p style="margin-top:8px">${s.isForecast ? '<span class="pill pill-w">is_forecast</span> ' : ''}${esc(s.tail)}</p>
    </div>`).join('');
}

function renderScope(vmData) {
  const row = x => `<div class="scope-row">
    <span class="dot ${dotCls(x.state)}"></span>
    <div class="sr-main"><b>${esc(x.name)}</b><span>${esc(x.valText)}${x.reqText && x.state !== 'needs_review' && x.state !== 'indeterminate' ? `（要求 ${esc(x.reqText)}）` : ''}</span></div>
    ${badge(x.state)}</div>`;
  const logicPill = l => l === 'any'
    ? `<span class="pill pill-b">或 · 任一支路满足即满足</span>` : '';
  const groupBlock = g => `
    <div class="scope-ghead"><b>${esc(g.title)}</b>${g.outcome ? badge(({ criteria_met: 'met', criteria_not_met: 'not_met', indeterminate: 'indeterminate' })[g.outcome] || 'indeterminate') : ''}</div>
    ${g.rows.map(sec => {
      if (sec.kind === 'branch') return sec.setId ? `<div class="scope-bhead">支路 ${esc(sec.setId.split('-').pop())}</div>` : '';
      return sec.rows.map(row).join('') + (sec.logic === 'any' ? `<div class="scope-bnote">${logicPill(sec.logic)}本条文任一支路满足即满足（不因单支路差一点错杀）。</div>` : '');
    }).join('')}`;
  const note = (label, c) => `<p class="scope-note">计数守恒：${label} 满足 ${c.met} · 未满足 ${c.not_met} · 不可判 ${c.indeterminate} · 待核查 ${c.needs_review} · 不适用 0（not_applicable 不计分母）。</p>`;
  $('#issuance-list').innerHTML = vmData.issuanceGroups.map(groupBlock).join('') + note('段①', vmData.issuanceCounts);
  $('#positioning-list').innerHTML = vmData.positioningGroups.map(groupBlock).join('') + note('段②', vmData.positioningCounts);
}

function renderAxes(vmData) {
  $('#axes-table').innerHTML = `
    <tr><th>套</th><th class="r">not_met 叶数</th><th class="r">max gap_ratio</th><th class="r">时间上界</th><th class="r">不可判叶数</th><th>路径输出</th></tr>
    ${vmData.axes.map(a => `<tr>
      <td><b>${esc(a.label)}</b><div style="font-size:12px;color:var(--faint)">${esc(a.boardsText)}</div></td>
      <td class="r num"><b>${a.nm}</b></td>
      <td class="r num"><b>${a.maxGap === null ? '—' : a.maxGap.toFixed(2)}</b></td>
      <td class="r num" data-tip="${esc(a.yearsNote)}">${a.years}</td>
      <td class="r num">${a.unc}</td>
      <td>${a.pathMark[0] === '前沿' ? '<b style="color:var(--brand)">前沿</b><div style="font-size:12px;color:var(--muted)">不被任何套支配</div>'
        : a.pathMark[0] === '推荐' ? '<b style="color:var(--met)">★ 推荐</b>'
        : a.pathMark[0] === '备选' ? '<span style="color:var(--review);font-weight:650">☆ 备选</span>'
        : a.pathMark[0] === '排除' ? `<span style="color:var(--notmet);font-weight:650">排除</span> <span class="info-dot" data-excl="${esc(a.groupId)}">ⓘ</span>` : '—'}</td>
    </tr>`).join('')}`;
  const rec = vmData.path.recommendation || [], alt = vmData.path.alternatives || [];
  const fronts = vmData.path.pareto_frontier || [];
  const excl = vmData.path.excluded || [];
  const lbl = g => { const c = vmData.setCards.find(x => x.groupId === g); return c ? c.label : g; };
  // excluded[] 语义 = 不进推荐（前沿套也可能在其中：硬缺口未满足但互不支配）
  const frontSet = new Set(fronts);
  const exclTxt = excl.map(e => {
    const dominated = (e.dominated_by || []).length ? `，被 ${(e.dominated_by || []).map(lbl).join('、')} 支配` : '';
    return frontSet.has(e.group_id) ? `${lbl(e.group_id)}（有硬缺口${dominated}，仍在前沿）` : `${lbl(e.group_id)}（${esc(e.reason)}${dominated}）`;
  }).join('；');
  $('#path-note').innerHTML = `
    ${fronts.length ? `前沿 = { ${fronts.map(lbl).join('、')} }（互不支配）；` : ''}${excl.length ? `不进推荐 = ${exclTxt}；` : ''}
    <b>${rec.length ? `推荐：${rec.map(lbl).join('、')}` : alt.length ? `无推荐；备选（带不确定）：${alt.map(lbl).join('、')}` : '无 recommendation —— 存在 not_met 硬叶的套契约禁止推荐（设计 0001 §5.1）'}</b>。
    时间上界缺省 = growth 情景不适用（无来源不编年数）；不可判叶数度量数据完整度，<b>不表征审核通过概率</b>（G6）。${esc(vmData.path.hard_gate?.note || '')}`;
}

function renderAttr(a) {
  const cellHtml = key => {
    const items = a.cells[key];
    if (!items || !items.length) return '<td class="empty">—</td>';
    return `<td>${items.map(c => {
      const row = vm.rowsByLeaf[c.leaf_id];
      const name = row ? row.name : c.item_ref;
      // 有结构化差距就白话呈现（数字来自 facts.checks，非编造）；否则引擎 basis 原文
      const detail = row && row.diffText
        ? `${esc(row.diffText)}（gap_ratio ${(row.ratio ?? 0).toFixed(2)}）—— 有实测有阈值，实质缺口而非数据问题`
        : esc(c.basis || '');
      return `<span class="item"><b>${esc(name)}</b><br><span>${detail}</span></span>`;
    }).join('')}</td>`;
  };
  $('#atmx').innerHTML = `
    <table class="atmx-t">
      <tr><th style="width:150px">可核验性 ＼ 实质障碍</th>${a.OBST_COLS.map(c => `<th class="c">${esc(c[1])}<br><small style="font-weight:400;color:var(--faint)">${esc(c[2])}</small></th>`).join('')}</tr>
      ${a.VERIF_ROWS.map(r => `<tr>
        <td class="rowhead">${esc(r[1])}<br><small style="font-weight:400;color:var(--faint)">${esc(r[2])}</small></td>
        ${a.OBST_COLS.map(o => cellHtml(`${r[0]}|${o[0]}`)).join('')}
      </tr>`).join('')}
    </table>`;
}

function renderNarrative(n) {
  $('#nar-left').innerHTML = `
    <b>narrative_handoff 预览</b> —— 第四层叙述报告不在本引擎内生成。引擎输出结构化 result.json，由外部 agent 读取后复述数字（必带 refs）；本区块即该 handoff 契约的静态预览。
    <ul class="banlist">
      ${n.okExample ? `<li><span class="ok">✓</span><span>叙述层<b>能说</b>（引擎 unit 原文）：「${esc(n.okExample)}」</span></li>` : ''}
      ${n.noExample ? `<li><span class="x">✗</span><span>叙述层<b>禁说</b>：「${esc(n.noExample)}」</span></li>` : ''}
    </ul>`;
  $('#nar-right').innerHTML = `
    <b style="font-size:13px">disclaimers（免责）</b>
    <ul class="disl">${n.disclaimers.map((d, i) => `<li><b>${['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧'][i] || '·'}</b>${esc(d)}</li>`).join('')}</ul>
    <b style="font-size:13px;display:block;margin-top:12px">forbidden_claims（禁令）</b>
    <ul class="banlist">${n.forbidden.map(f => `<li><span class="x">✗</span><span>${esc(f)}</span></li>`).join('')}</ul>`;
}

/* ── 指标列表（矩阵；V17 跨列口径切换在阶段 3 加） ── */
const MX_FILTERS = [
  { k: 'all', label: '全部' },
  { k: 'met', label: '满足', color: 'var(--met)' },
  { k: 'not_met', label: '未满足', color: 'var(--notmet)' },
  { k: 'indeterminate', label: '不可判', color: 'var(--indet)' },
  { k: 'needs_review', label: '待核查', color: 'var(--review)' },
  { k: 'not_applicable', label: '不适用', color: 'var(--faint)' },
];

function renderMx(m) {
  // 列选择缺省：全选
  m.setIds.forEach(g => { if (mxSel[g] === undefined) mxSel[g] = true; });
  const cols = m.setIds.filter(g => mxSel[g]);
  $('#mx-chips').innerHTML = m.setIds.map(g => {
    const card = vm.setCards.find(c => c.groupId === g);
    return `<button class="chip ${mxSel[g] ? 'on' : ''}" data-mx="${esc(g)}" type="button">
      <span class="sc-dot" style="background:${mxSel[g] ? '#fff' : (card && card.front ? '#3b82f6' : 'var(--faint)')}"></span>${esc(m.labels[g])}
      <small style="font-weight:400;opacity:.75">${card && card.front ? '前沿' : card && card.pathMark.startsWith('✕') ? '排除' : ''}</small></button>`;
  }).join('');

  const inCols = r => cols.map(g => r.cells[g]).filter(Boolean);
  const match = (r, k) => k === 'all' ? true : inCols(r).some(c => c.state === k);
  const rows = m.rows.filter(r => match(r, mxFilter));
  $('#mx-filters').innerHTML = MX_FILTERS.map(f => {
    const n = m.rows.filter(r => match(r, f.k)).length;
    return `<button class="fbtn ${mxFilter === f.k ? 'on' : ''}" data-mf="${f.k}" type="button"
      ${f.color && mxFilter !== f.k ? `style="color:${f.color}"` : ''}>${f.color && mxFilter !== f.k ? `<i class="dot" style="background:${f.color};width:6px;height:6px"></i>` : ''}${f.label}<span class="fnum">${n}</span></button>`;
  }).join('');

  const cell = (r, g) => {
    const c = r.cells[g];
    if (!c || c.state === 'not_applicable') return '<td class="mx-na">—</td>';
    return `<td class="mx-cell"><span class="mx-b">${badge(c.state)}</span><div class="mx-thr">${esc(c.reqText)}${c.diffText ? `<span class="mx-gap">${esc(c.diffText)}</span>` : ''}${c.state === 'indeterminate' && c.reason ? `<span class="mx-gap">${esc(c.reason)}</span>` : ''}</div></td>`;
  };
  if (!cols.length) {
    $('#mx-table').innerHTML = `<tr><td style="padding:34px 0;text-align:center;color:var(--faint);font-size:13px">未选择对比标准 —— 点击上方套 chip 至少选一个</td></tr>`;
    return;
  }
  $('#mx-table').innerHTML = `
    <tr><th style="width:34px">#</th><th style="width:88px">维度</th><th style="width:24%">测评项（去重）</th><th style="width:104px">公司数据</th>${cols.map(g => `<th>${esc(m.labels[g])}</th>`).join('')}</tr>
    ${rows.length ? rows.map((r, i) => `<tr>
      <td class="mx-idx">${i + 1}</td>
      <td><span class="pill">${esc(r.dim)}</span></td>
      <td><div class="leaf-name">${esc(r.name)}</div><small>${esc(r.q)}</small></td>
      <td><b class="num">${esc(r.valText)}</b></td>
      ${cols.map(g => cell(r, g)).join('')}
    </tr>`).join('') : `<tr><td colspan="${4 + cols.length}" style="padding:34px 0;text-align:center;color:var(--faint);font-size:13px">当前筛选下无匹配项</td></tr>`}`;
}

/* ── 总渲染 ── */
export function renderResult(viewModel, companyProfile) {
  vm = viewModel;
  profile = companyProfile;
  factsAudit = vm.result.facts.audit || null;
  curTab = null;
  mxSel = {}; mxFilter = 'all';
  $('#result-error').style.display = 'none';
  renderHeader(vm.header);
  renderVerdict(vm.verdict);
  renderSetCards(vm.setCards);
  renderSetTabs(vm);
  renderLeaves(vm);
  renderScen(vm.scenCards);
  renderScope(vm);
  renderAxes(vm);
  renderAttr(vm.attr);
  renderNarrative(vm.narrative);
  renderMx(vm.matrix);
}

export function renderError(msg) {
  const el = $('#result-error');
  el.style.display = '';
  el.innerHTML = `<div class="errbox">加载结果失败：${esc(String(msg))}</div>`;
}

/* 事件委托（容器监听，替代原型内联 onclick） */
export function initResultEvents(getProfile) {
  $('#set-tabs').addEventListener('click', e => {
    const b = e.target.closest('[data-tab]');
    if (!b) return;
    curTab = b.dataset.tab;
    renderSetTabs(vm); renderLeaves(vm);
  });
  const leafTarget = e => {
    const info = e.target.closest('[data-leaf]');
    if (info) { const row = Object.values(vm.rowsByGroup).flat().find(r => r.leafId === info.dataset.leaf); if (row) showInfo(row); return true; }
    const note = e.target.closest('[data-note]');
    if (note) {
      const row = Object.values(vm.rowsByGroup).flat().find(r => r.leafId === note.dataset.note);
      if (row) showModal('口径与依据 · ' + row.name, `
        <p style="margin-bottom:10px"><b>口径：</b>${row.basis.map(esc).join('、') || '—'}</p>
        <p style="margin-bottom:10px"><b>判定说明：</b>${esc(row.reason || '—')}</p>
        ${row.pending.length ? `<p style="margin-bottom:10px"><b>待补证据：</b>${row.pending.map(esc).join('；')}</p>` : ''}`);
      return true;
    }
    const src = e.target.closest('[data-src]');
    if (src) { const row = Object.values(vm.rowsByGroup).flat().find(r => r.leafId === src.dataset.src); if (row) showSrc(row); return true; }
    const bp = e.target.closest('[data-basis]');
    if (bp) { showBasis(bp.dataset.basis); return true; }
    const excl = e.target.closest('[data-excl]');
    if (excl) {
      const x = (vm.path.excluded || []).find(x2 => x2.group_id === excl.dataset.excl);
      if (x) showModal('排除原因 · ' + (vm.setCards.find(c => c.groupId === x.group_id) || {}).label || x.group_id, `
        <p><b>原因：</b>${esc(x.reason)}</p>
        ${(x.dominated_by || []).length ? `<p style="margin-top:8px"><b>被支配于：</b>${esc((x.dominated_by || []).join('、'))}</p>` : ''}
        ${(x.hard_leaves || []).length ? `<p style="margin-top:8px"><b>硬缺口叶：</b>${x.hard_leaves.map(h => esc((vm.rowsByLeaf[h.leaf_id] || {}).name || h.item_ref) + (h.diff !== undefined && h.diff !== null ? `（差 ${esc(fmtYuan(h.diff))}）` : '')).join('；')}</p>` : ''}`);
      return true;
    }
    return false;
  };
  ['#leaf-table', '#setcards', '#axes-table', '#atmx'].forEach(sel => {
    document.querySelector(sel).addEventListener('click', leafTarget);
  });

  // 矩阵 chips / 筛选
  $('#mx-chips').addEventListener('click', e => {
    const b = e.target.closest('[data-mx]');
    if (!b) return;
    mxSel[b.dataset.mx] = !mxSel[b.dataset.mx];
    renderMx(vm.matrix);
  });
  $('#mx-filters').addEventListener('click', e => {
    const b = e.target.closest('[data-mf]');
    if (!b) return;
    mxFilter = b.dataset.mf;
    renderMx(vm.matrix);
  });

  // 键盘可达：ⓘ 支持 Enter/Space
  document.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.classList?.contains('info-dot')) {
      e.preventDefault();
      leafTarget({ target: e.target });
    }
  });
}
