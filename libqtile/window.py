import Xlib
from Xlib import X
import Xlib.protocol.event as event

class _Window:
    _windowMask = X.StructureNotifyMask |\
                 X.PropertyChangeMask |\
                 X.EnterWindowMask |\
                 X.FocusChangeMask
    def __init__(self, window, qtile):
        self.window, self.qtile = window, qtile
        self.hidden = True
        window.change_attributes(event_mask=self._windowMask)
        self.x, self.y, self.width, self.height = None, None, None, None

    def info(self):
        return dict(
            name = self.name,
            x = self.x,
            y = self.y,
            width = self.width,
            height = self.height,
            id = str(hex(self.window.id))
        )

    @property
    def name(self):
        try:
            return self.window.get_wm_name()
        except Xlib.error.BadWindow:
            return "<nonexistent>"

    def kill(self):
        if self.hasProtocol("WM_DELETE_WINDOW"):
            e = event.ClientMessage(
                    window = self.window,
                    client_type = self.qtile.display.intern_atom("WM_PROTOCOLS"),
                    data = [
                        # Use 32-bit format:
                        32,
                        # Must be exactly 20 bytes long:
                        [
                            self.qtile.display.intern_atom("WM_DELETE_WINDOW"),
                            X.CurrentTime,
                            0,
                            0,
                            0
                        ]
                    ]
            )
            self.window.send_event(e)
        else:
            self.window.kill_client()

    def hide(self):
        # We don't want to get the UnmapNotify for this unmap
        self.x, self.y, self.width, self.height = None, None, None, None
        self.disableMask(X.StructureNotifyMask)
        self.window.unmap()
        self.resetMask()
        self.hidden = True

    def unhide(self):
        self.window.map()
        self.hidden = False

    def disableMask(self, mask):
        self.window.change_attributes(
            event_mask=self._windowMask&(~mask)
        )

    def resetMask(self):
        self.window.change_attributes(
            event_mask=self._windowMask
        )

    def place(self, x, y, width, height):
        """
            Places the window at the specified location with the given size.
        """
        self.x, self.y, self.width, self.height = x, y, width, height
        self.window.configure(
            x=x,
            y=y,
            width=width,
            height=height,
        )

    def focus(self, warp):
        if not self.hidden:
            self.window.set_input_focus(
                X.RevertToPointerRoot,
                X.CurrentTime
            )
            self.window.configure(
                stack_mode = X.Above
            )
            if warp:
                self.window.warp_pointer(0, 0)

    def hasProtocol(self, name):
        s = set()
        d = self.qtile.display
        for i in self.window.get_wm_protocols():
            s.add(d.get_atom_name(i))
        return name in s


class Internal(_Window):
    """
        An internal window, that should not be managed by qtile.
    """
    @classmethod
    def create(klass, qtile, x, y, width, height):
        colormap = qtile.display.screen().default_colormap
        background = colormap.alloc_named_color("black").pixel
        win = qtile.root.create_window(
                    x, y, width, height, 1,
                    X.CopyFromParent, X.InputOutput,
                    X.CopyFromParent,
                    background_pixel = background,
                    event_mask = X.StructureNotifyMask | X.ExposureMask
               )
        return Internal(win, qtile)

    def __repr__(self):
        return "Internal(%s)"%self.name


class Window(_Window):
    group = None
    def __repr__(self):
        return "Window(%s)"%self.name


