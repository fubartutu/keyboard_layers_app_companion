"""Watches several keyboards at once and follows whichever one is in use.

The page shows one keyboard at a time: the one that last sent a layer change or a
key press, or, when that one goes away, another one that is still connected. A
switch is announced with {"t": "active", "kb": <id>, ...}; after that, only the
active keyboard's events are passed on.

A keyboard can also be pinned (from the page): it then stays on screen whichever
keyboard is typed on, until it's unpinned. Whenever a keyboard connects or
disconnects, {"t": "boards", ...} lists them all, so the page can offer the choice.
"""


class Keyboards:
    NAMES = {"main": "Charybdis", "voyager": "Voyager"}  # shown until the product name is known

    def __init__(self, boards):
        self.boards = boards  # {id: keyboard}, in order of preference
        self.active = next((k for k, b in boards.items() if b.connected), next(iter(boards)))
        self.pinned = None

    @property
    def board(self):
        return self.boards[self.active]

    @property
    def connected(self):
        return self.board.connected

    @property
    def product(self):
        return self.board.product

    @property
    def mask(self):
        return self.board.mask

    def boards_msg(self):
        return {
            "t": "boards",
            "pinned": self.pinned,
            "active": self.active,
            "boards": [
                {"kb": k, "name": self.NAMES.get(k) or b.product or k, "product": b.product, "connected": b.connected}
                for k, b in self.boards.items()
            ],
        }

    def switch(self, kb):
        self.active = kb
        b = self.board
        return {"t": "active", "kb": kb, "connected": b.connected, "product": b.product, "mask": b.mask}

    def pin(self, kb):
        """Pin a keyboard (None to follow the one in use again). Returns the events to send."""
        if kb is not None and kb not in self.boards:
            return []
        self.pinned = kb
        out = []
        if kb is not None and kb != self.active:
            out.append(self.switch(kb))
        out.append(self.boards_msg())
        return out

    def read_events(self):
        out = []
        changed = False
        for kb, board in self.boards.items():
            for ev in board.read_events():
                t = ev["t"]
                if t == "connection":
                    changed = True
                if kb != self.active:
                    if self.pinned:
                        continue  # stay on the pinned keyboard
                    in_use = t in ("layer", "pos")
                    came_back = t == "connection" and ev["connected"] and not self.board.connected
                    if not (in_use or came_back):
                        continue
                    out.append(self.switch(kb))
                    if came_back:
                        continue
                elif t == "connection" and not ev["connected"] and not self.pinned:
                    other = next((k for k, b in self.boards.items() if k != kb and b.connected), None)
                    if other:
                        out.append(self.switch(other))
                        continue
                out.append(ev)
        if changed:
            out.append(self.boards_msg())
        return out

    def notify_changes(self):
        """Layer-only API used by the TCP server and the Kivy client."""
        for _ in self.read_events():
            pass
        layer = max(self.mask.bit_length() - 1, 0)
        if layer == getattr(self, "last_layer", 0):
            return None
        self.last_layer = layer
        return layer
