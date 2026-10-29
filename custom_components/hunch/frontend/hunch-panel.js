const HANDLE_RADIUS = 6;
const MIN_ZONE = 0.01;

class HunchPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.cameras = [];
    this.selected = null;
    this.image = null;
    this.zone = null;
    this.drag = null;
    this.dirty = false;
    this.loading = false;
    this.viewWidth = 0;
    this.viewHeight = 0;
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this.camerasLoaded && !this.loadingCameras) this.loadCameras();
  }

  connectedCallback() {
    this.render();
    this.observer = new ResizeObserver(() => this.resizeCanvas());
    this.observer.observe(this.stage);
    if (this._hass) this.loadCameras();
  }

  disconnectedCallback() {
    this.observer?.disconnect();
  }

  render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --ink: var(--primary-text-color, #17202a);
          --muted: var(--secondary-text-color, #64707d);
          --paper: var(--card-background-color, #fff);
          --line: var(--divider-color, #d7dde3);
          --accent: var(--primary-color, #087f8c);
          --stage: #11181f;
          --danger: var(--error-color, #b3261e);
          display: block;
          min-height: 100vh;
          background: var(--primary-background-color, #f4f6f8);
          color: var(--ink);
          font-family: Roboto, Arial, sans-serif;
        }
        * { box-sizing: border-box; }
        button, select { font: inherit; }
        button:focus-visible, select:focus-visible, canvas:focus-visible {
          outline: 3px solid color-mix(in srgb, var(--accent) 45%, transparent);
          outline-offset: 3px;
        }
        header {
          min-height: 72px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 20px;
          padding: 16px 28px;
          background: var(--paper);
          border-bottom: 1px solid var(--line);
        }
        h1 { font-size: 22px; line-height: 1.25; font-weight: 500; margin: 0; letter-spacing: -0.02em; }
        header p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
        .layout { display: grid; grid-template-columns: 232px minmax(0, 1fr); min-height: calc(100vh - 73px); }
        aside { background: var(--paper); border-right: 1px solid var(--line); padding: 20px 14px; }
        aside h2, .inspector h2 { font-size: 14px; font-weight: 500; margin: 0 8px 12px; }
        .camera {
          display: flex;
          width: 100%;
          align-items: center;
          gap: 10px;
          border: 0;
          border-radius: 8px;
          background: transparent;
          color: var(--ink);
          text-align: left;
          padding: 12px 10px;
          cursor: pointer;
        }
        .camera:hover { background: color-mix(in srgb, var(--accent) 7%, transparent); }
        .camera.selected { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
        .camera-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .dot { width: 8px; height: 8px; flex: 0 0 8px; border-radius: 50%; background: #8a959f; }
        .dot.on { background: #2d9d78; }
        .dot.off { background: #c48536; }
        main { min-width: 0; padding: 24px 28px 32px; }
        .toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
        .toolbar .spacer { flex: 1; }
        button.action {
          border: 1px solid var(--line);
          border-radius: 7px;
          background: var(--paper);
          color: var(--ink);
          padding: 9px 14px;
          cursor: pointer;
        }
        button.action:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
        button.primary { background: var(--accent); border-color: var(--accent); color: var(--text-primary-color, #fff); }
        button.primary:hover:not(:disabled) { color: var(--text-primary-color, #fff); filter: brightness(1.08); }
        button:disabled { opacity: 0.5; cursor: wait; }
        .workspace { display: grid; grid-template-columns: minmax(0, 1fr) 220px; gap: 20px; align-items: start; }
        .stage-shell { min-width: 0; background: var(--stage); border-radius: 10px; overflow: hidden; box-shadow: 0 12px 34px rgba(17, 24, 31, 0.14); }
        #stage { display: block; width: 100%; min-height: 280px; touch-action: none; cursor: crosshair; }
        .stage-footer { display: flex; justify-content: space-between; gap: 16px; padding: 11px 14px; color: #c4cdd5; font-size: 12px; }
        .inspector { padding-top: 4px; }
        .inspector h2 { margin-left: 0; }
        .inspector p { color: var(--muted); font-size: 13px; line-height: 1.5; margin: 0 0 16px; }
        #cropPreview { display: block; width: 100%; aspect-ratio: 16 / 10; object-fit: contain; background: var(--stage); border-radius: 7px; margin-bottom: 14px; }
        .readout { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0; }
        .readout div { border-top: 1px solid var(--line); padding-top: 8px; }
        .readout span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 2px; }
        .readout strong { font-weight: 500; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px; }
        .message { min-height: 22px; margin-top: 14px; color: var(--muted); font-size: 13px; }
        .message.error { color: var(--danger); }
        .empty { padding: 24px 10px; color: var(--muted); font-size: 14px; line-height: 1.5; }
        @media (max-width: 900px) {
          .layout { grid-template-columns: 1fr; }
          aside { border-right: 0; border-bottom: 1px solid var(--line); padding: 12px 16px; display: flex; gap: 6px; overflow-x: auto; }
          aside h2 { display: none; }
          .camera { width: auto; flex: 0 0 auto; }
          .workspace { grid-template-columns: 1fr; }
          .inspector { display: grid; grid-template-columns: 180px 1fr; column-gap: 18px; }
          .inspector h2 { grid-column: 1 / -1; }
          #cropPreview { grid-row: 2 / 5; }
        }
        @media (max-width: 600px) {
          header { padding: 14px 16px; }
          main { padding: 18px 12px 24px; }
          .toolbar .spacer { display: none; }
          .inspector { display: block; }
          #cropPreview { max-width: 260px; }
          .stage-footer { display: block; }
          .stage-footer span { display: block; margin: 2px 0; }
        }
        @media (prefers-reduced-motion: no-preference) {
          .camera, button.action { transition: background-color 120ms, border-color 120ms; }
        }
      </style>
      <header>
        <div><h1>Detection zones</h1><p>Choose exactly where motion and people should be seen.</p></div>
      </header>
      <div class="layout">
        <aside><h2>CCTV sources</h2><div id="cameraList"></div></aside>
        <main>
          <div class="toolbar">
            <button class="action" id="refresh">Refresh snapshot</button>
            <button class="action" id="reset">Use full frame</button>
            <span class="spacer"></span>
            <button class="action primary" id="save">Save zone</button>
          </div>
          <div class="workspace">
            <section class="stage-shell" aria-label="Detection zone editor">
              <canvas id="stage" tabindex="0" role="img" aria-label="Camera snapshot. Drag to draw a detection zone. Arrow keys move it; Shift and arrow keys resize it."></canvas>
              <div class="stage-footer"><span>Drag to draw · drag inside to move · use handles to resize</span><span id="dimensions"></span></div>
            </section>
            <section class="inspector">
              <h2>Active area</h2>
              <canvas id="cropPreview" aria-label="Cropped detection area"></canvas>
              <p id="zoneDescription">The whole frame is active.</p>
              <div class="readout">
                <div><span>Horizontal</span><strong id="xReadout">Full</strong></div>
                <div><span>Vertical</span><strong id="yReadout">Full</strong></div>
              </div>
              <p>Motion outside this area is ignored. Only the cropped image is sent for human detection.</p>
            </section>
          </div>
          <div class="message" id="message" role="status" aria-live="polite"></div>
        </main>
      </div>`;
    this.stage = this.shadowRoot.getElementById("stage");
    this.cropPreview = this.shadowRoot.getElementById("cropPreview");
    this.shadowRoot.getElementById("refresh").addEventListener("click", () => this.loadFrame());
    this.shadowRoot.getElementById("reset").addEventListener("click", () => {
      this.zone = null;
      this.dirty = true;
      this.draw();
    });
    this.shadowRoot.getElementById("save").addEventListener("click", () => this.saveZone());
    this.stage.addEventListener("pointerdown", (event) => this.pointerDown(event));
    this.stage.addEventListener("pointermove", (event) => this.pointerMove(event));
    this.stage.addEventListener("pointerup", (event) => this.pointerUp(event));
    this.stage.addEventListener("pointercancel", () => { this.drag = null; });
    this.stage.addEventListener("keydown", (event) => this.keyDown(event));
  }

  async loadCameras() {
    this.loadingCameras = true;
    this.camerasLoaded = true;
    try {
      const result = await this._hass.callWS({ type: "hunch/cameras/list" });
      this.cameras = result.cameras;
      const list = this.shadowRoot.getElementById("cameraList");
      list.replaceChildren();
      if (!this.cameras.length) {
        list.innerHTML = '<div class="empty">Add a CCTV source from the Hunch integration, then return here to draw its zone.</div>';
        this.setMessage("No CCTV sources are configured.");
        return;
      }
      for (const camera of this.cameras) {
        const button = document.createElement("button");
        button.className = "camera";
        button.innerHTML = `<span class="dot ${camera.available ? (camera.human ? "on" : "") : "off"}"></span><span class="camera-name"></span>`;
        button.querySelector(".camera-name").textContent = camera.name;
        button.title = camera.available ? (camera.human ? "Human detected" : "No human detected") : "Camera unavailable";
        button.addEventListener("click", () => this.selectCamera(camera));
        list.appendChild(button);
      }
      this.selectCamera(this.cameras[0]);
    } catch (error) {
      this.setMessage(`Could not load CCTV sources: ${error.message}`, true);
    } finally {
      this.loadingCameras = false;
    }
  }

  async selectCamera(camera) {
    this.selected = camera;
    this.zone = camera.zone ? { ...camera.zone } : null;
    this.dirty = false;
    this.shadowRoot.querySelectorAll(".camera").forEach((element, index) => {
      element.classList.toggle("selected", this.cameras[index] === camera);
    });
    await this.loadFrame();
  }

  async loadFrame() {
    if (!this.selected || this.loading) return;
    this.loading = true;
    this.updateButtons();
    this.setMessage("Fetching a fresh snapshot…");
    try {
      const result = await this._hass.callWS({
        type: "hunch/cameras/frame",
        entry_id: this.selected.entry_id,
        subentry_id: this.selected.subentry_id,
      });
      const image = new Image();
      image.src = `data:${result.content_type};base64,${result.image}`;
      await image.decode();
      this.image = image;
      this.shadowRoot.getElementById("dimensions").textContent = `${result.width} × ${result.height} pixels`;
      this.setMessage("Snapshot updated. Draw or adjust the active area.");
      this.resizeCanvas();
    } catch (error) {
      this.setMessage(`Could not fetch the snapshot: ${error.message}`, true);
    } finally {
      this.loading = false;
      this.updateButtons();
    }
  }

  async saveZone() {
    if (!this.selected || this.loading) return;
    this.loading = true;
    this.updateButtons();
    try {
      const zone = this.zone ? Object.fromEntries(Object.entries(this.zone).map(([key, value]) => [key, Number(value.toFixed(6))])) : null;
      await this._hass.callWS({
        type: "hunch/cameras/save_zone",
        entry_id: this.selected.entry_id,
        subentry_id: this.selected.subentry_id,
        zone,
      });
      this.selected.zone = zone;
      this.zone = zone;
      this.dirty = false;
      this.setMessage("Detection zone saved and applied.");
    } catch (error) {
      this.setMessage(`Could not save the zone: ${error.message}`, true);
    } finally {
      this.loading = false;
      this.updateButtons();
    }
  }

  updateButtons() {
    for (const id of ["refresh", "reset", "save"]) {
      const button = this.shadowRoot.getElementById(id);
      button.disabled = this.loading || !this.selected;
    }
    this.shadowRoot.getElementById("save").textContent = this.dirty ? "Save zone" : "Zone saved";
  }

  setMessage(text, error = false) {
    const message = this.shadowRoot.getElementById("message");
    message.textContent = text;
    message.classList.toggle("error", error);
  }

  resizeCanvas() {
    if (!this.image || !this.stage) return;
    this.viewWidth = Math.max(280, this.stage.parentElement.clientWidth);
    this.viewHeight = this.viewWidth * this.image.naturalHeight / this.image.naturalWidth;
    const ratio = window.devicePixelRatio || 1;
    this.stage.width = Math.round(this.viewWidth * ratio);
    this.stage.height = Math.round(this.viewHeight * ratio);
    this.stage.style.height = `${this.viewHeight}px`;
    this.context = this.stage.getContext("2d");
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.draw();
  }

  draw() {
    this.updateButtons();
    if (!this.context || !this.image) return;
    const ctx = this.context;
    ctx.clearRect(0, 0, this.viewWidth, this.viewHeight);
    ctx.drawImage(this.image, 0, 0, this.viewWidth, this.viewHeight);
    if (this.zone) {
      const rect = this.rect();
      ctx.fillStyle = "rgba(7, 13, 18, 0.64)";
      ctx.fillRect(0, 0, this.viewWidth, rect.y);
      ctx.fillRect(0, rect.y, rect.x, rect.h);
      ctx.fillRect(rect.x + rect.w, rect.y, this.viewWidth - rect.x - rect.w, rect.h);
      ctx.fillRect(0, rect.y + rect.h, this.viewWidth, this.viewHeight - rect.y - rect.h);
      ctx.strokeStyle = "#4fd4de";
      ctx.lineWidth = 2;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
      for (const handle of this.handles()) {
        ctx.beginPath();
        ctx.fillStyle = "#ffffff";
        ctx.strokeStyle = "#087f8c";
        ctx.lineWidth = 2;
        ctx.arc(handle.x, handle.y, HANDLE_RADIUS, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
    }
    this.drawPreview();
    const percent = (value) => `${Math.round(value * 100)}%`;
    this.shadowRoot.getElementById("zoneDescription").textContent = this.zone
      ? `${percent(this.zone.width)} wide × ${percent(this.zone.height)} high`
      : "The whole frame is active.";
    this.shadowRoot.getElementById("xReadout").textContent = this.zone ? `${percent(this.zone.x)} → ${percent(this.zone.x + this.zone.width)}` : "Full";
    this.shadowRoot.getElementById("yReadout").textContent = this.zone ? `${percent(this.zone.y)} → ${percent(this.zone.y + this.zone.height)}` : "Full";
  }

  drawPreview() {
    const canvas = this.cropPreview;
    const ctx = canvas.getContext("2d");
    canvas.width = 440;
    canvas.height = 275;
    ctx.fillStyle = "#11181f";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!this.image) return;
    const zone = this.zone || { x: 0, y: 0, width: 1, height: 1 };
    const sx = zone.x * this.image.naturalWidth;
    const sy = zone.y * this.image.naturalHeight;
    const sw = zone.width * this.image.naturalWidth;
    const sh = zone.height * this.image.naturalHeight;
    const scale = Math.min(canvas.width / sw, canvas.height / sh);
    const w = sw * scale;
    const h = sh * scale;
    ctx.drawImage(this.image, sx, sy, sw, sh, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
  }

  rect() {
    return {
      x: this.zone.x * this.viewWidth,
      y: this.zone.y * this.viewHeight,
      w: this.zone.width * this.viewWidth,
      h: this.zone.height * this.viewHeight,
    };
  }

  handles() {
    if (!this.zone) return [];
    const r = this.rect();
    return [
      { name: "nw", x: r.x, y: r.y },
      { name: "n", x: r.x + r.w / 2, y: r.y },
      { name: "ne", x: r.x + r.w, y: r.y },
      { name: "e", x: r.x + r.w, y: r.y + r.h / 2 },
      { name: "se", x: r.x + r.w, y: r.y + r.h },
      { name: "s", x: r.x + r.w / 2, y: r.y + r.h },
      { name: "sw", x: r.x, y: r.y + r.h },
      { name: "w", x: r.x, y: r.y + r.h / 2 },
    ];
  }

  point(event) {
    const bounds = this.stage.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
      y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
    };
  }

  pointerDown(event) {
    if (!this.image || event.button !== 0) return;
    const point = this.point(event);
    const pixels = { x: point.x * this.viewWidth, y: point.y * this.viewHeight };
    const handle = this.handles().find((item) => Math.hypot(item.x - pixels.x, item.y - pixels.y) <= HANDLE_RADIUS + 6);
    let action = "draw";
    if (handle) action = handle.name;
    else if (this.zone && point.x >= this.zone.x && point.x <= this.zone.x + this.zone.width && point.y >= this.zone.y && point.y <= this.zone.y + this.zone.height) action = "move";
    this.drag = { action, start: point, original: this.zone ? { ...this.zone } : null };
    if (action === "draw") this.zone = { x: point.x, y: point.y, width: MIN_ZONE, height: MIN_ZONE };
    this.stage.setPointerCapture(event.pointerId);
    event.preventDefault();
    this.draw();
  }

  pointerMove(event) {
    if (!this.drag) return;
    const point = this.point(event);
    const { action, start, original } = this.drag;
    const dx = point.x - start.x;
    const dy = point.y - start.y;
    if (action === "draw") {
      this.zone = {
        x: Math.min(start.x, point.x),
        y: Math.min(start.y, point.y),
        width: Math.max(MIN_ZONE, Math.abs(dx)),
        height: Math.max(MIN_ZONE, Math.abs(dy)),
      };
    } else if (action === "move") {
      this.zone = {
        ...original,
        x: Math.max(0, Math.min(1 - original.width, original.x + dx)),
        y: Math.max(0, Math.min(1 - original.height, original.y + dy)),
      };
    } else {
      let left = original.x;
      let top = original.y;
      let right = original.x + original.width;
      let bottom = original.y + original.height;
      if (action.includes("w")) left = Math.max(0, Math.min(right - MIN_ZONE, original.x + dx));
      if (action.includes("e")) right = Math.min(1, Math.max(left + MIN_ZONE, original.x + original.width + dx));
      if (action.includes("n")) top = Math.max(0, Math.min(bottom - MIN_ZONE, original.y + dy));
      if (action.includes("s")) bottom = Math.min(1, Math.max(top + MIN_ZONE, original.y + original.height + dy));
      this.zone = { x: left, y: top, width: right - left, height: bottom - top };
    }
    this.dirty = true;
    this.draw();
  }

  pointerUp(event) {
    if (this.drag) {
      this.drag = null;
      this.dirty = true;
      this.stage.releasePointerCapture(event.pointerId);
      this.draw();
    }
  }

  keyDown(event) {
    if (!this.image || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    if (!this.zone) this.zone = { x: 0.2, y: 0.2, width: 0.6, height: 0.6 };
    const step = event.altKey ? 0.001 : 0.01;
    const zone = { ...this.zone };
    const direction = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -1, ArrowDown: 1 }[event.key];
    if (event.shiftKey) {
      const key = ["ArrowLeft", "ArrowRight"].includes(event.key) ? "width" : "height";
      zone[key] = Math.max(MIN_ZONE, Math.min(1 - zone[key === "width" ? "x" : "y"], zone[key] + direction * step));
    } else {
      const key = ["ArrowLeft", "ArrowRight"].includes(event.key) ? "x" : "y";
      const size = key === "x" ? zone.width : zone.height;
      zone[key] = Math.max(0, Math.min(1 - size, zone[key] + direction * step));
    }
    this.zone = zone;
    this.dirty = true;
    event.preventDefault();
    this.draw();
  }
}

customElements.define("hunch-panel", HunchPanel);
