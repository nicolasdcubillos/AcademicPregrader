/* UI helpers shared by the main page: toasts, accessible modals, event delegation. */
(function () {
  'use strict';

  // ── Event delegation: data-action (click) and data-on-<event> attributes ──
  const ACTIONS = {};
  const EVENT_ATTR = {
    click: 'data-action',
    input: 'data-on-input',
    change: 'data-on-change',
    keydown: 'data-on-keydown',
    focusout: 'data-on-focusout',
    dragover: 'data-on-dragover',
    dragleave: 'data-on-dragleave',
    drop: 'data-on-drop',
  };

  Object.entries(EVENT_ATTR).forEach(([type, attr]) => {
    document.addEventListener(type, ev => {
      const el = ev.target && ev.target.closest ? ev.target.closest(`[${attr}]`) : null;
      if (!el) return;
      const fn = ACTIONS[el.getAttribute(attr)];
      if (fn) fn(el, ev);
    });
  });

  function registerActions(map) { Object.assign(ACTIONS, map); }

  // ── Toasts ──
  const MAX_TOASTS = 4;

  function toast(message, opts = {}) {
    const region = document.getElementById('toast-region');
    if (!region) return null;
    const { type = 'info', duration = 4500, action = null } = opts;

    while (region.children.length >= MAX_TOASTS) region.firstElementChild.remove();

    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    el.setAttribute('role', type === 'error' ? 'alert' : 'status');

    const text = document.createElement('span');
    text.className = 'toast-text';
    text.textContent = message;
    el.appendChild(text);

    let timer = null;
    const dismiss = () => {
      clearTimeout(timer);
      el.classList.add('toast--out');
      setTimeout(() => el.remove(), 180);
    };

    if (action) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'toast-action';
      btn.textContent = action.label;
      btn.addEventListener('click', () => { dismiss(); action.onClick(); });
      el.appendChild(btn);
    }

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.setAttribute('aria-label', 'Cerrar aviso');
    close.textContent = '✕';
    close.addEventListener('click', dismiss);
    el.appendChild(close);

    const arm = () => { if (duration > 0) timer = setTimeout(dismiss, duration); };
    el.addEventListener('mouseenter', () => clearTimeout(timer));
    el.addEventListener('mouseleave', arm);
    arm();

    region.appendChild(el);
    return { el, dismiss };
  }

  // ── Accessible modals: focus trap, Esc, focus restore, backdrop click ──
  const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const openStack = [];

  function isOpen(overlay) { return !overlay.classList.contains('hidden'); }

  function focusables(overlay) {
    return Array.from(overlay.querySelectorAll(FOCUSABLE)).filter(el => el.offsetParent !== null);
  }

  function onOpen(overlay) {
    if (openStack.some(item => item.overlay === overlay)) return;
    const opener = document.activeElement && !overlay.contains(document.activeElement) ? document.activeElement : null;
    openStack.push({ overlay, opener });
    document.body.classList.add('modal-open');
    const body = overlay.querySelector('.modal-body');
    const target = (body && focusables(body)[0]) || overlay.querySelector('.modal-close') || overlay.querySelector('.modal');
    if (target) target.focus({ preventScroll: true });
  }

  function onClose(overlay) {
    const idx = openStack.findIndex(item => item.overlay === overlay);
    if (idx === -1) return;
    const [{ opener }] = openStack.splice(idx, 1);
    if (!openStack.length) document.body.classList.remove('modal-open');
    if (opener && document.contains(opener)) opener.focus({ preventScroll: true });
  }

  const observer = new MutationObserver(records => {
    records.forEach(rec => {
      const overlay = rec.target;
      if (isOpen(overlay)) onOpen(overlay); else onClose(overlay);
    });
  });

  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    observer.observe(overlay, { attributes: true, attributeFilter: ['class'] });
  });

  document.addEventListener('keydown', ev => {
    const top = openStack[openStack.length - 1];
    if (!top) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      const closeBtn = top.overlay.querySelector('.modal-close');
      if (closeBtn) closeBtn.click(); else top.overlay.classList.add('hidden');
      return;
    }
    if (ev.key !== 'Tab') return;
    const items = focusables(top.overlay);
    if (!items.length) { ev.preventDefault(); return; }
    const first = items[0];
    const last = items[items.length - 1];
    if (!top.overlay.contains(document.activeElement)) { ev.preventDefault(); first.focus(); }
    else if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  });

  let downTarget = null;
  document.addEventListener('mousedown', ev => { downTarget = ev.target; });
  document.addEventListener('click', ev => {
    const overlay = ev.target;
    if (!overlay.classList || !overlay.classList.contains('modal-overlay')) return;
    if (downTarget !== overlay) return;
    const closeBtn = overlay.querySelector('.modal-close');
    if (closeBtn) closeBtn.click();
  });

  // ── Sticky offsets: expose the header height to CSS ──
  const header = document.querySelector('header');
  if (header) {
    const setHeaderHeight = () => document.documentElement.style.setProperty('--hdr-h', header.offsetHeight + 'px');
    setHeaderHeight();
    if (window.ResizeObserver) new ResizeObserver(setHeaderHeight).observe(header);
    else window.addEventListener('resize', setHeaderHeight);
  }

  window.UI = { toast, registerActions };
})();
