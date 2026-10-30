/*!
 * Second Look lock module — login, PIN lock screen, idle/visibility locking.
 *
 * Drop-in for any frontend (plain HTML, Next.js, ...):
 *
 *   <script src="http://localhost:8700/second-look-lock.js"></script>
 *   SecondLook.lock.init({
 *     apiBase: 'http://localhost:8700',   // where security/server.py runs ('' = same origin)
 *     appRoot: '#app',                    // element that holds patient data (blurred + inert when locked)
 *     onUnlocked(user) {},                // signed in or PIN accepted: (re)load patient data
 *     onLocked(reason) {},                // 'idle' | 'manual' | 'hidden' | 'server' — clear sensitive DOM if you like
 *     onLoggedOut(reason) {},             // 'user' | 'not_me' | 'expired' | 'revoked' | 'pagehide'
 *   });
 *   const res = await SecondLook.lock.fetch('/api/ping');   // adds token, handles 401/423
 *
 * Security notes: the session token lives only in this closure (never in
 * localStorage/sessionStorage/cookies readable by JS). A reload therefore
 * always requires a full sign-in, and pagehide revokes the session server-side.
 */
(function (root, factory) {
  'use strict';
  var api = factory(root);
  root.SecondLook = root.SecondLook || {};
  root.SecondLook.lock = api;
  if (typeof module === 'object' && module && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : this, function (win) {
  'use strict';

  var doc = win.document;
  var ACTIVITY_EVENTS = ['pointerdown', 'pointermove', 'keydown', 'touchstart', 'wheel', 'scroll'];
  var REASON_TEXT = {
    idle: 'Locked after a period of inactivity',
    manual: 'Locked by you',
    hidden: 'Locked while the screen was hidden',
    server: 'Locked by the server'
  };

  var state = {
    opts: null,
    token: null,          // in memory only
    user: null,
    policy: null,
    status: 'signed_out', // 'signed_out' | 'unlocked' | 'locked'
    lockReason: null,
    attemptsLeft: null,
    pin: '',
    busy: false,
    lastActivity: 0,
    lastHeartbeat: 0,
    idleMs: 180000,
    expiryTimer: null,
    tickTimer: null,
    els: {},
    appRoot: null,
    leaving: false
  };

  function AuthError(code, status, message) {
    var e = new Error(message || code);
    e.name = 'SecondLookAuthError';
    e.code = code;
    e.status = status;
    return e;
  }

  // ------------------------------------------------------------------ helpers
  function now() { return Date.now(); }
  function apiUrl(path) { return (state.opts.apiBase || '').replace(/\/$/, '') + path; }
  function call(fn, arg) { try { if (typeof fn === 'function') fn(arg); } catch (e) { console.error(e); } }
  function initials(name) {
    var parts = String(name || '').replace(/^(dr|prof|mr|ms|mrs)\.?\s+/i, '').split(/\s+/).filter(Boolean);
    return ((parts[0] || '?')[0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
  }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  async function request(path, body, extra) {
    var headers = { 'Content-Type': 'application/json' };
    if (state.token) headers.Authorization = 'Bearer ' + state.token;
    var res = await win.fetch(apiUrl(path), Object.assign({
      method: body === undefined ? 'GET' : 'POST',
      headers: headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'omit',
      cache: 'no-store'
    }, extra || {}));
    var data = {};
    try { data = await res.json(); } catch (e) { /* empty body */ }
    return { res: res, data: data };
  }

  // ------------------------------------------------------------------ DOM
  var MARK_SVG =
    '<svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">' +
    '<rect width="32" height="32" rx="9" fill="currentColor"/>' +
    '<circle cx="13" cy="16" r="6.5" fill="none" stroke="#fff" stroke-width="2.2"/>' +
    '<circle cx="19.5" cy="16" r="6.5" fill="none" stroke="#fff" stroke-width="2.2" opacity=".6"/></svg>';
  var LOCK_SVG =
    '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">' +
    '<rect x="5" y="11" width="14" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>' +
    '<path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="2"/></svg>';
  var BACK_SVG =
    '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" focusable="false">' +
    '<path d="M9 6h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-6-6z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>' +
    '<path d="M12 10l4 4m0-4l-4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';

  function build() {
    var shell = doc.createElement('div');
    shell.className = 'sl-shell';
    shell.setAttribute('data-second-look', 'shell');
    shell.innerHTML =
      '<section class="sl-card sl-login" role="dialog" aria-modal="true" aria-labelledby="sl-login-title">' +
        '<div class="sl-brand"><span class="sl-mark">' + MARK_SVG + '</span>' +
          '<div><div class="sl-brand-name"></div><div class="sl-brand-sub">Clinical workstation</div></div></div>' +
        '<h1 class="sl-title" id="sl-login-title">Sign in</h1>' +
        '<p class="sl-help">Use your hospital staff ID and password.</p>' +
        '<form class="sl-form" novalidate>' +
          '<label class="sl-label" for="sl-staff">Staff ID</label>' +
          '<input class="sl-input" id="sl-staff" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required>' +
          '<label class="sl-label" for="sl-pass">Password</label>' +
          '<input class="sl-input" id="sl-pass" name="password" type="password" autocomplete="current-password" required>' +
          '<p class="sl-msg" data-el="loginMsg" role="alert" aria-live="assertive"></p>' +
          '<button class="sl-btn sl-btn-primary" type="submit" data-el="loginBtn">Sign in</button>' +
        '</form>' +
        '<p class="sl-foot" data-el="loginFoot"></p>' +
      '</section>' +
      '<section class="sl-card sl-lockcard" role="dialog" aria-modal="true" aria-labelledby="sl-lock-name" tabindex="-1" hidden>' +
        '<div class="sl-avatar" data-el="avatar" aria-hidden="true"></div>' +
        '<h1 class="sl-title" id="sl-lock-name" data-el="lockName"></h1>' +
        '<p class="sl-role" data-el="lockRole"></p>' +
        '<p class="sl-lockline">' + LOCK_SVG + '<span data-el="lockReason"></span></p>' +
        '<p class="sl-prompt" id="sl-pin-label">Enter your 4-digit PIN</p>' +
        '<div class="sl-dots" data-el="dots" role="status" aria-live="polite" aria-labelledby="sl-pin-label">' +
          '<span></span><span></span><span></span><span></span></div>' +
        '<p class="sl-msg" data-el="lockMsg" role="alert" aria-live="assertive"></p>' +
        '<div class="sl-pad" role="group" aria-label="PIN keypad" data-el="pad">' +
          [1, 2, 3, 4, 5, 6, 7, 8, 9].map(function (d) {
            return '<button type="button" class="sl-key" data-digit="' + d + '" aria-label="' + d + '">' + d + '</button>';
          }).join('') +
          '<span class="sl-key-spacer" aria-hidden="true"></span>' +
          '<button type="button" class="sl-key" data-digit="0" aria-label="0">0</button>' +
          '<button type="button" class="sl-key sl-key-back" data-action="back" aria-label="Delete last digit">' + BACK_SVG + '</button>' +
        '</div>' +
        '<button type="button" class="sl-link" data-action="notme">Not you? Log out</button>' +
      '</section>';
    doc.body.appendChild(shell);

    var els = { shell: shell };
    els.login = shell.querySelector('.sl-login');
    els.lock = shell.querySelector('.sl-lockcard');
    els.form = shell.querySelector('.sl-form');
    els.staff = shell.querySelector('#sl-staff');
    els.pass = shell.querySelector('#sl-pass');
    shell.querySelectorAll('[data-el]').forEach(function (el) { els[el.getAttribute('data-el')] = el; });
    shell.querySelector('.sl-brand-name').textContent = state.opts.title || 'Second Look';
    state.els = els;

    els.dots.addEventListener('animationend', function () { els.dots.classList.remove('sl-shake'); });
    els.form.addEventListener('submit', function (ev) { ev.preventDefault(); login(); });
    els.pad.addEventListener('click', function (ev) {
      var btn = ev.target.closest('button');
      if (!btn) return;
      if (btn.hasAttribute('data-digit')) pressDigit(btn.getAttribute('data-digit'));
      else if (btn.getAttribute('data-action') === 'back') backspace();
    });
    shell.querySelector('[data-action="notme"]').addEventListener('click', function () {
      signOut('not_me', 'Signed out. The next person can sign in.', true);
    });
  }

  function render() {
    var els = state.els, s = state.status;
    var hidden = doc.visibilityState === 'hidden';
    els.shell.classList.toggle('sl-open', s !== 'unlocked');
    els.shell.classList.toggle('sl-mode-login', s === 'signed_out');
    els.shell.classList.toggle('sl-mode-lock', s === 'locked');
    els.login.hidden = s !== 'signed_out';
    els.lock.hidden = s !== 'locked';
    doc.documentElement.classList.toggle('sl-active', s !== 'unlocked');

    var app = state.appRoot;
    if (app) {
      var protect = s !== 'unlocked' || hidden;
      app.classList.toggle('sl-app-blurred', protect);
      app.classList.toggle('sl-app-hidden', s === 'signed_out');
      if (protect) { app.setAttribute('inert', ''); app.setAttribute('aria-hidden', 'true'); }
      else { app.removeAttribute('inert'); app.removeAttribute('aria-hidden'); }
    }

    if (s === 'locked' && state.user) {
      els.avatar.textContent = initials(state.user.display_name);
      els.lockName.textContent = state.user.display_name;
      els.lockRole.textContent = state.user.role || '';
      els.lockReason.textContent = REASON_TEXT[state.lockReason] || REASON_TEXT.manual;
      renderDots();
    }
    var mins = Math.round((state.policy ? state.policy.idle_seconds : 180) / 60);
    els.loginFoot.textContent = 'Screen locks after ' + plural(Math.max(1, mins), 'minute') +
      ' without activity. Nothing is stored on this device.';
  }

  function renderDots() {
    var dots = state.els.dots.children;
    for (var i = 0; i < dots.length; i++) dots[i].classList.toggle('sl-filled', i < state.pin.length);
    state.els.dots.setAttribute('aria-label', state.pin.length + ' of 4 digits entered');
    state.els.pad.classList.toggle('sl-busy', state.busy);
  }

  function setMsg(el, text, kind) {
    el.textContent = text || '';
    el.classList.toggle('sl-msg-error', kind === 'error');
    el.classList.toggle('sl-msg-info', kind === 'info');
  }

  function shake() {
    var d = state.els.dots;
    d.classList.remove('sl-shake');
    void d.offsetWidth; // restart animation
    d.classList.add('sl-shake');
    if (win.navigator.vibrate) { try { win.navigator.vibrate(120); } catch (e) { /* ignore */ } }
  }

  // ------------------------------------------------------------------ login
  async function login() {
    var els = state.els;
    if (state.busy) return;
    var staffId = els.staff.value.trim(), password = els.pass.value;
    if (!staffId || !password) {
      setMsg(els.loginMsg, 'Enter your staff ID and password.', 'error');
      (staffId ? els.pass : els.staff).focus();
      return;
    }
    state.busy = true;
    els.loginBtn.disabled = true;
    els.loginBtn.textContent = 'Signing in…';
    setMsg(els.loginMsg, '');
    try {
      var r = await request('/auth/login', { staff_id: staffId, password: password });
      if (r.res.ok) {
        els.pass.value = '';
        state.token = r.data.token;
        state.user = r.data.user;
        state.policy = r.data.policy;
        state.idleMs = 1000 * (state.opts.idleSeconds || r.data.policy.idle_seconds);
        clearTimeout(state.expiryTimer);
        state.expiryTimer = setTimeout(function () {
          signOut('expired', 'Your session reached its maximum length. Please sign in again.', true);
        }, Math.min(r.data.expires_in * 1000, 2147483000));
        becomeUnlocked();
      } else {
        els.pass.value = '';
        els.pass.focus();
        setMsg(els.loginMsg, r.data.message || 'Sign-in failed.', 'error');
      }
    } catch (e) {
      setMsg(els.loginMsg, 'Cannot reach the Second Look server. Check your connection.', 'error');
    } finally {
      state.busy = false;
      els.loginBtn.disabled = false;
      els.loginBtn.textContent = 'Sign in';
    }
  }

  function becomeUnlocked() {
    state.status = 'unlocked';
    state.lockReason = null;
    state.attemptsLeft = null;
    state.pin = '';
    state.lastActivity = state.lastHeartbeat = now();
    setMsg(state.els.lockMsg, '');
    render();
    call(state.opts.onUnlocked, state.user);
  }

  // ------------------------------------------------------------------ lock / unlock
  function enterLocked(reason, attemptsLeft, notifyServer) {
    if (state.status === 'signed_out') return;
    var was = state.status;
    state.status = 'locked';
    state.lockReason = reason || 'manual';
    state.pin = '';
    if (attemptsLeft != null) state.attemptsLeft = attemptsLeft;
    if (was !== 'locked') {
      setMsg(state.els.lockMsg, state.attemptsLeft != null && state.attemptsLeft < (state.policy || {}).max_pin_attempts
        ? plural(state.attemptsLeft, 'attempt') + ' left' : '', 'info');
    }
    render();
    if (doc.activeElement && state.appRoot && state.appRoot.contains(doc.activeElement)) doc.activeElement.blur();
    if (doc.visibilityState !== 'hidden') state.els.lock.focus({ preventScroll: true });
    if (notifyServer && state.token) {
      request('/auth/lock', { reason: reason }, { keepalive: true }).then(function (r) {
        if (r.res.status === 401) signOut('expired', r.data.message, false);
      }).catch(function () { /* stays locked locally */ });
    }
    if (was !== 'locked') call(state.opts.onLocked, state.lockReason);
  }

  function pressDigit(d) {
    if (state.status !== 'locked' || state.busy || state.pin.length >= 4) return;
    state.pin += d;
    renderDots();
    if (state.pin.length === 4) setTimeout(submitPin, 120);
  }

  function backspace() {
    if (state.status !== 'locked' || state.busy) return;
    state.pin = state.pin.slice(0, -1);
    renderDots();
  }

  async function submitPin() {
    if (state.busy || state.pin.length !== 4) return;
    state.busy = true;
    renderDots();
    var pin = state.pin;
    try {
      var r = await request('/auth/unlock', { pin: pin });
      pin = null;
      state.pin = '';
      if (r.res.ok) {
        state.busy = false;
        becomeUnlocked();
        return;
      }
      if (r.res.status === 403) {
        state.attemptsLeft = r.data.attempts_left;
        shake();
        setMsg(state.els.lockMsg, 'Incorrect PIN · ' + plural(state.attemptsLeft, 'attempt') + ' left', 'error');
      } else if (r.res.status === 401) {
        state.busy = false;
        signOut('revoked', r.data.message || 'Please sign in again.', false);
        return;
      } else {
        setMsg(state.els.lockMsg, r.data.message || 'Could not unlock. Try again.', 'error');
      }
    } catch (e) {
      state.pin = '';
      setMsg(state.els.lockMsg, 'Cannot reach the server. Check your connection.', 'error');
    }
    state.busy = false;
    renderDots();
  }

  // ------------------------------------------------------------------ sign out
  function signOut(reason, message, notifyServer) {
    var token = state.token;
    state.token = null;
    state.user = null;
    state.pin = '';
    state.attemptsLeft = null;
    state.status = 'signed_out';
    clearTimeout(state.expiryTimer);
    if (notifyServer && token) {
      win.fetch(apiUrl('/auth/logout'), {
        method: 'POST', credentials: 'omit', keepalive: true,
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
        body: JSON.stringify({ reason: reason === 'not_me' ? 'not_me' : (reason === 'expired' ? 'expired' : 'user') })
      }).catch(function () { /* server will expire it */ });
    }
    token = null;
    if (state.els.shell) {
      state.els.pass.value = '';
      if (reason === 'not_me') state.els.staff.value = '';
      setMsg(state.els.loginMsg, message || '', reason === 'revoked' ? 'error' : 'info');
      render();
      if (doc.visibilityState !== 'hidden') (state.els.staff.value ? state.els.pass : state.els.staff).focus();
    }
    call(state.opts.onLoggedOut, reason);
  }

  function beaconLogout() {
    if (!state.token || state.leaving) return;
    state.leaving = true;
    var payload = JSON.stringify({ token: state.token, reason: 'pagehide' });
    var sent = false;
    try {
      // text/plain keeps this a "simple" request so it also works cross-origin.
      sent = win.navigator.sendBeacon && win.navigator.sendBeacon(apiUrl('/auth/logout'),
        new Blob([payload], { type: 'text/plain' }));
    } catch (e) { sent = false; }
    if (!sent) {
      try {
        win.fetch(apiUrl('/auth/logout'), { method: 'POST', keepalive: true, credentials: 'omit',
          headers: { 'Content-Type': 'text/plain' }, body: payload });
      } catch (e) { /* ignore */ }
    }
    state.token = null;
    state.user = null;
    state.status = 'signed_out';
  }

  // ------------------------------------------------------------------ activity / idle
  function onActivity() {
    if (state.status === 'unlocked') state.lastActivity = now();
  }

  function tick() {
    if (state.status !== 'unlocked') return;
    var t = now();
    if (t - state.lastActivity >= state.idleMs) {
      enterLocked('idle', null, true);
      return;
    }
    var hbMs = 1000 * (state.opts.heartbeatSeconds || 30);
    if (state.lastActivity > state.lastHeartbeat && t - state.lastHeartbeat >= hbMs) {
      state.lastHeartbeat = t;
      request('/auth/heartbeat', {}).then(function (r) {
        if (r.res.status === 423) enterLocked(r.data.reason || 'server', r.data.attempts_left, false);
        else if (r.res.status === 401) signOut('expired', r.data.message, false);
      }).catch(function () { /* offline: local idle timer still applies */ });
    }
  }

  function onKeydown(ev) {
    if (state.status !== 'locked' || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    if (/^[0-9]$/.test(ev.key)) { ev.preventDefault(); pressDigit(ev.key); }
    else if (ev.key === 'Backspace') { ev.preventDefault(); backspace(); }
    else if (ev.key === 'Escape') { ev.preventDefault(); if (!state.busy) { state.pin = ''; renderDots(); } }
  }

  function onVisibility() {
    if (doc.visibilityState === 'hidden') {
      if (state.status === 'unlocked' && state.opts.lockOnHidden !== false) enterLocked('hidden', null, true);
      else render(); // blur immediately (app switcher snapshots)
    } else {
      render();
      if (state.status === 'locked') state.els.lock.focus({ preventScroll: true });
    }
  }

  // ------------------------------------------------------------------ public fetch
  function isTrustedUrl(url) {
    var base = new URL(state.opts.apiBase || win.location.origin, win.location.href).origin;
    var origin = new URL(url, win.location.href).origin;
    return origin === base || origin === win.location.origin ||
      (state.opts.trustedOrigins || []).indexOf(origin) !== -1;
  }

  async function guardedFetch(input, init) {
    if (!state.opts) throw AuthError('not_initialised', 0, 'Call SecondLook.lock.init() first');
    var url = typeof input === 'string' && input.charAt(0) === '/' ? apiUrl(input) : input;
    if (state.status === 'signed_out' || !state.token) throw AuthError('unauthenticated', 401, 'Not signed in');
    if (state.status === 'locked') throw AuthError('locked', 423, 'Session locked');
    if (!isTrustedUrl(typeof url === 'string' ? url : url.url)) {
      throw AuthError('untrusted_origin', 0, 'Refusing to send the session token to ' + url);
    }
    init = Object.assign({ credentials: 'omit', cache: 'no-store' }, init || {});
    var headers = new Headers(init.headers || {});
    headers.set('Authorization', 'Bearer ' + state.token);
    if (init.body && typeof init.body === 'string' && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    init.headers = headers;
    var res = await win.fetch(url, init);
    if (res.status === 423) {
      var d = {};
      try { d = await res.clone().json(); } catch (e) { /* ignore */ }
      enterLocked(d.reason || 'server', d.attempts_left, false);
      throw AuthError('locked', 423, 'Session locked');
    }
    if (res.status === 401) {
      signOut('expired', 'Your session has ended. Please sign in again.', false);
      throw AuthError('unauthenticated', 401, 'Session ended');
    }
    return res;
  }

  // ------------------------------------------------------------------ init
  function init(options) {
    if (state.opts) throw new Error('SecondLook.lock.init() called twice');
    state.opts = Object.assign({ apiBase: '', appRoot: '[data-second-look-app]', lockOnHidden: true,
      heartbeatSeconds: 30, stylesheet: undefined, title: 'Second Look' }, options || {});
    state.opts.apiBase = (state.opts.apiBase || '').replace(/\/$/, '');

    var css = state.opts.stylesheet === undefined ? apiUrl('/lock.css') : state.opts.stylesheet;
    if (css && !doc.querySelector('link[data-second-look-css]')) {
      var link = doc.createElement('link');
      link.rel = 'stylesheet';
      link.href = css;
      link.setAttribute('data-second-look-css', '');
      doc.head.appendChild(link);
    }

    var start = function () {
      state.appRoot = typeof state.opts.appRoot === 'string' ? doc.querySelector(state.opts.appRoot) : state.opts.appRoot;
      build();
      if (state.opts.idleSeconds) state.idleMs = 1000 * state.opts.idleSeconds;
      ACTIVITY_EVENTS.forEach(function (name) {
        win.addEventListener(name, onActivity, { capture: true, passive: true });
      });
      doc.addEventListener('keydown', onKeydown);
      doc.addEventListener('visibilitychange', onVisibility);
      win.addEventListener('pagehide', beaconLogout);
      win.addEventListener('beforeunload', beaconLogout);
      win.addEventListener('pageshow', function (ev) {
        if (ev.persisted) { state.leaving = false; signOut('pagehide', 'Please sign in again.', false); }
      });
      state.tickTimer = setInterval(tick, 1000);
      render();
      state.els.staff.focus();
      // Fetch policy so the login footer shows the real idle time.
      request('/auth/policy').then(function (r) {
        if (r.res.ok && !state.policy) { state.policy = r.data; render(); }
      }).catch(function () { /* shown on login error instead */ });
    };
    if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', start);
    else start();
    return api;
  }

  var api = {
    init: init,
    fetch: guardedFetch,
    lock: function () { enterLocked('manual', null, true); },
    logout: function () { signOut('user', 'You have signed out.', true); },
    getUser: function () { return state.status === 'signed_out' ? null : Object.assign({}, state.user); },
    getState: function () {
      return {
        status: state.status,
        user: state.user ? Object.assign({}, state.user) : null,
        lockReason: state.lockReason,
        idleSeconds: Math.round(state.idleMs / 1000),
        idleRemaining: state.status === 'unlocked'
          ? Math.max(0, Math.ceil((state.idleMs - (now() - state.lastActivity)) / 1000)) : 0
      };
    },
    isUnlocked: function () { return state.status === 'unlocked'; }
  };
  return api;
});
