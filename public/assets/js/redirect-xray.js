// /xray.html moved into /analyze.html; keep old links (and their query) working.
(function () {
  var q = new URLSearchParams(location.search);
  q.delete('data');
  var s = q.toString();
  location.replace('/analyze.html' + (s ? '?' + s : '') + location.hash);
})();
