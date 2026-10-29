/* Çerez / KVKK bandı. Tercih localStorage'da durur, Consent Mode v2 güncellenir. */
(function () {
  "use strict";

  var KEY = "hobibul_consent_v1";
  var banner = document.getElementById("consent-banner");
  if (!banner) return;

  var settings = document.getElementById("consent-settings");
  var settingsBtn = document.getElementById("consent-settings-btn");
  var analyticsBox = document.getElementById("consent-analytics");
  var adsBox = document.getElementById("consent-ads");

  function read() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return null;
      var c = JSON.parse(raw);
      if (typeof c.analytics !== "boolean" || typeof c.ads !== "boolean") return null;
      return c;
    } catch (e) {
      return null;
    }
  }

  function apply(analytics, ads) {
    var payload = {
      analytics_storage: analytics ? "granted" : "denied",
      ad_storage: ads ? "granted" : "denied",
      ad_user_data: ads ? "granted" : "denied",
      ad_personalization: ads ? "granted" : "denied"
    };
    window.dataLayer = window.dataLayer || [];
    if (typeof gtag === "function") gtag("consent", "update", payload);
    window.HOBIBUL_CONSENT = { analytics: analytics, ads: ads, decided: true };
    try {
      localStorage.setItem(KEY, JSON.stringify({
        analytics: analytics,
        ads: ads,
        t: new Date().toISOString()
      }));
    } catch (e) { /* gizli pencerede kayıt tutmayabilir */ }
    document.dispatchEvent(new CustomEvent("hobibul:consent", { detail: window.HOBIBUL_CONSENT }));
  }

  function syncPad() {
    if (banner.hidden) {
      document.body.classList.remove("consent-open");
      document.body.style.paddingBottom = "";
      return;
    }
    document.body.classList.add("consent-open");
    document.body.style.paddingBottom = (banner.offsetHeight + 16) + "px";
  }

  function setSettings(open) {
    if (!settings || !settingsBtn) return;
    settings.hidden = !open;
    settingsBtn.setAttribute("aria-expanded", open ? "true" : "false");
    syncPad();
  }

  function fillBoxes() {
    var c = read() || window.HOBIBUL_CONSENT || { analytics: false, ads: false };
    if (analyticsBox) analyticsBox.checked = !!c.analytics;
    if (adsBox) adsBox.checked = !!c.ads;
  }

  function show(openSettings) {
    fillBoxes();
    banner.hidden = false;
    setSettings(!!openSettings);
    syncPad();
  }

  function hide() {
    setSettings(false);
    banner.hidden = true;
    syncPad();
  }

  document.getElementById("consent-accept").addEventListener("click", function () {
    apply(true, true);
    hide();
  });
  document.getElementById("consent-reject").addEventListener("click", function () {
    apply(false, false);
    hide();
  });
  if (settingsBtn) {
    settingsBtn.addEventListener("click", function () {
      var open = settings.hidden;
      if (open) fillBoxes();
      setSettings(open);
    });
  }
  document.getElementById("consent-save").addEventListener("click", function () {
    apply(!!(analyticsBox && analyticsBox.checked), !!(adsBox && adsBox.checked));
    hide();
  });

  document.querySelectorAll("[data-consent-open]").forEach(function (el) {
    el.addEventListener("click", function (e) {
      e.preventDefault();
      show(true);
      var first = banner.querySelector("button, a");
      if (first) first.focus();
    });
  });

  window.addEventListener("resize", syncPad);

  if (!read()) show(false);
  else hide();
})();
