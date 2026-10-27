import base64
import os
import time
from concurrent.futures import ThreadPoolExecutor
from html import escape as _html_escape

from PyQt5.QtCore import QBuffer, QIODevice, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from litebrowser.core import app_paths, app_version, prefs
from litebrowser.core import time_utils as _time_utils
from litebrowser.services import (
    ai_service,
    history_service,
    life_service,
    personal_service,
    tab_sets,
)
from litebrowser.ui import components, theme, win_titlebar


def _single_line_context_label(value, limit: int) -> str:
    """Keep page supplied labels from forging structure in the AI prompt."""
    return " ".join(str(value or "").split())[:limit]


# One prompt library feeds both the visible list and the empty-thread starters,
# so a starter can never promise a capability the workspace does not have.
_PROMPT_LIBRARY = (
    "Summarize this workspace",
    "Turn current page into a note",
    "Extract deadlines and tasks",
    "Build a study brief",
    "What changed in my recent saved pages?",
    "What should I focus on today?",
)
_STARTER_PROMPTS = (
    "Summarize this workspace",
    "What should I focus on today?",
    "What changed in my recent saved pages?",
)


def _html(value) -> str:
    return _html_escape(str(value or ""), quote=False)


def _answer_html(question: str, answer: str, provider_label: str, tokens: dict) -> str:
    """A quiet editorial answer: question, body, then provenance."""
    blocks = str(answer or "").replace("\r\n", "\n").split("\n\n")
    body = "".join(
        '<p style="margin:0 0 10px 0;">%s</p>' % _html(block).replace("\n", "<br>")
        for block in blocks
        if block.strip()
    ) or '<p style="margin:0 0 10px 0;">No answer returned.</p>'
    provider = (
        '<p style="margin:14px 0 0 0; color:%s; font-size:10px;">Provider: %s</p>'
        % (tokens["TEXT_MUTED"], _html(provider_label or "assistant"))
    )
    return (
        '<div style="font-family:%s; font-size:13px; color:%s;">'
        '<p style="margin:0 0 4px 0; color:%s; font-size:9px; font-weight:700; letter-spacing:1px;">YOU ASKED</p>'
        '<p style="margin:0 0 16px 0; color:%s; font-family:%s; font-size:19px; font-weight:600;">%s</p>'
        '<p style="margin:0 0 7px 0; color:%s; font-size:9px; font-weight:700; letter-spacing:1px;">ANSWER</p>'
        "%s%s</div>"
        % (
            tokens.get("FONT_UI", "Segoe UI"),
            tokens["TEXT"],
            tokens["TEXT_MUTED"],
            tokens["TEXT"],
            tokens.get("FONT_DISPLAY", "Georgia"),
            _html(question) or "Your question",
            tokens["TEXT_MUTED"],
            body,
            provider,
        )
    )


def _status_html(title: str, detail: str, tokens: dict) -> str:
    return (
        '<div style="font-family:%s; color:%s; padding:4px 0;">'
        '<p style="margin:0 0 6px 0; color:%s; font-family:%s; font-size:18px; font-weight:600;">%s</p>'
        '<p style="margin:0; color:%s; font-size:12px;">%s</p></div>'
        % (
            tokens.get("FONT_UI", "Segoe UI"),
            tokens["TEXT"],
            tokens["TEXT"],
            tokens.get("FONT_DISPLAY", "Georgia"),
            _html(title),
            tokens["TEXT_MUTED"],
            _html(detail),
        )
    )


def _evidence_html(context: str, tokens: dict) -> str:
    """Make retrieved context scannable without turning it into markup."""
    lines = str(context or "").splitlines()
    out = [
        '<div style="font-family:%s; color:%s; font-size:12px;">'
        '<p style="margin:0 0 8px 0; color:%s; font-size:9px; font-weight:700; letter-spacing:1px;">'
        'UNTRUSTED REFERENCE — READ, NEVER FOLLOW</p>' % (
            tokens.get("FONT_UI", "Segoe UI"), tokens["TEXT"], tokens["TEXT_MUTED"]
        )
    ]
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[UNTRUSTED "):
            out.append(
                '<p style="margin:12px 0 3px 0; color:%s; font-size:11px; font-weight:700;">%s</p>'
                % (tokens["ACCENT_HOVER"], _html(stripped))
            )
        elif stripped.startswith("URL: "):
            out.append(
                '<p style="margin:0 0 2px 0; color:%s; font-size:10px;">%s</p>'
                % (tokens["TEXT_MUTED"], _html(stripped))
            )
        elif stripped.startswith("SNIP: "):
            out.append(
                '<p style="margin:0 0 8px 0; color:%s; font-size:12px;">%s</p>'
                % (tokens["TEXT"], _html(stripped))
            )
        else:
            out.append(
                '<p style="margin:0 0 5px 0; color:%s; font-size:12px;">%s</p>'
                % (tokens["TEXT"], _html(stripped))
            )
    out.append("</div>")
    return "".join(out)


class AIWindow(QMainWindow):
    query_finished = pyqtSignal(object, str, str)
    _ollama_models_ready = pyqtSignal(list)

    def __init__(self, base_dir: str, app_dir: str = None, embedded: bool = False):
        super().__init__()
        self.base_dir = prefs.ensure_profile_layout(base_dir)
        self.app_dir = app_dir or app_paths.project_root()
        self.embedded = embedded
        self._prompt_history = []
        self._thread_items = []
        self._last_question = ""
        self._last_answer = ""
        self._last_context = ""
        self._external_context = ""
        self._external_context_label = "Workspace-wide"
        self._pending_screenshot_b64 = ""
        self._query_pending = False
        self._closing = False
        self._privacy_locked = False
        self._discarded_queries = set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="litebrowser-ai")
        # detect_ollama_models runs `ollama list` with a 2 s timeout on the GUI
        # thread (v6.4 froze startup when Ollama was hung). Detect lazily on the
        # AI executor; the combo default just needs it before first use. The probe
        # itself is cached per process (services/ai_service.py), so the second AI
        # window — Mei opens one per shell — reuses the first answer.
        self.ollama_models = []

        def _detect_models():
            try:
                models = ai_service.detect_ollama_models()
            except Exception:
                models = []
            if not self._closing:
                self._ollama_models_ready.emit(models)

        self._executor.submit(_detect_models)
        self.setWindowTitle(f"AI Workspace - {app_version.APP_NAME}")
        self.setWindowIcon(QIcon(os.path.join(self.app_dir, "icon.png")))
        self.resize(1180, 780)
        self.setMinimumSize(0 if embedded else 880, 0 if embedded else 620)
        if not self.embedded:
            win_titlebar.apply_dark_titlebar(self, enabled=True)

        root = QWidget()
        root.setObjectName("AIWorkspace")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # The nook opens like a page: a mark, a serif line, one deck sentence.
        self.masthead = components.masthead(
            "AI · Reading nook",
            "A companion at the table",
            "Ask across notes, tasks, saved pages and open tabs. Every piece of context is opt-in and visible below.",
        )
        layout.addWidget(self.masthead)

        hero = QFrame()
        hero.setObjectName("AIComposer")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(7)

        # The composer owns the page. Provider configuration stays one quiet
        # step away, beside the live provider badge rather than above the ask.
        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(components.eyebrow("Ask"))
        top_row.addStretch(1)
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setObjectName("AIStatus")
        self.lbl_status.setProperty("state", "ready")
        self.lbl_status.setAccessibleName("Assistant status")
        top_row.addWidget(self.lbl_status)
        self.lbl_provider = components.badge("Provider: RAG · local index")
        top_row.addWidget(self.lbl_provider)
        self.btn_ai_setup = components.chip("Provider setup ▾", checkable=True, checked=False)
        self.btn_ai_setup.setToolTip("Provider, model and API key settings")
        self.btn_ai_setup.setAccessibleName("Provider setup")
        top_row.addWidget(self.btn_ai_setup)
        hero_layout.addLayout(top_row)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)
        self.cmb_provider = QComboBox()
        self.cmb_provider.addItem("RAG · local index", "rag")
        self.cmb_provider.addItem("OpenRouter · remote", "openrouter")
        self.cmb_provider.addItem("Ollama · local", "ollama")
        self.cmb_provider.addItem("llama.cpp server", "llama_cpp")
        self.cmb_provider.setAccessibleName("AI provider")
        settings_row.addWidget(self.cmb_provider)
        self.ed_model = QLineEdit()
        self.ed_model.setPlaceholderText("Model name")
        self.ed_model.setMinimumWidth(140)
        settings_row.addWidget(self.ed_model)
        self.ed_api_key = QLineEdit()
        self.ed_api_key.setPlaceholderText("OpenRouter API key")
        self.ed_api_key.setEchoMode(QLineEdit.Password)
        self.ed_api_key.setMinimumWidth(150)
        self.ed_api_key.setAccessibleName("OpenRouter API key")
        settings_row.addWidget(self.ed_api_key, 1)
        self.btn_save_settings = QPushButton("Save settings")
        self.btn_save_settings.setObjectName("GhostButton")
        settings_row.addWidget(self.btn_save_settings)
        # Provider configuration is real capability, not the main story: it
        # stays one chip away instead of occupying the top of the page.
        self._setup_panel = QWidget()
        setup_panel_layout = QVBoxLayout(self._setup_panel)
        setup_panel_layout.setContentsMargins(0, 0, 0, 0)
        setup_panel_layout.setSpacing(7)
        setup_panel_layout.addWidget(components.eyebrow("Provider & model"))
        setup_hint = QLabel(
            "API keys stay masked here. Remote providers send the context you enable below."
        )
        setup_hint.setObjectName("AIHint")
        setup_hint.setWordWrap(True)
        setup_panel_layout.addWidget(setup_hint)
        setup_panel_layout.addLayout(settings_row)
        # Index and vision state describe the provider, not the question; they
        # belong with the other setup facts instead of competing with consent.
        index_row = QHBoxLayout()
        index_row.setSpacing(8)
        self.lbl_index = components.badge("Index: —")
        self.lbl_vision = components.badge("Vision: none", "muted")
        index_row.addWidget(self.lbl_index)
        index_row.addWidget(self.lbl_vision)
        index_row.addStretch(1)
        setup_panel_layout.addLayout(index_row)
        # Capture and index rebuilding are setup tools, not part of the ask
        # itself. Keeping them here means the composer stays a composer.
        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        self.btn_capture_screenshot = QPushButton("Capture tab")
        self.btn_capture_screenshot.setObjectName("QuietButton")
        self.btn_capture_screenshot.setToolTip(
            "Capture the visible current browser tab for the next local Ollama vision request"
        )
        self.btn_reindex = QPushButton("Rebuild index")
        self.btn_reindex.setObjectName("QuietButton")
        self.btn_reindex.setToolTip("Rebuild the local workspace index used by RAG")
        tools_row.addWidget(self.btn_capture_screenshot)
        tools_row.addWidget(self.btn_reindex)
        tools_row.addStretch(1)
        setup_panel_layout.addLayout(tools_row)
        self.btn_ai_setup.toggled.connect(self._setup_panel.setVisible)
        self._setup_panel.hide()

        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)
        self.ed_question = QLineEdit()
        self.ed_question.setPlaceholderText(
            "Ask about the current page, your notes, tasks, saved pages, or the whole workspace..."
        )
        self.ed_question.setObjectName("AIQuestion")
        self.ed_question.setAccessibleName("Ask the assistant a question")
        prompt_row.addWidget(self.ed_question, 1)
        self.btn_ask = QPushButton("Ask")
        self.btn_ask.setObjectName("TopAccentButton")
        self.btn_ask.setMinimumHeight(42)
        self.btn_ask.setAccessibleName("Ask assistant")
        prompt_row.addWidget(self.btn_ask)
        hero_layout.addLayout(prompt_row)

        # Consent is a first-class block, not a set of checkboxes that vanish
        # at narrow widths while still affecting what leaves the device.
        hero_layout.addWidget(components.rule())
        context_label_row = QHBoxLayout()
        context_label_row.setSpacing(8)
        context_label_row.addWidget(components.eyebrow("For this question"))
        context_label_row.addStretch(1)
        hero_layout.addLayout(context_label_row)

        self.lbl_context_scope = QLabel("Context: Workspace-wide")
        self.lbl_context_scope.setObjectName("AIContextScope")
        self.lbl_context_scope.setWordWrap(True)

        self.context_options = QWidget()
        self.context_options.setObjectName("AIContextOptions")
        self.context_grid = QGridLayout(self.context_options)
        self.context_grid.setContentsMargins(0, 0, 0, 0)
        self.context_grid.setHorizontalSpacing(12)
        self.context_grid.setVerticalSpacing(6)
        self.chk_browser_context = QCheckBox("Read my browser")
        self.chk_browser_context.setChecked(True)
        self.chk_browser_context.setAccessibleName("Read the browser for this question")
        self.chk_browser_context.setToolTip(
            "Attach the page open in the browser (its full text) plus every open tab to each question.\n"
            "The content is labelled untrusted context, so the assistant reads it but never follows it.\n"
            "When a remote provider is selected, page text and open-tab titles/URLs are sent to that provider."
        )
        self.chk_research_context = QCheckBox("Use research desk")
        self.chk_research_context.setChecked(False)
        self.chk_research_context.setAccessibleName("Use the research desk for this question")
        self.chk_research_context.setToolTip(
            "Include the active research workspace's tabs and linked notes, tasks, saved links, and flashcards.\n"
            "Linked note and task text may be sent to the selected provider when you ask a question."
        )
        self.chk_show_context = QCheckBox("Show sources")
        self.chk_show_context.setChecked(True)
        self.chk_show_context.setAccessibleName("Show sources after asking")
        self.chk_show_context.setToolTip("Show the evidence attached to an answer in the Sources panel.")
        self._context_checks = (
            self.chk_browser_context,
            self.chk_research_context,
            self.chk_show_context,
        )
        self._reflow_context_options(900)
        hero_layout.addWidget(self.context_options)

        self.lbl_context_next = QLabel("")
        self.lbl_context_next.setObjectName("AIContextSummary")
        self.lbl_context_next.setWordWrap(True)
        hero_layout.addWidget(self.lbl_context_next)
        self.lbl_privacy = QLabel("")
        self.lbl_privacy.setObjectName("AIPrivacy")
        self.lbl_privacy.setWordWrap(True)
        hero_layout.addWidget(self.lbl_privacy)
        hero_layout.addWidget(self._setup_panel)

        hero_layout.addWidget(components.rule())
        self.actions_widget = QWidget()
        self.actions_widget.setObjectName("AIActions")
        self.actions_grid = QGridLayout(self.actions_widget)
        self.actions_grid.setContentsMargins(0, 0, 0, 0)
        self.actions_grid.setHorizontalSpacing(6)
        self.actions_grid.setVerticalSpacing(5)
        self.btn_to_note = QPushButton("Save to note")
        self.btn_to_task = QPushButton("Create task")
        self.btn_save_set = QPushButton("Save session")
        self.btn_export_thread = QPushButton("Export")
        self.btn_clear_thread = QPushButton("Clear thread")
        for _action in (self.btn_to_note, self.btn_to_task):
            _action.setObjectName("GhostButton")
        for _action in (self.btn_save_set, self.btn_export_thread):
            _action.setObjectName("QuietButton")
        self.btn_clear_thread.setObjectName("DangerButton")
        self.btn_to_note.setToolTip("Save the current answer as a note")
        self.btn_to_task.setToolTip("Create a task from the current answer")
        self.btn_save_set.setToolTip("Save the prompt history as an AI session")
        self.btn_export_thread.setToolTip("Export this thread as Markdown or text")
        self.btn_clear_thread.setToolTip("Clear this visible thread; saved sessions remain in Sessions")
        self._action_buttons = (
            self.btn_to_note,
            self.btn_to_task,
            self.btn_save_set,
            self.btn_export_thread,
            self.btn_clear_thread,
        )
        self._reflow_action_row(900)
        hero_layout.addWidget(self.actions_widget)

        layout.addWidget(hero)

        body = QSplitter(Qt.Horizontal)
        body.setObjectName("AIBody")
        layout.addWidget(body, 1)

        left_card = QFrame()
        left_card.setObjectName("AISide")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(6)
        self.history_header = components.section_header(
            "Sessions", "Select an earlier answer", kicker="Earlier"
        )
        left_layout.addWidget(self.history_header)
        self.history_stack = QStackedWidget()
        self.history_empty = components.empty_state(
            "No questions yet",
            "Questions you ask will collect here, newest first.",
        )
        self.history_list = QListWidget()
        self.history_list.setObjectName("CafeList")
        self.history_list.setAccessibleName("Earlier AI questions")
        self.history_stack.addWidget(self.history_empty)
        self.history_stack.addWidget(self.history_list)
        left_layout.addWidget(self.history_stack, 1)
        body.addWidget(left_card)

        center_card = QFrame()
        center_card.setObjectName("SectionCard")
        center_layout = QVBoxLayout(center_card)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(6)
        center_layout.addWidget(
            components.section_header(
                "The thread", "Answers, with their sources attached", kicker="Conversation"
            )
        )
        self.thread_stack = QStackedWidget()
        self.thread_empty = self._build_thread_empty()
        self.txt_answer = QTextEdit()
        self.txt_answer.setObjectName("AIThread")
        self.txt_answer.setReadOnly(True)
        self.txt_answer.setAccessibleName("Conversation thread")
        self.txt_answer.document().setDocumentMargin(18)
        self.thread_stack.addWidget(self.thread_empty)
        self.thread_stack.addWidget(self.txt_answer)
        center_layout.addWidget(self.thread_stack, 1)
        body.addWidget(center_card)

        right_card = QFrame()
        right_card.setObjectName("AISide")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(6)
        right_layout.addWidget(
            components.section_header("Sources", "What the answer actually read", kicker="Evidence")
        )
        right_layout.addWidget(self.lbl_context_scope)
        self.context_stack = QStackedWidget()
        self.context_empty = self._build_evidence_empty()
        self.txt_context = QTextEdit()
        self.txt_context.setObjectName("AIEvidence")
        self.txt_context.setReadOnly(True)
        self.txt_context.setAccessibleName("Answer sources and context")
        self.txt_context.document().setDocumentMargin(12)
        self.context_stack.addWidget(self.context_empty)
        self.context_stack.addWidget(self.txt_context)
        right_layout.addWidget(self.context_stack, 3)
        right_layout.addWidget(
            components.section_header("Starter prompts", "Double-click to fill the composer", kicker="Try")
        )
        self.prompt_list = QListWidget()
        self.prompt_list.setObjectName("CafeList")
        self.prompt_list.setAccessibleName("Starter prompts")
        self.prompt_list.setToolTip("Double-click a prompt to put it in the composer")
        self.prompt_list.setMinimumHeight(70)
        self.prompt_list.setMaximumHeight(170)
        for text in _PROMPT_LIBRARY:
            self.prompt_list.addItem(text)
        right_layout.addWidget(self.prompt_list, 1)
        body.addWidget(right_card)
        body.setChildrenCollapsible(True)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([180, 760, 250])

        self.setStyleSheet(theme.main_qss(prefs.resolved_auto_theme(self.base_dir), prefs.get_accent(self.base_dir)))
        self.btn_reindex.clicked.connect(self._reindex)
        self.btn_capture_screenshot.clicked.connect(self._capture_current_tab)
        self.btn_ask.clicked.connect(self._ask)
        self.ed_question.returnPressed.connect(self._ask)
        self.cmb_provider.currentIndexChanged.connect(self._on_provider_change)
        self.btn_save_set.clicked.connect(self.save_current_set)
        self.btn_to_note.clicked.connect(self.save_answer_to_note)
        self.btn_to_task.clicked.connect(self.create_task_from_answer)
        self.btn_export_thread.clicked.connect(self._export_thread)
        self.btn_clear_thread.clicked.connect(self._clear_thread)
        self.prompt_list.itemDoubleClicked.connect(self._apply_prompt_template)
        self.history_list.itemDoubleClicked.connect(self._load_history_item)
        self.btn_save_settings.clicked.connect(self._save_settings_with_notice)
        self.chk_show_context.toggled.connect(self._on_show_sources_toggled)
        self.chk_browser_context.toggled.connect(lambda _checked: self._update_context_summary())
        self.chk_research_context.toggled.connect(lambda _checked: self._update_context_summary())
        self.query_finished.connect(self._finish_assistant_query)
        self._ollama_models_ready.connect(self._on_ollama_models_ready)
        self._load_settings()
        self._refresh_index_label()
        self._update_context_summary()
        self._show_thread_empty()
        self._show_context_empty()
        self._apply_compact_layout()
        # Make every label selectable and every button copyable via right-click.
        from litebrowser.ui.textselect import enable_text_selection

        enable_text_selection(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(0, self.width())
        bucket = 820 if width < 820 else 940 if width < 940 else 1180 if width < 1180 else 1 << 30
        if bucket != getattr(self, "_compact_bucket", None):
            self._compact_bucket = bucket
            self._apply_compact_layout()
        # These reflow inside a bucket too, so a slow drag never clips a
        # consent label or pushes an action off the composer.
        self._reflow_context_options(width)
        self._reflow_action_row(width)

    def _apply_compact_layout(self):
        width = max(0, self.width())
        body = self.findChild(QSplitter)
        # The masthead is the page's one serif voice; below 900px the title and
        # deck are already fully read, so drop the deck rather than let it eat
        # the thread's height.
        deck = getattr(getattr(self, "masthead", None), "_masthead_deck", None)
        if deck is not None:
            deck.setVisible(width >= 900)
        history_sub = getattr(getattr(self, "history_header", None), "_subtitle", None)
        if history_sub is not None:
            history_sub.setVisible(width >= 900)
        if body:
            if width < 560:
                left, right = 0, 176
            elif width < 760:
                left, right = 0, 176
            elif width < 940:
                left, right = 118, 188
            elif width < 1180:
                left, right = 150, 210
            else:
                left, right = 180, 250
            # Keep the evidence and conversation panes reachable at every
            # width. History may collapse first on a narrow desk, but its
            # splitter handle stays draggable.
            center = max(240, width - left - right - 24)
            body.setSizes([left, center, right])
            body.setCollapsible(0, True)
            body.setCollapsible(1, False)
            body.setCollapsible(2, False)
        self._reflow_context_options(width)
        self._reflow_action_row(width)
        self._update_context_summary()

    def _reflow_context_options(self, width):
        if not hasattr(self, "context_grid"):
            return
        # Three short consent labels fit one calm row on a desktop desk; a
        # mid-width composer pairs them, and a genuinely narrow one stacks.
        columns = 1 if width < 560 else 2 if width < 1000 else 3
        if getattr(self, "_context_columns", None) == columns:
            return
        while self.context_grid.count():
            self.context_grid.takeAt(0)
        for index, widget in enumerate(getattr(self, "_context_checks", ())):
            self.context_grid.addWidget(widget, index // columns, index % columns)
        for column in range(3):
            self.context_grid.setColumnStretch(column, 1 if column < columns else 0)
        self._context_columns = columns

    def _reflow_action_row(self, width):
        if not hasattr(self, "actions_grid"):
            return
        # Five action buttons on one row need roughly 800px of their own; below
        # that, break the thread verbs into two calm rows instead of clipping.
        compact = width < 900
        if getattr(self, "_actions_compact", None) == compact:
            return
        while self.actions_grid.count():
            self.actions_grid.takeAt(0)
        for column in range(6):
            self.actions_grid.setColumnStretch(column, 0)
        if compact:
            self.actions_grid.addWidget(self.btn_to_note, 0, 0)
            self.actions_grid.addWidget(self.btn_to_task, 0, 1)
            self.actions_grid.addWidget(self.btn_save_set, 1, 0)
            self.actions_grid.addWidget(self.btn_export_thread, 1, 1)
            self.actions_grid.addWidget(self.btn_clear_thread, 1, 2)
            self.actions_grid.setColumnStretch(2, 1)
        else:
            for column, button in enumerate(
                (
                    self.btn_to_note,
                    self.btn_to_task,
                    None,
                    self.btn_save_set,
                    self.btn_export_thread,
                    self.btn_clear_thread,
                )
            ):
                if button is not None:
                    self.actions_grid.addWidget(button, 0, column)
            self.actions_grid.setColumnStretch(2, 1)
        self._actions_compact = compact

    def _build_thread_empty(self):
        card = QFrame()
        card.setObjectName("AIEmptyState")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignCenter)

        glyph = QLabel("✦")
        glyph.setObjectName("EmptyGlyph")
        glyph.setAlignment(Qt.AlignCenter)
        layout.addWidget(glyph)
        title = QLabel("A quiet place to ask")
        title.setObjectName("AIEmptyTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)
        hint = QLabel(
            "Answers and their sources collect here. Start above, or try a starter."
        )
        hint.setObjectName("AIEmptyHint")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        starters = []
        for prompt in _STARTER_PROMPTS:
            button = QPushButton(prompt)
            button.setObjectName("AIStarter")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, text=prompt: self._use_prompt(text))
            starters.append(button)
        layout.addSpacing(4)
        layout.addWidget(
            components.ResponsiveGrid(starters, minimum_width=150, maximum_columns=2)
        )
        return card

    def _build_evidence_empty(self):
        card = QFrame()
        card.setObjectName("AIEvidenceEmpty")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        layout.addStretch(1)
        glyph = QLabel("✦")
        glyph.setObjectName("EmptyGlyph")
        glyph.setAlignment(Qt.AlignCenter)
        layout.addWidget(glyph)
        self._context_empty_title = QLabel("No sources yet")
        self._context_empty_title.setObjectName("AIEmptyTitle")
        self._context_empty_title.setAlignment(Qt.AlignCenter)
        self._context_empty_title.setWordWrap(True)
        layout.addWidget(self._context_empty_title)
        self._context_empty_hint = QLabel(
            "After you ask, the notes, pages and tabs the assistant read appear here. "
            "Nothing is sent until you submit."
        )
        self._context_empty_hint.setObjectName("AIEmptyHint")
        self._context_empty_hint.setAlignment(Qt.AlignCenter)
        self._context_empty_hint.setWordWrap(True)
        layout.addWidget(self._context_empty_hint)
        layout.addStretch(1)
        return card

    def _show_thread_empty(self):
        self.thread_stack.setCurrentWidget(self.thread_empty)

    def _show_thread_answer(self):
        self.thread_stack.setCurrentWidget(self.txt_answer)

    def _show_context_error(self, message):
        self._context_empty_title.setText("No sources collected")
        self._context_empty_hint.setText(message or "The request failed before sources were collected.")
        self.context_stack.setCurrentWidget(self.context_empty)

    def _show_context_empty(self, hidden=False):
        if hidden:
            self._context_empty_title.setText("Sources hidden")
            self._context_empty_hint.setText(
                "Turn on Show sources in the composer to inspect the evidence attached to this thread."
            )
        else:
            self._context_empty_title.setText("No sources yet")
            self._context_empty_hint.setText(
                "After you ask, the notes, pages and tabs the assistant read will appear here. "
                "Nothing is sent until you submit a question."
            )
        self.context_stack.setCurrentWidget(self.context_empty)

    def _set_status(self, text, state="ready"):
        self.lbl_status.setText(text)
        self.lbl_status.setProperty("state", state)
        style = self.lbl_status.style()
        style.unpolish(self.lbl_status)
        style.polish(self.lbl_status)

    def _tokens(self):
        return theme.palette(base_dir=self.base_dir)

    def _render_answer(self, question, answer, provider_label=""):
        self.txt_answer.setHtml(_answer_html(question, answer, provider_label, self._tokens()))
        self._show_thread_answer()

    def _render_loading(self, provider_name, dots=1):
        detail = "Gathering workspace context and sources." + (" " + "•" * (dots or 1))
        self.txt_answer.setHtml(
            _status_html(f"Thinking with {provider_name}", detail, self._tokens())
        )
        self._show_thread_answer()

    def _render_error(self, message):
        self.txt_answer.setHtml(
            _status_html(
                "The assistant could not answer",
                message or "Check the provider settings and try again.",
                self._tokens(),
            )
        )
        self._show_thread_answer()

    def _update_context_summary(self):
        if not hasattr(self, "lbl_context_next"):
            return
        parts = ["workspace index"]
        if self.chk_browser_context.isChecked():
            parts.append("browser page + open tabs")
        if self.chk_research_context.isChecked():
            parts.append("research desk")
        text = "Next question includes " + ", ".join(parts[:-1]) + (
            " and " if len(parts) > 1 else ""
        ) + parts[-1] + "."
        self.lbl_context_next.setText(text)
        self._update_provider_privacy()

    def _update_provider_privacy(self):
        if not hasattr(self, "lbl_privacy"):
            return
        provider = self.cmb_provider.currentData()
        self.lbl_provider.setText("Provider: " + (self.cmb_provider.currentText() or "—"))
        if provider == "openrouter":
            text = (
                "Remote provider: page text, open-tab titles/URLs and any opted-in research text "
                "may be sent to OpenRouter."
            )
            remote = True
        elif provider == "llama_cpp":
            text = (
                "Server provider: context is sent to the llama.cpp URL in Provider setup. "
                "Use a loopback URL to keep it on this device."
            )
            remote = True
        elif provider == "ollama":
            text = "Local processing: this question stays on this device through Ollama at 127.0.0.1."
            remote = False
        else:
            text = "Local index only: context is read on this device; no remote model is called."
            remote = False
        self.lbl_privacy.setText(text)
        self.lbl_privacy.setProperty("remote", remote)
        style = self.lbl_privacy.style()
        style.unpolish(self.lbl_privacy)
        style.polish(self.lbl_privacy)

    def _use_prompt(self, prompt):
        self.ed_question.setText(prompt)
        self.ed_question.setFocus()

    def _load_settings(self):
        data = prefs.load_ai_settings(self.base_dir)
        idx = self.cmb_provider.findData(data.get("provider", "rag"))
        if idx >= 0:
            self.cmb_provider.setCurrentIndex(idx)
        self.ed_api_key.setText(data.get("openrouter_api_key", ""))
        self._refresh_model_value()
        self.chk_show_context.setChecked(bool(data.get("show_sources", True)))
        self.chk_browser_context.setChecked(bool(data.get("read_browser", True)))
        self.chk_research_context.setChecked(bool(data.get("read_research", False)))
        self._on_provider_change()

    def _on_ollama_models_ready(self, models):
        """Background probe finished: fill the model field if still on the
        default and the user has not chosen a model yet."""
        self.ollama_models = list(models or [])
        settings = prefs.load_ai_settings(self.base_dir)
        if self.cmb_provider.currentData() == "ollama" and not (settings.get("ollama_model") or "").strip():
            if self.ollama_models:
                self.ed_model.setText(self.ollama_models[0])

    def _refresh_model_value(self):
        settings = prefs.load_ai_settings(self.base_dir)
        provider = self.cmb_provider.currentData()
        if provider == "openrouter":
            self.ed_model.setText(settings.get("openrouter_model", "openai/gpt-4o-mini"))
        elif provider == "ollama":
            self.ed_model.setText(settings.get("ollama_model", self.ollama_models[0] if self.ollama_models else ""))
        elif provider == "llama_cpp":
            self.ed_model.setText(settings.get("llama_cpp_url", "http://127.0.0.1:8080/completion"))
        else:
            self.ed_model.setText("")

    def _collect_settings_payload(self):
        provider = self.cmb_provider.currentData()
        payload = {
            "provider": provider,
            "openrouter_api_key": self.ed_api_key.text().strip(),
            "show_sources": self.chk_show_context.isChecked(),
            "read_browser": self.chk_browser_context.isChecked(),
            "read_research": self.chk_research_context.isChecked(),
        }
        if provider == "openrouter":
            payload["openrouter_model"] = self.ed_model.text().strip() or "openai/gpt-4o-mini"
        elif provider == "ollama":
            payload["ollama_model"] = self.ed_model.text().strip()
        elif provider == "llama_cpp":
            payload["llama_cpp_url"] = self.ed_model.text().strip() or "http://127.0.0.1:8080/completion"
        return payload

    def _research_context_for_ask(self):
        if not self.chk_research_context.isChecked():
            return None
        try:
            from litebrowser.services import tab_sets

            return tab_sets.build_research_context(self.base_dir)
        except (OSError, ValueError, RuntimeError):
            return None

    def _save_settings(self):
        from litebrowser.core import secret_store

        try:
            prefs.save_ai_settings(self.base_dir, self._collect_settings_payload())
        except secret_store.SecretStorageError as exc:
            QMessageBox.warning(
                self,
                "AI Assistant",
                "The API key could not be protected on this device, so the previous key "
                f"and settings were kept. Details: {exc}",
            )
            return False
        return True

    def _save_settings_with_notice(self):
        if not self._save_settings():
            return
        QMessageBox.information(self, "AI Assistant", "AI provider settings saved.")

    def _on_provider_change(self):
        provider = self.cmb_provider.currentData()
        if provider != "ollama" and self._pending_screenshot_b64:
            # A screenshot is valid only for the local Ollama vision path.
            # Discard it when the provider changes instead of silently losing
            # the user's capture on the next request.
            self._pending_screenshot_b64 = ""
            self.lbl_vision.setText("Vision: none")
        self.ed_api_key.setVisible(provider == "openrouter")
        self.btn_capture_screenshot.setEnabled(provider == "ollama")
        self.btn_capture_screenshot.setToolTip(
            "Capture the visible tab for local Ollama vision"
            if provider == "ollama"
            else "Select Ollama · local to enable screenshot vision"
        )
        self._refresh_model_value()
        self._update_provider_privacy()
        if provider == "rag":
            self.ed_model.setPlaceholderText("No remote model needed")
            self.ed_model.setEnabled(False)
        elif provider == "openrouter":
            self.ed_model.setPlaceholderText("Example: openai/gpt-4o-mini")
            self.ed_model.setEnabled(True)
        elif provider == "ollama":
            self.ed_model.setPlaceholderText("Ollama model name")
            self.ed_model.setEnabled(True)
        else:
            self.ed_model.setPlaceholderText("llama.cpp completion URL")
            self.ed_model.setEnabled(True)

    def _refresh_index_label(self):
        data = ai_service.load_index(self.base_dir)
        self.lbl_index.setText(f"Index: {len(data.get('docs', []))} docs")
        self.lbl_index.setToolTip(
            f"Local index updated {_format_ts(int(data.get('built_at', 0) or 0))}"
        )

    def _reindex(self):
        data = ai_service.rebuild_index(self.base_dir)
        self._refresh_index_label()
        QMessageBox.information(self, "AI Assistant", f"Rebuilt index with {len(data.get('docs', []))} docs.")

    def _apply_prompt_template(self, item: QListWidgetItem):
        self._use_prompt(item.text())

    def _append_history_item(
        self, question: str, answer: str, context_label: str, provider_label: str = ""
    ):
        payload = {
            "question": question,
            "answer": answer,
            "context_label": context_label,
            "context": self._last_context,
            "provider": provider_label,
        }
        self._thread_items.insert(0, payload)
        self._thread_items = self._thread_items[:24]
        self.history_list.clear()
        for entry in self._thread_items:
            row = QListWidgetItem(f"{entry['question']}\n{entry['context_label']}")
            row.setData(Qt.UserRole, entry)
            self.history_list.addItem(row)
        self.history_stack.setCurrentWidget(self.history_list)

    def _load_history_item(self, item: QListWidgetItem):
        payload = item.data(Qt.UserRole) or {}
        self.ed_question.setText(payload.get("question", ""))
        # Loading an earlier answer is also selecting it as the save/export
        # target. Without these assignments the thread actions still pointed at
        # whichever answer happened to be last, which is a silent data bug.
        self._last_question = payload.get("question", "")
        self._last_answer = payload.get("answer", "")
        self._last_context = payload.get("context", "")
        self._render_answer(
            self._last_question, self._last_answer, payload.get("provider", "")
        )
        self._render_source_text()
        self.lbl_context_scope.setText(payload.get("context_label", "Context: Workspace-wide"))
        self._set_status("Earlier answer", "ready")

    def _render_source_text(self):
        """Keep the evidence pane consistent with the show-sources choice."""
        if not self._last_context:
            self.txt_context.clear()
            self._show_context_empty()
        elif self.chk_show_context.isChecked():
            self.txt_context.setHtml(_evidence_html(self._last_context, self._tokens()))
            self.context_stack.setCurrentWidget(self.txt_context)
        else:
            # Clear the document as well as hiding it: a source title must not
            # survive behind a stack when the user disabled source display.
            self.txt_context.clear()
            self._show_context_empty(hidden=True)

    def _show_context_preview(self, context):
        if not context:
            self._show_context_empty()
        elif self.chk_show_context.isChecked():
            self.txt_context.setHtml(_evidence_html(context, self._tokens()))
            self.context_stack.setCurrentWidget(self.txt_context)
        else:
            self._show_context_empty(hidden=True)

    def _on_show_sources_toggled(self, _checked):
        # The checkbox used to take effect only on the next answer, leaving the
        # previous answer's evidence visible after the user asked to hide it.
        self._render_source_text()

    def _ask(self):
        question = (self.ed_question.text() or "").strip()
        if not question:
            self._set_status("Type a question to begin", "ready")
            self.ed_question.setFocus()
            return
        # Manual asks must not silently reuse the context injected by an older
        # "Ask AI about this note" — that leaked stale note/site text into
        # unrelated questions (v6.4 bug). One-shot context only.
        context_label, context = self._external_context_label, self._external_context
        self._external_context_label = "Workspace-wide"
        self._external_context = ""
        research = self._research_context_for_ask()
        if research:
            context = "\n\n".join(part for part in (context, research.get("text", "")) if part)
            context_label = (
                f"{context_label} + research: {research['title']}"
                if context_label != "Workspace-wide"
                else f"Research: {research['title']}"
            )
            self.lbl_context_scope.setText(
                f"Context: research desk “{research['title']}” · {self.cmb_provider.currentText()}"
            )
            self._show_context_preview(context)
        if self.chk_browser_context.isChecked() and (
            context_label == "Workspace-wide" or research is not None
        ):
            self._ask_with_browser(question, context, context_label)
            return
        self.run_assistant_query(question, context_label, context)

    def _host_browser_page(self):
        """The shell's browser workspace (tab list included), if this pane is embedded."""
        current = self.parentWidget()
        while current is not None:
            browser_page = getattr(current, "browser_page", None)
            if browser_page is not None and hasattr(browser_page, "get_current_tab_state"):
                return browser_page
            current = current.parentWidget()
        return None

    def _browser_tab_lines(self) -> list[str]:
        """Open tabs as context lines: the assistant should see the session, not one page."""
        page = self._host_browser_page()
        if page is None:
            return []
        try:
            tabs = page.get_current_tab_state() or []
        except Exception:
            return []
        lines = []
        for tab in tabs[:20]:
            if not isinstance(tab, dict):
                continue
            title = _single_line_context_label(tab.get("title"), 120)
            url = _single_line_context_label(tab.get("url"), 200)
            if not url:
                continue
            marker = "* " if tab.get("active") or tab.get("current") else "- "
            lines.append(f"{marker}{title or url} — {url}")
        return lines

    def _ask_with_browser(
        self, question: str, extra_context: str = "", context_label: str = "Workspace-wide"
    ):
        """Attach the *visible text* of the page being read, plus every open tab.

        The read happens in the page (JavaScript innerText), so the assistant is
        looking at what the user is looking at rather than at a cached title.
        """
        browser = self._host_browser()
        if browser is None or browser.page() is None:
            self.run_assistant_query(question, context_label, extra_context)
            return
        try:
            profile = browser.page().profile()
            if profile is None or profile.isOffTheRecord():
                self.lbl_context_scope.setText("Context: private page excluded")
                self.run_assistant_query(
                    question, context_label + " (private page excluded)", extra_context
                )
                return
        except Exception:
            # An unknown profile is treated as private; never send a page whose
            # isolation state cannot be verified.
            self.lbl_context_scope.setText("Context: page privacy could not be verified")
            self.run_assistant_query(
                question, context_label + " (page privacy unverified)", extra_context
            )
            return
        tabs = self._browser_tab_lines()
        self.lbl_context_scope.setText("Context: reading the browser…")

        def _on_text(text):
            try:
                title = _single_line_context_label(
                    browser.title() or browser.url().toString() or "Current page", 200
                )
                url = _single_line_context_label(browser.url().toString(), 500)
            except RuntimeError:
                # The tab (or the pane) went away while the page was answering.
                return
            page_text = (text or "").strip()
            parts = [extra_context.strip()] if extra_context.strip() else []
            parts.append(f"[Page open in browser: {title} — {url} (full text)]\n{page_text[:9000]}")
            if tabs:
                parts.append("[Open tabs in this window]\n" + "\n".join(tabs))
            if not page_text and not tabs:
                self.run_assistant_query(question, context_label, extra_context)
                return
            label = "Browser page + open tabs"
            if "[Untrusted local research workspace:" in extra_context:
                label += " + research"
            elif context_label != "Workspace-wide":
                label += " + " + context_label
            self.run_assistant_query(question, label, "\n\n".join(parts))

        try:
            browser.page().runJavaScript(
                "(function(){try{return (document.body && document.body.innerText) || '';}catch(e){return '';}})();",
                _on_text,
            )
        except Exception:
            # A tab may be closing or navigating while the user submits.
            # Keep the local context, but don't attach stale tab metadata.
            self.lbl_context_scope.setText("Context: browser page unavailable")
            self.run_assistant_query(
                question, context_label + " (browser page unavailable)", extra_context
            )

    def _host_browser(self):
        """Return the shell's selected browser tab, if this AI pane is embedded."""
        current = self.parentWidget()
        while current is not None:
            browser_page = getattr(current, "browser_page", None)
            if browser_page is not None and hasattr(browser_page, "current_browser"):
                try:
                    return browser_page.current_browser()
                except Exception:
                    return None
            current = current.parentWidget()
        return None

    def _capture_current_tab(self):
        """Capture one visible browser tab into an in-memory PNG for the next ask."""
        browser = self._host_browser()
        if browser is None:
            self.lbl_vision.setText("Vision: no browser tab")
            self._set_status("No browser tab to capture", "error")
            self._render_error("Open or select a browser tab first, then capture it.")
            return
        try:
            pixmap = browser.grab()
            if pixmap.isNull():
                raise ValueError("empty browser capture")
            buffer = QBuffer(self)
            buffer.open(QIODevice.WriteOnly)
            if not pixmap.save(buffer, "PNG"):
                raise ValueError("could not encode browser capture")
            encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
        except (OSError, TypeError, ValueError) as exc:
            self.lbl_vision.setText("Vision: capture failed")
            self._set_status("Screenshot failed", "error")
            self._render_error(f"Could not capture the current tab: {exc}")
            return
        self._pending_screenshot_b64 = encoded
        self.lbl_vision.setText("Vision: screenshot ready (local Ollama only)")
        self._set_status("Screenshot ready for the next question", "ready")
        self.txt_answer.setHtml(
            _status_html(
                "Screenshot ready",
                "The visible tab is held in memory for the next local Ollama vision question.",
                self._tokens(),
            )
        )
        self._show_thread_answer()

    def run_assistant_query(
        self,
        question: str,
        context_label: str = "Workspace-wide",
        extra_context: str = "",
        screenshot_b64: str = "",
    ):
        if getattr(self, "_closing", False):
            return
        if self._query_pending:
            self._set_status("A request is already running — please wait", "busy")
            return
        self._save_settings()
        screenshot_b64 = screenshot_b64 or self._pending_screenshot_b64
        self._pending_screenshot_b64 = ""
        self.lbl_vision.setText("Vision: attached" if screenshot_b64 else "Vision: none")
        self._privacy_locked = False
        self._last_question = question
        self._prompt_history.append(question)
        self._prompt_history = self._prompt_history[-20:]
        self._query_pending = True
        self.btn_ask.setEnabled(False)
        self.btn_reindex.setEnabled(False)
        provider_name = self.cmb_provider.currentText() or "assistant"
        self._set_status(f"Thinking with {provider_name}", "busy")
        self._render_loading(provider_name)
        self._start_thinking_pulse()
        future = self._executor.submit(
            ai_service.answer_query,
            self.base_dir,
            question,
            self.cmb_provider.currentData() or "rag",
            self.ed_model.text().strip(),
            extra_context,
            10,
            screenshot_b64,
        )
        self._active_query = future
        # Capture the provider label now: the user may switch the combo while
        # the query runs, and the answer must credit who produced it.
        provider_label = self.cmb_provider.currentText()
        future.add_done_callback(
            lambda done, label=context_label, prov=provider_label: self.query_finished.emit(done, label, prov) if not self._closing else None
        )

    def _start_thinking_pulse(self):
        """Animate the 'Thinking' dots while a query runs (a static 'Thinking...'
        read as a frozen app during long retrievals)."""
        if getattr(self, "_thinking_timer", None) is None:
            self._thinking_timer = QTimer(self)
            self._thinking_timer.setInterval(400)
            self._thinking_dots = 0

            def _tick():
                # The pulse must never cover an answer that arrived after the
                # future completed but before the queued result was delivered.
                if not self._query_pending or self._privacy_locked:
                    return
                self._thinking_dots = (self._thinking_dots + 1) % 4
                self._render_loading(
                    self.cmb_provider.currentText() or "assistant", self._thinking_dots
                )

            self._thinking_timer.timeout.connect(_tick)
        self._thinking_timer.start()

    def _stop_thinking_pulse(self):
        if getattr(self, "_thinking_timer", None) is not None:
            self._thinking_timer.stop()

    def _finish_assistant_query(self, future, context_label: str, provider_label: str = ""):
        if getattr(self, "_closing", False):
            return
        if future in getattr(self, "_discarded_queries", set()):
            self._discarded_queries.discard(future)
            return
        if getattr(self, "_privacy_locked", False):
            return
        self._stop_thinking_pulse()
        self._query_pending = False
        self.btn_ask.setEnabled(True)
        self.btn_reindex.setEnabled(True)
        try:
            result = future.result()
        except Exception as exc:
            # Do not leave a previous answer attached to the failed question;
            # the save actions would otherwise persist the wrong answer.
            self._last_answer = ""
            self._last_context = ""
            self.txt_context.clear()
            self.lbl_context_scope.setText("Context: request failed")
            self._set_status("Request failed", "error")
            self._render_error(f"{exc}\n\nCheck Provider setup, then try again.")
            self._show_context_error("The request failed before sources were collected.")
            return
        self._last_answer = result.get("answer", "")
        self._last_context = result.get("context", "")
        question = self._last_question or ""
        history_service.log_event(
            self.base_dir,
            "ai-question",
            question,
            (self._last_answer or "")[:280],
            {"provider": result.get("provider", ""), "context": context_label},
        )
        self.lbl_context_scope.setText(f"Context: {context_label}")
        self._render_source_text()
        if not provider_label:
            provider_label = self.cmb_provider.currentText()
        answer = self._last_answer or "No answer returned."
        self._render_answer(question, answer, provider_label)
        self._set_status(f"Answered by {provider_label}", "ready")
        self._append_history_item(
            question, answer, f"Context: {context_label}", provider_label
        )

    def ask_with_context(self, question: str, context_label: str, context_text: str):
        self._external_context_label = context_label or "Workspace-wide"
        self._external_context = context_text or ""
        self.ed_question.setText(question or "")
        self.run_assistant_query(question or "Summarize this context", self._external_context_label, self._external_context)

    def relock(self):
        """Discard late answers and visible private context, not persisted data."""
        self._privacy_locked = True
        future = getattr(self, "_active_query", None)
        if future is not None:
            self._discarded_queries.add(future)
            future.cancel()
        self._active_query = None
        self._query_pending = False
        self._stop_thinking_pulse()
        self.btn_ask.setEnabled(True)
        self.btn_reindex.setEnabled(True)
        try:
            self._auto_save_set()
        except OSError:
            # Locking must not fail because the disk is full. Visible private
            # data is cleared below even when the auto-save could not run.
            pass
        self._clear_thread()

    def _clear_thread(self):
        """Empty the in-memory thread, session list, and visible answer panes."""
        self._thread_items = []
        # Clear belongs to the thread, not just its view: the next Save session
        # and the close-time auto-save must not resurrect prompts the user
        # explicitly discarded. This also makes relock clear private prompts
        # when the auto-save above failed.
        self._prompt_history = []
        self.history_list.clear()
        self.history_stack.setCurrentWidget(self.history_empty)
        self.txt_answer.clear()
        self.txt_context.clear()
        self._show_thread_empty()
        self._show_context_empty()
        self._set_status("Ready", "ready")
        self._last_question = ""
        self._last_answer = ""
        self._last_context = ""
        self._external_context = ""
        self._external_context_label = "Workspace-wide"
        self._pending_screenshot_b64 = ""
        self.lbl_vision.setText("Vision: none")
        self.ed_question.clear()
        self.lbl_context_scope.setText("Context: Workspace-wide")

    def _export_thread(self):
        """Write the current assistant thread to a markdown/text file."""
        entries = list(self._thread_items)
        if not entries and not self._last_answer:
            QMessageBox.information(self, "AI Assistant", "Nothing to export yet.")
            return
        default = os.path.join(self.base_dir, "ai-thread-" + time.strftime("%Y%m%d-%H%M") + ".md")
        path, _ = QFileDialog.getSaveFileName(self, "Export AI thread", default, "Markdown (*.md);;Text (*.txt)")
        if not path:
            return
        lines = []
        for entry in reversed(entries):
            lines.append("## " + (entry.get("question") or "Question"))
            lines.append("")
            lines.append(entry.get("answer") or "")
            lines.append("")
        if not lines and self._last_answer:
            lines.append("## " + (self._last_question or "Thread"))
            lines.append("")
            lines.append(self._last_answer)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
        except OSError as exc:
            QMessageBox.warning(self, "AI Assistant", "Could not export the thread: %s" % (exc,))
            return
        QMessageBox.information(self, "AI Assistant", "AI thread exported to:\n" + path)

    def save_answer_to_note(self):
        if not self._last_answer:
            QMessageBox.information(self, "AI Assistant", "Ask something first.")
            return
        title = self._last_question[:60] or "AI note"
        body = "# " + title + "\n\n" + self._last_answer
        note = personal_service.create_note(self.base_dir, title, body)
        linked_to, linked = self._link_to_active_research("note", note.get("id", ""))
        message = "Saved answer to note: " + note["title"]
        if linked:
            message += f"\nLinked to research workspace: {linked_to}"
        elif linked_to:
            message += f"\nSaved, but could not link to research workspace: {linked_to}"
        QMessageBox.information(self, "AI Assistant", message)

    def create_task_from_answer(self):
        if not self._last_answer:
            QMessageBox.information(self, "AI Assistant", "Ask something first.")
            return
        title = self._last_question[:80] or "AI follow-up"
        task = life_service.add_task(self.base_dir, title, bucket="work")
        linked_to, linked = self._link_to_active_research("task", task.get("id", ""))
        message = "Created a task from the current answer."
        if linked:
            message += f"\nLinked to research workspace: {linked_to}"
        elif linked_to:
            message += f"\nCreated, but could not link to research workspace: {linked_to}"
        QMessageBox.information(self, "AI Assistant", message)

    def _link_to_active_research(self, entity_type: str, entity_id: str) -> tuple[str, bool]:
        """Attach an explicitly saved AI output and report link failures truthfully."""
        try:
            from litebrowser.services import tab_sets

            workspace = tab_sets.get_active_research_workspace(self.base_dir)
            if not workspace:
                return "", False
            title = str(workspace.get("title") or "")
            linked = tab_sets.add_research_reference(
                self.base_dir, workspace["id"], entity_type, entity_id
            )
            if linked:
                self._refresh_host_shell()
            return title, linked
        except (OSError, ValueError, RuntimeError):
            return "", False

    def _refresh_host_shell(self):
        """Refresh shell summaries after an AI result is linked to a desk."""
        current = self.parentWidget()
        while current is not None:
            refresh = getattr(current, "refresh_shell", None)
            if callable(refresh):
                refresh()
                return
            current = current.parentWidget()

    def get_current_ai_state(self):
        return [
            {"url": f"ai://prompt/{idx + 1}", "prompt": prompt, "active": idx == len(self._prompt_history) - 1}
            for idx, prompt in enumerate(self._prompt_history)
        ]

    def _auto_save_set(self):
        tabs = self.get_current_ai_state()
        if tabs:
            tab_sets.add_tab_set(self.base_dir, "ai", time.strftime("AI auto %Y-%m-%d %H:%M"), tabs)

    def save_current_set(self):
        tabs = self.get_current_ai_state()
        if not tabs:
            QMessageBox.information(self, "AI session", "No prompts yet.")
            return
        default = time.strftime("AI manual %Y-%m-%d %H:%M")
        name, ok = QInputDialog.getText(self, "Save AI session", "Session name:", text=default)
        if not ok:
            return
        tab_sets.add_tab_set(self.base_dir, "ai", name or default, tabs)
        QMessageBox.information(self, "AI session", "Current AI session saved.")

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        for timer in self.findChildren(QTimer):
            timer.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def closeEvent(self, event):
        try:
            self._auto_save_set()
        except Exception:
            pass
        # Deliberately do NOT shut down the executor: the AI window is embedded
        # in the shell and may be reused after close; a shut-down executor
        # would make every later submit raise RuntimeError (v6.4 bug). The
        # process lifetime owns the threads.
        event.accept()


def _format_ts(ts_value: int) -> str:
    """Backward-compatible alias; the canonical helper lives in core.time_utils."""
    return _time_utils.format_ts(ts_value)
