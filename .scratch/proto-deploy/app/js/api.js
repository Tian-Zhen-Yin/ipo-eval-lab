/* 原型 mock API（静态部署专用，替换真实 api.js；页面代码零改动）。
   GET → 内嵌 mock/*.json；POST → 内嵌剧本；上传按文件名路由演示态。 */

const delay = ms => new Promise(r => setTimeout(r, ms));

const GET_MAP = {
  '/api/rulebook': 'mock/rulebook.json',
  '/api/companies': 'mock/companies.json',
  '/api/enterprises': 'mock/enterprises.json',
  '/api/results': 'mock/results-index.json',
};

export async function getJSON(path) {
  await delay(100);
  if (GET_MAP[path]) {
    const r = await fetch(GET_MAP[path]);
    if (!r.ok) throw new Error(`mock 数据缺失：${GET_MAP[path]}`);
    return r.json();
  }
  const m = path.match(/^\/api\/results\/(.+)$/);
  if (m) {
    const r = await fetch('mock/results/' + decodeURIComponent(m[1]));
    if (!r.ok) throw new Error('mock 结果缺失');
    return r.json();
  }
  throw new Error(`原型模式：该接口未模拟（${path}）`);
}

export async function postJSON(path) {
  await delay(700);
  if (path === '/api/run') return { file: 'hszn_01_2026-11-21.json' };  // 直接回放样例企业的真实结果
  if (path === '/api/ingest/save') return { saved: 'enterprises/hszn_01', company_id: 'hszn_01' };
  throw new Error(`原型模式：该接口未模拟（${path}）`);
}

/* 上传剧本：文件名带「坏」→ 违例态；带「示例」→ 通过预览；其余（如空白模板）→ 缺必填违例 */
const PREVIEW_OK = {
  status: 'ok', violations: [], company_id: 'hszn_01', upload_id: 'mock',
  session_dir: 'mock-session',
  derived: ['balance.minority_interests', 'reconciliation.adjustments',
            'equity_roll.net_profit_attrib_parent', 'equity_roll.closing_attrib_parent'],
  preview: {
    display_name: '深圳华晟智能装备股份有限公司',
    fiscal_years: [2023, 2024, 2025],
    revenue: [120000000, 150000000, 180000000],
    net_profit_attrib: [15000000, 18000000, 22000000],
    audit_opinion: ['unqualified', 'unqualified', 'unqualified'],
    declared: { filled: 10, total: 30 },
  },
};

const VIOL = items => ({
  status: 'violations', violations: items, company_id: 'ent_demo',
  upload_id: 'mock', session_dir: null,
});

export async function uploadIngest(file) {
  await delay(900);
  const name = file.name;
  if (name.includes('坏')) {
    return VIOL([
      { sheet: '财务三年一期', coord: 'C2', label: '营业收入（元）', reason: '必填缺失' },
      { sheet: '财务三年一期', coord: 'D18', label: '审计状态', reason: "应填 已审计/未审计，实际 '已审计过'" },
    ]);
  }
  if (name.includes('示例')) return PREVIEW_OK;
  return VIOL([
    { sheet: '主体信息', coord: 'B2', label: '企业名称', reason: '必填缺失' },
    { sheet: '财务三年一期', coord: 'B2', label: '营业收入（元）', reason: '必填缺失' },
    { sheet: '财务三年一期', coord: 'B9', label: '资产总额（元）', reason: '必填缺失' },
  ]);
}

export async function saveIngest() {
  await delay(500);
  return { ok: true, status: 200, data: { saved: 'enterprises/hszn_01', company_id: 'hszn_01' } };
}
