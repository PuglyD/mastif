/* Collapse nested entries in the desktop TOC without replacing Material's links. */
(() => {
  "use strict";

  const toc = document.querySelector(".md-sidebar--secondary .md-nav--secondary");
  if (!toc) return;

  const branches = new Map();
  toc.querySelectorAll(".md-nav__item").forEach((item, index) => {
    const link = item.querySelector(":scope > a.md-nav__link");
    const children = item.querySelector(":scope > nav.md-nav");
    if (!link || !children) return;

    const title = link.textContent.trim();
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toc-toggle";
    children.id = `mastif-toc-branch-${index}`;
    button.setAttribute("aria-controls", children.id);

    const setExpanded = (expanded) => {
      children.hidden = !expanded;
      button.setAttribute("aria-expanded", String(expanded));
      button.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} ${title}`);
    };

    button.addEventListener("click", () => setExpanded(children.hidden));
    item.classList.add("toc-branch");
    link.after(button);
    branches.set(item, setExpanded);
    setExpanded(false);
  });

  const reveal = (link) => {
    for (let node = link.parentElement; node && node !== toc; node = node.parentElement) {
      branches.get(node)?.(true);
    }
  };

  const revealHash = () => {
    if (!window.location.hash) return;
    const link = [...toc.querySelectorAll("a.md-nav__link")]
      .find((entry) => entry.hash === window.location.hash);
    if (link) reveal(link);
  };

  toc.addEventListener("click", (event) => {
    const link = event.target.closest("a.md-nav__link");
    if (link) reveal(link);
  });
  window.addEventListener("hashchange", revealHash);
  revealHash();
})();
