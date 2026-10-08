"""GNOME desktop handoffs. Email composition never sends a message."""

import os
import shutil
import subprocess
import threading
import uuid
from pathlib import Path
from urllib.parse import urlencode, quote

from gi.repository import Gio, GLib


PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"


def mailto_uri(subject, body):
    return "mailto:?" + urlencode({"subject": subject, "body": body}, quote_via=quote)


def email_arguments(executable, subject, body, attachment=None):
    args = [executable, "--utf8", "--subject", subject, "--body", body]
    if attachment is not None:
        args.extend(["--attach", str(Path(attachment).resolve())])
    return args


def writer_app():
    apps = Gio.AppInfo.get_all_for_type("application/vnd.oasis.opendocument.text")
    for app in apps:
        identity = " ".join([app.get_id() or "", app.get_name() or "", app.get_executable() or ""]).lower()
        if "libreoffice" in identity:
            return app
    return None


def launch_writer(path, context=None):
    app = writer_app()
    if app is None:
        raise RuntimeError("Install LibreOffice Writer, or use Open Markdown copy with… to choose another application.")
    if not app.launch([Gio.File.new_for_path(str(path))], context):
        raise RuntimeError("LibreOffice could not open the formatted copy.")


def _fallback_email(subject, body, attachment, done):
    executable = shutil.which("xdg-email")
    if executable is None:
        if attachment is not None:
            done(RuntimeError("Email attachments need a desktop email portal or xdg-email. You can attach the saved copy manually."))
        else:
            Gio.AppInfo.launch_default_for_uri_async(mailto_uri(subject, body), None, None,
                lambda source, result: _finish_uri(result, done))
        return

    def launch():
        try:
            subprocess.run(email_arguments(executable, subject, body, attachment),
                           check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            error = RuntimeError("The mail app did not confirm opening. Check its compose window and your default mail application setting.")
        else:
            error = None
        GLib.idle_add(lambda: (done(error), False)[1])
    threading.Thread(target=launch, daemon=True).start()


def _finish_uri(result, done):
    try:
        Gio.AppInfo.launch_default_for_uri_finish(result)
    except GLib.Error as error:
        done(error)
    else:
        done(None)


class EmailRequest:
    """Keep the portal signal subscription alive until its response."""

    def __init__(self, subject, body, attachment, done):
        self.subject, self.body, self.attachment, self.done = subject, body, attachment, done
        self.connection = None
        self.subscription = None
        self.finished = False
        self.fds = Gio.UnixFDList.new()
        self.options = {"subject": GLib.Variant("s", subject), "body": GLib.Variant("s", body),
                        "handle_token": GLib.Variant("s", "cowriter_" + uuid.uuid4().hex)}
        if attachment is not None:
            fd = os.open(str(attachment), os.O_RDONLY)
            try:
                index = self.fds.append(fd)
            finally:
                os.close(fd)
            self.options["attachment_fds"] = GLib.Variant("ah", [index])
        Gio.bus_get(Gio.BusType.SESSION, None, self._bus_ready)

    def _subscribe(self, path):
        if self.subscription is not None:
            self.connection.signal_unsubscribe(self.subscription)
        self.subscription = self.connection.signal_subscribe(
            PORTAL_BUS, "org.freedesktop.portal.Request", "Response", path, None,
            Gio.DBusSignalFlags.NONE, self._response)

    def _bus_ready(self, source, result):
        try:
            self.connection = Gio.bus_get_finish(result)
            sender = self.connection.get_unique_name()[1:].replace(".", "_")
            path = f"{PORTAL_PATH}/request/{sender}/{self.options['handle_token'].unpack()}"
            self._subscribe(path)
            self.connection.call_with_unix_fd_list(
                PORTAL_BUS, PORTAL_PATH, "org.freedesktop.portal.Email", "ComposeEmail",
                GLib.Variant("(sa{sv})", ("", self.options)), GLib.VariantType.new("(o)"),
                Gio.DBusCallFlags.NONE, 10000, self.fds, None, self._called, path)
        except GLib.Error:
            self._fallback()

    def _called(self, connection, result, expected_path):
        try:
            reply, _ = connection.call_with_unix_fd_list_finish(result)
        except GLib.Error:
            self._fallback()
            return
        if not self.finished and reply.unpack()[0] != expected_path:
            self._subscribe(reply.unpack()[0])

    def _response(self, connection, sender, path, interface, signal, parameters, *_args):
        response, _ = parameters.unpack()
        # Cancellation leaves the user in control and does not launch a fallback.
        self._complete(None if response == 0 else
                       "cancelled" if response == 1 else
                       RuntimeError("The desktop could not open the mail composer. Check your default mail application."))

    def _cleanup(self):
        if self.subscription is not None:
            self.connection.signal_unsubscribe(self.subscription)
            self.subscription = None
        self.fds = None

    def _complete(self, error):
        if not self.finished:
            self.finished = True
            self._cleanup()
            self.done(error)

    def _fallback(self):
        if self.finished:
            return
        self.finished = True
        self._cleanup()
        _fallback_email(self.subject, self.body, self.attachment, self.done)


def compose_email(subject, body="", attachment=None, done=lambda error: None):
    """Use the desktop email portal, with xdg-email as a native fallback."""
    try:
        return EmailRequest(subject, body, attachment, done)
    except (OSError, GLib.Error) as error:
        done(error)
        return None
