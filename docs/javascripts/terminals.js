/* Run before the plugin's termynal.js: keep transcripts readable until requested. */
(() => {
  "use strict";
  document.querySelectorAll(".termy").forEach((terminal) => {
    // The plugin auto-starts .termy elements. Its styles use data-termynal instead.
    terminal.classList.remove("termy");
    terminal.setAttribute("role", "region");
    terminal.setAttribute("aria-label", "Recorded example terminal output");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    window.addEventListener("load", () => {
      if (typeof Termynal === "undefined") return;
      const play = document.createElement("button");
      play.type = "button";
      play.className = "terminal-play";
      play.textContent = "Play terminal demonstration";
      play.addEventListener("click", () => {
        new Termynal(terminal, { typeDelay: 35, lineDelay: 350 });
        play.remove();
      }, { once: true });
      terminal.before(play);
    }, { once: true });
  });
})();
