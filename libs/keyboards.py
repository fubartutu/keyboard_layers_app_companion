"""Watches several keyboards at once and follows whichever one is in use.

The page shows one keyboard at a time: the one that last sent a layer change or a
key press, or, when that one goes away, another one that is still connected. A
switch is announced with {"t": "active", "kb": <id>, ...}; after that, only the
active keyboard's events are passed on.
"""


class Keyboards:
    def __init__(self, boards):
        self.boards = boards  # {id: keyboard}, in order of preference
        self.active = next((k for k, b in boards.items() if b.connected), next(iter(boards)))

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

    def switch(self, kb):
        self.active = kb
        b = self.board
        return {"t": "active", "kb": kb, "connected": b.connected, "product": b.product, "mask": b.mask}

    def read_events(self):
        out = []
        for kb, board in self.boards.items():
            for ev in board.read_events():
                if kb != self.active:
                    t = ev["t"]
                    in_use = t in ("layer", "pos")
                    came_back = t == "connection" and ev["connected"] and not self.board.connected
                    if not (in_use or came_back):
                        continue
                    out.append(self.switch(kb))
                    if came_back:
                        continue
                elif ev["t"] == "connection" and not ev["connected"]:
                    other = next((k for k, b in self.boards.items() if k != kb and b.connected), None)
                    if other:
                        out.append(self.switch(other))
                        continue
                out.append(ev)
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
