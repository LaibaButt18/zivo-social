(function () {
  var KEY = "zivo-theme";
  var SUN =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><path stroke-linecap="round" d="M12 3.5v1.8M12 18.7v1.8M3.5 12h1.8M18.7 12h1.8M6 6l1.3 1.3M16.7 16.7 18 18M18 6l-1.3 1.3M7.3 16.7 6 18"/></svg>';
  var MOON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16.5 13.2A6.2 6.2 0 0 1 10.8 5 6.4 6.4 0 1 0 16.5 13.2z"/></svg>';

  function storedTheme() {
    try {
      var stored = localStorage.getItem(KEY);
      if (stored === "light" || stored === "dark") return stored;
    } catch (e) {}
    return "";
  }

  function savedTheme() {
    return storedTheme() || "dark";
  }

  function paint(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.colorScheme = theme;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#0f1419" : "#f7f9f9");
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) {
      var button = buttons[i];
      var toLight = theme === "dark";
      if (button.hasAttribute("data-theme-label")) {
        button.textContent = toLight ? "Light mode" : "Dark mode";
        button.setAttribute("aria-label", toLight ? "Switch to light mode" : "Switch to dark mode");
      } else {
        button.setAttribute("aria-label", toLight ? "Switch to light mode" : "Switch to dark mode");
        button.innerHTML = toLight ? SUN : MOON;
      }
    }
  }

  function toggle() {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(KEY, next);
    } catch (e) {}
    paint(next);
  }

  function bind(button) {
    if (!button || button.dataset.themeBound === "1") return button;
    button.dataset.themeBound = "1";
    button.type = "button";
    button.setAttribute("data-theme-toggle", "");
    if (button.hasAttribute("data-theme-label")) button.classList.add("z-theme-menu");
    else if (!button.classList.contains("z-theme-btn")) button.classList.add("z-theme-btn");
    button.addEventListener("click", toggle);
    paint(document.documentElement.getAttribute("data-theme") || savedTheme());
    return button;
  }

  paint(savedTheme());
  window.ZivoTheme = { toggle: toggle, bind: bind, paint: paint, current: savedTheme };

  document.addEventListener("DOMContentLoaded", function () {
    if (document.querySelector("[data-theme-toggle]")) return;
    if (document.getElementById("zTopbar")) return;
    var button = document.createElement("button");
    var host = document.querySelector("[data-theme-host]");
    if (host) host.appendChild(button);
    else {
      button.classList.add("z-theme-float");
      document.body.appendChild(button);
    }
    bind(button);
  });
})();
