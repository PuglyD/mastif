/*
 * Interactive Mermaid diagrams for the mastif docs.
 *
 * Material for MkDocs renders Mermaid into a closed shadow root, which no script can
 * reach, and scales wide diagrams down until they are unreadable. So the docs render
 * Mermaid themselves: mkdocs.yml gives ```mermaid fences the class "diagram" (which
 * Material ignores), and this script turns each one into a viewer with
 *
 *   - zoom buttons, a reset ("fit") button and a fullscreen button
 *   - drag to pan; Ctrl/Cmd + scroll to zoom (plain scroll in fullscreen, so the page
 *     still scrolls normally past inline diagrams)
 *   - double-click to open fullscreen; Esc to close it
 *   - keyboard: + / - to zoom, 0 to fit, f for fullscreen, arrow keys to pan
 *   - light/dark theme following Material's palette toggle
 *
 * A diagram that fails to render shows the error and its source instead of vanishing.
 */
(() => {
  "use strict";

  const MERMAID_URL = "https://unpkg.com/mermaid@11/dist/mermaid.min.js";
  const MIN_ZOOM = 0.1;
  const MAX_ZOOM = 8;
  const STEP = 1.25;
  const INLINE_MAX_HEIGHT = 0.7; // fraction of the window height
  const PAN_STEP = 60; // pixels per arrow-key press

  let mermaidReady = null;
  let renderCount = 0;
  const viewers = [];

  function loadMermaid() {
    if (!mermaidReady) {
      mermaidReady = new Promise((resolve, reject) => {
        if (window.mermaid) return resolve(window.mermaid);
        const script = document.createElement("script");
        script.src = MERMAID_URL;
        script.onload = () => resolve(window.mermaid);
        script.onerror = () => reject(new Error(`could not load ${MERMAID_URL}`));
        document.head.appendChild(script);
      });
    }
    return mermaidReady;
  }

  function isDark() {
    return document.body.getAttribute("data-md-color-scheme") === "slate";
  }

  function configure(mermaid) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: isDark() ? "dark" : "default",
      fontFamily: getComputedStyle(document.body).fontFamily,
      // Natural size: the viewer does the scaling, so text never shrinks on its own.
      flowchart: { useMaxWidth: false, htmlLabels: true },
      sequence: { useMaxWidth: false },
      state: { useMaxWidth: false },
    });
  }

  function button(label, title, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "diagram-button";
    b.textContent = label;
    b.title = title;
    b.setAttribute("aria-label", title);
    b.addEventListener("click", (event) => {
      event.stopPropagation();
      onClick();
    });
    return b;
  }

  class Viewer {
    constructor(pre) {
      this.source = pre.textContent;
      this.x = 0;
      this.y = 0;
      this.k = 1;
      this.width = 0;
      this.height = 0;
      this.fullscreen = false;

      this.frame = document.createElement("div");
      this.frame.className = "diagram-frame";

      const toolbar = document.createElement("div");
      toolbar.className = "diagram-toolbar";
      toolbar.append(
        button("+", "Zoom in (+)", () => this.zoomBy(STEP)),
        button("−", "Zoom out (-)", () => this.zoomBy(1 / STEP)),
        button("↺", "Fit to view (0)", () => this.fit()),
        (this.fullscreenButton = button("⛶", "Fullscreen (f)", () => this.toggleFullscreen()))
      );

      this.viewport = document.createElement("div");
      this.viewport.className = "diagram-viewport";
      this.viewport.tabIndex = 0;
      this.viewport.setAttribute("role", "img");
      this.viewport.setAttribute(
        "aria-label",
        "Diagram. Drag to pan, Ctrl+scroll or +/- to zoom, f for fullscreen."
      );

      this.stage = document.createElement("div");
      this.stage.className = "diagram-stage";
      this.viewport.appendChild(this.stage);

      this.hint = document.createElement("span");
      this.hint.className = "diagram-hint";

      const header = document.createElement("div");
      header.className = "diagram-header";
      header.append(this.hint, toolbar);

      this.frame.append(header, this.viewport);
      this.updateHint();
      pre.replaceWith(this.frame);
      this.bindInput();
    }

    async render(mermaid) {
      const id = `mastif-diagram-${++renderCount}`;
      try {
        const { svg, bindFunctions } = await mermaid.render(id, this.source);
        this.stage.innerHTML = svg;
        const el = this.stage.querySelector("svg");
        if (bindFunctions) bindFunctions(el);
        const box = el.viewBox.baseVal;
        this.width = box && box.width ? box.width : el.getBBox().width;
        this.height = box && box.height ? box.height : el.getBBox().height;
        el.removeAttribute("style"); // drop Mermaid's max-width
        el.setAttribute("width", this.width);
        el.setAttribute("height", this.height);
        this.frame.classList.remove("diagram-error");
        this.fit();
      } catch (error) {
        document.getElementById(id)?.remove(); // Mermaid leaves a temporary node behind
        document.getElementById(`d${id}`)?.remove();
        this.frame.classList.add("diagram-error");
        this.stage.innerHTML = "";
        const message = document.createElement("pre");
        message.textContent = `Diagram failed to render: ${error.message || error}\n\n${this.source}`;
        this.stage.appendChild(message);
        this.viewport.style.height = "";
        this.stage.style.transform = "";
      }
    }

    updateHint() {
      this.hint.textContent = this.fullscreen
        ? "Drag to pan · scroll to zoom · Esc to close"
        : "Drag to pan · Ctrl+scroll to zoom · double-click for fullscreen";
    }

    available() {
      const rect = this.viewport.getBoundingClientRect();
      return { w: rect.width, h: rect.height };
    }

    fit() {
      if (!this.width) return;
      if (this.fullscreen) {
        this.viewport.style.height = "";
      } else {
        // Inline: as wide as the text column, never enlarged beyond natural size, and
        // no taller than most of the window.
        const w = this.viewport.clientWidth;
        const scale = Math.min(1, w / this.width, (window.innerHeight * INLINE_MAX_HEIGHT) / this.height);
        this.viewport.style.height = `${Math.ceil(this.height * scale) + 16}px`;
      }
      const { w, h } = this.available();
      const pad = this.fullscreen ? 32 : 8;
      const limit = this.fullscreen ? 3 : 1;
      this.k = Math.min(limit, (w - pad) / this.width, (h - pad) / this.height);
      this.x = (w - this.width * this.k) / 2;
      this.y = (h - this.height * this.k) / 2;
      this.apply();
    }

    apply() {
      this.stage.style.transform = `translate(${this.x}px, ${this.y}px) scale(${this.k})`;
    }

    zoomBy(factor, px, py) {
      const { w, h } = this.available();
      const cx = px ?? w / 2;
      const cy = py ?? h / 2;
      const k = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.k * factor));
      // Keep the point under the cursor (or the centre) fixed while zooming.
      this.x = cx - ((cx - this.x) * k) / this.k;
      this.y = cy - ((cy - this.y) * k) / this.k;
      this.k = k;
      this.apply();
    }

    panBy(dx, dy) {
      this.x += dx;
      this.y += dy;
      this.apply();
    }

    toggleFullscreen() {
      this.fullscreen = !this.fullscreen;
      if (this.fullscreen) {
        this.placeholder = document.createElement("div");
        this.placeholder.style.height = `${this.frame.offsetHeight}px`;
        this.frame.replaceWith(this.placeholder);
        this.overlay = document.createElement("div");
        this.overlay.className = "diagram-overlay";
        this.overlay.addEventListener("click", (event) => {
          if (event.target === this.overlay) this.toggleFullscreen();
        });
        this.overlay.appendChild(this.frame);
        document.body.appendChild(this.overlay);
        document.body.classList.add("diagram-overlay-open");
        this.frame.classList.add("diagram-fullscreen");
        this.fullscreenButton.title = "Close fullscreen (Esc)";
        this.fullscreenButton.setAttribute("aria-label", "Close fullscreen (Esc)");
        this.fullscreenButton.textContent = "✕";
      } else {
        this.frame.classList.remove("diagram-fullscreen");
        this.placeholder.replaceWith(this.frame);
        this.overlay.remove();
        document.body.classList.remove("diagram-overlay-open");
        this.fullscreenButton.title = "Fullscreen (f)";
        this.fullscreenButton.setAttribute("aria-label", "Fullscreen (f)");
        this.fullscreenButton.textContent = "⛶";
      }
      this.updateHint();
      this.fit();
      this.viewport.focus({ preventScroll: true });
    }

    bindInput() {
      const vp = this.viewport;
      let drag = null;

      vp.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
        vp.setPointerCapture(event.pointerId);
        vp.classList.add("diagram-dragging");
      });
      vp.addEventListener("pointermove", (event) => {
        if (!drag || drag.id !== event.pointerId) return;
        this.panBy(event.clientX - drag.x, event.clientY - drag.y);
        drag.x = event.clientX;
        drag.y = event.clientY;
      });
      const end = (event) => {
        if (drag && drag.id === event.pointerId) {
          drag = null;
          vp.classList.remove("diagram-dragging");
        }
      };
      vp.addEventListener("pointerup", end);
      vp.addEventListener("pointercancel", end);

      vp.addEventListener(
        "wheel",
        (event) => {
          // Inline, plain scrolling must keep scrolling the page.
          if (!this.fullscreen && !event.ctrlKey && !event.metaKey) return;
          event.preventDefault();
          const rect = vp.getBoundingClientRect();
          const factor = Math.exp(-event.deltaY * (event.deltaMode === 1 ? 0.05 : 0.0015));
          this.zoomBy(factor, event.clientX - rect.left, event.clientY - rect.top);
        },
        { passive: false }
      );

      vp.addEventListener("dblclick", () => this.toggleFullscreen());

      vp.addEventListener("keydown", (event) => {
        const keys = {
          "+": () => this.zoomBy(STEP),
          "=": () => this.zoomBy(STEP),
          "-": () => this.zoomBy(1 / STEP),
          "0": () => this.fit(),
          f: () => this.toggleFullscreen(),
          Escape: () => this.fullscreen && this.toggleFullscreen(),
          ArrowLeft: () => this.panBy(PAN_STEP, 0),
          ArrowRight: () => this.panBy(-PAN_STEP, 0),
          ArrowUp: () => this.panBy(0, PAN_STEP),
          ArrowDown: () => this.panBy(0, -PAN_STEP),
        };
        const action = keys[event.key];
        if (action && !event.ctrlKey && !event.metaKey && !event.altKey) {
          event.preventDefault();
          action();
        }
      });
    }
  }

  async function renderAll() {
    const mermaid = await loadMermaid();
    configure(mermaid);
    for (const viewer of viewers) await viewer.render(mermaid);
  }

  function setup() {
    viewers.length = 0;
    document.querySelectorAll("pre.diagram").forEach((pre) => viewers.push(new Viewer(pre)));
    if (viewers.length) renderAll().catch((error) => console.error(error));
  }

  // Re-render in the other theme when the reader flips Material's palette toggle.
  new MutationObserver(() => {
    if (viewers.length) renderAll().catch((error) => console.error(error));
  }).observe(document.body, { attributes: true, attributeFilter: ["data-md-color-scheme"] });

  // Refit inline diagrams when the window changes size.
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => viewers.forEach((viewer) => viewer.fit()), 150);
  });

  // Escape closes fullscreen even when focus left the diagram.
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const open = viewers.find((viewer) => viewer.fullscreen);
    if (open) open.toggleFullscreen();
  });

  // Material's document$ fires on every page load, including instant navigation.
  if (window.document$) window.document$.subscribe(setup);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup);
  else setup();
})();
