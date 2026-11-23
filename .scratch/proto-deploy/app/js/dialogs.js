/* 弹窗机制（自原型 v0.4 迁移）：Esc 关闭（loading 除外）、弹窗内焦点收敛、
   点遮罩关闭；内容构造在 page-*.js，这里只管开合与可达性。 */

let maskLastFocus = null;

export const openMask = id => {
  document.getElementById(id).classList.add('on');
  maskLastFocus = document.activeElement;
};
export const closeMask = id => {
  document.getElementById(id).classList.remove('on');
  if (maskLastFocus && maskLastFocus.focus) maskLastFocus.focus();
};
export const closeAllMasks = () => {
  document.querySelectorAll('.mask.on').forEach(m => m.classList.remove('on'));
  if (maskLastFocus && maskLastFocus.focus) maskLastFocus.focus();
};

/* 通用信息弹窗（测评项说明 / 口径 / 法条） */
export const showModal = (title, html, maskId = 'mask-info') => {
  document.getElementById('mi-title').textContent = title;
  document.getElementById('mi-body').innerHTML = html;
  openMask(maskId);
};

export function initDialogs() {
  // 关闭按钮（data-close 委托，替代原型内联 onclick）
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-close]');
    if (btn) closeMask(btn.dataset.close);
    const m = e.target.closest('.mask');
    if (m && e.target === m) m.classList.remove('on');
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      const open = [...document.querySelectorAll('.mask.on')].filter(m => m.id !== 'mask-load');
      if (open.length) {
        open.forEach(m => m.classList.remove('on'));
        if (maskLastFocus && maskLastFocus.focus) maskLastFocus.focus();
      }
      return;
    }
    if (e.key === 'Tab') {
      const m = [...document.querySelectorAll('.mask.on')].filter(x => x.id !== 'mask-load')[0];
      if (!m) return;
      const f = [...m.querySelectorAll('button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])')]
        .filter(x => x.offsetParent !== null);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
}

/* loading 弹窗（阶段 2 跑引擎时用） */
export const showLoading = (text, steps) => {
  document.getElementById('load-text').innerHTML = text || '<b>正在执行测评…</b>';
  document.getElementById('load-steps').textContent = steps || '';
  openMask('mask-load');
};
export const hideLoading = () => closeMask('mask-load');
