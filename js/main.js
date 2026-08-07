/* Fenix 5ive — interactions */
(function () {
  "use strict";

  /* Sticky nav background on scroll */
  var nav = document.getElementById("nav");
  var onScroll = function () {
    nav.classList.toggle("is-scrolled", window.scrollY > 40);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* Mobile menu */
  var burger = document.getElementById("navBurger");
  var links = document.getElementById("navLinks");
  burger.addEventListener("click", function () {
    var open = links.classList.toggle("is-open");
    burger.classList.toggle("is-open", open);
    burger.setAttribute("aria-expanded", open ? "true" : "false");
  });
  links.addEventListener("click", function (e) {
    if (e.target.tagName === "A") {
      links.classList.remove("is-open");
      burger.classList.remove("is-open");
      burger.setAttribute("aria-expanded", "false");
    }
  });

  /* Scroll-reveal */
  var revealObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );
  document.querySelectorAll(".reveal").forEach(function (el) {
    revealObserver.observe(el);
  });

  /* Animated counters */
  var formatNum = function (el, value) {
    var prefix = el.dataset.prefix || "";
    var suffix = el.dataset.suffix || "";
    var raw = el.dataset.raw === "true";
    var text = raw ? String(value) : value.toLocaleString("en-US");
    el.textContent = prefix + text + suffix;
  };
  var animateCount = function (el) {
    var target = parseInt(el.dataset.count, 10);
    var duration = 1600;
    var start = null;
    var step = function (ts) {
      if (!start) start = ts;
      var progress = Math.min((ts - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      formatNum(el, Math.round(target * eased));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  var statObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          animateCount(entry.target);
          statObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.6 }
  );
  document.querySelectorAll(".stat__num").forEach(function (el) {
    statObserver.observe(el);
  });

  /* Tint simulator: VLT% = visible light transmission */
  var range = document.getElementById("tintRange");
  var shade = document.getElementById("tintShade");
  var value = document.getElementById("tintValue");
  var applyTint = function () {
    var vlt = parseInt(range.value, 10);
    shade.style.opacity = String(1 - vlt / 100);
    value.textContent = String(vlt);
  };
  range.addEventListener("input", applyTint);
  applyTint();

  /* Footer year */
  document.getElementById("year").textContent = String(new Date().getFullYear());
})();
