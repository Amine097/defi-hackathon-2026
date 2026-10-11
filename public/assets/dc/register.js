/* FAULTLINE runtime glue for the Claude Design pages (index.html, app.html).
   The approved export runs on the design runtime (support.js) which normally evals the page's
   <script data-dc-script> body with new Function. Production keeps that element (it carries the props metadata)
   but ships the class body as a same-origin file that calls FLRegister, so the CSP can stay script-src 'self'. */
(function () {
  'use strict';
  window.FLRegister = function (define) {
    function attach() {
      var reg = window.__dcRegistry;
      var name = window.__dcRootName && window.__dcRootName();
      if (!reg || !window.DCLogic || name == null || !reg[name] || !reg[name].tpl) { setTimeout(attach, 16); return; }
      var entry = reg[name];
      entry.Logic = define(window.DCLogic, window.React);
      entry.logicError = null;
      window.__dcSetProps(name, entry.propOverrides || null);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', attach);
    else attach();
  };
})();
