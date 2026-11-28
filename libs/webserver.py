import asyncio
import errno
import json
import logging
import mimetypes
import shutil
import socket
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

from aiohttp import web, WSMsgType
from aiohttp.web import Application, AppRunner, TCPSite, FileResponse

from .config import Config
from .consumer import ConsumerInterface
from .keymap import keymap_at_ref, parse_keymap

imageFolder = "./assets/"
POLL_INTERVAL = 0.01  # seconds between keyboard reads: keeps key highlights snappy


class WebSocketManager:
    def __init__(self):
        self.clients: set = set()

    async def add_client(self, websocket):
        self.clients.add(websocket)
        logging.info(f"WebSocket client connected. Total clients: {len(self.clients)}")

    async def remove_client(self, websocket):
        self.clients.discard(websocket)
        logging.info(
            f"WebSocket client disconnected. Total clients: {len(self.clients)}"
        )

    async def broadcast(self, message: str):
        for client in list(self.clients):
            try:
                await client.send_str(message)
            except Exception as e:
                logging.warning(f"Failed to send message to client: {e}")
                await self.remove_client(client)


class WebServer(ConsumerInterface):
    """Serves the web page and streams the keyboard's layer/key/status events over a WebSocket.

    host="0.0.0.0" makes it reachable from other devices on the network; the local
    desktop mode binds 127.0.0.1 and opens the page in an app window (open_window=True).
    """

    def __init__(self, keyboard_listener, args, host="0.0.0.0", open_window=False):
        self.host = host
        self.port = args.server_port
        self.open_window = open_window
        self.keyboard_listener = keyboard_listener
        self.args = args
        self.config = Config()
        self.oryx = None
        if self.config.oryx_layout:
            from .oryx import OryxLayout

            self.oryx = OryxLayout(self.config.oryx_layout, self.config.oryx_revision, self.config.oryx_geometry)

        # Live state, sent to each new client so it can draw straight away
        self.state = {"mask": 1, "default": 1, "down": set(), "status": None}

        self.websocket_manager = WebSocketManager()
        self.app: Application = None
        self.runner: AppRunner = None
        self.site: TCPSite = None
        self.keyboard_task = None
        self.last_top = None

        logging.basicConfig(level=logging.INFO)
        # Don't log every asset request
        logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    def hello_msg(self):
        kb = self.keyboard_listener
        return json.dumps(
            {
                "t": "hello",
                "keymap": self.config.keymap is not None or self.oryx is not None,
                "kb": self.active_kb(),
                "all_layers": self.config.layers,
                "connected": kb.connected,
                "product": kb.product,
                "mask": self.state["mask"],
                "default": self.state["default"],
                "down": sorted(self.state["down"]),
                "status": self.state["status"],
                "boards": self.boards_msg(),
            }
        )

    def boards_msg(self):
        kb = self.keyboard_listener
        return kb.boards_msg() if hasattr(kb, "boards_msg") else None

    async def handle_client_msg(self, data):
        """{"t": "pin", "kb": <id> or null}: show that keyboard only, or follow the one in use."""
        try:
            msg = json.loads(data)
        except ValueError:
            return
        kb = self.keyboard_listener
        if msg.get("t") == "pin" and hasattr(kb, "pin"):
            await self.send_events(kb.pin(msg.get("kb")))
            logging.info(f"Pinned {msg.get('kb')}" if msg.get("kb") else "Following the keyboard in use")

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        await self.websocket_manager.add_client(ws)

        try:
            await ws.send_str(self.hello_msg())
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self.handle_client_msg(msg.data)
                elif msg.type == WSMsgType.ERROR:
                    logging.error(f"WebSocket error: {ws.exception()}")
                    break
                elif msg.type == WSMsgType.CLOSE:
                    break
        except Exception as e:
            logging.error(f"WebSocket handler error: {e}")
        finally:
            await self.websocket_manager.remove_client(ws)

        return ws

    async def serve_static_file(
        self, file_path: str, content_type: str = None, status: int = 200
    ):
        try:
            full_path = Path(file_path).resolve()
            if not full_path.exists() or not full_path.is_file():
                return await self.serve_404()

            if content_type is None:
                content_type, _ = mimetypes.guess_type(str(full_path))
                if content_type is None:
                    content_type = "application/octet-stream"

            return FileResponse(
                path=full_path,
                status=status,
                headers={
                    # Revalidate every load so page updates show up straight away
                    "Cache-Control": "no-cache",
                    "Content-Type": content_type,
                },
            )

        except Exception as e:
            logging.error(f"Error serving static file {file_path}: {e}")
            return await self.serve_500()

    async def serve_index(self, _):
        return await self.serve_static_file("web/index.html", "text/html")

    async def serve_json(self, _):
        return await self.serve_static_file("web/manifest.json", "application/json")

    async def serve_css(self, _):
        return await self.serve_static_file("web/styles.css", "text/css")

    async def serve_js(self, request):
        file = request.match_info.get("file")
        if "/" in file or ".." in file:
            return await self.serve_404()
        return await self.serve_static_file(f"web/{file}.js", "application/javascript")

    async def serve_assets(self, request):
        filename = request.match_info.get("filename")
        if "/" in filename or ".." in filename:
            return await self.serve_404()
        return await self.serve_static_file(f"{imageFolder}/{filename}")

    def active_kb(self):
        return getattr(self.keyboard_listener, "active", "main")

    async def serve_keymap(self, request):
        """The keymap is parsed on every request, so edits show up without a restart.

        ?kb=voyager serves the Oryx layout instead (fetched at most once a minute).
        """
        kb = request.query.get("kb") or self.active_kb()
        if kb == "voyager" and self.oryx:
            try:
                data = await asyncio.to_thread(self.oryx.get)
            except Exception as e:
                return web.json_response({"error": f"Could not fetch the Oryx layout: {e}"}, status=502)
            return web.json_response(data, headers={"Cache-Control": "no-store"})
        if self.config.keymap is None:
            return web.json_response({"error": "No [KEYMAP] path in config.ini"}, status=404)
        try:
            if self.config.keymap_ref:
                path, label = keymap_at_ref(self.config.keymap, self.config.keymap_ref)
            else:
                path, label = self.config.keymap, self.config.keymap
            data = parse_keymap(path)
            data["file"] = label
        except Exception as e:
            logging.error(f"Could not parse keymap {self.config.keymap}: {e}")
            return web.json_response({"error": f"Could not parse keymap: {e}"}, status=500)
        return web.json_response(data, headers={"Cache-Control": "no-store"})

    async def serve_error_page(self, file_path: str, status_code: int):
        return await self.serve_static_file(
            file_path, content_type="text/html", status=status_code
        )

    async def serve_404(self, request=None):
        return await self.serve_error_page("web/404.html", 404)

    async def serve_500(self):
        return await self.serve_error_page("web/500.html", 500)

    def get_network_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception as e:
            logging.warning(f"Could not determine network IP address: {e}")
            return None

    def display_startup_urls(self):
        print("\n" + "=" * 60)
        print("🚀 Keyboard Layers Web Interface Started")
        print("=" * 60)

        print("📱 Local Access:")
        print(f"   Web Interface: http://localhost:{self.port}")

        network_ip = self.get_network_ip() if self.host != "127.0.0.1" else None
        if network_ip:
            print("\n🌐 Network Access:")
            print(f"   Web Interface: http://{network_ip}:{self.port}")
            print(
                "\n💡 Access from other devices on your network using the network URL"
            )

        if self.config.keymap:
            ref = f"  (git: {self.config.keymap_ref})" if self.config.keymap_ref else ""
            print(f"\n⌨️  Keymap: {self.config.keymap}{ref}")
        if self.config.oryx_layout:
            print(f"⌨️  Voyager: Oryx layout {self.config.oryx_layout} ({self.config.oryx_revision})")
        print("\n📋 Press Ctrl+C to stop")
        print("=" * 60 + "\n")

    def launch_window(self):
        """Open the page as a borderless app window (Chromium-style --app), or a browser tab."""
        url = f"http://localhost:{self.port}"
        launcher = shutil.which("omarchy-launch-webapp")
        if launcher:
            cmd = [launcher, url]
        else:
            browser = next(
                (b for b in ("chromium", "google-chrome-stable", "google-chrome", "brave", "microsoft-edge")
                 if shutil.which(b)),
                None,
            )
            cmd = [browser, f"--app={url}"] if browser else None
        if cmd:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return
            except Exception as e:
                logging.warning(f"Could not open app window ({e}), using the default browser")
        webbrowser.open(url)

    def setup_routes(self):
        self.app.router.add_get("/", self.serve_index)
        self.app.router.add_get("/index.html", self.serve_index)
        self.app.router.add_get("/styles.css", self.serve_css)
        self.app.router.add_get("/manifest.json", self.serve_json)
        self.app.router.add_get("/keymap.json", self.serve_keymap)
        self.app.router.add_get("/{file}.js", self.serve_js)
        self.app.router.add_get("/assets/{filename}", self.serve_assets)
        self.app.router.add_get("/ws", self.websocket_handler)
        self.app.router.add_route("*", "/{path:.*}", self.serve_404)

    async def start(self):
        try:
            self.app = web.Application()
            self.setup_routes()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            try:
                self.site = web.TCPSite(self.runner, self.host, self.port)
                await self.site.start()
            except OSError as e:
                if e.errno == errno.EADDRINUSE:
                    print(f"\n❌ Error: Port {self.port} is already in use!")
                else:
                    print(f"\n❌ Network Error: {e}")
                    print(f"   Failed to bind to {self.host}:{self.port}")
                await self.runner.cleanup()
                raise SystemExit(1)

            self.display_startup_urls()
            if self.open_window:
                self.launch_window()

            self.keyboard_task = asyncio.create_task(self.monitor_keyboard())
            logging.info("Keyboard monitoring started")
            await self.keyboard_task

        except (KeyboardInterrupt, asyncio.CancelledError):
            logging.info("Server shutdown requested")
            await self.cleanup()
            raise
        except SystemExit:
            raise
        except Exception as e:
            logging.error(f"Failed to start web server: {e}")
            await self.cleanup()
            raise

    async def monitor_keyboard(self):
        kb = self.keyboard_listener
        self.last_top = None
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                events = kb.read_events()
            except Exception as e:
                logging.error(f"Error reading keyboard: {e}")
                continue
            await self.send_events(events)

    async def send_events(self, events):
        for ev in events:
            t = ev["t"]
            if t == "layer":
                self.state["mask"], self.state["default"] = ev["mask"], ev["default"]
                top = max(ev["mask"].bit_length() - 1, 0)
                if top != self.last_top:
                    self.last_top = top
                    logging.info(f"Layer {top}")
            elif t == "pos":
                (self.state["down"].add if ev["down"] else self.state["down"].discard)(ev["pos"])
            elif t == "status":
                self.state["status"] = ev
            elif t == "active":
                # Another keyboard is on screen: start from its state
                self.state.update(mask=ev["mask"], default=1, down=set(), status=None)
                self.last_top = None
                logging.info(f"Showing {ev['product'] or ev['kb']}")
            elif t == "connection":
                if not ev["connected"]:
                    self.state.update(down=set(), status=None)
                ev["timestamp"] = datetime.now().isoformat()
            await self.websocket_manager.broadcast(json.dumps(ev))

    async def cleanup(self):
        logging.info("Starting web server cleanup...")
        try:
            if self.keyboard_task and not self.keyboard_task.done():
                self.keyboard_task.cancel()
                try:
                    await self.keyboard_task
                except asyncio.CancelledError:
                    pass

            if self.websocket_manager.clients:
                shutdown_message = {"t": "server_shutdown", "timestamp": datetime.now().isoformat()}
                try:
                    await asyncio.wait_for(
                        self.websocket_manager.broadcast(json.dumps(shutdown_message)),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    logging.warning("Timeout while notifying clients of shutdown")

                for client in list(self.websocket_manager.clients):
                    try:
                        await client.close()
                    except Exception as e:
                        logging.warning(f"Error closing WebSocket client: {e}")
                self.websocket_manager.clients.clear()

            if self.site:
                await self.site.stop()
                self.site = None

            if self.runner:
                await self.runner.cleanup()
                self.runner = None

            logging.info("Web server cleanup completed")

        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    def stop(self):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.cleanup())
            else:
                asyncio.run(self.cleanup())
        except Exception as e:
            logging.error(f"Error stopping web server: {e}")
