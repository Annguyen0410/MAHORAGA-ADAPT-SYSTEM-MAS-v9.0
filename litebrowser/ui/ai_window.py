import base64
import os
import time
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import QBuffer, QIODevice, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
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

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(14, 12, 14, 12)
        hero_layout.setSpacing(8)

        brand_row = QHBoxLayout()
        brand_row.addWidget(components.page_header("AI Assistant", "Ask one assistant across Browser, Personal, Library, and this workspace"), 1)
        hero_layout.addLayout(brand_row)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)
        self.cmb_provider = QComboBox()
        self.cmb_provider.addItem("RAG local only", "rag")
        self.cmb_provider.addItem("OpenRouter assistant", "openrouter")
        self.cmb_provider.addItem("Local LLM: Ollama", "ollama")
        self.cmb_provider.addItem("Local LLM: llama.cpp server", "llama_cpp")
        settings_row.addWidget(self.cmb_provider)
        self.ed_model = QLineEdit()
        self.ed_model.setPlaceholderText("Model name")
        self.ed_model.setMinimumWidth(150)
        settings_row.addWidget(self.ed_model)
        self.ed_api_key = QLineEdit()
        self.ed_api_key.setPlaceholderText("OpenRouter API key")
        self.ed_api_key.setEchoMode(QLineEdit.Password)
        self.ed_api_key.setMinimumWidth(160)
        settings_row.addWidget(self.ed_api_key, 1)
        self.btn_save_settings = QPushButton("Save AI settings")
        settings_row.addWidget(self.btn_save_settings)
        hero_layout.addLayout(settings_row)

        prompt_row = QHBoxLayout()
        self.ed_question = QLineEdit()
        self.ed_question.setPlaceholderText("Ask about the current page, your notes, tasks, saved pages, or the whole workspace...")
        prompt_row.addWidget(self.ed_question, 1)
        self.btn_ask = QPushButton("Ask assistant")
        self.btn_ask.setObjectName("TopAccentButton")
        self.btn_capture_screenshot = QPushButton("Capture tab")
        self.btn_capture_screenshot.setToolTip(
            "Capture the visible current browser tab for the next local Ollama vision request"
        )
        self.btn_reindex = QPushButton("Rebuild index")
        prompt_row.addWidget(self.btn_ask)
        prompt_row.addWidget(self.btn_capture_screenshot)
        prompt_row.addWidget(self.btn_reindex)
        hero_layout.addLayout(prompt_row)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        self.lbl_index = components.badge("Index: —", "accent")
        badge_row.addWidget(self.lbl_index)
        self.lbl_context_scope = components.badge("Context: Workspace-wide")
        badge_row.addWidget(self.lbl_context_scope)
        # Live provider badge: shows which engine will answer (v6.4 only
        # revealed the provider in the answer footer after the fact).
        self.lbl_provider = components.badge("Provider: RAG local only", "accent")
        self.lbl_vision = components.badge("Vision: none", "muted")
        self.cmb_provider.currentTextChanged.connect(
            lambda _t: self.lbl_provider.setText("Provider: " + (self.cmb_provider.currentText() or "—"))
        )
        badge_row.addWidget(self.lbl_provider)
        badge_row.addWidget(self.lbl_vision)
        badge_row.addStretch(1)
        self.chk_browser_context = QCheckBox("👁 Read my browser")
        self.chk_browser_context.setChecked(True)
        self.chk_browser_context.setToolTip(
            "Attach the page open in the browser (its full text) plus every open tab to each question.\n"
            "The content is labelled untrusted context, so the assistant reads it but never follows it.\n"
            "When a remote provider is selected, page text and open-tab titles/URLs are sent to that provider."
        )
        badge_row.addWidget(self.chk_browser_context)
        self.chk_research_context = QCheckBox("Use research desk")
        self.chk_research_context.setChecked(False)
        self.chk_research_context.setToolTip(
            "Include the active research workspace's tabs and linked notes, tasks, saved links, and flashcards.\n"
            "Linked note and task text may be sent to the selected provider when you ask a question."
        )
        badge_row.addWidget(self.chk_research_context)
        self.chk_show_context = QCheckBox("Show sources")
        self.chk_show_context.setChecked(True)
        badge_row.addWidget(self.chk_show_context)
        self.btn_to_note = QPushButton("☰ Save to note")
        self.btn_to_task = QPushButton("☑ Create task")
        self.btn_save_set = QPushButton("◫ Save session")
        self.btn_export_thread = QPushButton("⇩ Export")
        self.btn_clear_thread = QPushButton("✕ Clear")
        badge_row.addWidget(self.btn_to_note)
        badge_row.addWidget(self.btn_to_task)
        badge_row.addWidget(self.btn_save_set)
        badge_row.addWidget(self.btn_export_thread)
        badge_row.addWidget(self.btn_clear_thread)
        hero_layout.addLayout(badge_row)

        layout.addWidget(hero)

        body = QSplitter(Qt.Horizontal)
        layout.addWidget(body, 1)

        left_card = QFrame()
        left_card.setObjectName("SectionCard")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(6)
        left_layout.addWidget(components.section_header("Sessions", "Ask history"))
        self.history_list = QListWidget()
        self.history_list.setObjectName("CafeList")
        left_layout.addWidget(self.history_list, 1)
        body.addWidget(left_card)

        center_card = QFrame()
        center_card.setObjectName("SectionCard")
        center_layout = QVBoxLayout(center_card)
        center_layout.setContentsMargins(12, 12, 12, 12)
        center_layout.setSpacing(6)
        center_layout.addWidget(components.section_header("Assistant thread", "Answers from the assistant"))
        self.txt_answer = QTextEdit()
        self.txt_answer.setReadOnly(True)
        self.txt_answer.setPlaceholderText("Answers from the assistant will appear here.")
        center_layout.addWidget(self.txt_answer, 1)
        body.addWidget(center_card)

        right_card = QFrame()
        right_card.setObjectName("SectionCard")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(6)
        right_layout.addWidget(components.section_header("Sources & prompts", "Retrieved sources + quick prompts"))
        self.txt_context = QTextEdit()
        self.txt_context.setReadOnly(True)
        self.txt_context.setPlaceholderText("Retrieved sources and injected workspace context show here.")
        right_layout.addWidget(self.txt_context, 1)
        right_layout.addWidget(components.section_header("Prompt Library", "Double-click to use"))
        self.prompt_list = QListWidget()
        self.prompt_list.setObjectName("CafeList")
        for text in (
            "Summarize this workspace",
            "Turn current page into a note",
            "Extract deadlines and tasks",
            "Build a study brief",
            "What changed in my recent saved pages?",
            "What should I focus on today?",
        ):
            self.prompt_list.addItem(text)
        right_layout.addWidget(self.prompt_list, 1)
        body.addWidget(right_card)
        body.setChildrenCollapsible(True)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([180, 760, 220])

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
        self.query_finished.connect(self._finish_assistant_query)
        self._ollama_models_ready.connect(self._on_ollama_models_ready)
        self._load_settings()
        self._refresh_index_label()
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

    def _apply_compact_layout(self):
        width = max(0, self.width())
        compact = width < 1180
        narrow = width < 940
        tiny = width < 820
        body = self.findChild(QSplitter)
        if body:
            left = 132 if tiny else 150 if narrow else 170 if compact else 190
            right = 0 if tiny else 180 if narrow else 210 if compact else 240
            center = max(320, width - left - right - 24)
            body.setSizes([left, center, right])
        self.chk_show_context.setVisible(not tiny)
        self.chk_browser_context.setVisible(not narrow)
        self.chk_research_context.setVisible(not narrow)
        self.btn_to_note.setVisible(not narrow)
        self.btn_to_task.setVisible(not narrow)
        self.btn_save_set.setVisible(not tiny)

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
        prefs.save_ai_settings(self.base_dir, self._collect_settings_payload())

    def _save_settings_with_notice(self):
        self._save_settings()
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
            else "Select Local LLM: Ollama to enable screenshot vision"
        )
        self._refresh_model_value()
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
        self.lbl_index.setText(f"Index: {len(data.get('docs', []))} docs · updated {_format_ts(int(data.get('built_at', 0) or 0))}")

    def _reindex(self):
        data = ai_service.rebuild_index(self.base_dir)
        self._refresh_index_label()
        QMessageBox.information(self, "AI Assistant", f"Rebuilt index with {len(data.get('docs', []))} docs.")

    def _apply_prompt_template(self, item: QListWidgetItem):
        self.ed_question.setText(item.text())
        self.ed_question.setFocus()

    def _append_history_item(self, question: str, answer: str, context_label: str):
        payload = {"question": question, "answer": answer, "context_label": context_label, "context": self._last_context}
        self._thread_items.insert(0, payload)
        self._thread_items = self._thread_items[:24]
        self.history_list.clear()
        for entry in self._thread_items:
            row = QListWidgetItem(f"{entry['question']}\n{entry['context_label']}")
            row.setData(Qt.UserRole, entry)
            self.history_list.addItem(row)

    def _load_history_item(self, item: QListWidgetItem):
        payload = item.data(Qt.UserRole) or {}
        self.ed_question.setText(payload.get("question", ""))
        self.txt_answer.setPlainText(payload.get("answer", ""))
        self.txt_context.setPlainText(payload.get("context", ""))
        self.lbl_context_scope.setText(payload.get("context_label", "Context: Workspace-wide"))

    def _ask(self):
        question = (self.ed_question.text() or "").strip()
        if not question:
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
            if self.chk_show_context.isChecked():
                self.txt_context.setPlainText(context)
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
            title = (tab.get("title") or "").strip()[:120]
            url = (tab.get("url") or "").strip()[:200]
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
                title = browser.title() or browser.url().toString() or "Current page"
                url = browser.url().toString()
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
            self.txt_answer.setPlainText("Open or select a browser tab first, then capture it.")
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
            self.txt_answer.setPlainText(f"Could not capture the current tab: {exc}")
            return
        self._pending_screenshot_b64 = encoded
        self.lbl_vision.setText("Vision: screenshot ready (local Ollama only)")
        self.txt_answer.setPlainText(
            "Current tab screenshot captured in memory. Ask a question to analyze it with a local Ollama vision model."
        )

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
            self.txt_answer.setPlainText("Another request is still running — please wait for it to finish.")
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
        self.txt_answer.setPlainText(f"Thinking with {provider_name}...\n\nGathering workspace context and sources.")
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
                self._thinking_dots = (self._thinking_dots + 1) % 4
                base = "Thinking with %s...\n\nGathering workspace context and sources." % (
                    self.cmb_provider.currentText() or "assistant"
                )
                self.txt_answer.setPlainText(base + "\n" + "•" * (self._thinking_dots or 1))

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
            self.txt_answer.setPlainText(f"Assistant request failed: {exc}")
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
        if self.chk_show_context.isChecked():
            self.txt_context.setPlainText(self._last_context or "(no sources)")
        else:
            self.txt_context.setPlainText("(hidden)")
        if not provider_label:
            provider_label = self.cmb_provider.currentText()
        answer = self._last_answer or "No answer returned."
        self.txt_answer.setPlainText(f"{answer}\n\n---\nProvider: {provider_label}")
        self._append_history_item(question, self.txt_answer.toPlainText(), f"Context: {context_label}")

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
            # Locking must not fail because the disk is full. Keep the prompt
            # history for the normal save path, but clear visible private data.
            pass
        else:
            self._prompt_history = []
        self._clear_thread()

    def _clear_thread(self):
        """Empty the in-memory thread, session list, and visible answer panes."""
        self._thread_items = []
        self.history_list.clear()
        self.txt_answer.clear()
        self.txt_context.clear()
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
        if not entries and not self.txt_answer.toPlainText().strip():
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
        if not lines and self.txt_answer.toPlainText().strip():
            lines.append("## " + (self._last_question or "Thread"))
            lines.append("")
            lines.append(self.txt_answer.toPlainText())
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
