/* Hobi Bul — analitik paneli.
 * Supabase'teki olayları çeker ve makale/ürün bazında görüntüler.
 * Bağlantı yoksa "demo mod"da çalışır ve nasıl bağlanacağını gösterir.
 */
(function () {
  "use strict";

  var cfg = window.HOBIBUL_CONFIG || {};
  var supabaseUrl = (cfg.supabaseUrl || "").replace(/\/+$/, "");
  var supabaseKey = cfg.supabaseAnonKey || "";
  var passHash = cfg.dashboardHash || "";
  var enabled = supabaseUrl && supabaseKey &&
    supabaseUrl.indexOf("SUPABASE_URL") === -1 &&
    supabaseKey.indexOf("SUPABASE_ANON_KEY") === -1;
  var articles = window.HOBIBUL_ARTICLES || [];

  var banner = document.getElementById("dash-banner");
  var statCards = document.getElementById("stat-cards");
  var artWrap = document.getElementById("dash-articles");
  var prodWrap = document.getElementById("dash-products");
  var lock = document.getElementById("dash-lock");
  var content = document.getElementById("dash-content");
  var form = document.getElementById("dash-login");
  var passInput = document.getElementById("dash-pass");
  var passErr = document.getElementById("dash-err");

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function fmt(n) { return Number(n || 0).toLocaleString("tr-TR"); }
  function setBanner(type, html) { banner.className = "dash-banner " + type; banner.innerHTML = html; }
  function stat(label, value) {
    return '<div class="stat-card"><div class="label">' + esc(label) + '</div><div class="value">' + value + '</div></div>';
  }

  function renderAll(events) {
    var byPage = {};
    var byProd = {};
    (events || []).forEach(function (ev) {
      if (ev.event_type === "pageview") {
        byPage[ev.page] = byPage[ev.page] || { views: 0, clicks: 0 };
        byPage[ev.page].views++;
      } else if (ev.event_type === "click") {
        byPage[ev.page] = byPage[ev.page] || { views: 0, clicks: 0 };
        byPage[ev.page].clicks++;
        if (ev.product_id) byProd[ev.product_id] = (byProd[ev.product_id] || 0) + 1;
      }
    });

    var totalViews = 0, totalClicks = 0;
    Object.keys(byPage).forEach(function (k) {
      totalViews += byPage[k].views;
      totalClicks += byPage[k].clicks;
    });
    var ctr = totalViews > 0 ? (totalClicks / totalViews * 100) : 0;

    statCards.innerHTML =
      stat("Toplam Görüntülenme", fmt(totalViews)) +
      stat("Affiliate Tıklama", fmt(totalClicks)) +
      stat("Genel CTR", ctr.toFixed(2) + "%") +
      stat("İzlenen Sayfa", fmt(Object.keys(byPage).length));

    var rows = articles.map(function (a) {
      var s = byPage[a.path] || { views: 0, clicks: 0 };
      var c = s.views > 0 ? (s.clicks / s.views * 100) : 0;
      return '<tr><td>' + esc(a.title) + '</td><td>' + fmt(s.views) + '</td><td>' +
        fmt(s.clicks) + '</td><td><span class="ctr-badge">' + c.toFixed(2) + '%</span></td></tr>';
    }).join("");
    artWrap.innerHTML = '<table><thead><tr><th>Makale</th><th>Görüntülenme</th><th>Tıklama</th><th>CTR</th></tr></thead><tbody>' +
      rows + '</tbody></table>';

    var prods = Object.keys(byProd).map(function (id) { return { id: id, clicks: byProd[id] }; })
      .sort(function (a, b) { return b.clicks - a.clicks; }).slice(0, 15);
    var prows = prods.length ? prods.map(function (p) {
      return '<tr><td><code>' + esc(p.id) + '</code></td><td>' + fmt(p.clicks) + '</td></tr>';
    }).join("") : '<tr><td colspan="2">Henüz tıklama kaydı yok.</td></tr>';
    prodWrap.innerHTML = '<table><thead><tr><th>Ürün</th><th>Tıklama</th></tr></thead><tbody>' + prows + '</tbody></table>';
  }

  function sha256js(ascii) {
    function rr(v, a) { return (v >>> a) | (v << (32 - a)); }
    var maxWord = Math.pow(2, 32), i, j, result = "", words = [], asciiBitLength = ascii.length * 8;
    var hash = sha256js.h = sha256js.h || [];
    var k = sha256js.k = sha256js.k || [];
    var primeCounter = k.length, isComposite = {};
    for (var candidate = 2; primeCounter < 64; candidate++) {
      if (!isComposite[candidate]) {
        for (i = 0; i < 313; i += candidate) isComposite[i] = candidate;
        hash[primeCounter] = (Math.pow(candidate, .5) * maxWord) | 0;
        k[primeCounter++] = (Math.pow(candidate, 1 / 3) * maxWord) | 0;
      }
    }
    ascii += "\x80";
    while (ascii.length % 64 - 56) ascii += "\x00";
    for (i = 0; i < ascii.length; i++) {
      j = ascii.charCodeAt(i);
      if (j >> 8) return "";
      words[i >> 2] |= j << ((3 - i) % 4) * 8;
    }
    words[words.length] = ((asciiBitLength / maxWord) | 0);
    words[words.length] = (asciiBitLength);
    for (j = 0; j < words.length;) {
      var w = words.slice(j, j += 16), oldHash = hash;
      hash = hash.slice(0, 8);
      for (i = 0; i < 64; i++) {
        var w15 = w[i - 15], w2 = w[i - 2], a = hash[0], e = hash[4];
        var temp1 = hash[7] + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + ((e & hash[5]) ^ ((~e) & hash[6])) + k[i]
          + (w[i] = (i < 16) ? w[i] : (w[i - 16] + (rr(w15, 7) ^ rr(w15, 18) ^ (w15 >>> 3)) + w[i - 7] + (rr(w2, 17) ^ rr(w2, 19) ^ (w2 >>> 10))) | 0);
        var temp2 = (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
        hash = [(temp1 + temp2) | 0].concat(hash);
        hash[4] = (hash[4] + temp1) | 0;
      }
      for (i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i]) | 0;
    }
    for (i = 0; i < 8; i++) for (j = 3; j + 1; j--) {
      var b = (hash[i] >> (j * 8)) & 255;
      result += ((b < 16) ? 0 : "") + b.toString(16);
    }
    return result;
  }

  function sha256hex(str) {
    if (window.crypto && crypto.subtle && crypto.subtle.digest) {
      try {
        var data = new TextEncoder().encode(str);
        return crypto.subtle.digest("SHA-256", data).then(function (buf) {
          return Array.prototype.map.call(new Uint8Array(buf), function (b) {
            return ("0" + b.toString(16)).slice(-2);
          }).join("");
        });
      } catch (e) { /* saf-JS yedeğe düş */ }
    }
    return Promise.resolve(sha256js(str));
  }

  function loadData() {
    if (!enabled) {
      setBanner("demo", "⚠️ <strong>Demo mod:</strong> Analitik henüz bağlanmadı, değerler 0 gösteriliyor. Gerçek veriler için Supabase bağlantısını kurun — adımlar <code>README.md</code> dosyasında.");
      renderAll([]);
      return;
    }
    setBanner("live", "🟢 Canlı veriler — Supabase bağlantısı aktif.");
    fetch(supabaseUrl + "/rest/v1/analytics_events?select=event_type,page,product_id&limit=1000", {
      headers: { "apikey": supabaseKey, "Authorization": "Bearer " + supabaseKey }
    })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (events) { renderAll(events || []); })
      .catch(function (err) {
        setBanner("error", "❌ Veri çekilemedi: " + esc(err.message) + ". Supabase'te <code>analytics_events</code> tablosunun kurulu olduğundan emin olun.");
        renderAll([]);
      });
  }

  function unlock() {
    if (lock) lock.style.display = "none";
    if (content) content.style.display = "block";
    loadData();
  }

  if (!passHash || sessionStorage.getItem("hb_auth") === "1") {
    unlock();
  }

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var val = passInput ? passInput.value.trim() : "";
      sha256hex(val).then(function (h) {
        if (h === passHash) {
          sessionStorage.setItem("hb_auth", "1");
          if (passErr) passErr.textContent = "";
          unlock();
        } else if (passErr) {
          passErr.textContent = "Hatalı şifre, tekrar dene.";
        }
      }).catch(function () {
        if (passErr) passErr.textContent = "Bu tarayıcı şifrelemeyi desteklemiyor (HTTPS gerekli).";
      });
    });
  }
})();
