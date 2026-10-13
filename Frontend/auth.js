(function () {
  const tabs = document.querySelectorAll('[role="tab"]');
  if (!tabs.length) return;

  const panels = {};
  tabs.forEach((tab) => {
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    if (panel) panels[tab.id] = panel;
  });

  function animateFields(panel) {
    panel.querySelectorAll(".field-wrap").forEach((field, index) => {
      field.classList.remove("field-animate");
      void field.offsetWidth;
      field.classList.add("field-animate");
      field.style.setProperty("--field-delay", `${index * 70}ms`);
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((item) => item.setAttribute("aria-selected", "false"));
      tab.setAttribute("aria-selected", "true");

      Object.values(panels).forEach((panel) => {
        panel.classList.add("is-hidden");
        panel.classList.remove("is-active");
        panel.hidden = true;
      });

      const active = panels[tab.id];
      if (!active) return;
      active.hidden = false;
      active.classList.remove("is-hidden");
      active.classList.add("is-active");
      animateFields(active);
    });
  });

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => event.preventDefault());
  });

  const first = document.querySelector(".auth-panel.is-active");
  if (first) animateFields(first);
})();
