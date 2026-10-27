// Menü: bir menü açılınca diğerini kapat, dışarı tıklayınca / Esc ile kapat.
(function () {
  var d = document;
  function closeAll(except) {
    d.querySelectorAll('.dd[open]').forEach(function (x) { if (x !== except) x.removeAttribute('open'); });
  }
  d.addEventListener('toggle', function (e) {
    var t = e.target;
    if (t.classList && t.classList.contains('dd') && t.open) closeAll(t);
  }, true);
  d.addEventListener('click', function (e) { if (!e.target.closest('.dd')) closeAll(); });
  d.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeAll(); });
})();
