"""Reads layer changes and key presses from a ZSA keyboard (Voyager) running Oryx firmware.

Oryx's raw HID protocol (zsa/qmk_modules oryx/oryx.h, protocol 0x06): once the host
sends ORYX_CMD_PAIRING_INIT the board answers ORYX_EVT_PAIRING_SUCCESS and from then
on reports
  layer:  05 <highest active layer> FE
  key:    06 <col> <row> FE  (down)   07 <col> <row> FE  (up)
Nothing else is changed on the keyboard. Keymapp can stay open alongside.
"""
import time

import hid

from libs.oryx import MATRIX_TO_INDEX

ZSA_VENDOR_ID = 0x3297
USAGE_PAGE, USAGE = 0xFF60, 0x61
REPORT_SIZE = 32
CMD_PAIRING_INIT = 0x01
EVT_LAYER, EVT_KEYDOWN, EVT_KEYUP = 0x05, 0x06, 0x07
RECONNECT_EVERY = 2.0  # seconds between attempts to find the keyboard
PAIR_EVERY = 30.0  # re-send the pairing command now and then, in case the board dropped the session


def parse_report(r):
    r = bytes(r)
    if len(r) >= 2 and r[0] == EVT_LAYER:
        return {"t": "layer", "default": 1, "mask": 1 << r[1]}
    if len(r) >= 3 and r[0] in (EVT_KEYDOWN, EVT_KEYUP):
        pos = MATRIX_TO_INDEX.get((r[2], r[1]))  # sent as col, row
        if pos is not None:
            return {"t": "pos", "pos": pos, "down": r[0] == EVT_KEYDOWN}
    return None


class OryxKeyboard:
    """Same interface as libs.keyboard_hid.Keyboard (connected, product, mask, read_events)."""

    def __init__(self):
        self.hid = None
        self.product = None
        self.mask = 1
        self.last_attempt = 0.0
        self.last_pair = 0.0
        self.open()

    @property
    def connected(self):
        return self.hid is not None

    def open(self):
        self.last_attempt = time.monotonic()
        for info in hid.enumerate(ZSA_VENDOR_ID):
            if info["usage_page"] != USAGE_PAGE or info["usage"] != USAGE:
                continue
            try:
                device = hid.Device(path=info["path"])
            except Exception as e:
                print(f"Could not open {info['path']}: {e}")
                continue
            device.nonblocking = True
            self.hid = device
            self.product = info.get("product_string") or "ZSA keyboard"
            self.mask = 1
            print("Found Keyboard:")
            print(f"    Manufacturer: {info.get('manufacturer_string') or ''}")
            print(f"    Product: {self.product}")
            self.pair()
            return True
        return False

    def pair(self):
        self.last_pair = time.monotonic()
        try:
            # Report ID 0, then the command padded to the report size
            self.hid.write(bytes([0, CMD_PAIRING_INIT]) + bytes(REPORT_SIZE - 1))
        except Exception:
            pass

    def close(self):
        if self.hid is not None:
            try:
                self.hid.close()
            except Exception:
                pass
        self.hid = None

    def read_events(self):
        events = []
        if self.hid is None:
            if time.monotonic() - self.last_attempt >= RECONNECT_EVERY and self.open():
                events.append(self.connection_event())
            return events
        if time.monotonic() - self.last_pair >= PAIR_EVERY:
            self.pair()
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
            print(f"{self.product} disconnected, waiting for it to come back..")
            self.close()
            events.append(self.connection_event())
        return events

    def connection_event(self):
        return {"t": "connection", "connected": self.connected, "product": self.product}

    def __del__(self):
        self.close()
