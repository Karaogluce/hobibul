/* Bağlantı kopyala. Üçüncü taraf betiği yok. */
(function () {
  function done(btn) {
    var prev = btn.textContent;
    btn.textContent = "Kopyalandı";
    btn.setAttribute("aria-label", "Bağlantı kopyalandı");
    window.setTimeout(function () {
      btn.textContent = prev;
      btn.setAttribute("aria-label", "Bağlantıyı kopyala");
    }, 1600);
  }

  function fallback(url) {
    var input = document.createElement("textarea");
    input.value = url;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.left = "-999px";
    document.body.appendChild(input);
    input.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    input.remove();
    return ok;
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest("[data-copy-url]") : null;
    if (!btn) return;
    var url = btn.getAttribute("data-copy-url") || "";
    if (!url) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { done(btn); }).catch(function () {
        if (fallback(url)) done(btn);
      });
      return;
    }
    if (fallback(url)) done(btn);
  });
})();
