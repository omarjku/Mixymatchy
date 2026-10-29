/* Demo host page wiring for SecondLook.lock. Your real app only needs the init() call. */
(function () {
  'use strict';
  var lock = window.SecondLook.lock;
  var $ = function (id) { return document.getElementById(id); };

  // ?idle=5 shortens the client idle timeout for demos (seconds).
  var idleParam = Number(new URLSearchParams(window.location.search).get('idle'));

  var EVENT_LABEL = {
    login: 'Signed in', login_failed: 'Sign-in failed', login_blocked: 'Sign-in blocked',
    unlock: 'Unlocked', unlock_failed: 'Wrong PIN', lock: 'Locked', idle_lock: 'Idle lock',
    logout: 'Signed out', session_revoked: 'Session revoked', session_expired: 'Session expired',
    data_access: 'Patient opened'
  };
  var GOOD = { login: 1, unlock: 1, data_access: 1 };
  var BAD = { login_failed: 1, login_blocked: 1, unlock_failed: 1, session_revoked: 1 };

  function setResult(text, kind) {
    var el = $('result');
    el.textContent = text;
    el.className = 'app-result' + (kind ? ' ' + kind : '');
  }

  function clearSensitive() {
    // A real app would drop patient data from the DOM here.
    setResult('');
    $('audit').textContent = '';
  }

  function detailFor(e) {
    var bits = [];
    if (e.staff_id) bits.push(e.staff_id);
    if (e.patient_id) bits.push('patient ' + e.patient_id);
    if (e.task_sha256) bits.push('task #' + e.task_sha256.slice(0, 8));
    if (e.reason) bits.push(e.reason.replace(/_/g, ' '));
    if (e.source) bits.push('by ' + e.source);
    if (e.attempts_left != null) bits.push(e.attempts_left + ' left');
    if (e.lockout_seconds) bits.push('locked out ' + e.lockout_seconds + ' s');
    if (e.retry_after) bits.push('retry in ' + e.retry_after + ' s');
    return bits.join(' · ');
  }

  async function refreshAudit() {
    try {
      var res = await lock.fetch('/auth/audit?limit=30');
      var data = await res.json();
      var list = $('audit');
      list.textContent = '';
      if (!data.entries.length) {
        var empty = document.createElement('li');
        empty.className = 'app-empty';
        empty.textContent = 'No events yet.';
        list.appendChild(empty);
      }
      data.entries.forEach(function (e) {
        var li = document.createElement('li');
        var t = document.createElement('span');
        t.className = 'app-audit-time';
        t.textContent = new Date(e.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        var ev = document.createElement('span');
        ev.className = 'app-ev' + (GOOD[e.event] ? ' app-ev-good' : BAD[e.event] ? ' app-ev-bad' : '');
        ev.textContent = EVENT_LABEL[e.event] || e.event;
        var d = document.createElement('span');
        d.className = 'app-audit-detail';
        d.textContent = detailFor(e);
        li.append(t, ev, d);
        list.appendChild(li);
      });
      var chain = $('chain');
      chain.textContent = data.chain_ok ? 'hash chain intact' : 'hash chain BROKEN';
      chain.className = 'app-badge' + (data.chain_ok ? '' : ' bad');
    } catch (err) { /* locked or signed out: the module already shows the right screen */ }
  }

  lock.init({
    apiBase: '',
    appRoot: '#app',
    stylesheet: false, // index.html links lock.css itself
    idleSeconds: idleParam > 0 ? idleParam : undefined,
    onUnlocked: function (user) {
      $('who-name').textContent = user.display_name;
      $('who-role').textContent = user.role;
      refreshAudit();
    },
    onLocked: clearSensitive,
    onLoggedOut: clearSensitive
  });

  $('btn-lock').addEventListener('click', function () { lock.lock(); });
  $('btn-logout').addEventListener('click', function () { lock.logout(); });
  $('btn-audit').addEventListener('click', refreshAudit);

  $('btn-ping').addEventListener('click', async function () {
    try {
      var res = await lock.fetch('/api/ping');
      var data = await res.json();
      setResult('Protected API answered for ' + data.user.display_name + '.', 'ok');
    } catch (err) {
      setResult('Blocked: ' + err.code, 'err');
    }
  });

  $('btn-open').addEventListener('click', async function () {
    try {
      var res = await lock.fetch('/api/patient-access', {
        method: 'POST',
        body: JSON.stringify({ patient_id: '0000-0001', task: 'anaesthetist, pre-operative check before breast surgery' })
      });
      if (!res.ok) throw new Error('failed');
      setResult('Access to patient 0000-0001 recorded in the audit trail (task stored as a hash only).', 'ok');
      refreshAudit();
    } catch (err) {
      setResult('Blocked: ' + (err.code || 'error'), 'err');
    }
  });

  setInterval(function () {
    var s = lock.getState();
    var el = $('idle');
    if (s.status !== 'unlocked') return;
    var r = s.idleRemaining;
    el.textContent = 'Auto-lock in ' + Math.floor(r / 60) + ':' + String(r % 60).padStart(2, '0');
    el.classList.toggle('app-idle-soon', r <= Math.min(30, s.idleSeconds / 2));
  }, 500);
})();
