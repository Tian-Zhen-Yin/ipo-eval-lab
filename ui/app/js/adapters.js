/* adapters：result.json / 规则库摘要 → 视图模型。
   数据层铁律（设计 0010 §1）：契约键名（layers.gap.progress 之类）只允许出现在本文件，
   页面代码只消费这里的视图模型 —— 引擎字段改名时只改此处。 */

import {
  esc, ST, badge, dotCls, fmtYuan, fmtPct, fmtInt, fmtThr, fmtDiff, qLabel,
  BOARD_NAMES, TYPE_NAMES, NATURE_NAMES, OUTCOME, lawTag,
} from './format.js';

/* ── 上下文：规则库摘要 + 公司夹具 → 查找表 ── */
export function buildCtx(rulebook, companies) {
  return {
    items: rulebook.items,
    laws: rulebook.laws || {},
    groups: Object.fromEntries(rulebook.groups.map(g => [g.group_id, g])),
    companies: Object.fromEntries(companies.map(c => [c.id, c])),
    meta: rulebook.meta,
  };
}

/* 组标签：display 占位值（「general 标准 None」）不出 UI。
   套组带板块短名防跨板块撞名（主板标准 1 / 科创板标准 1）。 */
const BOARD_SHORT = { 'SSE-MB': '主板', 'SZSE-MB': '主板', STAR: '科创板', ChiNext: '创业板', BSE: '北交所' };
const SECTION_NAMES = { subject_qualification: '主体资格', conduct_compliance: '规范运作' };

const groupLabel = (gid, ctx) => {
  const g = ctx.groups[gid];
  if (!g) return gid;
  if (g.scope === 'issuance') return `发行条件·${SECTION_NAMES[g.section] || g.section || gid}`;
  if (g.scope === 'positioning') return `定位·${(g.boards || []).map(b => BOARD_SHORT[b] || b).join('/')}`;
  return g.group_no
    ? `${BOARD_SHORT[(g.boards || [])[0]] || ''}标准 ${g.group_no}`
    : g.display;
};

/* refs（契约 source_ref 路径）→ 口径 pill 标签 */
function basisFromRefs(refs = []) {
  const out = [];
  const has = pat => refs.some(r => String(r).includes(pat));
  if (has('as_reported')) out.push('归母');
  if (has('excl_nonrecurring')) out.push('扣非孰低');
  if (has('mktcap') || has('self_estimate')) out.push('自估');
  if (has('AUD-')) out.push('审计意见');
  return out;
}

/* check 实测值 → 展示串（缺数据 ≠ 0：indeterminate 永远显示 reason，不显示数值） */
function valueText(c) {
  if (c.state === 'indeterminate') return c.reason || '不可判（缺数据）';
  if (c.state === 'needs_review') return '待专业意见';
  if (c.state === 'not_applicable') return '不适用';
  if (c.value === null || c.value === undefined) return '—';
  const f = c.threshold?.format;
  if (f === 'boolean') return c.value === true ? '✓ 是' : '✗ 否';
  if (f === 'percent') return fmtPct(c.value, Math.abs(c.value * 100) % 1 > 1e-9 ? 2 : 1);
  if (f === 'integer') return fmtInt(c.value);
  return fmtYuan(c.value);
}

export function checkRow(c, ctx) {
  const item = ctx.items[c.item_ref] || {};
  const lawRef = (c.refs || []).find(r => String(r).includes('#'));
  return {
    raw: c,
    leafId: c.leaf_id,
    itemRef: c.item_ref,
    clauseId: c.clause_id,
    clauseLogic: c.clause_logic,
    setId: c.set_id || null,
    groupId: c.group_id,
    state: c.state,
    name: item.display || c.item_ref,
    nature: item.nature,
    q: qLabel(item),
    reqText: fmtThr(c.threshold),
    thr: c.threshold,
    valText: valueText(c),
    diffText: c.state === 'not_met' ? fmtDiff(c.diff, c.threshold?.format) : null,
    ratio: (c.state === 'not_met' && typeof c.gap_ratio === 'number' && c.gap_ratio >= 0) ? c.gap_ratio : null,
    basis: basisFromRefs(c.refs),
    reason: c.reason,
    pending: c.pending_evidence || item.pending_evidence || [],
    refs: c.refs || [],
    lawHtml: lawTag(lawRef, ctx.laws),
  };
}

/* 叶表分区：支路（set_id）→ 条文（clause_id）两级小节头 */
function leafSections(rows, ctx) {
  const sections = [];
  let cur = null, lastSet = null, lastClause = null;
  for (const c of rows) {
    if (c.setId !== lastSet) {
      lastSet = c.setId;
      cur = null;
      sections.push({ kind: 'branch', setId: c.setId, title: c.setId ? `支路 ${c.setId.split('-').pop()}` : '共用条文', rows: [] });
      cur = sections[sections.length - 1];
      cur.rows = [];
      cur.isContainer = true;
      lastClause = null;
    }
    if (c.clauseId !== lastClause) {
      lastClause = c.clauseId;
      const meta = clauseMeta(c, ctx);
      sections.push({ kind: 'clause', clauseId: c.clauseId, title: meta.display, logic: meta.logic, lawHtml: meta.lawHtml, rows: [] });
      cur = sections[sections.length - 1];
    }
    cur.rows.push(c);
  }
  return sections.filter(s => s.kind === 'clause' || s.rows.length || s.kind === 'branch');
}

function clauseMeta(c, ctx) {
  const g = ctx.groups[c.groupId];
  const pool = [...((g && g.shared_clauses) || []), ...(((g && g.branches) || []).flatMap(b => b.clauses || []))];
  const m = pool.find(x => x.clause_id === c.clauseId);
  return {
    display: (m && m.display) || c.clauseId,
    logic: (m && m.logic) || c.clauseLogic || 'all',
    lawHtml: lawTag((m && m.law_ref) || null, ctx.laws),
  };
}

/* 结论带（措辞禁令见设计 0007 §5.2：只说指标层面，禁「预计能过」） */
function buildVerdict(vm, result, ctx) {
  const sets = vm.gapSets;
  const nMet = sets.filter(s => s.outcome === 'criteria_met').length;
  const nNot = sets.filter(s => s.outcome === 'criteria_not_met').length;
  const nInd = sets.filter(s => s.outcome === 'indeterminate').length;
  const total = sets.length;
  const rec = vm.path.recommendation || [];
  const alt = vm.path.alternatives || [];
  const name = esc(vm.displayName);
  const qual = esc((vm.nh.disclaimers || []).find(d => d.includes('上市资格')) || '上市资格由交易所/证监会认定，本工具输出为指标层面参照。');

  let tag, tone, headline, detail;
  if (rec.length) {
    tone = 'met';
    tag = '指标层面 · 有满足套';
    headline = `基于所提供数据与 as_of 规则版本，${name}在指标层面<em>满足</em> ${total} 个适用套中的 ${rec.map(l => esc(groupLabel(l, ctx))).join('、')}（帕累托推荐）。`;
    detail = alt.length ? `备选路径（带数据不确定）：${alt.map(l => esc(groupLabel(l, ctx))).join('、')}。` : '';
  } else {
    const worst = sets
      .filter(s => s.outcome === 'criteria_not_met')
      .sort((a, b) => (b.progress || 0) - (a.progress || 0))[0];
    const gapSets = sets.filter(s => s.outcome === 'criteria_not_met');
    if (gapSets.length) {
      tone = 'not_met';
      tag = '指标层面 · 未满足';
      const w = vm.setCards.find(c => c.groupId === (worst && worst.group_id));
      const others = gapSets.filter(s => s !== worst).slice(0, 2)
        .map(s => vm.setCards.find(c => c.groupId === s.group_id))
        .filter(Boolean)
        .map(c => `${esc(c.label)} 存在未满足条件${c.progress ? `（进度 ${c.progress} 分）` : ''}`);
      const scopeTxt = gapSets.length === sets.length ? `全部 ${sets.length} 个适用套` : `${gapSets.length} / ${sets.length} 个适用套`;
      headline = `基于所提供数据与 as_of 规则版本，${name}在指标层面<em>未满足</em> ${scopeTxt}${nInd ? `（另 ${nInd} 套因数据不完整<em>不可判</em>）` : ''}${w ? ` —— 缺口最小的是<em>${esc(w.label)}</em>：${w.bindingHTML}` : ''}。`;
      detail = others.length ? `${others.join('；')}。` : '';
      const highRolls = vm.rolls.filter(r => r.risk === 'high').length;
      if (highRolls) detail += ` 注意：${highRolls} 个窗口型条件在滚动一年后存在反转风险（见情景推演）。`;
    } else {
      tone = 'ind';
      tag = '指标层面 · 不可判';
      headline = `${name}的 ${total} 个适用套均因数据不完整<em>不可判</em> —— 缺哪些数据见层①明细与层③归因；本工具不做默认赋值（缺数据 ≠ 0）。`;
      detail = '';
    }
  }
  return { tone, tag, headline, detail, qual };
}

/* 套卡（v0.5：进度 + 覆盖率 + 卡点/次弱行；呈现禁令见设计 0007 §3.1） */
function bindingLine(s, rowsByGroup, ctx, key) {
  const cid = key === 'binding' ? s.binding_clause_id : s.next_binding_clause_id;
  if (!cid) return null;
  const rows = rowsByGroup[s.group_id] || [];
  const hit = rows.find(r => r.clauseId === cid && r.state === 'not_met')
    || rows.find(r => r.clauseId === cid && r.state === 'indeterminate')
    || rows.find(r => r.clauseId === cid);
  if (!hit) return null;
  if (hit.state === 'not_met') return `<b>${esc(hit.name)}</b> ${esc(hit.valText)}，要求 ${esc(hit.reqText)}${hit.diffText ? `（${esc(hit.diffText)}）` : ''}`;
  if (hit.state === 'indeterminate') return `<b>${esc(hit.name)}</b> 不可判（${esc(hit.reason || '缺数据')}）`;
  if (hit.state === 'met') return `<b>${esc(hit.name)}</b> 已满足（${esc(hit.valText)}）`;
  return null;
}

function buildSetCards(vm, result, ctx) {
  const pareto = new Set(vm.path.pareto_frontier || []);
  const rec = new Set(vm.path.recommendation || []);
  const alt = new Set(vm.path.alternatives || []);
  const excludedMap = Object.fromEntries((vm.path.excluded || []).map(e => [e.group_id, e]));
  return vm.gapSets.map(s => {
    const rows = vm.rowsByGroup[s.group_id] || [];
    const counts = { met: 0, not_met: 0, indeterminate: 0, needs_review: 0, not_applicable: 0 };
    rows.forEach(r => { if (counts[r.state] !== undefined) counts[r.state]++; });
    const st = OUTCOME[s.outcome] ? OUTCOME[s.outcome].st : 'indeterminate';
    const notMet = rows.filter(r => r.state === 'not_met');
    const inds = rows.filter(r => r.state === 'indeterminate');
    let summary;
    if (notMet.length) {
      const top = notMet.slice(0, 2).map(r => `<b>${esc(r.name)}${r.diffText ? ' ' + esc(r.diffText) : ''}</b>`).join('、');
      summary = `硬缺口：${top}${notMet.length > 2 ? ` 等 ${notMet.length} 项` : ''}${inds.length ? `；另有 ${inds.length} 项不可判` : ''}`;
    } else if (inds.length) {
      summary = `数据不完整：${inds.slice(0, 2).map(r => esc(r.name)).join('、')}${inds.length > 2 ? ` 等 ${inds.length} 项` : ''}不可判 —— 不按 0 处理`;
    } else {
      summary = `全部 ${rows.length} 项条件满足${counts.needs_review ? `（另 ${counts.needs_review} 项待核查，不挡套终态）` : ''}`;
    }
    const pathMark = rec.has(s.group_id) ? '★ 推荐路径' : alt.has(s.group_id) ? '☆ 备选（带不确定）'
      : pareto.has(s.group_id) ? '◆ 帕累托前沿'
        : excludedMap[s.group_id] ? '✕ 已排除' : '';
    const excludedTip = excludedMap[s.group_id]
      ? `排除原因：${esc(excludedMap[s.group_id].reason)}${(excludedMap[s.group_id].dominated_by || []).length ? `（被 ${(excludedMap[s.group_id].dominated_by || []).map(g => groupLabel(g, ctx)).join('、')} 支配）` : ''}`
      : '';
    return {
      groupId: s.group_id,
      label: groupLabel(s.group_id, ctx),
      boardsText: (s.boards || []).map(b => BOARD_NAMES[b] || b).join(' / '),
      outcomeSt: st,
      outcomeLabel: (OUTCOME[s.outcome] || {}).label || s.outcome,
      pathMark, excludedTip,
      front: pareto.has(s.group_id),
      progress: s.progress, coverage: s.coverage,
      counts,
      summaryHTML: summary,
      bindingHTML: bindingLine(s, vm.rowsByGroup, ctx, 'binding'),
      nextHTML: bindingLine(s, vm.rowsByGroup, ctx, 'next'),
      lawHtml: lawTag((vm.ruleGroups[s.group_id]?.law_refs || [])[0], ctx.laws),
    };
  });
}

/* 情景推演卡（数据驱动；window_roll 确定性 / growth 必带 is_forecast）。
   RISK_MAP：engine risk 值 → 中文 + 色调（medium=琥珀，与 needs_review 同语义级）。 */
const RISK_MAP = { high: ['高', 'warn'], medium: ['中', 'ind'], low: ['低', 'ok'] };

function buildScen(vm, ctx) {
  const rolls = vm.rolls.map(r => {
    const row = vm.rowsByLeaf[r.leaf_id];
    const name = row ? row.name : r.item_ref;
    const req = row ? row.reqText : '';
    const setLbl = row ? groupLabel(row.groupId, ctx) : '';
    const [riskTxt, tone] = RISK_MAP[r.risk] || [String(r.risk), 'ind'];
    const toneColor = tone === 'warn' ? 'var(--notmet)' : tone === 'ok' ? 'var(--met)' : 'var(--review)';
    const mult = (typeof r.k === 'number' && r.recent_actual) ? (r.required / r.recent_actual) : null;
    return {
      kind: 'window_roll', tone, title: `window_roll · ${esc(name)}${setLbl ? `（${esc(setLbl)} · 确定性重算）` : '（确定性重算）'}`,
      lines: [
        `当前要求 ${esc(req)}。`,
        `窗口滚动一年后，进入年需 ≥ <span class="bignum" style="color:${toneColor}">${esc(fmtYuan(r.required))}</span>`,
        `而最近一年实际 <b>${esc(fmtYuan(r.recent_actual))}</b>${mult ? `，为所需值的 <b>${esc(mult.toFixed(2))} 倍</b>${mult > 2 ? '（超 2 倍参考阈值）' : ''}` : ''} → <b style="color:${toneColor}">滚动风险：${esc(riskTxt)}</b>。`,
      ],
      tail: '该值为确定性重算（阈值 − 窗口剩余年值合计），非预测。',
      isForecast: false,
    };
  });
  const seen = new Set();
  const growth = [];
  for (const g of vm.growths) {
    const key = `${g.item_ref}|${g.hist_cagr}|${g.years_high}`;
    if (seen.has(key)) continue;  // 同 item 同参数的多套重复行只展示一次
    seen.add(key);
    const row = vm.rowsByLeaf[g.leaf_id];
    const name = row ? row.name : g.item_ref;
    growth.push({
      kind: 'growth', tone: 'ind', title: `growth · ${esc(name)}（历史 CAGR 情景）`,
      lines: [
        `历史 CAGR <b>${esc(fmtPct(g.hist_cagr, 1))}</b>；按此外推窗口年合计 ${esc(fmtYuan(g.years_low))} ~ ${esc(fmtYuan(g.years_high))}。`,
      ],
      tail: '仅作区间参考，不作为结论输出；无历史来源不编数（ADR-0004）。',
      isForecast: g.is_forecast !== false,
    });
  }
  return [...rolls, ...growth];
}

/* 层② 四轴明细（时间轴不编数：growth 不适用即「—」） */
function buildAxes(vm, ctx) {
  const pareto = new Set(vm.path.pareto_frontier || []);
  const rec = new Set(vm.path.recommendation || []);
  const alt = new Set(vm.path.alternatives || []);
  const excludedMap = Object.fromEntries((vm.path.excluded || []).map(e => [e.group_id, e]));
  return vm.gapSets.map(s => {
    const rows = vm.rowsByGroup[s.group_id] || [];
    const notMet = rows.filter(r => r.state === 'not_met');
    const gaps = notMet.map(r => r.ratio).filter(v => v !== null && v !== undefined);
    const unc = rows.filter(r => r.state === 'indeterminate').length;
    const gid = s.group_id;
    const pathMark = rec.has(gid) ? ['推荐', 'good'] : alt.has(gid) ? ['备选', 'alt']
      : pareto.has(gid) ? ['前沿', 'front'] : excludedMap[gid] ? ['排除', 'excl'] : ['—', ''];
    return {
      groupId: gid, label: groupLabel(gid, ctx),
      boardsText: (s.boards || []).map(b => BOARD_NAMES[b] || b).join('/'),
      nm: notMet.length,
      maxGap: gaps.length ? Math.max(...gaps) : null,
      unc,
      years: '—',
      yearsNote: 'growth 情景不适用即缺省（不编年数）',
      pathMark,
      excludedTip: excludedMap[gid] ? esc(excludedMap[gid].reason) : '',
    };
  });
}

/* 层③ 归因 5×3（只落有值的格） */
const VERIF_ROWS = [
  ['verified', '可核验', '财报数据齐全'],
  ['missing_data', '缺数据', '报表缺年份/缺科目'],
  ['pending_worksheet', '待底稿', '等企业填报'],
  ['pending_judgment', '待专业意见', 'judgment 项'],
  ['pending_audit', '待审计', '等审计报告'],
];
const OBST_COLS = [
  ['none', '无实质障碍', '补数据即可判'],
  ['numeric_gap', '数值缺口', '经营结果本身不足'],
  ['boolean_gap', '布尔缺口', '条件型是/否未确认'],
];
function buildAttr(vm) {
  const cells = {};  // 'ver|obs' → [items]
  for (const c of (vm.attribution.cells || [])) {
    const key = `${c.verifiability}|${c.substantive_obstacle}`;
    (cells[key] = cells[key] || []).push(c);
  }
  return { VERIF_ROWS, OBST_COLS, cells };
}

/* 指标列表矩阵（叶子按 item_ref 去重 × 套列） */
function buildMatrix(vm, ctx) {
  const setIds = vm.gapSets.map(s => s.group_id);
  const rows = [];
  const idx = {};
  for (const gid of setIds) {
    for (const r of (vm.rowsByGroup[gid] || [])) {
      let row = idx[r.itemRef];
      if (!row) {
        row = idx[r.itemRef] = {
          itemRef: r.itemRef, name: r.name, q: r.q,
          dim: NATURE_NAMES[r.nature] || r.nature || '—',
          // 公司数据列只报值；不可判行显示「—」（缺数据 ≠ 0，理由在格内 cell.reason）
          valText: (r.raw.value !== null && r.raw.value !== undefined) ? r.valText : '—',
          cells: {},
        };
        rows.push(row);
      }
      row.cells[gid] = { reqText: r.reqText, state: r.state, diffText: r.diffText, reason: r.reason };
    }
  }
  return { rows, setIds, labels: Object.fromEntries(setIds.map(g => [g, groupLabel(g, ctx)])) };
}

/* ═══ 主装配：result.json → VM ═══ */
export function fromResult(file, result, ctx) {
  const run = result.run, facts = result.facts, layers = result.layers, nh = result.narrative_handoff;
  const company = ctx.companies[run.company_id];

  // checks → 行模型 + 三张查找表
  const allRows = (facts.checks || []).map(c => checkRow(c, ctx));
  const rowsByGroup = {};
  const rowsByLeaf = {};
  const checkByLeaf = {};
  for (const r of allRows) {
    (rowsByGroup[r.groupId] = rowsByGroup[r.groupId] || []).push(r);
    rowsByLeaf[r.leafId] = r;
    checkByLeaf[r.leaf_id ?? r.leafId] = r.raw;
  }

  const setGroupIds = new Set((layers.gap.sets || []).map(s => s.group_id));
  const issGroupIds = new Set((facts.issuance || []).map(s => s.group_id));
  const posGroupIds = new Set((facts.positioning || []).map(s => s.group_id));

  const vm = {
    file,
    result,
    displayName: (company && company.display_name) || run.company_id,
    nh,
    path: layers.path || {},
    gapSets: layers.gap.sets || [],
    rolls: layers.gap.window_roll || [],
    growths: layers.gap.growth_rows || [],
    attribution: layers.attribution || { cells: [] },
    rowsByGroup, rowsByLeaf, checkByLeaf, leafById: rowsByLeaf,
    ruleGroups: ctx.groups,
    stateCounts: (() => {
      const c = { met: 0, not_met: 0, indeterminate: 0, needs_review: 0, not_applicable: 0 };
      allRows.forEach(r => { if (c[r.state] !== undefined) c[r.state]++; });
      return c;
    })(),
  };

  vm.leafSectionsByGroup = {};
  for (const gid of Object.keys(rowsByGroup)) vm.leafSectionsByGroup[gid] = leafSections(rowsByGroup[gid], ctx);

  vm.setCards = buildSetCards(vm, result, ctx);
  vm.verdict = buildVerdict(vm, result, ctx);
  vm.scenCards = buildScen(vm, ctx);
  vm.axes = buildAxes(vm, ctx);
  vm.attr = buildAttr(vm);
  vm.matrix = buildMatrix(vm, ctx);

  // 段①② 分组行（display 占位值「general 标准 None」不出 UI —— 标签由 groupLabel 派生）
  const scopeGroups = (ids, scope) => [...ids].map(gid => ({
    gid,
    title: groupLabel(gid, ctx),
    outcome: (scope === 'issuance' ? facts.issuance : facts.positioning).find(s => s.group_id === gid)?.outcome,
    rows: leafSections(rowsByGroup[gid] || [], ctx),
    counts: (() => {
      const c = { met: 0, not_met: 0, indeterminate: 0, needs_review: 0 };
      (rowsByGroup[gid] || []).forEach(r => { if (c[r.state] !== undefined) c[r.state]++; });
      return c;
    })(),
  }));
  vm.issuanceGroups = scopeGroups(issGroupIds, 'issuance');
  vm.positioningGroups = scopeGroups(posGroupIds, 'positioning');
  vm.issuance = vm.issuanceGroups.flatMap(g => g.rows.flatMap(s => s.rows || []));
  vm.positioning = vm.positioningGroups.flatMap(g => g.rows.flatMap(s => s.rows || []));
  const scopeCounts = rows => {
    const c = { met: 0, not_met: 0, indeterminate: 0, needs_review: 0 };
    rows.forEach(r => { if (c[r.state] !== undefined) c[r.state]++; });
    return c;
  };
  vm.issuanceCounts = scopeCounts(vm.issuance);
  vm.positioningCounts = scopeCounts(vm.positioning);

  // run 坐标头
  const rp = run.report_period || {};
  const ap = run.applicant_profile || {};
  const versions = run.applied_rule_versions || [];
  const rbVersion = versions[0] ? versions[0].rulebook_version : (ctx.meta && ctx.meta.rulebook_version) || '—';
  vm.header = {
    name: esc(vm.displayName),
    companyId: run.company_id,
    fileLabel: file,
    boards: run.target && run.target.boards ? run.target.boards.map(b => BOARD_NAMES[b] || b).join('、') : '全部适用板块',
    type: TYPE_NAMES[ap.company_type] || ap.company_type || '—',
    industry: ap.industry || '',
    yearsLabel: (rp.fiscal_years || []).length ? `${rp.fiscal_years[0]}–${rp.fiscal_years[rp.fiscal_years.length - 1]}（${rp.fiscal_years.length} 年${rp.stub ? '，含中期' : ''}）` : '—',
    audit: `${rp.audit_status === 'audited' ? '已审计' : rp.audit_status === 'partial' ? '部分审计' : '未审计'}${rp.audit_opinion ? ` / ${rp.audit_opinion}` : ''}`,
    asOf: run.as_of_date,
    rbVersion,
    effectiveCount: versions.length,
    setsCount: setGroupIds.size,
    counts: vm.stateCounts,
  };

  // 层④ 叙述
  const setUnits = (nh.units || []).filter(u => u.kind === 'set_outcome');
  vm.narrative = {
    okExample: setUnits[0] ? setUnits[0].text : '',
    noExample: (nh.forbidden_claims || []).find(f => f.includes('预计')) || (nh.forbidden_claims || [])[0] || '',
    disclaimers: nh.disclaimers || [],
    forbidden: nh.forbidden_claims || [],
  };

  vm.company = company || null;
  return vm;
}
