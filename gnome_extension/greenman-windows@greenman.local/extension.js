import Gio from 'gi://Gio';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'com.greenman.Windows';
const OBJECT_PATH = '/com/greenman/Windows';
const INTERFACE = `
<node>
  <interface name="com.greenman.Windows">
    <method name="List">
      <arg type="s" direction="out" name="windows"/>
    </method>
    <method name="Activate">
      <arg type="s" direction="in" name="title"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="Close">
      <arg type="s" direction="in" name="title"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="ActivateOwned">
      <arg type="s" direction="in" name="title"/>
      <arg type="u" direction="in" name="pid"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="IsOwnedFocused">
      <arg type="s" direction="in" name="title"/>
      <arg type="u" direction="in" name="pid"/>
      <arg type="s" direction="out" name="result"/>
    </method>
    <method name="OwnedGeometry">
      <arg type="s" direction="in" name="title"/>
      <arg type="u" direction="in" name="pid"/>
      <arg type="s" direction="out" name="result"/>
    </method>
  </interface>
</node>`;

function normalWindows() {
    return global.get_window_actors()
        .map(actor => actor.meta_window)
        .filter(window => window && window.get_window_type() === 0);
}

function findUnique(title) {
    const matches = normalWindows().filter(window => window.get_title() === title);
    if (matches.length === 0)
        return [null, 'not_found'];
    if (matches.length > 1)
        return [null, 'ambiguous'];
    return [matches[0], 'ok'];
}

export default class GreenManWindows extends Extension {
    enable() {
        this._dbus = Gio.DBusExportedObject.wrapJSObject(INTERFACE, this);
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);
        this._owner = Gio.bus_own_name_on_connection(
            Gio.DBus.session, BUS_NAME, Gio.BusNameOwnerFlags.NONE, null, null);
    }

    disable() {
        if (this._owner) {
            Gio.bus_unown_name(this._owner);
            this._owner = null;
        }
        if (this._dbus) {
            this._dbus.unexport();
            this._dbus = null;
        }
    }

    List() {
        return JSON.stringify(normalWindows().map(window => ({
            title: window.get_title(),
            app: window.get_wm_class(),
        })));
    }

    Activate(title) {
        const [window, status] = findUnique(title);
        if (!window)
            return status;
        window.activate(global.get_current_time());
        return 'ok';
    }

    ActivateOwned(title, pid) {
        const [window, status] = findUnique(title);
        if (!window)
            return status;
        if (window.get_pid() !== pid)
            return 'wrong_process';
        window.activate(global.get_current_time());
        return 'ok';
    }

    IsOwnedFocused(title, pid) {
        const [window, status] = findUnique(title);
        if (!window)
            return status;
        if (window.get_pid() !== pid)
            return 'wrong_process';
        return global.display.get_focus_window() === window ? 'ok' : 'not_focused';
    }

    OwnedGeometry(title, pid) {
        const [window, status] = findUnique(title);
        if (!window)
            return JSON.stringify({status});
        if (window.get_pid() !== pid)
            return JSON.stringify({status: 'wrong_process'});
        const frame = window.get_frame_rect();
        const monitor = global.display.get_monitor_geometry(window.get_monitor());
        return JSON.stringify({
            status: 'ok',
            frame: [frame.x, frame.y, frame.width, frame.height],
            monitor: [monitor.x, monitor.y, monitor.width, monitor.height],
            monitor_count: global.display.get_n_monitors(),
        });
    }

    Close(title) {
        const [window, status] = findUnique(title);
        if (!window)
            return status;
        window.delete(global.get_current_time());
        return 'ok';
    }
}
