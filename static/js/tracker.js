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

  function analyticsOn() {
    return !!(window.HOBIBUL_CONSENT && window.HOBIBUL_CONSENT.analytics);
  }

  var pageviewSent = false;
  function sendPageview() {
    if (pageviewSent || !analyticsOn()) return;
    pageviewSent = true;
    track("pageview", { referrer: document.referrer });
  }

  ready(function () {
    // Sayfa görüntülemesi yalnızca analitik izni açıksa gider.
    sendPageview();
    document.addEventListener("hobibul:consent", sendPageview);

    // affiliate tıklaması (event delegation)
    document.addEventListener("click", function (e) {
      if (!analyticsOn()) return;
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
