"""Real-widget product QA with disposable profiles and no external requests."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import litebrowser  # noqa: E402,F401
from litebrowser.qt import QtCore, QtWidgets, QtWebEngineCore  # noqa: E402
from litebrowser.core import prefs  # noqa: E402
from litebrowser.services import personal_service, personal_plan, security, study_session, focus_service, sync_folder, life_service  # noqa: E402
from litebrowser.ui.app_shell import AppShell  # noqa: E402
from litebrowser.ui.board_canvas import InkStrokeItem  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402


class OfflineOnly(QtWebEngineCore.QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        if info.requestUrl().scheme() in ("http", "https"):
            info.block(True)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["mei-product-qa"])
    app.setQuitOnLastWindowClosed(False)
    from litebrowser.qt import QtGui
    font = QtGui.QFont("Segoe UI", 10)
    font.setFamilies(["Segoe UI", "Segoe UI Symbol", "Segoe UI Emoji", "Arial"])
    app.setFont(font)
    output = ROOT / "docs/reports/product-qa"
    output.mkdir(parents=True, exist_ok=True)
    facts = []
    def fact(name, condition):
        facts.append({"name": name, "ok": bool(condition)})
        print(("PASS " if condition else "FAIL ") + name, flush=True)
        if not condition:
            raise AssertionError(name)
    def pump(seconds=0.3):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(0.01)
    with tempfile.TemporaryDirectory(prefix="mei-product-qa-", ignore_cleanup_errors=True) as temp:
        base = prefs.ensure_profile_layout(str(Path(temp) / "profile"))
        prefs.save_pref(base, "onboarding_done", True)
        prefs.set_auto_theme(base, False)
        security.set_passcode(base, "qa-only")
        with mock.patch.object(AppShell, "_startup_update_check"), mock.patch.object(AppShell, "_init_tray"), mock.patch.object(AppShell, "_init_global_hotkey"), mock.patch.object(security, "ensure_unlocked", return_value=True):
            shell = AppShell(base, app_dir=temp, window_slot="secondary")
            blockers = []
            for profile in shell.findChildren(QtWebEngineCore.QWebEngineProfile):
                blocker = OfflineOnly(profile)
                profile.setUrlRequestInterceptor(blocker)
                blockers.append(blocker)
            shell.show(); pump(0.7)
            secret = personal_service.create_note(base, "Private reading", "# Reading\n\nFirst draft")
            shell.home_page.refresh()
            fact("locked Home does not expose private note titles", "Private reading" not in " ".join(shell.home_page.recent_notes.item(i).text() for i in range(shell.home_page.recent_notes.count())))
            # Real navigation buttons, editor and filter controls.
            shell.nav_buttons["personal"].click(); pump()
            shell.personal_page.select_note(secret["id"]); pump()
            shell.personal_page.note_editor.setPlainText("# Reading\n\nTyped before switching")
            other = personal_service.create_note(base, "Second reading", "other")
            shell.personal_page._refresh_notes()
            shell.personal_page.select_note(other["id"]); pump()
            fact("note switching saves the previous draft", "Typed before switching" in personal_service.read_note(base, secret["id"])["content"])
            shell.personal_page.ed_note_search.setText("missing result"); shell.personal_page._refresh_notes()
            shell.open_library_item({"kind": "note", "id": secret["id"]}); pump()
            fact("deep link clears stale note filters", shell.personal_page.current_note_id == secret["id"] and not shell.personal_page.ed_note_search.text())
            shell.personal_page.note_editor.setPlainText("my concurrent draft")
            personal_service.save_note(base, secret["id"], "newer external version")
            fact("concurrent editor does not overwrite newer content", not shell.personal_page._flush_note_edits())
            shell.personal_page._save_note(); pump()
            fact("explicit Save keeps both conflicting versions", shell.personal_page.current_note_id != secret["id"] and personal_service.read_note(base, secret["id"])["content"] == "newer external version")
            shell.nav_buttons["library"].click(); pump()
            shell.library_page.ed_search.clear(); shell.library_page.btn_refresh.click(); pump()
            fact("Library Refresh works without a query", shell.library_page.list_widget.count() > 0)
            shell.library_page.library_filter_buttons["notes"].click(); pump()
            fact("Library note filter can be selected", shell.library_page._library_filter == "notes")
            item = personal_plan.create_item(base, "Study one chapter", duration_minutes=25)
            shell.open_flow_step({"step": "study", "kind": "planner-item", "id": item["id"], "minutes": 25, "start": True}); pump()
            fact("study journey starts one linked focus session", focus_service.focus_status(base)["running"])
            study_session.finish(base)
            shell.refresh_shell(); pump()
            shell.nav_buttons["home"].click(); pump()
            for width, height, name in [(1440, 900, "home-wide"), (800, 640, "home-narrow")]:
                shell.resize(width, height); pump(0.6)
                shell.grab().save(str(output / (name + ".png")))
                scroll = shell.home_page.home_scroll
                print(f"GEOMETRY {name}: shell={shell.width()} page={shell.home_page.width()} content={scroll.widget().width()} viewport={scroll.viewport().width()}")
                if scroll.widget().width() > scroll.viewport().width() + 2:
                    widgets = sorted(scroll.widget().findChildren(QtWidgets.QWidget), key=lambda widget: widget.minimumSizeHint().width(), reverse=True)
                    for widget in widgets[:12]:
                        print('MINIMUM', type(widget).__name__, widget.objectName(), widget.minimumSizeHint().width(), widget.width())
                fact(name + " remains within window width", scroll.widget().width() <= scroll.viewport().width() + 2)
            shell.nav_buttons["personal"].click(); shell.personal_page.select_note(other["id"]); pump()
            shell.grab().save(str(output / "notes-narrow.png"))
            shell.resize(1440, 900); pump(); shell.grab().save(str(output / "notes-wide.png"))
            # Desktop polish: actual mouse gestures and native popup hit testing.
            personal = shell.personal_page
            board = life_service.add_board(base, "Creative workspace")
            personal.open_life_item("board", board["id"]); pump()
            view = personal.board_view
            viewport = view.viewport()
            view.set_zoom(1)
            view.centerOn(500, 350); pump()
            fact("board paper defaults to white independently from chrome", view.background_color == "#ffffff")
            def drag(widget, start, end, button=QtCore.Qt.LeftButton):
                shell.activateWindow(); widget.setFocus(); pump(.1)
                QTest.mousePress(widget, button, pos=start)
                # QTest.mouseMove uses OS movement, but mousePress is injected:
                # provide held-button state through Qt's real viewport pipeline.
                move = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove, QtCore.QPointF(end), QtCore.QPointF(widget.mapToGlobal(end)), QtCore.Qt.NoButton, button, QtCore.Qt.KeyboardModifier.NoModifier)
                app.sendEvent(widget, move)
                QTest.mouseRelease(widget, button, pos=end)
                pump(.08)
            for index, tool in enumerate(("pen", "pencil", "marker", "line", "rectangle", "ellipse")):
                personal.cmb_board_tool.setCurrentIndex(personal.cmb_board_tool.findData(tool))
                personal.btn_mode_draw.click()
                start = QtCore.QPoint(80 + index * 65, 100 + (index % 2) * 100)
                end = start + QtCore.QPoint(55, 60)
                drag(viewport, start, end)
                strokes = personal._board_snapshot()["strokes"]
                fact("native gesture creates " + tool, any(s["tool"] == tool and len(s["points"]) >= 2 for s in strokes))
            personal.btn_board_undo.click(); pump()
            fact("Undo removes the last drawn shape", len(personal._board_snapshot()["strokes"]) == 5)
            personal.btn_board_redo.click(); pump()
            fact("Redo restores the shape", len(personal._board_snapshot()["strokes"]) == 6)
            with mock.patch.object(QtWidgets.QColorDialog, "getColor", return_value=QtGui.QColor("#315986")):
                personal.btn_pen_custom.click()
            fact("custom drawing color has visible hex feedback", view.pen_color == "#315986" and "315986" in personal.btn_pen_custom.text())
            with mock.patch.object(QtWidgets.QColorDialog, "getColor", return_value=QtGui.QColor("#f1f6ec")):
                personal.btn_canvas_color.click()
            fact("paper color is independently customizable", view.background_color == "#f1f6ec")
            personal.btn_board_zoom_in.click(); pump()
            fact("zoom preserves scene/viewport coordinate mapping", (view.mapToScene(view.mapFromScene(QtCore.QPointF(450, 300))) - QtCore.QPointF(450, 300)).manhattanLength() < 1.1)
            old_scroll = (view.horizontalScrollBar().value(), view.verticalScrollBar().value())
            old_count = len(personal._board_snapshot()["strokes"])
            drag(viewport, QtCore.QPoint(300, 260), QtCore.QPoint(340, 295), QtCore.Qt.MiddleButton)
            fact("middle-drag pans without drawing", old_scroll != (view.horizontalScrollBar().value(), view.verticalScrollBar().value()) and len(personal._board_snapshot()["strokes"]) == old_count)
            personal.cmb_board_tool.setCurrentIndex(personal.cmb_board_tool.findData("eraser"))
            target = next(i for i in personal.board_scene.items() if isinstance(i, InkStrokeItem) and i.stroke['tool'] == 'pen')
            point = target.stroke["points"][0]
            position = view.mapFromScene(QtCore.QPointF(point["x"], point["y"]))
            QTest.mouseClick(viewport, QtCore.Qt.LeftButton, pos=position); pump()
            fact("eraser removes ink and is undoable", len(personal._board_snapshot()["strokes"]) < old_count and personal.btn_board_undo.isEnabled())
            personal.btn_board_undo.click(); pump()
            def click_menu(button, text):
                menu = button.menu()
                action = next(a for a in menu.actions() if a.text() == text)
                QtCore.QTimer.singleShot(70, lambda: QTest.mouseClick(menu, QtCore.Qt.LeftButton, pos=menu.actionGeometry(action).center()))
                QTest.mouseClick(button, QtCore.Qt.LeftButton)
                pump(.2)
            board_more = next(b for b in personal.stack.currentWidget().findChildren(QtWidgets.QPushButton) if b.menu())
            click_menu(board_more, "Save board")
            saved = next(b for b in life_service.load_boards(base) if b['id'] == board['id'])
            fact("More Save persists full drawing records and paper", len(saved['strokes']) == 6 and saved['background'] == "#f1f6ec")
            click_menu(board_more, "Clear the ink on this board")
            fact("More Clear ink is genuinely clickable", not personal._board_snapshot()['strokes'])
            personal.btn_board_undo.click(); pump()
            click_menu(board_more, "Clear every link")
            with mock.patch.object(QtWidgets.QInputDialog, "getText", return_value=("New menu board", True)):
                click_menu(board_more, "New board…")
            fact("More New board selects a fresh white board", personal.current_board_id != board['id'] and view.background_color == "#ffffff" and not personal._board_snapshot()['strokes'])
            with mock.patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
                click_menu(board_more, "Delete this board")
            fact("More Delete removes only the selected board", len(life_service.load_boards(base)) == 1)
            personal.open_life_item('board', board['id']); view.fit_canvas(); pump()
            shell.grab().save(str(output / "board-wide.png"))
            personal._switch_page('calendar'); pump()
            fact("Calendar import/export labels are explicit and visible", personal.btn_ics_import.text() == "Import .ics" and personal.btn_ics_export.text() == "Export .ics" and personal.btn_ics_import.isVisible() and personal.btn_ics_export.isVisible())
            shell.grab().save(str(output / "calendar-wide.png"))
            personal._switch_page('plan'); pump()
            fact("Weekly Plan opens calmly with advanced forms collapsed", personal._plan_setup.isHidden() and personal._plan_details.isHidden())
            fact("Weekly Plan day labels use real line breaks", all(chr(10) in label.text() and chr(92) + 'n' not in label.text() for label, _ in personal.plan_day_lists.values()))
            shell.grab().save(str(output / "plan-wide.png"))
            shell.nav_buttons['ai'].click(); pump()
            shell.grab().save(str(output / "ai-wide.png"))
            shell.nav_buttons['settings'].click(); pump()
            settings = shell.settings_page
            with mock.patch.object(QtWidgets.QMessageBox, 'information'):
                for appearance in ('dark', 'light', 'system'):
                    settings.cmb_appearance.setCurrentIndex(settings.cmb_appearance.findData(appearance))
                    settings.btn_save_ui.click(); pump()
                    fact(appearance + " appearance reaches every Desktop workspace", all(w.styleSheet() == shell.styleSheet() for w in (shell.browser_page, shell.ai_page, shell.personal_page, settings, shell.home_page)))
                settings.cmb_appearance.setCurrentIndex(settings.cmb_appearance.findData('light'))
                with mock.patch.object(QtWidgets.QColorDialog, 'getColor', return_value=QtGui.QColor('#378e9b')):
                    settings.btn_custom_accent.click()
                settings.btn_save_ui.click(); pump()
            fact("custom accent persists", prefs.get_accent(base) == '#378e9b')
            settings.ed_display_name.setText('Unsaved profile draft'); shell.refresh_shell(); pump()
            fact("routine refresh preserves unsaved Settings drafts", settings.ed_display_name.text() == 'Unsaved profile draft')
            shell.grab().save(str(output / "settings-wide.png"))
            shell.nav_buttons['browser'].click(); pump()
            browser = shell.browser_page
            active = browser.current_browser()
            browser.on_load_started(active)
            fact("browser reload turns into accessible Stop", browser.btn_reload.accessibleName() == 'Stop loading')
            browser.on_load_finished(False, active)
            fact("browser stop/loading state resets on failure", browser.btn_reload.accessibleName() == 'Reload' and browser.load_progress.isHidden())
            # Real engine history, no external site or authenticated session.
            local_pages = []
            for index in range(2):
                path = Path(temp) / ('browser-qa-' + str(index) + '.html')
                path.write_text('<!doctype html><title>Desktop QA page ' + str(index) + '</title><h1>Local navigation test</h1>', encoding='utf-8')
                local_pages.append(QtCore.QUrl.fromLocalFile(str(path)))
                active.setUrl(local_pages[-1]); pump(.6)
            fact('browser Back reflects engine history', browser.btn_back.isEnabled())
            browser.btn_back.click(); pump(.6)
            fact('browser Back navigates and enables Forward', active.url() == local_pages[0] and browser.btn_forward.isEnabled())
            browser.btn_forward.click(); pump(.6)
            fact('browser Forward returns to the newer page', active.url() == local_pages[1])
            browser.zoom_in(); pump()
            QTest.mouseClick(browser.lbl_zoom, QtCore.Qt.LeftButton); pump()
            fact("browser zoom reset is a real keyboard-focusable button", isinstance(browser.lbl_zoom, QtWidgets.QToolButton) and active.zoomFactor() == 1)
            browser.add_new_tab(None, 'New Tab'); pump(1)
            current = browser.current_browser()
            deadline = time.monotonic() + 8
            while current.property('mei_loading') and time.monotonic() < deadline:
                pump(.1)
            rendered = []
            current.page().runJavaScript("({heading:document.querySelector('h1')?.textContent, width:innerWidth, height:innerHeight})", rendered.append)
            pump(.6)
            print('NEW-TAB-RENDER', rendered, flush=True)
            fact('internal new tab renders its heading', bool(rendered and rendered[0] and rendered[0].get('heading')))
            shell.grab().save(str(output / "browser-wide.png"))
            for workspace, page in (('personal', 'boards'), ('personal', 'plan'), ('personal', 'calendar'), ('settings', None), ('browser', None), ('ai', None), ('personal', 'tasks'), ('personal', 'review'), ('personal', 'files'), ('personal', 'sites'), ('personal', 'overview'), ('history', None), ('library', None)):
                shell.resize(800, 640)
                shell.nav_buttons[workspace].click()
                if page:
                    personal._switch_page(page)
                pump(1.5 if workspace == 'browser' else .3)
                name = page or workspace
                if workspace == 'browser':
                    rendered_narrow = []
                    browser.current_browser().page().runJavaScript("({heading:document.querySelector('h1')?.textContent, width:innerWidth, height:innerHeight})", rendered_narrow.append)
                    pump(1)
                    fact('narrow internal page retains rendered content after workspace switching', bool(rendered_narrow and rendered_narrow[0] and rendered_narrow[0].get('heading')))
                image = shell.grab()
                if workspace == 'browser':
                    # QWidget.grab can omit a native child compositor after hide/show;
                    # capture the WebEngine surface itself and compose the evidence.
                    painter = QtGui.QPainter(image)
                    painter.drawPixmap(browser.current_browser().mapTo(shell, QtCore.QPoint(0, 0)), browser.current_browser().grab())
                    painter.end()
                image.save(str(output / (name + '-narrow.png')))
                if workspace == 'browser':
                    fact('narrow browser retains visible panel controls', all(b.isVisible() and b.width() >= 32 for b in (browser.btn_panel_tabs, browser.btn_panel_bookmarks, browser.btn_panel_history, browser.btn_panel_downloads, browser.btn_panel_reading)))
                if workspace == 'settings':
                    fact("compact Settings content fits viewport", settings.settings_scroll.widget().width() <= settings.settings_scroll.viewport().width() + 2)
            shell.resize(1440, 900); pump()
            # A short repeated-use soak checks actual navigation and widget
            # ownership rather than only a single screenshot.
            timer_count = len(shell.findChildren(QtCore.QTimer))
            for _ in range(12):
                for workspace in ('home', 'library', 'settings', 'personal'):
                    shell.nav_buttons[workspace].click()
                    app.processEvents()
            fact("repeated navigation does not accumulate timers", len(shell.findChildren(QtCore.QTimer)) == timer_count)
            sync_folder.set_folder(base, str(Path(temp) / 'shared-sync'))
            shell.settings_page._refresh_folder_sync()
            with mock.patch.object(QtWidgets.QMessageBox, 'information'):
                shell.settings_page.btn_preview_sync.click()
                fact("folder preview runs asynchronously with controls disabled", shell.settings_page._folder_sync_running and not shell.settings_page.btn_apply_sync.isEnabled())
                deadline = time.monotonic() + 5
                while shell.settings_page._folder_sync_running and time.monotonic() < deadline:
                    pump(0.05)
                fact("folder preview recovers controls without writing a payload", not shell.settings_page._folder_sync_running and shell.settings_page.btn_preview_sync.isEnabled() and not Path(sync_folder.payload_path(base)).exists())
            peer = AppShell(base, app_dir=temp, window_slot="primary")
            peer.show(); peer.nav_buttons['personal'].click(); pump()
            prefs.save_pref(base, 'appearance_mode', 'dark')
            shell.refresh_shell(); pump()
            fact("appearance updates another open profile window", peer._qss_key == shell._qss_key and peer.styleSheet() == shell.styleSheet())
            shell.grab().save(str(output / 'theme-dark.png'))
            security.lock(base); pump()
            fact("lock hides Personal and clears AI preview", shell.stack.currentWidget() is shell.home_page and not shell.ai_preview.text())
            fact("profile lock relocks every open window", peer.stack.currentWidget() is peer.home_page and peer._private_locked)
            peer.close(); peer.deleteLater(); pump()
            with mock.patch.object(shell.personal_page, "persist_state", return_value=False):
                shell.close(); pump()
                fact("failed save cancels window close", shell.isVisible() and not shell._closing)
            fact("session persists before closing", shell.persist_state())
            shell.close(); pump()
            fact("normal close shuts down embedded resources", shell._closing and shell.browser_page._closing and shell.ai_page._closing)
            reopened = AppShell(base, app_dir=temp, window_slot="secondary")
            reopened.show(); pump()
            reopened.nav_buttons["personal"].click(); reopened.personal_page.select_note(other["id"]); pump()
            fact("reopening restores saved note contents", reopened.personal_page.note_editor.toPlainText() == "other")
            reopened.close(); reopened.deleteLater()
            shell.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
            pump()
            app.processEvents()
    (output / "journeys.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print(f"SUMMARY {len(facts)} journeys passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
