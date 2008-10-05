# Copyright (c) 2008, Aldo Cortesi. All rights reserved.
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import inspect, UserDict, traceback, textwrap, os, inspect
import ipc, config, manager

class CommandError(Exception): pass
class CommandException(Exception): pass

SUCCESS = 0
ERROR = 1
EXCEPTION = 2

SOCKBASE = ".qtilesocket.%s"

class _Server(ipc.Server):
    def __init__(self, fname, qtile, conf):
        if os.path.exists(fname):
            os.unlink(fname)
        ipc.Server.__init__(self, fname, self.call)
        self.qtile = qtile
        self.widgets = {}
        for i in conf.screens:
            for j in i.gaps:
                if hasattr(j, "widgets"):
                    for w in j.widgets:
                        if w.name:
                            self.widgets[w.name] = w

    def call(self, data):
        selectors, name, args, kwargs = data
        obj = self.qtile.select(selectors)
        if not obj:
            return ERROR, "No such object."
        cmd = obj.command(name)
        if not cmd:
            return ERROR, "No such command."
        self.qtile.log.add("Command: %s(%s, %s)"%(name, args, kwargs))
        try:
            return SUCCESS, cmd(*args, **kwargs)
        except CommandError, v:
            return ERROR, v.message
        except Exception, v:
            return EXCEPTION, traceback.format_exc()
        if self.qtile._testing:
            self.qtile.display.sync()


class _Command:
    def __init__(self, call, selectors, name):
        """
            :command A string command name specification
            :*args Arguments to be passed to the specified command
            :*kwargs Arguments to be passed to the specified command
        """
        self.selectors, self.name = selectors, name
        self.call = call

    def __call__(self, *args, **kwargs):
        return self.call(self.selectors, self.name, *args, **kwargs)


class _CommandTree(object):
    """
        A CommandTree a hierarchical collection of command objects.
        CommandTree objects act as containers, allowing them to be nested. The
        commands themselves appear on the object as callable attributes.
    """
    def __init__(self, call, selectors, myselector=None):
        self.call, self.selectors, self.myselector = call, selectors, myselector

    def __getitem__(self, select):
        if self.myselector:
            raise KeyError, "No such key: %s"%select
        c = self.__class__(self.call, self.selectors, select)
        return c

    def __getattr__(self, name):
        nextSelector = self.selectors[:]
        if self.name:
            nextSelector.append((self.name, self.myselector))
        if name in self._contains:
            c = _TreeMap[name](self.call, nextSelector)
            for i in c._contains:
                setattr(c, i, _TreeMap[i](self.call, nextSelector))
            return c
        else:
            return _Command(self.call, nextSelector, name)


class _TLayout(_CommandTree):
    name = "layout"
    _contains = ["group", "window", "screen"]


class _TWidget(_CommandTree):
    name = "widget"
    _contains = ["bar", "screen", "group"]


class _TBar(_CommandTree):
    name = "bar"
    _contains = ["screen", "group", "widget"]


class _TWindow(_CommandTree):
    name = "window"
    _contains = ["group", "screen", "layout"]


class _TScreen(_CommandTree):
    name = "screen"
    _contains = ["layout", "window", "bar"]


class _TGroup(_CommandTree):
    name = "group"
    _contains = ["layout", "window", "screen"]


_TreeMap = {
    "layout":   _TLayout,
    "widget":   _TWidget,
    "bar":      _TBar,
    "window":   _TWindow,
    "screen":   _TScreen,
    "group":    _TGroup,
}


class _CommandRoot(_CommandTree):
    name = None
    _contains = ["layout", "widget", "screen", "bar", "window", "group"]
    def __init__(self):
        """
            This method constructs the entire hierarchy of callable commands
            from a conf object.
        """
        _CommandTree.__init__(self, self.call, [])

    def __getitem__(self, select):
        raise KeyError, "No such key: %s"%select

    def call(self, selectors, name, *args, **kwargs):
        """
            This method is called for issued commands.
                
                :selectors A list of (name, selector) tuples. 
                :name Command name.
        """
        pass


class Client(_CommandRoot):
    """
        Exposes a command tree used to communicate with a running instance of
        Qtile.
    """
    def __init__(self, fname=None, conf=None):
        if not fname:
            d = os.environ.get("DISPLAY")
            if not d:
                d = ":0.0"
            fname = os.path.join("~", SOCKBASE%d)
            fname = os.path.expanduser(fname)
        self.client = ipc.Client(fname)
        _CommandRoot.__init__(self)

    def call(self, selectors, name, *args, **kwargs):
        state, val = self.client.call((selectors, name, args, kwargs))
        if state == SUCCESS:
            return val
        elif state == ERROR:
            raise CommandError(val)
        else:
            raise CommandException(val)


class _Call:
    def __init__(self, klass, selectors, name, *args, **kwargs):
        """
            :command A string command name specification
            :*args Arguments to be passed to the specified command
            :*kwargs Arguments to be passed to the specified command
        """
        self.klass, self.selectors, self.name = klass, selectors, name
        self.args, self.kwargs = args, kwargs
        # Conditionals
        self.layout = None

    def when(self, layout=None):
        self.layout = layout
        return self

    def check(self, q):
        if self.layout and q.currentLayout.name != self.layout:
            return False
        return True


class Commander(_CommandRoot):
    def call(self, klass, selectors, name, *args, **kwargs):
        return _Call(klass, selectors, name, *args, **kwargs)


class CommandObject(object):
    """
        Base class for objects that expose commands. Each command should be a
        method named cmd_X, where X is the command name. 
    """
    def select(self, selectors):
        raise NotImplementedError

    def command(self, name):
        return getattr(self, "cmd_" + name, None)

    def commands(self):
        lst = []
        for i in dir(self):
            if i.startswith("cmd_"):
                lst.append(i[4:])
        return lst

    def docSig(self, name):
        args, varargs, varkw, defaults = inspect.getargspec(self.command(name))
        if args and args[0] == "self":
            args = args[1:]
        return name + inspect.formatargspec(args, varargs, varkw, defaults)

    def docText(self, name):
        return textwrap.dedent(self.command(name).__doc__ or "")

    def doc(self, name):
        spec = self.docSig(name)
        htext = self.docText(name)
        htext = "\n".join(["\t" + i for i in htext.splitlines()])
        return spec + htext
