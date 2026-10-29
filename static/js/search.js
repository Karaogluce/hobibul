/* Üst menüdeki arama. Ana sayfada kategori kartlarını da süzer. */
(function () {
  var input = document.getElementById("site-search");
  var panel = document.getElementById("search-panel");
  var dataEl = document.getElementById("search-index");
  if (!input || !panel || !dataEl) return;

  var index = [];
  try { index = JSON.parse(dataEl.textContent || "[]"); } catch (e) { index = []; }

  var cards = document.querySelectorAll("#cat-grid .cat-card");
  var none = document.getElementById("no-result");
  var active = -1;

  function tr(s) {
    return (s || "").toLocaleLowerCase("tr");
  }

  function matches(q) {
    if (!q) return [];
    var out = [];
    for (var i = 0; i < index.length; i++) {
      var row = index[i];
      if (tr(row.hay).indexOf(q) !== -1 || tr(row.title).indexOf(q) !== -1) out.push(row);
      if (out.length >= 8) break;
    }
    return out;
  }

  function filterCards(q) {
    if (!cards.length) return;
    var shown = 0;
    cards.forEach(function (c) {
      var hay = tr(c.getAttribute("data-search"));
      var ok = !q || hay.indexOf(q) !== -1;
      c.classList.toggle("hide", !ok);
      if (ok) shown++;
    });
    if (none) none.classList.toggle("hide", shown !== 0);
  }

  function render(rows) {
    panel.innerHTML = "";
    active = -1;
    if (!rows.length) {
      panel.hidden = true;
      input.setAttribute("aria-expanded", "false");
      return;
    }
    rows.forEach(function (row, i) {
      var a = document.createElement("a");
      a.href = row.url;
      a.setAttribute("role", "option");
      a.id = "search-opt-" + i;
      var strong = document.createElement("span");
      strong.textContent = row.title;
      var small = document.createElement("small");
      small.textContent = row.kind || "";
      a.appendChild(strong);
      a.appendChild(small);
      panel.appendChild(a);
    });
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function setActive(i) {
    var links = panel.querySelectorAll("a");
    links.forEach(function (a) { a.removeAttribute("aria-selected"); });
    if (i < 0 || i >= links.length) {
      active = -1;
      input.removeAttribute("aria-activedescendant");
      return;
    }
    active = i;
    links[i].setAttribute("aria-selected", "true");
    input.setAttribute("aria-activedescendant", links[i].id);
  }

  function go(url) {
    if (url) window.location.href = url;
  }

  input.addEventListener("input", function () {
    var q = tr(input.value.trim());
    filterCards(q);
    render(matches(q));
  });

  input.form.addEventListener("submit", function (e) {
    var q = tr(input.value.trim());
    var rows = matches(q);
    if (active >= 0 && panel.querySelectorAll("a")[active]) {
      e.preventDefault();
      go(panel.querySelectorAll("a")[active].href);
      return;
    }
    if (rows.length) {
      e.preventDefault();
      go(rows[0].url);
      return;
    }
    if (cards.length) e.preventDefault();
  });

  input.addEventListener("keydown", function (e) {
    var links = panel.querySelectorAll("a");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(Math.min(active + 1, links.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(Math.max(active - 1, 0));
    } else if (e.key === "Escape") {
      panel.hidden = true;
      input.setAttribute("aria-expanded", "false");
    }
  });

  document.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest(".nav-search")) {
      panel.hidden = true;
      input.setAttribute("aria-expanded", "false");
    }
  });

  var params = new URLSearchParams(window.location.search);
  var initial = params.get("q");
  if (initial) {
    input.value = initial;
    var q0 = tr(initial.trim());
    filterCards(q0);
    render(matches(q0));
  }
})();
