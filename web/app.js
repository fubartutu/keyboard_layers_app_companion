/**
 * Keyboard Layout WebSocket Client
 * Handles real-time communication with the keyboard companion server
 */

const imageFolder = "/assets/";
const KEYMAP_POLL_MS = 3000; // pick up keymap edits without a reload

class KeyboardLayoutClient {
  constructor() {
    this.websocket = null;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    this.maxReconnectDelay = 10000;
    this.isConnecting = false;
    this.mode = null; // "keymap" or "images"
    this.allLayers = [];
    this.keyboard = {connected: false, product: null};

    this.elements = {
      layoutImage: document.getElementById("layoutImage"),
      keymap: document.getElementById("keymap"),
      keymapError: document.getElementById("keymapError"),
      layerPill: document.getElementById("layerPill"),
      kbstat: document.getElementById("kbstat"),
      connectionStatus: document.getElementById("connectionStatus"),
      statusIndicator: document.getElementById("statusIndicator"),
      statusText: document.getElementById("statusText"),
      layoutContainer: document.getElementById("layoutContainer"),
      fullscreenButton: document.getElementById("fullscreenButton"),
    };

    this.view = new KeymapView(this.elements.keymap);
    this.view.onLayer = (name, color) => this.showLayer(name, color);

    this.init();
  }

  init() {
    this.connect();
    this.setupEventListeners();
    this.setupFullscreen();
  }

  connect() {
    if (
      this.isConnecting ||
      (this.websocket && this.websocket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this.isConnecting = true;
    this.updateConnectionStatus("connecting", "Connecting...");

    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      this.websocket = new WebSocket(`${protocol}//${window.location.host}/ws`);
      this.websocket.onopen = this.onOpen.bind(this);
      this.websocket.onmessage = this.onMessage.bind(this);
      this.websocket.onclose = this.onClose.bind(this);
      this.websocket.onerror = this.onError.bind(this);
    } catch (error) {
      console.error("Failed to create WebSocket connection:", error);
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  onOpen() {
    this.isConnecting = false;
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    this.updateConnectionStatus("connected", "Connected");
  }

  onMessage(event) {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (error) {
      console.error("Failed to parse WebSocket message:", error);
      return;
    }
    switch (msg.t) {
      case "hello":
        this.allLayers = msg.all_layers || [];
        this.switchKeyboard(msg.kb || "main");
        this.setMode(msg.keymap ? "keymap" : "images");
        this.setKeyboard(msg.connected, msg.product);
        this.showKbStatus(msg.status);
        this.view.setLayer(msg.mask, msg.default);
        this.view.setDown(msg.down || []);
        this.showImage();
        break;
      case "layer":
        this.view.setLayer(msg.mask, msg.default);
        this.showImage();
        break;
      case "pos":
        this.view.setKey(msg.pos, msg.down);
        break;
      case "status":
        this.showKbStatus(msg);
        break;
      case "connection":
        this.setKeyboard(msg.connected, msg.product);
        if (!msg.connected) { this.view.setDown([]); this.showKbStatus(null); }
        break;
      case "active": // another keyboard is in use (e.g. the Voyager): draw its keymap
        this.switchKeyboard(msg.kb);
        this.setKeyboard(msg.connected, msg.product);
        this.showKbStatus(null);
        this.view.setDown([]);
        this.view.setLayer(msg.mask, 1);
        this.showImage();
        break;
      case "server_shutdown":
        this.updateConnectionStatus("disconnected", "Server stopped");
        break;
    }
  }

  setMode(mode) {
    if (this.mode === mode) return;
    this.mode = mode;
    this.elements.keymap.toggleAttribute("hidden", mode !== "keymap"); // SVG has no .hidden property
    this.elements.layoutImage.hidden = mode !== "images";
    clearInterval(this.keymapPoll);
    if (mode === "keymap") {
      this.loadKeymap();
      this.keymapPoll = setInterval(() => this.loadKeymap(), KEYMAP_POLL_MS);
    } else {
      for (const layer of this.allLayers) {
        if (layer.trim() !== "") new Image().src = `${imageFolder}${layer}`; // preload
      }
    }
  }

  switchKeyboard(kb) {
    if (this.kb === kb) return;
    this.kb = kb;
    this.view.mtime = null; // draw the new keyboard's keymap even if it hasn't changed
    if (this.mode === "keymap") this.loadKeymap();
  }

  async loadKeymap() {
    const err = this.elements.keymapError;
    const kb = this.kb || "main";
    try {
      const r = await fetch(`/keymap.json?kb=${encodeURIComponent(kb)}`, {cache: "no-store"});
      const data = await r.json();
      if (kb !== (this.kb || "main")) return; // switched keyboards while this was loading
      if (data.error) throw new Error(data.error);
      err.hidden = true;
      if (data.mtime === this.view.mtime) return;
      this.view.mtime = data.mtime;
      this.view.load(data);
    } catch (e) {
      err.textContent = "Could not load keymap: " + (e.message || e);
      err.hidden = false;
    }
  }

  // Image mode: show the image for the top active layer (layers past the list use the last one)
  showImage() {
    if (this.mode !== "images" || !this.allLayers.length) return;
    const top = Math.max(Math.floor(Math.log2(this.view.mask | this.view.defaultMask)), 0);
    const image = this.allLayers[Math.min(top, this.allLayers.length - 1)];
    this.elements.layoutImage.src = `${imageFolder}${image}`;
    this.showLayer(`Layer ${top}`, null);
  }

  showLayer(name, color) {
    const pill = this.elements.layerPill;
    pill.hidden = false;
    pill.textContent = name;
    pill.style.setProperty("--layer-c", color || "#667eea");
  }

  setKeyboard(connected, product) {
    this.keyboard = {connected, product};
    this.refreshStatusText();
  }

  refreshStatusText() {
    if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) return;
    if (this.keyboard.connected) {
      this.updateConnectionStatus("connected", this.keyboard.product || "Keyboard connected");
    } else {
      this.updateConnectionStatus("connecting", "Waiting for keyboard...");
    }
  }

  // Battery and connection chips, from the keyboard's 0xF3 status report
  showKbStatus(s) {
    const el = this.elements.kbstat;
    el.hidden = !s;
    if (!s) return;
    const esc = x => String(x).replace(/[&<>"]/g, c => "&#" + c.charCodeAt(0) + ";");
    const batt = (label, pct, tip) => {
      if (pct === null || pct === undefined)
        return `<span class="chip" title="${esc(tip)}">${label} <b>–</b></span>`;
      return `<span class="chip${pct <= 20 ? " low" : ""}" title="${esc(tip)}">${label} ` +
        `<span class="batt"><i style="width:${Math.max(0, Math.min(100, pct)) * 0.12}px"></i></span><b>${pct}%</b></span>`;
    };
    let out = batt("L", s.battery.left, s.halves ? "Left half battery" : "Left half not connected to the right half");
    out += batt("R", s.battery.right, "Right half battery" + (s.usbPowered ? " (charging)" : ""));
    if (!s.halves) out += `<span class="chip bad" title="The right half can't see the left half">left half offline</span>`;
    if (s.output === "USB") {
      out += `<span class="chip">output <b>USB</b></span>`;
    } else {
      const state = s.profileOpen ? "not paired" : s.profileConnected ? "connected" : "not connected";
      out += `<span class="chip${s.profileConnected ? "" : " bad"}"><b>BT ${esc(s.profile)}</b> ${state}</span>`;
    }
    el.innerHTML = out;
  }

  onClose(event) {
    console.log("WebSocket connection closed:", event.code, event.reason);
    this.isConnecting = false;
    this.websocket = null;

    if (event.code !== 1000) {
      // Not a normal closure
      this.updateConnectionStatus("disconnected", "Disconnected");
      this.scheduleReconnect();
    }
  }

  onError(event) {
    console.error("WebSocket error:", event);
    this.isConnecting = false;
    this.updateConnectionStatus("disconnected", "Connection Error");
  }

  updateConnectionStatus(status, text) {
    const indicator = this.elements.statusIndicator;
    const statusText = this.elements.statusText;

    indicator.classList.remove("connected", "disconnected", "connecting");
    indicator.classList.add(status);
    statusText.textContent = text;

  }

  scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay,
    );

    console.log(
      `Scheduling reconnection attempt ${this.reconnectAttempts} in ${delay}ms`,
    );
    this.updateConnectionStatus(
      "disconnected",
      `Reconnecting in ${Math.ceil(delay / 1000)}s...`,
    );

    setTimeout(() => {
      if (!this.websocket || this.websocket.readyState === WebSocket.CLOSED) {
        this.connect();
      }
    }, delay);
  }

  setupEventListeners() {
    document.addEventListener("visibilitychange", () => {
      if (
        !document.hidden &&
        (!this.websocket || this.websocket.readyState === WebSocket.CLOSED)
      ) {
        console.log("Page became visible, attempting to reconnect");
        this.connect();
      }
    });

    window.addEventListener("focus", () => {
      if (!this.websocket || this.websocket.readyState === WebSocket.CLOSED) {
        console.log("Window focused, attempting to reconnect");
        this.connect();
      }
    });

    window.addEventListener("beforeunload", () => {
      if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
        this.websocket.close(1000, "Page unloading");
      }
    });
  }

  reconnect() {
    if (this.websocket) {
      this.websocket.close();
    }
    this.reconnectAttempts = 0;
    this.connect();
  }

  getConnectionState() {
    if (!this.websocket) return "disconnected";

    switch (this.websocket.readyState) {
      case WebSocket.CONNECTING:
        return "connecting";
      case WebSocket.OPEN:
        return "connected";
      case WebSocket.CLOSING:
        return "disconnecting";
      case WebSocket.CLOSED:
        return "disconnected";
      default:
        return "unknown";
    }
  }

  setupFullscreen() {
    if (!this.elements.fullscreenButton) {
      console.warn("Fullscreen button not found");
      return;
    }

    this.elements.fullscreenButton.addEventListener("click", () => {
      this.toggleFullscreen();
    });

    document.addEventListener("fullscreenchange", () => {
      this.handleFullscreenChange();
    });

    document.addEventListener("webkitfullscreenchange", () => {
      this.handleFullscreenChange();
    });

    document.addEventListener("mozfullscreenchange", () => {
      this.handleFullscreenChange();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && this.isFullscreen()) {
        this.exitFullscreen();
      }
    });
  }

  toggleFullscreen() {
    if (this.isFullscreen()) {
      this.exitFullscreen();
    } else {
      this.enterFullscreen();
    }
  }

  enterFullscreen() {
    const container = this.elements.layoutContainer;

    try {
      if (container.requestFullscreen) {
        container.requestFullscreen();
      } else if (container.webkitRequestFullscreen) {
        container.webkitRequestFullscreen();
      } else if (container.mozRequestFullScreen) {
        container.mozRequestFullScreen();
      } else if (container.msRequestFullscreen) {
        container.msRequestFullscreen();
      } else {
        this.enterCSSFullscreen();
      }
    } catch (error) {
      console.warn("Fullscreen API not supported, using CSS fallback");
      this.enterCSSFullscreen();
    }
  }

  exitFullscreen() {
    try {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      } else if (document.mozCancelFullScreen) {
        document.mozCancelFullScreen();
      } else if (document.msExitFullscreen) {
        document.msExitFullscreen();
      } else {
        this.exitCSSFullscreen();
      }
    } catch (error) {
      console.warn("Error exiting fullscreen, using CSS fallback");
      this.exitCSSFullscreen();
    }
  }

  enterCSSFullscreen() {
    document.body.classList.add("fullscreen-mode");
    this.updateFullscreenButton(true);
  }

  exitCSSFullscreen() {
    document.body.classList.remove("fullscreen-mode");
    this.updateFullscreenButton(false);
  }

  isFullscreen() {
    return !!(
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      document.mozFullScreenElement ||
      document.msFullscreenElement ||
      document.body.classList.contains("fullscreen-mode")
    );
  }

  handleFullscreenChange() {
    const isFullscreen = this.isFullscreen();
    this.updateFullscreenButton(isFullscreen);

    if (isFullscreen) {
      console.log("Entered fullscreen mode");
    } else {
      console.log("Exited fullscreen mode");
      document.body.classList.remove("fullscreen-mode");
    }
  }

  updateFullscreenButton(isFullscreen) {
    const button = this.elements.fullscreenButton;
    const icon = button.querySelector(".fullscreen-icon");

    if (isFullscreen) {
      button.title = "Exit fullscreen";
      icon.innerHTML =
        '<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>';
    } else {
      button.title = "Enter fullscreen";
      icon.innerHTML =
        '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>';
    }
  }
}

class App {
  constructor() {
    this.client = null;
    this.init();
  }

  init() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => {
        this.start();
      });
    } else {
      this.start();
    }
  }

  start() {
    this.client = new KeyboardLayoutClient();
    this.setupGlobalEventHandlers();
  }

  setupGlobalEventHandlers() {
    window.addEventListener("keydown", (event) => {
      // Press 'R' to manually reconnect (for debugging)
      if (event.key === "r" && event.ctrlKey) {
        event.preventDefault();
        console.log("Manual reconnection triggered");
        if (this.client) {
          this.client.reconnect();
        }
      }
    });
  }
}

const app = new App();
