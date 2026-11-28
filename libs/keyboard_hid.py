import sys
import time
import hid
from libs.config import Config

BYTES_TO_READ = 32
# zmk-feature-appcompanion / QMK snippet: PAYLOAD_MARK at byte 24, layer number at byte 25
PAYLOAD_MARK = 0x90
PAYLOAD_BEGIN = 24
RECONNECT_EVERY = 2.0  # seconds between attempts to reopen a lost device
STATUS_EVERY = 30.0  # seconds between status (battery) requests


def parse_report(r):
    """Turn one raw HID report into an event dict, or None if it isn't one we know.

    zmk-raw-hid + zmk-keypeek-layer-notifier (zmk-charybdis):
      layer:  FF 04 <default layer mask, u32 LE> <active layer mask, u32 LE>
      key:    F1 00 <position> <1 = pressed, 0 = released>
    modules/status-report (zmk-charybdis):
      status: F3 01 <right %> <left %> <halves linked> <output> <BT profile> <flags>
    zmk-feature-appcompanion / QMK: PAYLOAD_MARK at byte 24, layer at byte 25.
    """
    r = bytes(r)
    if len(r) >= 10 and r[0] == 0xFF and r[1] == 0x04:
        return {
            "t": "layer",
            "default": int.from_bytes(r[2:6], "little"),
            "mask": int.from_bytes(r[6:10], "little"),
        }
    if len(r) >= 4 and r[0] == 0xF1:
        return {"t": "pos", "pos": r[2], "down": r[3] == 1}
    if len(r) >= 8 and r[0] == 0xF3 and r[1] == 0x01:
        pct = lambda b: None if b == 0xFF else b  # noqa: E731
        flags = r[7]
        return {
            "t": "status",
            "battery": {"right": pct(r[2]), "left": pct(r[3]) if r[4] else None},
            "halves": r[4] > 0,
            "output": "Bluetooth" if r[5] == 1 else "USB",
            "profile": r[6],
            "profileConnected": bool(flags & 1),
            "profileOpen": bool(flags & 2),
            "usbPowered": bool(flags & 4),
            "usbReady": bool(flags & 8),
        }
    if len(r) > PAYLOAD_BEGIN + 1 and r[PAYLOAD_BEGIN] == PAYLOAD_MARK:
        return {"t": "layer", "default": 1, "mask": 1 | (1 << r[PAYLOAD_BEGIN + 1])}
    return None


def top_layer(mask):
    return max(mask.bit_length() - 1, 0)


class Keyboard:
    """Reads layer, key and status reports from the keyboard's Raw HID interface.

    With required=False the app keeps running while the keyboard is absent and
    picks it up when it appears (e.g. after Bluetooth wakes).
    """

    def __init__(self, required=True):
        self.config = Config()
        self.hid = None
        self.product = None
        self.mask = 1
        self.last_layer = 0
        self.last_attempt = 0.0
        self.last_status_request = 0.0

        self.open()
        if self.hid is None and required:
            self.print_instructions()
            sys.exit(1)

    @property
    def connected(self):
        return self.hid is not None

    def open(self):
        self.last_attempt = time.monotonic()
        interfaces = [
            i
            for i in hid.enumerate()
            if i["usage_page"] == self.config.usage_page
            and i["usage"] == self.config.usage
            and i["vendor_id"] != 0x3297  # ZSA (Voyager): Oryx protocol, read by libs/keyboard_oryx.py
            and (
                not getattr(self.config, "product", None)
                or (i.get("product_string") or "") == self.config.product
            )
        ]
        for info in interfaces:
            try:
                device = hid.Device(path=info["path"])
            except Exception as e:
                print(f"Could not open {info['path']}: {e}")
                continue
            device.nonblocking = True
            self.hid = device
            self.product = info.get("product_string") or "keyboard"
            print("Found Keyboard:")
            print(f"    Manufacturer: {info.get('manufacturer_string') or ''}")
            print(f"    Product: {self.product}")
            self.request_status()
            return True
        return False

    def close(self):
        if self.hid is not None:
            try:
                self.hid.close()
            except Exception:
                pass
        self.hid = None

    def request_status(self):
        """Ask for a status report now; firmware without the status module ignores it."""
        self.last_status_request = time.monotonic()
        if self.hid is None:
            return
        try:
            # Report ID 0, then the 0xF3 request padded to the report size
            self.hid.write(bytes([0, 0xF3]) + bytes(BYTES_TO_READ - 1))
        except Exception:
            pass

    def read_events(self):
        """Drain all queued reports and return them as event dicts (non-blocking).

        Emits {"t": "connection", "connected": bool, "product": str} when the
        keyboard appears or disappears.
        """
        events = []
        if self.hid is None:
            if time.monotonic() - self.last_attempt >= RECONNECT_EVERY and self.open():
                events.append(self.connection_event())
            return events
        if time.monotonic() - self.last_status_request >= STATUS_EVERY:
            self.request_status()
        try:
            while True:
                data = self.hid.read(64)
                if not data:
                    break
                ev = parse_report(data)
                if ev is None:
                    continue
                if ev["t"] == "layer":
                    self.mask = ev["mask"]
                events.append(ev)
        except hid.HIDException:
            print("Keyboard disconnected, waiting for it to come back..")
            self.close()
            events.append(self.connection_event())
        return events

    def connection_event(self):
        return {"t": "connection", "connected": self.connected, "product": self.product}

    def notify_changes(self):
        """Layer-only API used by the TCP server and the Kivy client: the new top layer, or None."""
        for _ in self.read_events():
            pass
        layer = top_layer(self.mask)
        if layer == self.last_layer:
            return None
        self.last_layer = layer
        print(f"Layer change detected: '{layer}'")
        return layer

    def print_instructions(self):
        print("No keyboard found.")
        print(
            f"Please ensure your keyboard is connected and configured correctly on the file {self.config._config_file}"
        )

    def __del__(self):
        self.close()
