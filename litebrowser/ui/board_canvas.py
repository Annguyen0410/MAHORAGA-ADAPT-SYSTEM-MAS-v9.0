"""Desktop whiteboard interaction; saved strokes remain plain JSON records."""
import copy
import math
import uuid

from litebrowser.qt import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


def _number(value, default=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


class InkStrokeItem(QtWidgets.QGraphicsPathItem):
    def __init__(self, stroke):
        super().__init__()
        self.stroke = dict(stroke) if isinstance(stroke, dict) else {}
        self.setZValue(-20)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.set_points(self.stroke.get("points", []))

    def set_points(self, points):
        clean = [{"x": _number(p.get("x")), "y": _number(p.get("y"))}
                 for p in (points if isinstance(points, list) else []) if isinstance(p, dict)]
        self.stroke["points"] = clean
        color = QtGui.QColor(str(self.stroke.get("color") or "#292d32"))
        if not color.isValid():
            color = QtGui.QColor("#292d32")
        width = max(0.5, min(64.0, _number(self.stroke.get("width"), 3.0)))
        opacity = max(0.05, min(1.0, _number(self.stroke.get("opacity"), 1.0)))
        self.stroke.update(color=color.name(), width=width, opacity=opacity)
        self.setOpacity(opacity)
        path = QtGui.QPainterPath()
        if clean:
            first, last = clean[0], clean[-1]
            start = QtCore.QPointF(first["x"], first["y"])
            end = QtCore.QPointF(last["x"], last["y"])
            tool = self.stroke.get("tool", "pen")
            if tool in ("rectangle", "ellipse"):
                rect = QtCore.QRectF(start, end).normalized()
                if tool == "rectangle":
                    path.addRect(rect)
                else:
                    path.addEllipse(rect)
            else:
                path.moveTo(start)
                if tool == "line":
                    path.lineTo(end)
                elif len(clean) == 1:
                    path.lineTo(start + QtCore.QPointF(0.1, 0.1))
                else:
                    for point in clean[1:]:
                        path.lineTo(point["x"], point["y"])
        self.setPath(path)
        self.setPen(QtGui.QPen(color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))


class BoardView(QtWidgets.QGraphicsView):
    stroke_finished = QtCore.pyqtSignal()
    link_created = QtCore.pyqtSignal(str, str)
    zoom_changed = QtCore.pyqtSignal(int)
    history_changed = QtCore.pyqtSignal(bool, bool)
    TOOLS = ("pen", "pencil", "marker", "eraser", "line", "rectangle", "ellipse")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setTransformationAnchor(self.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Idea board canvas")
        self.setToolTip("Ctrl+wheel to zoom · middle-drag or Space+drag to pan · Ctrl+Z to undo")
        self.mode = "pan"
        self.tool = "pen"
        self.pen_color = "#292d32"
        self.pen_width = 3.0
        self.pen_opacity = 1.0
        self.background_color = "#ffffff"
        # The desk around the paper follows the active theme (set by the page);
        # the paper itself is the board's saved colour and never themed.
        self.desk_color = "#b7b8b8"
        self.grid_visible = True
        self._drawing_item = None
        self._drawing_points = []
        self._link_start = None
        self._gesture_before = None
        self._space_down = False
        self._pan_pos = None
        self._undo = []
        self._redo = []
        self._restore = None
        self._capture = None
        self.set_mode("pan")

    def set_history_callbacks(self, capture, restore):
        self._capture, self._restore = capture, restore
        self.reset_history()

    def reset_history(self):
        self._undo.clear()
        self._redo.clear()
        self.history_changed.emit(False, False)

    def snapshot(self):
        return copy.deepcopy(self._capture()) if self._capture else None

    def record_change(self, before):
        if before is None or before == self.snapshot():
            return
        self._undo.append(before)
        # Cap both steps and approximate geometry memory, not an unbounded log.
        while len(self._undo) > 40 or sum(len(repr(s)) for s in self._undo) > 8_000_000:
            self._undo.pop(0)
        self._redo.clear()
        self.history_changed.emit(bool(self._undo), False)
        self.stroke_finished.emit()

    def undo(self):
        if self._undo and self._restore:
            self.cancel_gesture()
            self._redo.append(self.snapshot())
            self._restore(self._undo.pop())
            self.history_changed.emit(bool(self._undo), bool(self._redo))
            self.stroke_finished.emit()

    def redo(self):
        if self._redo and self._restore:
            self.cancel_gesture()
            self._undo.append(self.snapshot())
            self._restore(self._redo.pop())
            self.history_changed.emit(bool(self._undo), bool(self._redo))
            self.stroke_finished.emit()

    def set_background(self, color):
        value = QtGui.QColor(str(color))
        self.background_color = value.name() if value.isValid() else "#ffffff"
        self.viewport().update()

    def set_desk_color(self, color):
        """Tint the area around the paper; the saved paper colour is untouched."""
        value = QtGui.QColor(str(color))
        self.desk_color = value.name() if value.isValid() else "#b7b8b8"
        self.viewport().update()

    def set_grid_visible(self, visible):
        self.grid_visible = bool(visible)
        self.viewport().update()

    def drawBackground(self, painter, rect):
        # Paper is independent from chrome/theme; outside it is the desk the
        # page tinted. A soft shadow lifts the sheet without decorating the
        # drawing surface itself.
        painter.fillRect(rect, QtGui.QColor(self.desk_color))
        if not self.scene():
            return
        paper = self.sceneRect()
        if paper.isEmpty():
            return
        scale = max(self.transform().m11(), 0.01)
        painter.fillRect(
            QtCore.QRectF(paper).translated(4 / scale, 5 / scale),
            QtGui.QColor(0, 0, 0, 40),
        )
        painter.fillRect(paper, QtGui.QColor(self.background_color))
        if self.grid_visible:
            self._draw_dot_grid(painter, rect, paper, scale)
        painter.setPen(QtGui.QPen(QtGui.QColor("#9da0a3"), 1 / scale))
        painter.drawRect(paper)

    def _draw_dot_grid(self, painter, rect, paper, scale):
        """A faint dot grid, at a constant on-screen pitch, clipped to view.

        Its colour is derived from the paper's luminance so it stays a whisper
        on white paper and still reads on a dark custom background. Only dots
        inside the exposed rect are built, so panning a large board stays cheap.
        """
        visible = QtCore.QRectF(rect).intersected(paper)
        if visible.isEmpty():
            return
        paper_color = QtGui.QColor(self.background_color)
        luminance = (paper_color.red() * 299 + paper_color.green() * 587 + paper_color.blue() * 114) / 1000
        ink = QtGui.QColor(0, 0, 0, 30) if luminance >= 150 else QtGui.QColor(255, 255, 255, 38)
        step = max(8.0, 26.0 / scale)
        left = paper.left() + math.ceil((visible.left() - paper.left()) / step) * step
        top = paper.top() + math.ceil((visible.top() - paper.top()) / step) * step
        points = []
        y = top
        while y <= visible.bottom() + 0.5:
            x = left
            while x <= visible.right() + 0.5:
                points.append(QtCore.QPointF(x, y))
                x += step
            y += step
        if points:
            # Constant on-screen dot weight: the pen is in scene units, so it
            # divides by the zoom (a fixed 1.0 became a 4 px blob at 4×).
            painter.setPen(QtGui.QPen(ink, max(0.3, 1.5 / scale), Qt.SolidLine, Qt.RoundCap))
            painter.drawPoints(QtGui.QPolygonF(points))

    def set_zoom(self, value):
        value = max(0.1, min(4.0, _number(value, 1.0)))
        current = self.transform().m11()
        self.scale(value / current, value / current)
        self.zoom_changed.emit(round(value * 100))

    def fit_canvas(self):
        if self.scene():
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
            self.set_zoom(self.transform().m11())

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.transform().m11() * (1.12 if event.angleDelta().y() > 0 else 1 / 1.12))
            event.accept()
        else:
            super().wheelEvent(event)

    def set_mode(self, mode):
        self.cancel_gesture()
        self._clear_link_start()
        self.mode = mode if mode in ("pan", "draw", "link") else "pan"
        self.setDragMode(self.ScrollHandDrag if self.mode == "pan" else self.NoDrag)
        self.viewport().setCursor(Qt.OpenHandCursor if self.mode == "pan" else Qt.CrossCursor)

    def set_tool(self, tool):
        self.tool = tool if tool in self.TOOLS else "pen"
        self.set_mode("draw")
        self.viewport().setCursor(Qt.PointingHandCursor if self.tool == "eraser" else Qt.CrossCursor)

    def set_pen(self, color, width, opacity=1.0):
        value = QtGui.QColor(str(color))
        self.pen_color = value.name() if value.isValid() else "#292d32"
        self.pen_width = max(0.5, min(64.0, _number(width, 3)))
        self.pen_opacity = max(0.05, min(1.0, _number(opacity, 1)))

    def _card(self, item):
        while item is not None:
            if hasattr(item, "node"):
                return item
            item = item.parentItem()
        return None

    def _erase_at(self, pos):
        point = self.mapToScene(pos)
        radius = max(6, self.pen_width * 2) / self.transform().m11()
        area = QtCore.QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2)
        for item in self.scene().items(area):
            if isinstance(item, InkStrokeItem):
                self.scene().removeItem(item)

    def mousePressEvent(self, event):
        if not self.scene() or not self.isEnabled():
            return super().mousePressEvent(event)
        self.setFocus()
        if event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton and self._space_down:
            self._pan_pos = event.pos()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        if self.mode == "link":
            card = self._card(self.itemAt(event.pos()))
            if card is None or card is self._link_start:
                self._clear_link_start()
            elif self._link_start is None:
                self._link_start = card
                card._orig_pen = card.pen()
                card.setPen(QtGui.QPen(QtGui.QColor("#487b9c"), 3))
            else:
                from_id, to_id = self._link_start.node.get("id"), card.node.get("id")
                self._clear_link_start()
                self.link_created.emit(from_id, to_id)
            event.accept()
            return
        self._gesture_before = self.snapshot()
        if self.mode == "draw" and not self._card(self.itemAt(event.pos())):
            if self.tool == "eraser":
                self._erase_at(event.pos())
            else:
                scene_pos = self.mapToScene(event.pos())
                if not self.sceneRect().contains(scene_pos):
                    self._gesture_before = None
                    event.accept()
                    return
                opacity = self.pen_opacity * (0.3 if self.tool == "marker" else 0.7 if self.tool == "pencil" else 1)
                stroke = {"id": uuid.uuid4().hex, "tool": self.tool, "color": self.pen_color,
                          "width": self.pen_width * (3 if self.tool == "marker" else 0.7 if self.tool == "pencil" else 1),
                          "opacity": opacity, "points": [{"x": scene_pos.x(), "y": scene_pos.y()}]}
                self._drawing_item = InkStrokeItem(stroke)
                self._drawing_points = stroke["points"]
                self.scene().addItem(self._drawing_item)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_pos is not None:
            delta = event.pos() - self._pan_pos
            self._pan_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self.mode == "draw" and self._gesture_before is not None and event.buttons() & Qt.LeftButton:
            if self.tool == "eraser":
                self._erase_at(event.pos())
                event.accept()
                return
            if self._drawing_item is not None:
                pos = self.mapToScene(event.pos())
                bounds = self.sceneRect()
                point = {"x": max(bounds.left(), min(bounds.right(), pos.x())), "y": max(bounds.top(), min(bounds.bottom(), pos.y()))}
                if self.tool in ("line", "rectangle", "ellipse"):
                    self._drawing_points[:] = [self._drawing_points[0], point]
                elif abs(point["x"] - self._drawing_points[-1]["x"]) + abs(point["y"] - self._drawing_points[-1]["y"]) >= 1:
                    self._drawing_points.append(point)
                self._drawing_item.set_points(self._drawing_points)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_pos is not None:
            self._pan_pos = None
            self.viewport().setCursor(Qt.OpenHandCursor if self.mode == "pan" else Qt.CrossCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton and self._gesture_before is not None:
            before = self._gesture_before
            self._gesture_before = None
            self._drawing_item = None
            self._drawing_points = []
            self.record_change(before)

    def cancel_gesture(self):
        before = self._gesture_before
        self._gesture_before = None
        if self._drawing_item is not None and self.scene():
            self.scene().removeItem(self._drawing_item)
        self._drawing_item = None
        self._drawing_points = []
        self._pan_pos = None
        # Escape also restores erased strokes or a partly moved card.
        if before is not None and self._restore and before != self.snapshot():
            self._restore(before)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_down = True
            self.viewport().setCursor(Qt.OpenHandCursor)
            event.accept()
        elif event.matches(QtGui.QKeySequence.Undo):
            self.undo()
        elif event.matches(QtGui.QKeySequence.Redo):
            self.redo()
        elif event.key() == Qt.Key_Escape:
            self.cancel_gesture()
            self._clear_link_start()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_down = False
            self.viewport().setCursor(Qt.OpenHandCursor if self.mode == "pan" else Qt.CrossCursor)
        else:
            super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._space_down = False
        self._pan_pos = None
        self.cancel_gesture()
        self.viewport().setCursor(Qt.OpenHandCursor if self.mode == "pan" else Qt.CrossCursor)
        super().focusOutEvent(event)

    def _clear_link_start(self):
        if self._link_start is not None:
            try:
                self._link_start.setPen(self._link_start._orig_pen)
                del self._link_start._orig_pen
            except RuntimeError:
                pass
        self._link_start = None
