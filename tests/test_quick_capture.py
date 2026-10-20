"""Quick-capture dialog keeps inputs reviewable and validates destinations."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import litebrowser  # noqa: E402,F401 - activate the supported Qt compatibility layer first
from litebrowser.qt import QtWidgets  # noqa: E402
from litebrowser.ui.dialogs.quick_capture import QuickCaptureDialog  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["quick-capture-tests"])


def test_selected_text_is_prefilled_for_note_and_flashcard(tmp_path):
    dialog = QuickCaptureDialog(
        str(tmp_path),
        {"title": "Study page", "url": "https://example.test/lesson", "selected_text": "Key passage"},
    )
    note = dialog._forms["note"]
    assert note["title"].text() == "Study page"
    assert "Key passage" in note["content"].toPlainText()
    assert "https://example.test/lesson" in note["content"].toPlainText()

    dialog.cmb_kind.setCurrentIndex(dialog.cmb_kind.findData("flashcard"))
    card = dialog._forms["flashcard"]
    assert card["front"].toPlainText() == "Key passage"
    card["back"].setPlainText("The answer")
    dialog._save()
    assert dialog.capture_payload == {"kind": "flashcard", "front": "Key passage", "back": "The answer"}
    dialog.deleteLater()
    app.processEvents()


def test_capture_shows_which_active_research_workspace_will_receive_it(tmp_path):
    dialog = QuickCaptureDialog(
        str(tmp_path),
        {"research_workspace_title": "Chemistry field notes"},
    )
    labels = [label.text() for label in dialog.findChildren(QtWidgets.QLabel)]
    assert any("Chemistry field notes" in label and "link to research workspace" in label for label in labels)
    dialog.deleteLater()
    app.processEvents()


def test_link_capture_rejects_non_web_schemes_and_accepts_https(tmp_path):
    dialog = QuickCaptureDialog(str(tmp_path))
    dialog.cmb_kind.setCurrentIndex(dialog.cmb_kind.findData("link"))
    fields = dialog._forms["link"]
    fields["title"].setText("Example")
    fields["url"].setText("javascript:alert(1)")
    dialog._save()
    assert dialog.capture_payload is None
    assert "http:// or https://" in dialog.lbl_error.text()

    fields["url"].setText("https://example.test/article")
    dialog._save()
    assert dialog.capture_payload == {
        "kind": "link", "title": "Example", "url": "https://example.test/article"
    }
    dialog.deleteLater()
    app.processEvents()


def test_empty_note_task_and_flashcard_drafts_are_not_saved(tmp_path):
    dialog = QuickCaptureDialog(str(tmp_path))

    dialog._save()
    assert dialog.capture_payload is None
    assert "title" in dialog.lbl_error.text().lower()

    dialog.cmb_kind.setCurrentIndex(dialog.cmb_kind.findData("task"))
    dialog._save()
    assert dialog.capture_payload is None
    assert "task" in dialog.lbl_error.text().lower()

    dialog.cmb_kind.setCurrentIndex(dialog.cmb_kind.findData("flashcard"))
    dialog._save()
    assert dialog.capture_payload is None
    assert "front and back" in dialog.lbl_error.text().lower()
    dialog.deleteLater()
    app.processEvents()


def test_private_context_is_not_rendered_or_prefilled(tmp_path):
    dialog = QuickCaptureDialog(
        str(tmp_path),
        {"private": True, "title": "Private title", "url": "https://private.test", "selected_text": "secret"},
    )
    assert dialog._forms["note"]["title"].text() == ""
    assert dialog._forms["flashcard"]["front"].toPlainText() == ""
    labels = [label.text() for label in dialog.findChildren(QtWidgets.QLabel)]
    assert any("Private tab" in label for label in labels)
    assert not any("Private title" in label or "private.test" in label or "secret" in label for label in labels)
    dialog.deleteLater()
    app.processEvents()
