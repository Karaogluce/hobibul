// Hangi Hobi Sana Uygun? — tamamen istemci tarafında, sunucu/çerez gerekmez.
(function () {
  "use strict";
  var QUESTIONS = [
    {
      q: "Haftada hobine kaç saat ayırabilirsin?",
      opts: [
        { t: "1-2 saat", w: { "yazi-edebiyat": 2, "koleksiyon": 2, "bilim-astronomi": 1, "sanat": 1 } },
        { t: "3-5 saat", w: { "muzik": 2, "el-sanatlari": 2, "yemek-mutfak": 2, "bahce-bitki": 1, "yazilim-kodlama": 1 } },
        { t: "6 saat ve üzeri", w: { "outdoor": 2, "spor-fitness": 2, "teknoloji": 2, "seyahat-gezi": 2 } }
      ]
    },
    {
      q: "Evde hobine ayırabileceğin alan ne kadar?",
      opts: [
        { t: "Çok az — bir çekmece yeter", w: { "yazi-edebiyat": 2, "koleksiyon": 2, "muzik": 1, "yazilim-kodlama": 2 } },
        { t: "Orta — bir masa/köşe", w: { "el-sanatlari": 2, "sanat": 2, "bilim-astronomi": 1, "yemek-mutfak": 1, "teknoloji": 1 } },
        { t: "Bol — ayrı oda, garaj veya bahçe", w: { "bahce-bitki": 2, "evcil-hayvan": 2, "outdoor": 1, "spor-fitness": 1 } }
      ]
    },
    {
      q: "Ses, koku veya dağınıklık senin için sorun mu?",
      opts: [
        { t: "Evet, sessiz ve düzenli olmalı", w: { "yazi-edebiyat": 2, "bilim-astronomi": 2, "koleksiyon": 1, "yazilim-kodlama": 1 } },
        { t: "Biraz idare ederim", w: { "el-sanatlari": 1, "sanat": 1, "muzik": 1, "yemek-mutfak": 1 } },
        { t: "Hiç sorun değil", w: { "outdoor": 2, "bahce-bitki": 1, "evcil-hayvan": 1, "spor-fitness": 1, "teknoloji": 1 } }
      ]
    },
    {
      q: "Hobini kiminle yapmak istersin?",
      opts: [
        { t: "Tek başıma", w: { "yazi-edebiyat": 2, "bilim-astronomi": 1, "koleksiyon": 1, "yazilim-kodlama": 1, "sanat": 1 } },
        { t: "Aile veya çocuklarla", w: { "bahce-bitki": 2, "evcil-hayvan": 2, "yemek-mutfak": 1, "outdoor": 1 } },
        { t: "Fark etmez", w: { "muzik": 1, "teknoloji": 1, "spor-fitness": 1, "seyahat-gezi": 1, "koleksiyon": 1 } }
      ]
    },
    {
      q: "Başlarken ne istersin?",
      opts: [
        { t: "Az eşyayla basit başlamak", w: { "yazi-edebiyat": 2, "spor-fitness": 1, "bahce-bitki": 1, "yemek-mutfak": 1 } },
        { t: "Gelişmiş, teknik bir kurulum", w: { "teknoloji": 2, "bilim-astronomi": 2, "yazilim-kodlama": 2, "muzik": 1 } },
        { t: "Ortası iyi, zamanla büyüsün", w: { "el-sanatlari": 1, "sanat": 1, "koleksiyon": 1, "outdoor": 1, "evcil-hayvan": 1, "seyahat-gezi": 1 } }
      ]
    }
  ];

  var CATS = {
    "outdoor": "Outdoor & Doğa", "el-sanatlari": "El Sanatları & DIY", "muzik": "Müzik",
    "teknoloji": "Teknoloji", "koleksiyon": "Koleksiyon", "spor-fitness": "Spor & Fitness",
    "sanat": "Sanat", "yemek-mutfak": "Yemek & Mutfak", "bahce-bitki": "Bahçe & Bitki",
    "evcil-hayvan": "Evcil Hayvan", "bilim-astronomi": "Bilim & Astronomi",
    "seyahat-gezi": "Seyahat & Gezi", "yazilim-kodlama": "Yazılım & Kodlama", "yazi-edebiyat": "Yazı & Edebiyat"
  };

  var root = document.getElementById("hb-quiz");
  if (!root) return;
  var state = { step: 0, scores: {} };

  function render() {
    if (state.step < QUESTIONS.length) {
      var q = QUESTIONS[state.step];
      root.innerHTML =
        '<div class="quiz-progress">Soru ' + (state.step + 1) + ' / ' + QUESTIONS.length + '</div>' +
        '<h2 class="quiz-q">' + q.q + '</h2>' +
        '<div class="quiz-opts">' +
        q.opts.map(function (o, i) { return '<button type="button" class="quiz-opt" data-i="' + i + '">' + o.t + '</button>'; }).join("") +
        '</div>';
      root.querySelectorAll(".quiz-opt").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var opt = q.opts[parseInt(btn.getAttribute("data-i"), 10)];
          Object.keys(opt.w).forEach(function (k) { state.scores[k] = (state.scores[k] || 0) + opt.w[k]; });
          state.step++;
          render();
        });
      });
    } else {
      var ranked = Object.keys(state.scores).sort(function (a, b) { return state.scores[b] - state.scores[a]; }).slice(0, 3);
      root.innerHTML =
        '<h2 class="quiz-q">Sana uygun olabilecek hobiler</h2>' +
        '<div class="quiz-results">' +
        ranked.map(function (id) {
          return '<a class="quiz-result" href="/kategori/' + id + '/">' + (CATS[id] || id) + ' →</a>';
        }).join("") +
        '</div>' +
        '<button type="button" class="quiz-restart">Tekrar başla</button>';
      root.querySelector(".quiz-restart").addEventListener("click", function () {
        state = { step: 0, scores: {} };
        render();
      });
    }
  }
  render();
})();
