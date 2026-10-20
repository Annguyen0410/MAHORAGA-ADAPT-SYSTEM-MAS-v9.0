"""Desktop-only interaction regressions with disposable profile data."""
import os
import tempfile
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import litebrowser  # noqa: E402,F401
from litebrowser.qt import QtCore, QtWidgets  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from litebrowser.core import prefs, theme_data  # noqa: E402
from litebrowser.services import life_service  # noqa: E402
from litebrowser.ui.personal_window import PersonalWindow  # noqa: E402
from litebrowser.ui import theme  # noqa: E402
from litebrowser.ui.board_canvas import InkStrokeItem  # noqa: E402
from litebrowser.ui.dialogs.common import more_menu  # noqa: E402
from litebrowser.ui.shell.pages import SettingsPage  # noqa: E402
from test_ui_wiring import _StubShell  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["desktop-polish-tests"])
Qt = QtCore.Qt


def test_all_palettes_and_custom_accents_have_readable_text():
    for mode in theme_data.PALETTES:
        for accent in (*theme_data.ACCENTS, "#ffffff", "#000000", "#aacc44", "#592075"):
            palette = theme_data.palette_tokens(mode, accent)
            assert theme_data.contrast_ratio(palette["TEXT_ON_ACCENT"], palette["ACCENT"]) >= 4.5
            assert theme_data.contrast_ratio(palette["TEXT_ON_ACCENT"], palette["ACCENT_FILL_HOVER"]) >= 4.5
            assert theme_data.contrast_ratio(palette["TEXT_ON_DANGER"], palette["DANGER"]) >= 4.5
            assert theme_data.contrast_ratio(palette["TEXT_MUTED"], palette["MAIN_BG"]) >= 4.5
            for background in ('MAIN_BG', 'CARD_BG', 'MAIN_BG_ALT', 'ACCENT_SOFT'):
                assert theme_data.contrast_ratio(palette["ACCENT_HOVER"], palette[background]) >= 4.5
            assert theme_data.contrast_ratio(palette["TEXT_MUTED"], palette['CARD_BG']) >= 4.5


def test_surface_styles_never_use_accent_foreground_as_background():
    for qss in (theme.main_qss('minimal'), theme.dialog_qss('minimal')):
        assert 'background-color: ' + theme_data.palette_tokens('minimal')['TEXT_ON_ACCENT'] + '; color:' not in qss.split('QDialog {')[0]
    import re
    source = __import__('inspect').getsource(theme)
    assert not re.search(r'background-color:\s*%\(TEXT_ON_ACCENT\)s', source)


def test_light_dark_and_system_resolution():
    with tempfile.TemporaryDirectory() as base:
        prefs.set_shell_theme(base, "lavender-day")
        prefs.save_pref(base, "appearance_mode", "dark")
        assert prefs.resolved_auto_theme(base) == "lavender-night"
        prefs.save_pref(base, "appearance_mode", "light")
        assert prefs.resolved_auto_theme(base) == "lavender-day"
        prefs.set_accent(base, "#abcdef")
        assert prefs.get_accent(base) == "#abcdef"
        prefs.save_pref(base, "appearance_mode", "system")
        try:
            import winreg
        except ImportError:
            assert not theme_data.is_night_theme(prefs.resolved_auto_theme(base))
        else:
            # Isolate both registry operations so the test follows the mocked
            # value even when the host has no Personalize key or denies access.
            with mock.patch.object(winreg, "OpenKey") as open_key:
                open_key.return_value.__enter__.return_value = object()
                with mock.patch.object(winreg, "QueryValueEx", return_value=(0, 4)):
                    assert theme_data.is_night_theme(prefs.resolved_auto_theme(base))
                with mock.patch.object(winreg, "QueryValueEx", return_value=(1, 4)):
                    assert not theme_data.is_night_theme(prefs.resolved_auto_theme(base))


def test_settings_drafts_and_separate_snapshot_sync_controls():
    with tempfile.TemporaryDirectory() as temp:
        base = prefs.ensure_profile_layout(temp)
        shell = _StubShell(base)
        page = SettingsPage(shell)
        page.refresh()
        page.ed_display_name.setText("Unsaved name")
        page.cmb_appearance.setCurrentIndex(page.cmb_appearance.findData("dark"))
        page.cmb_motion.setCurrentIndex(page.cmb_motion.findData("reduce"))
        page.refresh()
        assert page.ed_display_name.text() == "Unsaved name"
        assert page.cmb_appearance.currentData() == "dark"
        assert page.cmb_motion.currentData() == "reduce"
        assert page.chk_local_snapshot is not page.chk_sync_enabled
        with mock.patch.object(QtWidgets.QMessageBox, "information"):
            page.save_ui()
        assert prefs.get_pref(base, "appearance_mode") == "dark"
        assert prefs.get_pref(base, "reduced_motion") == "reduce"
        page.deleteLater()
        shell.deleteLater()
        app.processEvents()


def test_overflow_mouse_and_keyboard_inside_modal_dialog():
    dialog = QtWidgets.QDialog()
    layout = QtWidgets.QVBoxLayout(dialog)
    calls = []
    button = more_menu((("First action", lambda: calls.append("first")), ("Second action", lambda: calls.append("second"))))
    layout.addWidget(button)
    dialog.setModal(True)
    dialog.show()
    app.processEvents()
    menu = button.menu()
    def click_first():
        assert menu.isVisible()
        QTest.mouseClick(menu, Qt.LeftButton, pos=menu.actionGeometry(menu.actions()[0]).center())
    QtCore.QTimer.singleShot(80, click_first)
    QTest.mouseClick(button, Qt.LeftButton)
    QTest.qWait(150)
    assert calls == ["first"]
    def choose_second():
        menu.setActiveAction(menu.actions()[1])
        QTest.keyClick(menu, Qt.Key_Return)
    QtCore.QTimer.singleShot(80, choose_second)
    QTest.mouseClick(button, Qt.LeftButton)
    QTest.qWait(150)
    assert calls == ["first", "second"]
    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_board_history_save_reopen_and_failed_switch():
    with tempfile.TemporaryDirectory() as temp:
        base = prefs.ensure_profile_layout(temp)
        first = life_service.add_board(base, "First")
        second = life_service.add_board(base, "Second")
        window = PersonalWindow(base, embedded=True)
        window.resize(1200, 800)
        window.show()
        window.open_life_item("board", first["id"])
        app.processEvents()
        view = window.board_view
        assert view.background_color == "#ffffff"
        for tool in ("pen", "pencil", "marker", "line", "rectangle", "ellipse"):
            before = window._board_snapshot()
            stroke = {"id": tool, "tool": tool, "color": "#3e799f", "width": 6, "opacity": .65,
                      "points": [{"x": 20, "y": 30}, {"x": 200, "y": 160}]}
            window.board_scene.addItem(InkStrokeItem(stroke))
            view.record_change(before)
        expected = window._board_snapshot()
        window._refresh_boards()
        assert view._undo, "Routine refresh must preserve drawing history"
        view.undo()
        assert len(window._board_snapshot()["strokes"]) == 5
        view.redo()
        assert window._board_snapshot() == expected
        before = window._board_snapshot()
        view.set_background("#e4eadf")
        view.record_change(before)
        assert window._save_current_board_positions(notify=False)
        window.open_life_item("board", second["id"])
        window.open_life_item("board", first["id"])
        assert window._board_snapshot()["background"] == "#e4eadf"
        assert window._board_snapshot()["strokes"] == expected["strokes"]
        before = window._board_snapshot()
        view._gesture_before = before
        window.board_scene.removeItem(next(i for i in window.board_scene.items() if isinstance(i, InkStrokeItem)))
        view.cancel_gesture()
        assert window._board_snapshot() == before
        view.set_zoom(2)
        scene_point = QtCore.QPointF(100, 100)
        assert (view.mapToScene(view.mapFromScene(scene_point)) - scene_point).manhattanLength() < 1.1
        view.fit_canvas()
        assert view.transform().m11() >= .1
        before = window._board_snapshot()
        view.set_background("#ffeedd")
        view.record_change(before)
        with mock.patch.object(life_service, "update_board", side_effect=OSError("disk unavailable")):
            window.open_life_item("board", second["id"])
        assert window.current_board_id == first["id"]
        assert window.boards_list.currentItem().data(Qt.UserRole) == first["id"]
        assert view.background_color == "#ffeedd"
        concurrent = next(b for b in life_service.load_boards(base) if b['id'] == first['id'])
        concurrent['background'] = '#123456'
        life_service.update_board(base, concurrent)
        assert not window._save_current_board_positions(notify=False)
        assert next(b for b in life_service.load_boards(base) if b['id'] == first['id'])['background'] == '#123456'
        with mock.patch.object(QtWidgets.QInputDialog, 'getText', return_value=('Recovered canvas', True)):
            window._save_board_copy()
        assert window.current_board_id != first['id']
        assert next(b for b in life_service.load_boards(base) if b['id'] == window.current_board_id)['background'] == '#ffeedd'
        window.close()
        window.deleteLater()
        app.processEvents()


def test_bad_stroke_values_cannot_break_painting():
    item = InkStrokeItem({"color": "nonsense", "width": float("nan"), "opacity": float("inf"),
                          "points": [None, {"x": float("nan"), "y": "bad"}]})
    assert item.pen().color().isValid()
    assert item.stroke["points"] == [{"x": 0.0, "y": 0.0}]
    assert item.opacity() == 1
