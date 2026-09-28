/* Bea: behavior helpers for the CSS components in bundle.css. Framework-free; no React needed. */
(function () {
  var CHECK = '<svg class="bea-draw" width="16" height="16" viewBox="0 0 16 16" fill="none" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="stroke: COLOR"><path d="M3 8.5l3 3 7-7"/></svg>';
  var SPINNER = '<svg class="bea-spinner" width="16" height="16" viewBox="0 0 16 16" fill="none" style="stroke: var(--on-accent)" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M8 2a6 6 0 1 1-6 6"/></svg>';

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function check(color) {
    return '<span class="bea-pop">' + CHECK.replace('COLOR', color || 'var(--on-accent)') + '</span>';
  }

  /* Count numbers up from zero (ease-out cubic, ~1.1s). format(value) returns the display string. */
  function countUp(el, target, format, duration) {
    var fmt = format || function (v) { return Math.round(v).toLocaleString('en-US'); };
    var dur = duration || 1100;
    if (reducedMotion()) { el.textContent = fmt(target); return; }
    var t0 = performance.now();
    function step(now) {
      var t = Math.min(1, (now - t0) / dur);
      var e = 1 - Math.pow(1 - t, 3);
      el.textContent = fmt(target * e);
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  /* Wire a .bea-seg: its .bea-knob slides to the pressed .bea-seg-opt. Calls onChange(index). */
  function segmented(root, onChange) {
    var knob = root.querySelector('.bea-knob');
    var opts = Array.prototype.slice.call(root.querySelectorAll('.bea-seg-opt'));
    if (knob) knob.style.width = 'calc(' + (100 / opts.length) + '% - ' + (6 / opts.length) + 'px)';
    opts.forEach(function (o, i) {
      o.addEventListener('click', function () {
        opts.forEach(function (p) { p.setAttribute('aria-pressed', p === o ? 'true' : 'false'); });
        if (knob) knob.style.transform = 'translateX(' + (i * 100) + '%)';
        if (onChange) onChange(i);
      });
    });
  }

  /* Async primary button: idle -> spinner + busyLabel -> green check + doneLabel -> idle.
     run() may return a Promise; the done state shows when it resolves. */
  function asyncButton(btn, opts) {
    var o = opts || {};
    var idle = btn.innerHTML;
    var busy = false;
    btn.addEventListener('click', function () {
      if (busy) return;
      busy = true;
      btn.innerHTML = SPINNER + '<span>' + (o.busyLabel || 'Working…') + '</span>';
      var result = o.run ? o.run() : new Promise(function (r) { setTimeout(r, 1100); });
      Promise.resolve(result).then(function () {
        btn.classList.add('is-done');
        btn.innerHTML = check('var(--on-accent)') + '<span>' + (o.doneLabel || 'Done') + '</span>';
        setTimeout(function () { btn.classList.remove('is-done'); btn.innerHTML = idle; busy = false; }, o.resetAfter || 2200);
      }, function () { btn.innerHTML = idle; busy = false; });
    });
  }

  /* Copy button: copies text, confirms with a green check that pops and draws, then reverts. */
  function copyButton(btn, getText) {
    var idle = btn.innerHTML;
    btn.addEventListener('click', function () {
      try { navigator.clipboard.writeText(typeof getText === 'function' ? getText() : String(getText)); } catch (e) {}
      btn.innerHTML = check('var(--status-positive)');
      clearTimeout(btn._beaT);
      btn._beaT = setTimeout(function () { btn.innerHTML = idle; }, 1600);
    });
  }

  /* Theme: 'light' | 'dark' set data-theme; 'system' removes it so prefers-color-scheme decides.
     Switches are instant: transitions are suppressed for one frame (see .bea-theme-switching in bea.css). */
  function setTheme(theme, root) {
    var el = root || document.documentElement;
    el.classList.add('bea-theme-switching');
    if (theme === 'system') el.removeAttribute('data-theme'); else el.setAttribute('data-theme', theme);
    void el.offsetWidth; // flush styles with transitions off
    requestAnimationFrame(function () { requestAnimationFrame(function () { el.classList.remove('bea-theme-switching'); }); });
  }

  /* The theme currently in effect for an element: its nearest data-theme, else the OS preference. */
  function getTheme(el) {
    var node = el || document.documentElement;
    var owner = node.closest ? node.closest('[data-theme]') : null;
    if (owner) return owner.getAttribute('data-theme');
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  }

  window.Bea = {
    setTheme: setTheme,
    getTheme: getTheme,
    reducedMotion: reducedMotion,
    countUp: countUp,
    segmented: segmented,
    asyncButton: asyncButton,
    copyButton: copyButton
  };
})();
