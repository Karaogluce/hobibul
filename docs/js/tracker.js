/* Hobi Bul — trafik & affiliate tıklama izleme.
 * Supabase (ücretsiz) backend'ine olay yazar. Yapılandırma /js/config.js içindedir;
 * URL/anahtar yer tutucu ise izleme sessizce devre dışı kalır.
 */
(function () {
  "use strict";

  var cfg = window.HOBIBUL_CONFIG || {};
  var supabaseUrl = (cfg.supabaseUrl || "").replace(/\/+$/, "");
  var supabaseKey = cfg.supabaseAnonKey || "";

  var enabled = supabaseUrl &&
                supabaseKey &&
                supabaseUrl.indexOf("SUPABASE_URL") === -1 &&
                supabaseKey.indexOf("SUPABASE_ANON_KEY") === -1;

  function track(eventType, data) {
    if (!enabled) return;
    var payload = Object.assign({ event_type: eventType, page: location.pathname }, data || {});
    // keepalive: istek, sayfa gezinmesi sırasında bile tamamlanır.
    fetch(supabaseUrl + "/rest/v1/analytics_events", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "apikey": supabaseKey,
        "Authorization": "Bearer " + supabaseKey,
        "Prefer": "return=minimal"
      },
      body: JSON.stringify(payload),
      keepalive: true
    }).catch(function () { /* sessizce yut */ });
  }

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    // sayfa görüntülenmesi
    track("pageview", { referrer: document.referrer });

    // affiliate tıklaması (event delegation)
    document.addEventListener("click", function (e) {
      var el = e.target && e.target.closest ? e.target.closest("a[data-aff-link]") : null;
      if (!el) return;
      track("click", {
        product_id: el.getAttribute("data-aff-link"),
        network: el.getAttribute("data-network") || "amazon",
        page: location.pathname
      });
    });
  });
})();
