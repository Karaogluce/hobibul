// Alışveriş listesi aracı — sayfadaki affiliate linklerini otomatik toplar.
// Hiçbir sunucuya veri göndermez; seçimler yalnızca bu tarayıcıda saklanır.
(function () {
  "use strict";
  var body = document.querySelector(".article-body");
  var mount = document.getElementById("hb-checklist");
  if (!body || !mount) return;

  var links = Array.prototype.slice.call(body.querySelectorAll("a.aff-link[data-aff-link]"));
  var seen = {};
  var items = [];
  links.forEach(function (a) {
    var id = a.getAttribute("data-aff-link");
    if (seen[id]) return;
    seen[id] = true;
    var name = a.textContent.trim().replace(/^(satın al|satin al|i̇ncele|i̇ncele:)\s*:?\s*/i, "");
    items.push({ id: id, name: name || a.textContent.trim(), href: a.getAttribute("href") });
  });
  if (!items.length) return;

  var STATUSES = ["Olmazsa olmaz", "İyi olur", "Şimdilik alma", "Zaten var"];
  var key = "hb_checklist:" + location.pathname;
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { saved = {}; }

  function save() {
    try { localStorage.setItem(key, JSON.stringify(saved)); } catch (e) { /* yoksay */ }
  }

  function row(item) {
    var cur = saved[item.id] || { status: STATUSES[0], done: false };
    var wrap = document.createElement("div");
    wrap.className = "cl-row" + (cur.done ? " cl-done" : "");
    wrap.innerHTML =
      '<label class="cl-check"><input type="checkbox"' + (cur.done ? " checked" : "") + '><span></span></label>' +
      '<a class="cl-name" href="' + item.href + '" target="_blank" rel="nofollow sponsored noopener">' + item.name + '</a>' +
      '<select class="cl-status">' + STATUSES.map(function (s) {
        return '<option' + (s === cur.status ? " selected" : "") + '>' + s + '</option>';
      }).join("") + '</select>';
    wrap.querySelector("input").addEventListener("change", function (e) {
      cur.done = e.target.checked;
      saved[item.id] = cur;
      wrap.classList.toggle("cl-done", cur.done);
      save();
    });
    wrap.querySelector("select").addEventListener("change", function (e) {
      cur.status = e.target.value;
      saved[item.id] = cur;
      save();
    });
    return wrap;
  }

  var panel = document.createElement("div");
  panel.className = "checklist";
  panel.innerHTML =
    '<h3>📋 Alışveriş listesi</h3>' +
    '<p class="cl-hint">Her ürünü işaretle, durumunu seç. Seçimler yalnızca bu tarayıcıda saklanır.</p>' +
    '<div class="cl-rows"></div>' +
    '<div class="cl-actions">' +
    '<button type="button" class="cl-copy">Listeyi kopyala</button>' +
    '<button type="button" class="cl-print">Yazdır</button>' +
    '</div><p class="cl-msg" aria-live="polite"></p>';
  var rowsEl = panel.querySelector(".cl-rows");
  items.forEach(function (it) { rowsEl.appendChild(row(it)); });

  panel.querySelector(".cl-copy").addEventListener("click", function () {
    var text = items.map(function (it) {
      var s = saved[it.id] || { status: STATUSES[0], done: false };
      return (s.done ? "[x] " : "[ ] ") + it.name + " — " + s.status;
    }).join("\n");
    var msg = panel.querySelector(".cl-msg");
    navigator.clipboard && navigator.clipboard.writeText(text).then(function () {
      msg.textContent = "Liste kopyalandı.";
      setTimeout(function () { msg.textContent = ""; }, 2500);
    }).catch(function () { msg.textContent = "Kopyalanamadı, elle seçip kopyalayabilirsin."; });
  });
  panel.querySelector(".cl-print").addEventListener("click", function () { window.print(); });

  mount.appendChild(panel);
})();
