import sys
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cowriter import desktop


class DesktopTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('dbus-run-session'), 'Requires a private D-Bus session')
    def test_real_portal_transport_passes_attachment_without_a_mail_client(self):
        # A private bus and fake portal exercise PyGObject callbacks and FD
        # transport without contacting the user's desktop or mail application.
        script = '''
import os
import tempfile
from pathlib import Path
from gi.repository import Gio, GLib
from cowriter import desktop

loop = GLib.MainLoop()
errors = []
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
info = Gio.DBusNodeInfo.new_for_xml("""<node><interface name="org.freedesktop.portal.Email">
<method name="ComposeEmail"><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/>
<arg type="o" direction="out"/></method></interface></node>""")

def failed(error):
    errors.append(str(error))
    loop.quit()
desktop._fallback_email = lambda *args: failed('Unexpected native email fallback')

def compose(bus, sender, path, interface, method, parameters, invocation):
    try:
        parent, options = parameters.unpack()
        assert options['subject'] == 'Test subject'
        assert options['body'] == 'Only test text'
        fd = invocation.get_message().get_unix_fd_list().get(options['attachment_fds'][0])
        try:
            assert os.read(fd, 100) == b'fake attachment'
        finally:
            os.close(fd)
        request_path = desktop.PORTAL_PATH + '/request/' + sender[1:].replace('.', '_') + '/' + options['handle_token']
        invocation.return_value(GLib.Variant('(o)', (request_path,)))
        def respond():
            bus.emit_signal(None, request_path, 'org.freedesktop.portal.Request', 'Response',
                            GLib.Variant('(ua{sv})', (0, {})))
            return False
        GLib.timeout_add(20, respond)
    except Exception as error:
        failed(error)

registration = connection.register_object(desktop.PORTAL_PATH, info.interfaces[0], compose, None, None)
with tempfile.TemporaryDirectory() as directory:
    attachment = Path(directory) / 'test.odt'
    attachment.write_bytes(b'fake attachment')
    def acquired(*args):
        def done(error):
            if error:
                errors.append(str(error))
            loop.quit()
        desktop.compose_email('Test subject', 'Only test text', attachment, done)
    owner = Gio.bus_own_name_on_connection(connection, desktop.PORTAL_BUS, Gio.BusNameOwnerFlags.NONE, acquired, None)
    GLib.timeout_add_seconds(3, lambda: failed('Portal test timed out'))
    loop.run()
    Gio.bus_unown_name(owner)
connection.unregister_object(registration)
assert not errors, errors
'''
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', script],
                                env=env, capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_email_arguments_keep_special_text_in_literal_arguments(self):
        body = "Quotes ' and commas, $(echo test)\nUnicode café & links"
        args = desktop.email_arguments("xdg-email", "A subject", body, "/tmp/a file.odt")
        self.assertEqual(args[5], body)
        self.assertEqual(args[-1], "/tmp/a file.odt")
        fields = parse_qs(urlparse(desktop.mailto_uri("A & B", body)).query)
        self.assertEqual(fields['body'], [body])
        self.assertEqual(fields['subject'], ['A & B'])

    def test_writer_discovery_respects_installed_desktop_handlers(self):
        wrong = Mock()
        wrong.get_id.return_value = "other.desktop"
        wrong.get_name.return_value = "Other editor"
        wrong.get_executable.return_value = "other"
        writer = Mock()
        writer.get_id.return_value = "libreoffice-writer.desktop"
        writer.get_name.return_value = "LibreOffice Writer"
        writer.get_executable.return_value = "libreoffice"
        with patch.object(desktop.Gio.AppInfo, "get_all_for_type", return_value=[wrong, writer]):
            self.assertIs(desktop.writer_app(), writer)
            desktop.launch_writer(Path('/tmp/sample.odt'))
            self.assertEqual(writer.launch.call_args.args[0][0].get_path(), '/tmp/sample.odt')
        with patch.object(desktop, "writer_app", return_value=None):
            with self.assertRaises(RuntimeError):
                desktop.launch_writer(Path('/tmp/sample.odt'))

    def test_portal_attachments_use_file_descriptors_and_cancel_does_not_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'attachment.odt'
            path.write_bytes(b'test attachment')
            done = Mock()
            with patch.object(desktop.Gio, 'bus_get'), patch.object(desktop, '_fallback_email') as fallback:
                request = desktop.compose_email('Subject', 'Body', path, done)
                self.assertEqual(request.fds.get_length(), 1)
                self.assertEqual(request.options['attachment_fds'].unpack(), [0])
                request._response(None, None, None, None, None, desktop.GLib.Variant('(ua{sv})', (1, {})), None)
                done.assert_called_once_with('cancelled')
                fallback.assert_not_called()
                self.assertIsNone(request.fds)

    def test_portal_response_success_and_failure_complete_once(self):
        for status in (0, 2):
            done = Mock()
            with patch.object(desktop.Gio, 'bus_get'):
                request = desktop.compose_email('Subject', done=done)
            request._response(None, None, None, None, None, desktop.GLib.Variant('(ua{sv})', (status, {})))
            request._complete(None)
            self.assertEqual(done.call_count, 1)
            if status == 0:
                done.assert_called_once_with(None)
            else:
                self.assertIsInstance(done.call_args.args[0], RuntimeError)

    def test_unavailable_portal_falls_back_once_without_sending(self):
        done = Mock()
        with patch.object(desktop.Gio, 'bus_get'), patch.object(desktop, '_fallback_email') as fallback:
            request = desktop.compose_email('Subject', 'Body', done=done)
            request._fallback()
            request._fallback()
            fallback.assert_called_once_with('Subject', 'Body', None, done)

    def test_portal_call_subscribes_before_composing_and_uses_typed_options(self):
        connection = Mock()
        connection.get_unique_name.return_value = ':1.42'
        connection.signal_subscribe.return_value = 7
        done = Mock()
        with patch.object(desktop.Gio, 'bus_get'), \
             patch.object(desktop.Gio, 'bus_get_finish', return_value=connection):
            request = desktop.compose_email('Subject', 'Body', done=done)
            request._bus_ready(None, Mock())
        self.assertEqual(connection.method_calls[1][0], 'signal_subscribe')
        call = connection.call_with_unix_fd_list.call_args.args
        self.assertEqual(call[:4], (desktop.PORTAL_BUS, desktop.PORTAL_PATH,
                                   'org.freedesktop.portal.Email', 'ComposeEmail'))
        parent, options = call[4].unpack()
        self.assertEqual(parent, '')
        self.assertEqual(options['subject'], 'Subject')
        self.assertEqual(options['body'], 'Body')
        expected = call[-1]
        self.assertIn('/request/1_42/cowriter_', expected)
        connection.call_with_unix_fd_list_finish.return_value = (desktop.GLib.Variant('(o)', (expected,)), None)
        request._called(connection, Mock(), expected)
        request._response(None, None, None, None, None, desktop.GLib.Variant('(ua{sv})', (0, {})))
        done.assert_called_once_with(None)
        connection.signal_unsubscribe.assert_called_once_with(7)
