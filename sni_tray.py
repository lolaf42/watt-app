"""StatusNotifierItem D-Bus tray icon.

Left-click fires on_activate; right-click fires on_context (optional).
ItemIsMenu=False tells the GNOME shell extension NOT to show a menu on click.
"""

import logging
import os
from typing import Callable, Optional

import gi
gi.require_version('Gio', '2.0')
gi.require_version('GLib', '2.0')
from gi.repository import Gio, GLib
from PIL import Image

logger = logging.getLogger("watt.sni")

_SNI_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category"            type="s"          access="read"/>
    <property name="Id"                  type="s"          access="read"/>
    <property name="Title"               type="s"          access="read"/>
    <property name="Status"              type="s"          access="read"/>
    <property name="WindowId"            type="i"          access="read"/>
    <property name="IconName"            type="s"          access="read"/>
    <property name="IconPixmap"          type="a(iiay)"    access="read"/>
    <property name="OverlayIconName"     type="s"          access="read"/>
    <property name="OverlayIconPixmap"   type="a(iiay)"    access="read"/>
    <property name="AttentionIconName"   type="s"          access="read"/>
    <property name="AttentionIconPixmap" type="a(iiay)"    access="read"/>
    <property name="AttentionMovieName"  type="s"          access="read"/>
    <property name="ToolTip"             type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu"          type="b"          access="read"/>
    <property name="Menu"                type="o"          access="read"/>
    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewAttentionIcon"/>
    <signal name="NewOverlayIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg type="s"/></signal>
    <method name="Activate">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="ContextMenu">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="SecondaryActivate">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="Scroll">
      <arg type="i" direction="in" name="delta"/>
      <arg type="s" direction="in" name="orientation"/>
    </method>
  </interface>
</node>
"""

_WATCHER_BUS   = "org.kde.StatusNotifierWatcher"
_WATCHER_PATH  = "/StatusNotifierWatcher"
_WATCHER_IFACE = "org.kde.StatusNotifierWatcher"
_OBJ_PATH      = "/StatusNotifierItem"
_IFACE         = "org.kde.StatusNotifierItem"


def _to_argb32(img: Image.Image) -> bytearray:
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    return bytearray(Image.merge("RGBA", (a, r, g, b)).tobytes())


class SNITray:
    def __init__(self, app_id: str, title: str,
                 on_activate: Callable,
                 on_context: Optional[Callable] = None):
        self._id       = app_id
        self._title    = title
        self._on_act   = on_activate
        self._on_ctx   = on_context
        self._icon: Optional[Image.Image] = None
        self._conn: Optional[Gio.DBusConnection] = None
        self._loop: Optional[GLib.MainLoop] = None
        self._svc     = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        self._iface   = (Gio.DBusNodeInfo.new_for_xml(_SNI_XML)
                         .lookup_interface(_IFACE))

    # ── Public ────────────────────────────────────────────────────────────────

    def set_icon(self, img: Image.Image) -> None:
        self._icon = img
        if self._conn:
            GLib.idle_add(self._emit_new_icon)

    def set_title(self, text: str) -> None:
        self._title = text
        if self._conn:
            GLib.idle_add(self._emit_new_title)

    def run(self) -> None:
        self._loop = GLib.MainLoop()
        Gio.bus_get(Gio.BusType.SESSION, None, self._on_bus, None)
        self._loop.run()

    def stop(self) -> None:
        if self._loop:
            GLib.idle_add(self._loop.quit)

    # ── D-Bus setup ───────────────────────────────────────────────────────────

    def _on_bus(self, src, res, _):
        try:
            self._conn = Gio.bus_get_finish(res)
        except Exception:
            return
        self._conn.register_object(
            _OBJ_PATH, self._iface,
            self._on_method, self._on_get_prop, None)
        self._conn.call(
            "org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", "RequestName",
            GLib.Variant("(su)", (self._svc, 0)),
            GLib.VariantType("(u)"),
            Gio.DBusCallFlags.NONE, -1, None,
            self._on_name, None)

    def _on_name(self, src, res, _):
        try:
            self._conn.call_finish(res)
        except Exception:
            return
        logger.info("SNI: D-Bus name acquired: %s", self._svc)
        self._conn.call(
            _WATCHER_BUS, _WATCHER_PATH, _WATCHER_IFACE,
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (self._svc,)),
            None, Gio.DBusCallFlags.NONE, -1, None,
            self._on_registered, None)

    def _on_registered(self, src, res, _):
        try:
            self._conn.call_finish(res)
            logger.info("SNI: registered with StatusNotifierWatcher")
        except Exception as e:
            logger.warning("SNI: registration failed: %s", e)

    def _emit_new_icon(self):
        if self._conn:
            self._conn.emit_signal(
                None, _OBJ_PATH, _IFACE, "NewIcon", None)
        return False

    def _emit_new_title(self):
        if self._conn:
            self._conn.emit_signal(
                None, _OBJ_PATH, _IFACE, "NewTitle", None)
        return False

    # ── Method / property handlers ────────────────────────────────────────────

    def _on_method(self, conn, sender, path, iface, method, params, inv):
        logger.info("SNI method called: %s %s", method, params.unpack() if params else "")
        inv.return_value(None)
        if method in ("Activate", "SecondaryActivate"):
            x, y = params.unpack()
            GLib.idle_add(self._fire, self._on_act, x, y)
        elif method == "ContextMenu":
            x, y = params.unpack()
            GLib.idle_add(self._fire, self._on_ctx or self._on_act, x, y)

    @staticmethod
    def _fire(fn, *args):
        fn(*args)
        return False  # must return False so GLib.idle_add does not repeat

    def _on_get_prop(self, conn, sender, path, iface, prop):
        if prop == "Category":             return GLib.Variant("s", "ApplicationStatus")
        if prop == "Id":                   return GLib.Variant("s", self._id)
        if prop == "Title":                return GLib.Variant("s", self._title)
        if prop == "Status":               return GLib.Variant("s", "Active")
        if prop == "WindowId":             return GLib.Variant("i", 0)
        if prop == "IconName":             return GLib.Variant("s", "")
        if prop == "OverlayIconName":      return GLib.Variant("s", "")
        if prop == "AttentionIconName":    return GLib.Variant("s", "")
        if prop == "AttentionMovieName":   return GLib.Variant("s", "")
        if prop == "ItemIsMenu":           return GLib.Variant("b", False)
        if prop == "Menu":                 return GLib.Variant("o", "/NO_DBUSMENU")
        if prop in ("OverlayIconPixmap", "AttentionIconPixmap"):
            return GLib.Variant("a(iiay)", [])
        if prop == "ToolTip":
            return GLib.Variant("(sa(iiay)ss)", ("", [], self._title, ""))
        if prop == "IconPixmap":
            if self._icon is None:
                return GLib.Variant("a(iiay)", [])
            w, h = self._icon.size
            return GLib.Variant("a(iiay)", [(w, h, _to_argb32(self._icon))])
        return None
