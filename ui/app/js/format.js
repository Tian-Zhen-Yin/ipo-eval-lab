/* 格式化与五态呈现（设计 0007 §3 视觉规范：色板契约级，换色需过评审）。
   单位约定（契约 v0.2 §3.3）：金额整数元、百分比小数（0.25=25%）、日期 isoformat。 */

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));

/* ── 五态（键 = result.json 全名） ── */
export const ST = {
  met:            { label: '满足',   cls: 'st-met', dot: 'd-met' },
  not_met:        { label: '未满足', cls: 'st-not', dot: 'd-not' },
  indeterminate:  { label: '不可判', cls: 'st-ind', dot: 'd-ind' },
  needs_review:   { label: '待核查', cls: 'st-rev', dot: 'd-rev' },
  not_applicable: { label: '不适用', cls: 'st-na',  dot: 'd-na' },
};

export const badge = s => {
  const t = ST[s];
  return t ? `<span class="st ${t.cls}"><i></i>${t.label}</span>`
           : `<span class="st st-ind"><i></i>${esc(s)}</span>`;
};
export const dotCls = s => (ST[s] || ST.indeterminate).dot;

/* ── 数值 ── */
const trim = n => String(n).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1');

/* 元 → 亿/万 口径展示（阈值与实测同用；tabular-nums 由全局承担） */
export function fmtYuan(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  const a = Math.abs(n);
  if (a >= 1e8) return `${trim((n / 1e8).toFixed(2))} 亿`;
  if (a >= 1e4) return `${trim((n / 1e4).toFixed(a >= 1e6 ? 0 : 1))} 万`;
  return `${trim(String(n))} 元`;
}

/* 小数 → 百分比（0.25 → 25%；0.60 → 60%） */
export function fmtPct(x, dp = 0) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return '—';
  return `${(Number(x) * 100).toFixed(dp)}%`;
}

export function fmtInt(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('zh-CN');
}

export const opSym = { eq: '=', ne: '≠', gt: '＞', ge: '≥', lt: '＜', le: '≤' };

/* 阈值 → 展示串（format 契约四值） */
export function fmtThr(thr) {
  if (!thr) return '—';
  const { value, format } = thr;
  if (format === 'boolean') return value === true ? '✓' : '✗';
  if (format === 'percent') return `${opSymOp(thr)} ${fmtPct(value, value * 100 % 1 ? 1 : 0)}`;
  if (format === 'integer') return `${opSymOp(thr)} ${fmtInt(value)}`;
  return `${opSymOp(thr)} ${fmtYuan(value)}`;
}
const opSymOp = thr => opSym[thr.op || 'ge'] || thr.op;

/* 差距（diff 可为负=富余）→「差 X」/「富余 X」 */
export function fmtDiff(diff, format = 'number') {
  if (diff === null || diff === undefined) return null;
  const v = Number(diff);
  if (Number.isNaN(v)) return null;
  if (Math.abs(v) < 1e-12) return null;
  const txt = format === 'percent' ? fmtPct(Math.abs(v), 1) : format === 'integer' ? fmtInt(Math.abs(v)) : fmtYuan(Math.abs(v));
  return v > 0 ? `差 ${txt}` : `富余 ${txt}`;
}

/* ── 条件型标签（items 表 → 白话量词） ── */
export function qLabel(item) {
  if (!item) return '';
  const q = item.quantifier, w = item.window;
  if (q === 'audit_clean') return '审计形态 · 逐年意见';
  if (q === 'latest') return '最近一年';
  if (q === 'sum' && w?.kind === 'last_n_years') return `近 ${w.n} 年累计`;
  if (q === 'sum') return '累计';
  if (q === 'all_periods') return w?.kind === 'last_n_years' ? `近 ${w.n} 年逐年` : '逐年均须';
  if (q === 'avg') return '年均';
  if (q === 'cagr') return '年复合增长率';
  if (q === 'ratio') return '比率';
  return q || '';
}

/* ── 枚举中文名 ── */
export const BOARD_NAMES = {
  'SSE-MB': '上交所主板', 'SZSE-MB': '深交所主板', STAR: '科创板', ChiNext: '创业板', BSE: '北交所',
};
export const TYPE_NAMES = {
  general: '一般企业',
  redchip_unlisted: '红筹企业（境外未上市）',
  redchip_listed: '红筹企业（已境外上市）',
  weighted_voting: '表决权差异企业',
};
export const NATURE_NAMES = { quantitative: '可计算', documentary: '填报核验', judgment: '专业判断' };

export const OUTCOME = {
  criteria_met:     { label: '满足',   st: 'met' },
  criteria_not_met: { label: '未满足', st: 'not_met' },
  indeterminate:    { label: '不可判', st: 'indeterminate' },
};

/* 法条号 → 展示（真实原文悬浮；#5 校准已收口，不再有占位标记） */
export function lawTag(lawRef, laws) {
  if (!lawRef) return '';
  const [lawId, art] = String(lawRef).split('#');
  const law = laws?.[lawId];
  const artText = law?.articles?.[art.split('(')[0]]?.text;
  const title = law ? law.title : lawId;
  const tip = artText ? esc(artText.slice(0, 240)) + (artText.length > 240 ? '…' : '') : '条文原文见规则库 rulebook/legal/';
  return `<span class="law" data-tip="${esc(title)} ${esc(art)}：${tip}">${esc(art)}<sup style="font-size:9.5px;color:var(--faint)">${esc(lawId.replace(/_\d{4}$|_recommend$|_attr$|_measure$/, ''))}</sup></span>`;
}
