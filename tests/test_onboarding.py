import os
import tempfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import litebrowser  # noqa: F401
from litebrowser.qt import QtCore, QtWidgets
from litebrowser.core import prefs
from litebrowser.ui import onboarding
from litebrowser.ui import personal_window  # noqa: F401 - load WebEngine before QApplication


def test_onboarding_preserves_current_choices_and_completes():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["onboarding-test"])
    with tempfile.TemporaryDirectory() as directory:
        base = prefs.ensure_profile_layout(directory)
        prefs.set_accent(base, "teal")
        shell = QtWidgets.QWidget()
        shell.profile_dir = base
        shell.refresh_shell = mock.Mock()
        steps = []
        def click_next():
            dialog = app.activeModalWidget()
            if dialog is None:
                return
            buttons = dialog.findChildren(QtWidgets.QPushButton)
            next_button = next(button for button in buttons if button.text() in ("Next", "Finish ✨"))
            steps.append(next_button.text())
            next_button.click()
        timer = QtCore.QTimer()
        timer.timeout.connect(click_next)
        timer.start(10)
        try:
            onboarding.show_onboarding(shell)
        finally:
            timer.stop()
        assert steps == ["Next", "Next", "Finish ✨"]
        assert prefs.get_accent(base) == "teal"
        assert prefs.get_pref(base, "onboarding_done", False)
        shell.deleteLater()


def test_skip_setup_is_remembered():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["onboarding-test"])
    with tempfile.TemporaryDirectory() as directory:
        shell = QtWidgets.QWidget()
        shell.profile_dir = prefs.ensure_profile_layout(directory)
        def skip():
            dialog = app.activeModalWidget()
            next(button for button in dialog.findChildren(QtWidgets.QPushButton) if button.text() == "Skip setup").click()
        QtCore.QTimer.singleShot(10, skip)
        onboarding.show_onboarding(shell)
        assert prefs.get_pref(shell.profile_dir, "onboarding_done", False)
        with mock.patch.object(onboarding.QDialog, "exec_", side_effect=AssertionError("setup repeated")):
            onboarding.show_onboarding(shell)
        shell.deleteLater()
