/* 结果页渲染：消费 adapters 的视图模型，不触碰契约键名。
   交互沿原型 v0.4：事件委托（无内联 onclick）、ⓘ/溯源/口径弹窗、五态筛选。 */

import { esc, badge, dotCls, fmtYuan, fmtPct, fmtThr, fmtIntCn, fmtDiff, ST, NATURE_NAMES, friendly, opZh, gapText, opinionZh } from './format.js';
import { openMask, showModal } from './dialogs.js';
import { getJSON } from './api.js';

const $ = s => document.querySelector(s);

let vm = null;            // 当前视图模型（fromResult 产物）
let profile = null;       // 当前公司 profile（溯源解析用）
let factsAudit = null;    // facts.audit（审计溯源用）
let curTab = null;        // 层① 当前套页签
let rollSeq = 0;          // 窗口滚动对比的竞态守卫（连续切换结果时只渲染最后一次）
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
    return { path: ref, val: node, note: `${year} 年度 · 审计 ${opinionZh(aud.opinion || aud.status) || '—'}${aud.report_id ? `（${aud.report_id}）` : ''}` };
  }
  if (parts[0] === 'documentary') {
    let node = profile.documentary;
    for (const p of parts.slice(1)) node = node?.[p];
    return { path: ref, val: node, note: '企业填报项（底稿）' };
  }
  if (parts[0] === 'declared') {
    let node = profile.declared;
    for (const p of parts.slice(1)) node = node?.[p];
    return { path: ref, val: node, note: '企业声明项（仅作专业判断的证据，不单独作为达标依据）' };
  }
  if (/^AUD-/.test(ref)) {
    const year = (ref.match(/AUD-(\d{4})/) || [])[1];
    const a = factsAudit && factsAudit[year];
    return { path: ref, val: a ? `${a.status}/${opinionZh(a.opinion) || '—'}` : null, note: a ? `${year} 年度审计` : '审计档案' };
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
    ? `<table class="t"><tr><th>数据项</th><th>值</th><th>期间 / 审计</th></tr>${
      refs.map(ref => {
        const r = resolveRef(ref);
        return `<tr><td style="font-family:ui-monospace,monospace;font-size:12px">${esc(ref)}</td><td><b class="num">${showVal(r.val)}</b></td><td style="font-size:12.5px;color:var(--muted)">${esc(r.note)}</td></tr>`;
      }).join('')}</table>
      <p style="margin-top:12px;color:var(--faint);font-size:12.5px">每行数值对应底表中的一个具体数据项（带年度与审计意见）；更底层的工作底稿属后续接入。</p>`
    : `<p style="color:var(--muted)">该行无数据来源（${esc(row.reasonF || row.reason || '待填报或待专业意见')}）。</p>
       <p style="margin-top:10px"><span class="pill pill-w">待补</span> ${(row.pending || []).map(esc).join('；') || '补齐动作见补录弹窗'}</p>`;
  document.getElementById('ms-body').innerHTML = body;
  openMask('mask-src');
}

function showInfo(row) {
  const logicNote = row.clauseLogic === 'any'
    ? '本条包含多个可选路径：任一满足即可，不因单一路径略差而整体不通过。'
    : '本条各细项须全部满足。';
  showModal('测评项说明 · ' + row.name.replace(/<[^>]+>/g, ''), `
    <p style="margin-bottom:10px"><b>条件类型：</b>${esc(row.q || '—')} · 要求 ${esc(row.reqText)} · ${esc(NATURE_NAMES[row.nature] || row.nature || '')}</p>
    <p style="margin-bottom:10px"><b>判定方式：</b>实测值与要求同口径比对。五种结果：满足 / 未满足 / 暂无法判定（缺数据不会当作 0）/ 不适用（企业情况不符合该条件）/ 待核查（须专业意见，工具不代作结论）。</p>
    <p style="margin-bottom:10px">${esc(logicNote)}</p>
    ${row.reasonF ? `<p style="margin-bottom:10px"><b>本行判定说明：</b>${esc(row.reasonF)}</p>` : ''}
    ${row.pending.length ? `<p style="margin-bottom:10px"><b>待补材料：</b>${row.pending.map(esc).join('；')}</p>` : ''}
    <p style="color:var(--faint);font-size:12.5px">条款与阈值来自正式规则库（唯一权威源）。</p>`);
}

function showBasis(b) {
    const common = {
    '归母': [['口径定义', '归属于母公司所有者的净利润（合并利润表行项目）'], ['取值期间', '按条件的量词窗口取值：累计 / 最近一年']],
    '扣非孰低': [
      ['规则', '同一年度取「归母净利润」与「扣非归母净利润」孰低作为实测值'],
      ['逐年孰低', '按年逐期取孰低后再做量词聚合（累计 / 逐年），不是先合计再取孰低'],
      ['缺数处理', '任一年度扣非缺失 → 整项转暂无法判定（不静默回退、不按 0 参与）'],
      ['依据', '「measures 逐年孰低」口径'],
    ],
    '自估': [
      ['规则', '市值类条件无财报来源，取值依赖企业自估（填报 / 声明项）'],
      ['限定', '一切市值类结论必须带「企业自估」限定语；缺依据 → 暂无法判定'],
      ['依据', '缺数据 ≠ 0 原则'],
    ],
    '审计意见': [['规则', '审计形态条件：逐年审计意见全部为标准无保留才判满足；未审计 → 暂无法判定，非标 → 待核查']],
  }[b];
  if (!common) return;
  showModal('口径取值过程 · ' + b, `<table class="t">${common.map(([k, v]) => `<tr><th style="width:110px">${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</table>`);
}

/* ── 各区块渲染 ── */

function renderHeader(h, whenLabel) {
  $('#rh-name').innerHTML = `${h.name}`;
  // 字段网格（替代「·」串联流水账）+ 彩色判定统计条
  $('#rh-meta').innerHTML = `
    <div class="rh-grid">
      <div><label>拟上市板块</label><b>${esc(h.boards)}</b></div>
      <div><label>企业类型</label><b>${esc(h.type)}</b></div>
      ${h.industry ? `<div><label>行业</label><b>${esc(h.industry)}</b></div>` : ''}
      <div><label>报告期</label><b class="num">${esc(h.yearsLabel)}</b></div>
      <div><label>审计</label><b>${esc(h.audit)}</b></div>
      <div><label>测评基准日</label><b class="num">${esc(h.asOf)}</b></div>
    </div>
    <div class="rh-stats">
      <span class="pill pill-b">规则 ${(h.rbVersion || '').replace(/^rb-/, '')} 版</span>
      <span class="pill">适用上市标准 ${h.setsCount} 个</span>
      <span class="rh-div"></span>
      <span class="statchip s-met">满足 <b>${h.counts.met}</b></span>
      <span class="statchip s-not">未满足 <b>${h.counts.not_met}</b></span>
      <span class="statchip s-ind">暂无法判定 <b>${h.counts.indeterminate}</b></span>
      ${h.counts.needs_review ? `<span class="statchip s-rev">待核查 <b>${h.counts.needs_review}</b></span>` : ''}
    </div>`;
  $('#run-no').textContent = whenLabel || '';
}

function renderVerdict(v) {
  const el = $('#verdict');
  if (!v) { el.style.display = 'none'; return; }
  el.style.display = '';
  el.className = `verdict vt-${v.tone}`;
  el.innerHTML = `
    <span class="vtag"><span class="dot"></span>${esc(v.tag)}</span>
    <h2>${v.headline}</h2>
    ${v.points && v.points.length ? `<ul class="vpoints">${v.points.map(p => `<li>${p}</li>`).join('')}</ul>` : ''}
    <span class="qual">注：以上为指标层面的判定结果，不代表发行条件或上市资格的最终认定 —— 上市资格由交易所/证监会审核确定。</span>`;
}

function progColor(st) {
  return { met: 'var(--met)', not_met: 'var(--notmet)', indeterminate: 'var(--indet)', needs_review: 'var(--review)' }[st] || 'var(--indet)';
}

function renderSetCards(cards) {
  $('#setcards').innerHTML = cards.map(c => `
    <div class="card setcard ${c.front ? 'front' : ''}">
      <div class="rk" ${c.excludedTip ? `data-tip="${c.excludedTip}"` : c.frontTip ? `data-tip="${c.frontTip}"` : ''}>${esc(c.pathMark)}</div>
      <h4>${esc(c.label)}</h4>
      <div class="desc">${esc(c.boardsText)}${c.lawHtml ? ' · ' + c.lawHtml : ''}</div>
      <div>${badge(c.outcomeSt)}</div>
      <div class="prog">
        <div class="bar" data-tip="进度条：已可判定条件的占比"><span style="width:${c.progress}%;background:${progColor(c.outcomeSt)}"></span></div>
        <span class="pdiv">·</span>
        <span class="cover ${c.coverage < 100 ? 'low' : ''}">${c.coverage < 100 ? '⚠ 数据覆盖 ' + c.coverage + '%' : '数据全覆盖'}</span>
      </div>
      <div class="counts">
        <span>满足 <b class="c-met">${c.counts.met}</b></span>
        <span>未满足 <b class="c-not">${c.counts.not_met}</b></span>
        <span>暂无法判定 <b class="c-ind">${c.counts.indeterminate}</b></span>
        ${c.counts.needs_review ? `<span>待核查 <b class="c-rev">${c.counts.needs_review}</b></span>` : ''}
      </div>
      <div class="summary tone-${c.outcomeSt}">${c.summaryHTML}</div>
      <div class="bline">
        ${c.bindingHTML ? `主要卡点：${c.bindingHTML}` : ''}
        ${c.nextHTML ? `<span class="nextline">下一项：${c.nextHTML}</span>` : ''}
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
    ? `<span class="pill pill-b">或 · 任一路径满足即满足</span>`
    : `<span class="pill">并 · 须全部满足</span>`;
  $('#leaf-table').innerHTML = secs.length ? `
    <table class="t">
      <tr><th>条件与统计口径</th><th>上市要求</th><th>公司数据</th><th class="r">差距</th><th>结果</th><th>取值口径</th></tr>
      ${secs.map(sec => {
        if (sec.kind === 'branch') {
          return `<tr class="secrow"><td colspan="6">${esc(sec.title)}</td></tr>`;
        }
        return `<tr class="clrow"><td colspan="6">${esc(sec.title)} ${logicPill(sec.logic)} ${sec.lawHtml || ''}</td></tr>${
          sec.rows.map(rowLeaf).join('')}`;
      }).join('')}
    </table>` : '<p class="loadslot">该标准暂无可展示的条件。</p>';
}

function rowLeaf(l) {
  return `<tr>
    <td><div class="leaf-name">${esc(l.name)} <span class="info-dot" data-leaf="${esc(l.leafId)}" role="button" tabindex="0">ⓘ</span></div><small>${esc(l.q)}</small></td>
    <td><b class="num">${esc(l.reqText)}</b></td>
    <td>${l.refs.length ? `<span class="val val-link num" data-src="${esc(l.leafId)}" role="button" tabindex="0" title="查看数据溯源">${l.valText}</span>` : `<span class="val num">${l.valText}</span>`}${l.ratio !== null ? `
      <div class="gapbar-wrap"><div class="gapbar"><span style="width:${Math.max(4, Math.round((1 - l.ratio) * 100))}%;background:${l.ratio > 0.5 ? 'var(--notmet)' : l.ratio > 0.25 ? '#f59e0b' : 'var(--met)'}"></span></div><small class="gap-ratio">${esc(gapText(l.ratio))}</small></div>` : ''}</td>
    <td class="r gapcell">${l.diffText ? `<b style="color:var(--notmet)">${esc(l.diffText)}</b>` : (l.state === 'met' ? '—' : (l.state === 'indeterminate' ? '—' : '—'))}</td>
    <td>${badge(l.state)}</td>
    <td style="font-size:12.5px;color:var(--muted)">
      ${l.basis.map(b => `<span class="pill basis-pill ${b === '自估' ? 'pill-w' : b === '归母' ? 'pill-b' : ''}" data-basis="${esc(b)}">${esc(b)} ⓘ</span>`).join(' ')}
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
      <p style="margin-top:8px">${s.isForecast ? '<span class="pill pill-w">推算值</span> ' : ''}${esc(s.tail)}</p>
    </div>`).join('');
}

/* ── 窗口滚动对比（跨申报时点）：随当前主体定位；同主体存在报告期不同的多次测评才显示。
   数据 = /api/results 索引 → 同 company_id 的各 run 全量；当前 run 列标「当前」。 ── */
const ROLL_OUTCOME = {
  criteria_met: ['满足', 'd-met'],
  criteria_not_met: ['未满足', 'd-not'],
  indeterminate: ['暂无法判定', 'd-ind'],
};
export async function renderRollCompare(file, result) {
  const seq = ++rollSeq;
  const card = $('#rollcmp-card'), body = $('#rollcmp-body');
  if (!card || !result) return;
  try {
    const cid = result.run.company_id;
    const index = await getJSON('/api/results');
    const runs = [{ file, run: result.run, gapSets: result.layers.gap.sets || [], current: true }];
    for (const item of index) {
      if (item.file === file || item.run.company_id !== cid) continue;
      const full = await getJSON('/api/results/' + encodeURIComponent(item.file));
      runs.push({ file: item.file, run: full.run, gapSets: full.layers.gap.sets || [], current: false });
    }
    // 老窗口在前（锚年升序）
    runs.sort((a, b) => {
      const fa = a.run.report_period?.fiscal_years || [], fb = b.run.report_period?.fiscal_years || [];
      return (fa[fa.length - 1] - fb[fb.length - 1]) || (a.file < b.file ? -1 : 1);
    });
    const wins = new Set(runs.map(r => (r.run.report_period?.fiscal_years || []).join('-')));
    if (seq !== rollSeq) return;                    // 已有更新的结果载入，放弃本次渲染
    if (wins.size < 2) { card.style.display = 'none'; return; }
    const outcomeOf = (r, gid) => {
      const s = (r.gapSets || []).find(x => x.group_id === gid);
      return s ? s.outcome : null;
    };
    const gids = [];
    for (const r of runs) for (const s of r.gapSets) if (!gids.includes(s.group_id)) gids.push(s.group_id);
    const reversed = gids.filter(g => new Set(runs.map(r => outcomeOf(r, g))).size > 1);
    // 套名复用视图模型里 adapters 已转好的中文标签（setCards 覆盖当前适用套；跨 run 同板同名）
    const shortLabel = gid => {
      const c = (vm && vm.setCards || []).find(c => c.groupId === gid);
      return c ? c.label : gid;
    };
    const winLbl = r => {
      const fy = r.run.report_period?.fiscal_years || [];
      return `${fy[0]}–${fy[fy.length - 1]} 年报口径`;
    };
    body.innerHTML = `
      <div style="font-size:12.5px;color:var(--muted);margin-bottom:10px">
        ${esc(vm.displayName || cid)} · ${runs.length} 个申报时点（同一底表的逐字重算）
        ${reversed.length ? `<span class="pill pill-w" style="margin-left:8px">${reversed.map(g => esc(shortLabel(g))).join('、')} 结论反转</span>` : '<span class="pill" style="margin-left:8px">各套结论未随窗口滚动变化</span>'}
      </div>
      <table class="t roll-t">
        <tr><th style="text-align:left">标准</th>${runs.map(r => `
          <th style="text-align:left">${esc(winLbl(r))}${r.current ? ' <span class="pill pill-b">当前</span>' : ''}
            <div style="font-weight:400;font-size:11px;color:var(--faint)">基准日 ${esc(r.run.as_of_date)}</div></th>`).join('')}
        </tr>
        ${gids.map(g => `<tr>
          <td style="white-space:nowrap">${esc(shortLabel(g))}</td>
          ${runs.map((r, j) => {
            const o = outcomeOf(r, g);
            const [txt, dot] = ROLL_OUTCOME[o] || [o || '—', 'd-ind'];
            const flip = j > 0 && o && outcomeOf(runs[j - 1], g) !== o;
            return `<td style="white-space:nowrap"><span class="dot ${dot}"></span> ${txt}${flip ? ' <span class="pill pill-w">反转</span>' : ''}</td>`;
          }).join('')}
        </tr>`).join('')}
      </table>`;
    card.style.display = '';
  } catch (err) {
    card.style.display = 'none';   // 对比数据拉取失败 → 静默隐藏，不影响主结果展示
  }
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
      if (sec.kind === 'branch') return sec.setId ? `<div class="scope-bhead">可选路径 ${esc(sec.setId.split('-').pop())}</div>` : '';
      return sec.rows.map(row).join('') + (sec.logic === 'any' ? `<div class="scope-bnote">${logicPill(sec.logic)}本条文任一路径满足即整体满足（不因单路径差一点而错杀）。</div>` : '');
    }).join('')}`;
  const note = (label, c) => `<p class="scope-note">统计：满足 ${c.met} · 未满足 ${c.not_met} · 暂无法判定 ${c.indeterminate} · 待核查 ${c.needs_review}（不适用项不计入）。</p>`;
  // 早期 run 无该段数据 → 显式说明，不出「全 0 统计」（用户会误以为工具坏了）
  const emptyNote = `<p style="padding:10px 0;color:var(--faint);font-size:13px">该次测评未包含此部分数据（早期版本的测评记录）——切换右上角选择器查看新测评。</p>`;
  $('#issuance-list').innerHTML = vmData.issuanceGroups.length
    ? vmData.issuanceGroups.map(groupBlock).join('') + note('段①', vmData.issuanceCounts)
    : emptyNote;
  $('#positioning-list').innerHTML = vmData.positioningGroups.length
    ? vmData.positioningGroups.map(groupBlock).join('') + note('段②', vmData.positioningCounts)
    : emptyNote;
}

function renderAxes(vmData) {
  // 「时间上界」一列当前恒为「—」（growth 不适用时不编年数）——整列撤掉，说明并入脚注
  $('#axes-table').innerHTML = `
    <tr><th>上市标准</th><th class="r">未满足项数</th><th class="r">最大缺口</th><th class="r">暂无法判定项数</th><th title="按四轴对比与硬性条件闸门筛选后的推荐情况：推荐 / 前沿（互不支配、各有优势）/ 未进推荐">推荐情况</th></tr>
    ${vmData.axes.map(a => `<tr>
      <td><b>${esc(a.label)}</b><div style="font-size:12px;color:var(--faint)">${esc(a.boardsText)}</div></td>
      <td class="r num"><b>${a.nm}</b></td>
      <td class="r num"><b>${a.maxGap === null ? '—' : esc(gapText(a.maxGap))}</b></td>
      <td class="r num">${a.unc}</td>
      <td>${a.pathMark[0] === '前沿' ? `<b style="color:var(--brand)" title="四轴对比中不被其他标准全面优于（各有优势）">前沿</b>`
        : a.pathMark[0] === '推荐' ? '<b style="color:var(--met)">★ 推荐</b>'
        : a.pathMark[0] === '备选' ? '<span style="color:var(--review);font-weight:650">☆ 备选</span>'
        : a.pathMark[0] === '排除' ? `<span style="color:var(--notmet);font-weight:650">未进推荐</span> <span class="info-dot" data-excl="${esc(a.groupId)}">ⓘ</span>` : '—'}</td>
    </tr>`).join('')}`;
  const rec = vmData.path.recommendation || [], alt = vmData.path.alternatives || [];
  const fronts = vmData.path.pareto_frontier || [];
  const lbl = g => { const c = vmData.setCards.find(x => x.groupId === g); return c ? c.label : g; };
  // 低密度结论区：只留「结论行 + 前沿补充一行 + 可折叠口径说明」。
  // 逐套明细（哪个标准、什么原因、被谁支配）上表的标记与 ⓘ 弹窗已承接，这里不复述。
  const verdict = rec.length
    ? `<span class="st st-met"><i></i>推荐</span><b>${esc(rec.map(lbl).join('、'))}</b>`
    : alt.length
      ? `<span class="st st-rev"><i></i>无推荐</span><span>备选（数据尚不完整，带不确定）：<b>${esc(alt.map(lbl).join('、'))}</b></span>`
      : `<span class="st st-not"><i></i>无推荐</span><span>存在未满足硬性条件的标准，本工具不作推荐</span>`;
  // 前沿但未进推荐的套：唯一值得点名的细节（各有优势但没过硬性条件闸）
  const frontsNotRec = fronts.filter(g => !rec.includes(g));
  const frontLine = frontsNotRec.length
    ? `<div class="pn-line"><b>前沿</b>（各有优势、不被任何标准全面优于）：${esc(frontsNotRec.map(lbl).join('、'))}——各有优势但未进推荐，原因见表内 ⓘ</div>`
    : '';
  const footNotes = [
    '时间上界缺省 = 增长情景不适用（无来源不编年数）',
    '暂无法判定项数度量数据完整度，<b>不代表审核通过概率</b>',
    friendly(vmData.path.hard_gate?.note || ''),
  ].filter(Boolean);
  const footHtml = footNotes.length
    ? `<details class="pn-more"><summary>口径说明（${footNotes.length}）</summary><ul class="pn-foot">${footNotes.map(t => `<li>${t}</li>`).join('')}</ul></details>`
    : '';
  $('#path-note').innerHTML = `
    <div class="pn-verdict">${verdict}</div>
    ${frontLine}
    ${footHtml}`;
}

function renderAttr(a) {
  const cellHtml = key => {
    const items = a.cells[key];
    if (!items || !items.length) return '<td class="empty">—</td>';
    return `<td>${items.map(c => {
      const row = vm.rowsByLeaf[c.leaf_id];
      const name = row ? row.name : c.item_ref;
      // 有结构化差距就白话呈现（数字来自实测与阈值）；否则用判定说明原文（已白话化）
      const detail = row && row.diffText
        ? `${esc(row.diffText)}（${esc(gapText(row.ratio ?? 0))}）—— 有实测有阈值，属实质缺口而非数据问题`
        : esc(friendly(c.basis) || '—');
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
  // 报告生成说明/复述示例/表述禁令是给报告撰写方（agent）的契约，不上界面；界面只保留免责事项
  $('#nar-right').innerHTML = `
    <ul class="disl">${n.disclaimers.map((d, i) => `<li><b>${['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧'][i] || '·'}</b>${esc(d)}</li>`).join('')}</ul>`;
}

/* ── 指标列表（矩阵；V17：跨列口径切换 = 任一列命中 / 全部列命中） ── */
const MX_FILTERS = [
  { k: 'all', label: '全部' },
  { k: 'met', label: '满足', color: 'var(--met)' },
  { k: 'not_met', label: '未满足', color: 'var(--notmet)' },
  { k: 'indeterminate', label: '暂无法判定', color: 'var(--indet)' },
  { k: 'needs_review', label: '待核查', color: 'var(--review)' },
  { k: 'not_applicable', label: '不适用', color: 'var(--faint)' },
];
let mxScope = 'any';   // any=任一列命中（缺省） | all=全部可见列命中（不适用列不参与）

function renderMx(m) {
  // 列选择缺省：全选
  m.setIds.forEach(g => { if (mxSel[g] === undefined) mxSel[g] = true; });
  const cols = m.setIds.filter(g => mxSel[g]);
  $('#mx-chips').innerHTML = m.setIds.map(g => {
    const card = vm.setCards.find(c => c.groupId === g);
    return `<button class="chip ${mxSel[g] ? 'on' : ''}" data-mx="${esc(g)}" type="button">
      <span class="sc-dot" style="background:${mxSel[g] ? '#fff' : (card && card.front ? '#3b82f6' : 'var(--faint)')}"></span>${esc(m.labels[g])}
      <small style="font-weight:400;opacity:.75">${card && card.front ? '前沿' : card && card.pathMark.startsWith('✕') ? '未进推荐' : ''}</small></button>`;
  }).join('');

  const inCols = r => cols.map(g => r.cells[g]).filter(Boolean);
  // 筛选是视图参数（≠契约五态，评审 0004 V17 处置）：计数只数当前可见列
  const match = (r, k) => {
    if (k === 'all') return true;
    const cells = inCols(r);
    if (mxScope === 'all') return cols.length > 0 && cells.length === cols.length && cells.every(c => c.state === k);
    return cells.some(c => c.state === k);
  };
  const rows = m.rows.filter(r => match(r, mxFilter));
  $('#mx-filters').innerHTML = `
    <span class="fbtn-group" style="display:inline-flex;gap:4px;margin-right:6px">
      <button class="fbtn ${mxScope === 'any' ? 'on' : ''}" data-ms="any" type="button" title="该条件在任一所选标准中命中即计入">任一标准满足</button>
      <button class="fbtn ${mxScope === 'all' ? 'on' : ''}" data-ms="all" type="button" title="该条件在全部所选标准中都命中才计入（不适用列不参与）">全部标准满足</button>
    </span>`
    + MX_FILTERS.map(f => {
      const n = m.rows.filter(r => match(r, f.k)).length;
      return `<button class="fbtn ${mxFilter === f.k ? 'on' : ''}" data-mf="${f.k}" type="button"
        ${f.color && mxFilter !== f.k ? `style="color:${f.color}"` : ''}>${f.color && mxFilter !== f.k ? `<i class="dot" style="background:${f.color};width:6px;height:6px"></i>` : ''}${f.label}<span class="fnum">${n}</span></button>`;
    }).join('');

  const cell = (r, g) => {
    const c = r.cells[g];
    if (!c || c.state === 'not_applicable') return '<td class="mx-na">—</td>';
    return `<td class="mx-cell"><span class="mx-b">${badge(c.state)}</span><div class="mx-thr">${esc(c.reqText)}${c.diffText ? `<span class="mx-gap">${esc(c.diffText)}</span>` : ''}${c.state === 'indeterminate' && c.reason ? `<span class="mx-gap">${esc(friendly(c.reason))}</span>` : ''}</div></td>`;
  };
  if (!cols.length) {
    $('#mx-table').innerHTML = `<tr><td style="padding:34px 0;text-align:center;color:var(--faint);font-size:13px">未选择对比标准 —— 点击上方标准名称至少选一个</td></tr>`;
    return;
  }
  $('#mx-table').innerHTML = `
    <tr><th style="width:34px">#</th><th style="width:88px">维度</th><th style="width:24%">测评项（去重）</th><th style="width:104px">公司数据</th>${cols.map(g => `<th class="mx-col">${esc(m.labels[g])}</th>`).join('')}</tr>
    ${rows.length ? rows.map((r, i) => `<tr>
      <td class="mx-idx">${i + 1}</td>
      <td><span class="pill">${esc(r.dim)}</span></td>
      <td><div class="leaf-name">${esc(r.name)}</div><small>${esc(r.q)}</small></td>
      <td><b class="num">${esc(r.valText)}</b></td>
      ${cols.map(g => cell(r, g)).join('')}
    </tr>`).join('') : `<tr><td colspan="${4 + cols.length}" style="padding:34px 0;text-align:center;color:var(--faint);font-size:13px">当前筛选下无匹配项</td></tr>`}`;
}

/* ── 总渲染 ── */
export function renderResult(viewModel, companyProfile, opts = {}) {
  vm = viewModel;
  profile = companyProfile;
  factsAudit = vm.result.facts.audit || null;
  curTab = null;
  mxSel = {}; mxFilter = 'all';
  $('#result-error').style.display = 'none';
  renderHeader(vm.header, opts.whenLabel);
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
        <p style="margin-bottom:10px"><b>判定说明：</b>${esc(row.reasonF || '—')}</p>
        ${row.pending.length ? `<p style="margin-bottom:10px"><b>待补材料：</b>${row.pending.map(esc).join('；')}</p>` : ''}`);
      return true;
    }
    const src = e.target.closest('[data-src]');
    if (src) { const row = Object.values(vm.rowsByGroup).flat().find(r => r.leafId === src.dataset.src); if (row) showSrc(row); return true; }
    const bp = e.target.closest('[data-basis]');
    if (bp) { showBasis(bp.dataset.basis); return true; }
    const excl = e.target.closest('[data-excl]');
    if (excl) {
      const x = (vm.path.excluded || []).find(x2 => x2.group_id === excl.dataset.excl);
      if (x) showModal('未进推荐的原因 · ' + (vm.setCards.find(c => c.groupId === x.group_id) || {}).label || x.group_id, `
        <p><b>原因：</b>${esc(friendly(x.reason) || x.reason)}</p>
        ${(x.dominated_by || []).length ? `<p style="margin-top:8px"><b>被全面优于：</b>${esc((x.dominated_by || []).map(g => { const c = vm.setCards.find(y => y.groupId === g); return c ? c.label : g; }).join('、'))}</p>` : ''}
        ${(x.hard_leaves || []).length ? `<p style="margin-top:8px"><b>硬缺口项：</b>${x.hard_leaves.map(h => esc((vm.rowsByLeaf[h.leaf_id] || {}).name || h.item_ref) + (h.diff !== undefined && h.diff !== null ? `（${esc(fmtDiff(h.diff, 'number') || '')}）` : '')).join('；')}</p>` : ''}`);
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
    const ms = e.target.closest('[data-ms]');
    if (ms) { mxScope = ms.dataset.ms; renderMx(vm.matrix); return; }
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
