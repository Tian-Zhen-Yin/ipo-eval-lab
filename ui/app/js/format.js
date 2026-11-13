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

/* 大整数 → 中文口径（80,000,000 → 8,000 万；120,000,000 → 1.2 亿）；小数原样 */
export function fmtIntCn(v) {
  if (v === null || v === undefined) return '—';
  const n = Number(v);
  const a = Math.abs(n);
  if (a >= 1e8) return `${trim((n / 1e8).toFixed(2))} 亿`;
  if (a >= 1e4) return `${trim((n / 1e4).toFixed(a >= 1e6 ? 0 : 1))} 万`;
  return fmtInt(n);
}

export const opSym = { eq: '=', ne: '≠', gt: '＞', ge: '≥', lt: '＜', le: '≤' };
const OP_ZH = { eq: '等于', ne: '不等于', gt: '大于', ge: '不低于', lt: '小于', le: '不超过' };
export const opZh = op => OP_ZH[op] || op || '';

/* 阈值 → 展示串（format 契约四值；单位白话化：大数走万/亿，不漏原始数字） */
export function fmtThr(thr) {
  if (!thr) return '—';
  const { value, format } = thr;
  if (format === 'boolean') return value === true ? '✓' : '✗';
  if (format === 'percent') return `${opSymOp(thr)} ${fmtPct(value, value * 100 % 1 ? 1 : 0)}`;
  if (format === 'integer') return `${opSymOp(thr)} ${fmtIntCn(value)}`;
  if (Number(value) === 0) return `${opSymOp(thr)} 0`;
  return `${opSymOp(thr)} ${fmtYuan(value)}`;
}

/* ── 白话翻译层：引擎英文枚举/内部标记 → 用户可读文案（原值只进弹窗） ── */
const OPINION_ZH = {
  unqualified: '标准无保留意见',
  qualified: '带事项段（非标准）',
  disclaimer: '无法表示意见',
  adverse: '否定意见',
};
export const opinionZh = o => OPINION_ZH[o] || o || '';

const REASON_RULES = [
  // 长句规则（先长后短，避免半替换）
  [/企业自估缺数据（G-[A-Z]）\s*→\s*indeterminate/g, '企业未提供估值依据，暂无法判定'],
  [/缺数据\s*→\s*indeterminate/g, '缺少数据，暂无法判定'],
  [/judgment × declared[：:]?需专业意见，?永不\s*met（declared 值只作证据）?/g, '须由专业意见核查确认（本工具不代作结论）'],
  // 硬门槛注记（引擎 hard_gate.note 原文）白话化
  [/judgment\/needs_review\s*不挡[，;；]?\s*不挡不等于\s*met（indeterminate\s*套可过闸但\s*coverage\s*<\s*100）/g,
    '专业判断项与待核查项不影响该套结论；不影响不等于已满足（数据未全覆盖的标准也可能通过该闸）'],
  [/（G-[A-Z]）/g, ''],
  // 术语白话化
  [/帕累托\s*前沿/g, '各有优势（前沿）'],
  [/帕累托/g, '四轴对比'],
  [/终态/g, '结论'],
  [/量词/g, '统计口径'],
  [/叶子级/g, '条件级'],
  [/叶子|叶表/g, '条件项'],
  [/单叶|硬叶/g, '硬性条件'],
  [/\bnot_met\b/g, '未满足'],
  [/\bindeterminate\b/g, '暂无法判定'],
  [/\bneeds_review\b/g, '待核查'],
  [/\bnot_applicable\b/g, '不适用'],
  [/\bmet\b/g, '满足'],
  [/\bgap_ratio\b/g, '缺口比例'],
  [/\bwindow_roll\b/g, '窗口滚动'],
  [/\bas_of\b/g, '基准日'],
  [/\bcoverage\b/g, '数据覆盖'],
  [/\bprogress\b/g, '进度'],
  [/\bjudgment\b/g, '专业判断项'],
];
export function friendly(s) {
  if (!s) return s;
  let out = String(s);
  for (const [re, to] of REASON_RULES) out = out.replace(re, to);
  return out;
}
const opSymOp = thr => opSym[thr.op || 'ge'] || thr.op;

/* 差距（diff 可为负=富余）→「差 X」/「富余 X」
   gap_ratio 口径（读数 = 缺口 ÷ 要求，保留两位小数）：<0.25 小 · <0.5 中 · ≥0.5 大。 */
export const GAP_TONE = r => r < 0.25 ? '小' : r < 0.5 ? '中' : '大';
export function gapText(r) {
  if (r === null || r === undefined || Number.isNaN(Number(r))) return null;
  return `缺口比例 ${fmtPct(r, 0)}（${GAP_TONE(Number(r))}）`;
}
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
/* 硬筛操作符 → 白话（新建页行业负面清单用） */
export const FILTER_OP_ZH = { not_in: '不包含', in: '属于' };

export const OUTCOME = {
  criteria_met:     { label: '满足',   st: 'met' },
  criteria_not_met: { label: '未满足', st: 'not_met' },
  indeterminate:    { label: '不可判', st: 'indeterminate' },
};

/* 法条号 → 展示（真实原文悬浮；只显示条款号，不漏英文库标识） */
export function lawTag(lawRef, laws) {
  if (!lawRef) return '';
  const [lawId, art] = String(lawRef).split('#');
  const law = laws?.[lawId];
  const artText = law?.articles?.[art.split('(')[0]]?.text;
  const title = law ? law.title : '上市规则';
  const tip = artText ? esc(`${title} 第${art}条：`) + esc(artText.slice(0, 240)) + (artText.length > 240 ? '…' : '') : esc(`${title} 第${art}条`);
  return `<span class="law" data-tip="${tip}">${esc(art)}</span>`;
}
