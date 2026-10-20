"""Small, review-first capture dialog for existing local Mei stores."""
from urllib.parse import urlsplit

from litebrowser.qt import QtCore, QtWidgets
from litebrowser.core import prefs
from litebrowser.ui import theme
from litebrowser.ui.dialogs.common import dialog_footer, primary_button


class QuickCaptureDialog(QtWidgets.QDialog):
    """Collect a note, task, saved link, or manual flashcard draft."""

    KINDS = (
        ("Note", "note"),
        ("Task", "task"),
        ("Saved link", "link"),
        ("Flashcard", "flashcard"),
    )

    def __init__(self, base_dir: str, context: dict | None = None, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.context = context if isinstance(context, dict) else {}
        self.capture_payload = None
        self.setWindowTitle("Quick capture")
        self.setMinimumWidth(440)
        self.setModal(True)
        self.setStyleSheet(theme.dialog_qss(prefs.resolved_auto_theme(base_dir), prefs.get_accent(base_dir)))

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        heading = QtWidgets.QLabel("Capture to your local workspace")
        heading.setObjectName("DialogTitle")
        layout.addWidget(heading)

        self.cmb_kind = QtWidgets.QComboBox()
        for label, key in self.KINDS:
            self.cmb_kind.addItem(label, key)
        self.cmb_kind.setAccessibleName("Capture destination")
        layout.addWidget(self.cmb_kind)

        private_context = bool(self.context.get("private"))
        title = "" if private_context else str(self.context.get("title") or "").strip()
        url = "" if private_context else str(self.context.get("url") or "").strip()
        selected = "" if private_context else str(self.context.get("selected_text") or "").strip()
        selected = selected[:4000]
        research_title = "" if private_context else str(self.context.get("research_workspace_title") or "").strip()[:120]
        if private_context:
            source_text = "Private tab — page details are not copied into a saved item."
        else:
            source_text = "From this page: " + (title or url) + ("\n" + url if title and url else "") if title or url else ""
        if research_title:
            source_text += ("\n" if source_text else "") + f"This capture will link to research workspace: {research_title}"
        if source_text:
            source = QtWidgets.QLabel(source_text)
            source.setObjectName("MutedLabel")
            source.setTextFormat(QtCore.Qt.PlainText)
            source.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            source.setWordWrap(True)
            layout.addWidget(source)

        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)
        self._forms = {}

        note = self._form_page()
        note_title = self._line("Title", title)
        note_category = self._line("Category", "Clippings" if selected else "General")
        note_body = self._text("Note content")
        if selected:
            note_body.setPlainText(f"> {selected}\n\nSource: {title or url}\n{url}".strip())
        self._add_field(note, "Title", note_title)
        self._add_field(note, "Category", note_category)
        self._add_field(note, "Content", note_body)
        self._forms["note"] = {"title": note_title, "category": note_category, "content": note_body}
        self.stack.addWidget(note)

        task = self._form_page()
        task_title = self._line("Task", title)
        task_notes = self._text("Notes (optional)")
        self._add_field(task, "Task", task_title)
        self._add_field(task, "Notes", task_notes)
        self._forms["task"] = {"title": task_title, "notes": task_notes}
        self.stack.addWidget(task)

        link = self._form_page()
        link_title = self._line("Title", title)
        link_url = self._line("URL", url)
        link_url.setPlaceholderText("https://example.com/article")
        self._add_field(link, "Title", link_title)
        self._add_field(link, "URL", link_url)
        self._forms["link"] = {"title": link_title, "url": link_url}
        self.stack.addWidget(link)

        flashcard = self._form_page()
        front = self._text("Front")
        front.setPlainText(selected)
        back = self._text("Back")
        self._add_field(flashcard, "Front", front)
        self._add_field(flashcard, "Back", back)
        self._forms["flashcard"] = {"front": front, "back": back}
        self.stack.addWidget(flashcard)

        self.lbl_error = QtWidgets.QLabel("")
        self.lbl_error.setObjectName("DangerLabel")
        self.lbl_error.setWordWrap(True)
        layout.addWidget(self.lbl_error)
        self.btn_save = primary_button("Save capture", "Save this item to the selected local workspace")
        self.btn_save.clicked.connect(self._save)
        dialog_footer(layout, primary=self.btn_save, close=self.reject)
        self.cmb_kind.currentIndexChanged.connect(self.stack.setCurrentIndex)

    @staticmethod
    def _form_page():
        page = QtWidgets.QWidget()
        page.setLayout(QtWidgets.QFormLayout())
        page.layout().setContentsMargins(0, 0, 0, 0)
        page.layout().setSpacing(8)
        return page

    @staticmethod
    def _line(accessible_name: str, value: str = ""):
        field = QtWidgets.QLineEdit(value)
        field.setAccessibleName(accessible_name)
        return field

    @staticmethod
    def _text(accessible_name: str):
        field = QtWidgets.QPlainTextEdit()
        field.setAccessibleName(accessible_name)
        field.setMaximumHeight(150)
        return field

    @staticmethod
    def _add_field(page, label: str, field):
        page.layout().addRow(label, field)

    def _save(self):
        kind = self.cmb_kind.currentData()
        fields = self._forms[kind]
        if kind == "note":
            payload = {
                "kind": kind,
                "title": fields["title"].text().strip(),
                "category": fields["category"].text().strip() or "General",
                "content": fields["content"].toPlainText(),
            }
            valid = bool(payload["title"])
            message = "Enter a title for this note."
        elif kind == "task":
            payload = {"kind": kind, "title": fields["title"].text().strip(), "notes": fields["notes"].toPlainText().strip()}
            valid = bool(payload["title"])
            message = "Enter a title for this task."
        elif kind == "link":
            payload = {"kind": kind, "title": fields["title"].text().strip(), "url": fields["url"].text().strip()}
            try:
                parsed = urlsplit(payload["url"])
                parsed.port  # Accessing this also rejects malformed/out-of-range ports.
                valid = (
                    parsed.scheme in ("http", "https")
                    and bool(parsed.hostname)
                    and parsed.username is None
                    and parsed.password is None
                )
            except ValueError:
                valid = False
            message = "Enter a valid http:// or https:// URL without embedded credentials."
            if valid and not payload["title"]:
                payload["title"] = payload["url"]
        else:
            payload = {"kind": kind, "front": fields["front"].toPlainText().strip(), "back": fields["back"].toPlainText().strip()}
            valid = bool(payload["front"] and payload["back"])
            message = "Enter both the front and back of the flashcard."

        if not valid:
            self.lbl_error.setText(message)
            return
        self.capture_payload = payload
        self.accept()
