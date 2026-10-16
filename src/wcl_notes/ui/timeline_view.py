"""Lorrgs-like timeline: one row per track, one icon per cast, WCL and NSRT phases.

Wheel scrolls in time, Ctrl+wheel zooms, clicking a cast disables it in the note.
The name column is painted in the foreground, in viewport coordinates, so it stays
on the left while scrolling.
"""

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QHelpEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QToolTip,
    QWidget,
)

from wcl_notes.domain.models import Cast, TrackRef
from wcl_notes.exporters.mrt import format_mrt_time
from wcl_notes.exporters.nsrt import format_nsrt_phase, format_nsrt_time
from wcl_notes.i18n import tr
from wcl_notes.labels import format_duration, spec_label
from wcl_notes.services.data_files import nsrt_mapping
from wcl_notes.services.phases import PhaseSegment, nsrt_segments
from wcl_notes.services.workspace import TrackEntry
from wcl_notes.ui.controller import AppController
from wcl_notes.ui.icons import IconProvider
from wcl_notes.ui.style import (
    ACCENT,
    BACKGROUND,
    BORDER,
    ERROR,
    SURFACE,
    SURFACE_ALT,
    TEXT_DIM,
    class_color,
)

LABEL_WIDTH = 200
RULER_HEIGHT = 26
ROW_HEIGHT = 58
ICON_SIZE = 28
TIME_ORIGIN = ICON_SIZE  # margin so that a cast at 0:00 is fully visible
LANE_OFFSET = 11  # vertical shift of a cast that would hide the previous one
MIN_PX_PER_S = 1.0
MAX_PX_PER_S = 40.0
DEFAULT_PX_PER_S = 6.0
TICK_STEPS_S = (5, 10, 15, 30, 60, 120, 300)
MIN_TICK_SPACING_PX = 70

CastCallback = Callable[[TrackRef, Cast], None]


class CastItem(QGraphicsPixmapItem):
    def __init__(self, pixmap: QPixmap, ref: TrackRef, cast: Cast, on_click: CastCallback) -> None:
        super().__init__(pixmap)
        self.ref = ref
        self.cast = cast
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.ref, self.cast)
            event.accept()
        else:
            super().mousePressEvent(event)


def tick_step(px_per_s: float) -> int:
    return next((s for s in TICK_STEPS_S if s * px_per_s >= MIN_TICK_SPACING_PX), 600)


class TimelineView(QGraphicsView):
    def __init__(
        self, controller: AppController, icons: IconProvider, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._icons = icons
        self._px_per_s = DEFAULT_PX_PER_S
        self._rows: list[TrackEntry] = []
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setBackgroundBrush(QBrush(QColor(BACKGROUND)))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        # The name column is drawn over the scene: repaint everything when scrolling.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(80)
        self._rebuild_timer.timeout.connect(self.rebuild)

        controller.workspace_changed.connect(self.rebuild)
        controller.selection_changed.connect(self.rebuild)
        icons.icon_ready.connect(lambda _: self._rebuild_timer.start())
        self.rebuild()

    @property
    def px_per_s(self) -> float:
        return self._px_per_s

    def cast_items(self) -> list[CastItem]:
        return [item for item in self._scene.items() if isinstance(item, CastItem)]

    # --- zoom, scroll, mouse ------------------------------------------------------

    def zoom(self, factor: float, anchor_x: float | None = None) -> None:
        new = min(max(self._px_per_s * factor, MIN_PX_PER_S), MAX_PX_PER_S)
        if new == self._px_per_s:
            return
        view_x = anchor_x if anchor_x is not None else self.viewport().width() / 2
        time_s = (self.mapToScene(int(view_x), 0).x() - TIME_ORIGIN) / self._px_per_s
        self._px_per_s = new
        self.rebuild()
        scroll = self.horizontalScrollBar()
        left = self.mapToScene(0, 0).x()
        scroll.setValue(round(scroll.value() + (TIME_ORIGIN + time_s * new - left) - view_x))

    def zoom_in(self) -> None:
        self.zoom(1.25)

    def zoom_out(self) -> None:
        self.zoom(0.8)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.25 if delta > 0 else 0.8, event.position().x())
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            super().wheelEvent(event)
        else:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Casts scrolled under the name column are hidden: never click them by accident.
        if event.position().x() < LABEL_WIDTH:
            event.accept()
            return
        super().mousePressEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        on_names = isinstance(event, QHelpEvent) and event.pos().x() < LABEL_WIDTH
        if event.type() == QEvent.Type.ToolTip and isinstance(event, QHelpEvent) and on_names:
            entry = self._row_at(event.pos().y())
            if entry is None:
                QToolTip.hideText()
            else:
                QToolTip.showText(
                    event.globalPos(), f"{entry.track.player.name} — {entry.origin}", self
                )
            return True
        return super().viewportEvent(event)

    def _row_at(self, viewport_y: int) -> TrackEntry | None:
        scene_y = self.mapToScene(0, viewport_y).y()
        row = int((scene_y - RULER_HEIGHT) // ROW_HEIGHT)
        return self._rows[row] if scene_y >= RULER_HEIGHT and 0 <= row < len(self._rows) else None

    # --- scene --------------------------------------------------------------------

    def rebuild(self) -> None:
        had_rows = bool(self._rows)
        h_scroll = self.horizontalScrollBar().value()
        v_scroll = self.verticalScrollBar().value()
        self._scene.clear()
        self._rows = self._controller.workspace.visible_entries()
        if not self._rows:
            self._draw_empty()
            return

        duration_s = max(e.track.fight.duration_ms for e in self._rows) / 1000
        width = TIME_ORIGIN + duration_s * self._px_per_s + ICON_SIZE * 2
        height = RULER_HEIGHT + len(self._rows) * ROW_HEIGHT
        self._draw_ruler(duration_s, width, height)
        for row, entry in enumerate(self._rows):
            self._draw_row(row, entry, width)
        # The scene starts LABEL_WIDTH left of the pull: room for the name column.
        self._scene.setSceneRect(QRectF(-LABEL_WIDTH, 0, width + LABEL_WIDTH, height + 8))
        if had_rows:
            self.horizontalScrollBar().setValue(h_scroll)
            self.verticalScrollBar().setValue(v_scroll)
        else:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().minimum())
            self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())
        self.viewport().update()

    def _draw_empty(self) -> None:
        text = self._scene.addSimpleText(
            tr("Ajoutez des joueurs depuis l'onglet Log pour remplir la timeline.")
        )
        text.setBrush(QBrush(QColor(TEXT_DIM)))
        self._scene.setSceneRect(QRectF(-20, -20, 600, 100))

    def _x(self, time_ms: int) -> float:
        return TIME_ORIGIN + time_ms / 1000 * self._px_per_s

    def _draw_ruler(self, duration_s: float, width: float, height: float) -> None:
        self._scene.addRect(
            QRectF(-LABEL_WIDTH, 0, width + LABEL_WIDTH, RULER_HEIGHT),
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(SURFACE)),
        )
        step = tick_step(self._px_per_s)
        grid_pen = QPen(QColor(BORDER))
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        for second in range(0, int(duration_s) + step, step):
            x = self._x(second * 1000)
            self._scene.addLine(x, RULER_HEIGHT - 6, x, RULER_HEIGHT, QPen(QColor(TEXT_DIM)))
            self._scene.addLine(x, RULER_HEIGHT, x, height, grid_pen)
            label = self._scene.addSimpleText(format_duration(second * 1000))
            label.setBrush(QBrush(QColor(TEXT_DIM)))
            label.setPos(x + 3, 4)

    def _draw_row(self, row: int, entry: TrackEntry, width: float) -> None:
        top = RULER_HEIGHT + row * ROW_HEIGHT
        fight = entry.track.fight
        background = QColor(SURFACE if row % 2 == 0 else SURFACE_ALT)
        self._scene.addRect(
            QRectF(0, top, self._x(fight.duration_ms), ROW_HEIGHT),
            QPen(Qt.PenStyle.NoPen),
            QBrush(background),
        )
        self._scene.addLine(0, top + ROW_HEIGHT, width, top + ROW_HEIGHT, QPen(QColor(BORDER)))
        self._draw_wcl_phases(entry, top)
        segments = nsrt_segments(fight, nsrt_mapping(fight.encounter_id))
        self._draw_nsrt_phases(segments, top)

        selection = self._controller.workspace.selection
        lane_ends = [float("-inf"), float("-inf")]
        for cast in self._controller.workspace.displayed_casts(entry):
            x = self._x(cast.time_ms) - ICON_SIZE / 2
            # Up to 40 % overlap stays on the main lane, beyond that use the shifted lane.
            lane = next((i for i, end in enumerate(lane_ends) if x >= end), 1)
            lane_ends[lane] = x + ICON_SIZE * 0.6
            spell = self._controller.workspace.spell(cast.spell_id)
            item = CastItem(
                self._icons.pixmap(spell.icon, ICON_SIZE),
                entry.ref,
                cast,
                self._controller.toggle_cast,
            )
            item.setPos(x, top + 15 + lane * LANE_OFFSET)  # phase labels above and below
            disabled = selection.is_disabled(entry.ref, cast)
            item.setToolTip(self._tooltip(spell.name, cast, segments, disabled))
            item.setZValue(2 + lane)
            self._scene.addItem(item)
            if disabled:
                item.setOpacity(0.3)
                self._draw_cross(item.pos(), item.zValue() + 0.5)

    def _draw_wcl_phases(self, entry: TrackEntry, top: float) -> None:
        fight = entry.track.fight
        infos = {p.id: p for p in entry.phase_infos}
        transitions = list(fight.phase_transitions)
        for index, transition in enumerate(transitions):
            start = max(transition.start_ms - fight.start_ms, 0)
            end = (
                transitions[index + 1].start_ms - fight.start_ms
                if index + 1 < len(transitions)
                else fight.duration_ms
            )
            info = infos.get(transition.phase_id)
            intermission = bool(info and info.is_intermission)
            if intermission:
                band = QGraphicsRectItem(
                    QRectF(self._x(start), top, self._x(end) - self._x(start), ROW_HEIGHT)
                )
                band.setBrush(QBrush(QColor(255, 183, 77, 28)))
                band.setPen(QPen(Qt.PenStyle.NoPen))
                band.setZValue(0.5)
                self._scene.addItem(band)
            if start > 0:
                line = self._scene.addLine(
                    self._x(start), top, self._x(start), top + ROW_HEIGHT, QPen(QColor(TEXT_DIM))
                )
                line.setZValue(1)
            label = self._scene.addSimpleText("Int." if intermission else f"P{transition.phase_id}")
            label.setBrush(QBrush(QColor(TEXT_DIM)))
            label.setFont(_small_font())
            label.setPos(self._x(start) + 3, top + 1)
            name = info.name if info else f"Phase {transition.phase_id}"
            label.setToolTip(tr("WCL : {name}").format(name=name))
            label.setZValue(1)

    def _draw_nsrt_phases(self, segments: tuple[PhaseSegment, ...], top: float) -> None:
        pen = QPen(QColor(ACCENT))
        pen.setStyle(Qt.PenStyle.DashLine)
        for segment in segments[1:]:
            x = self._x(segment.start_ms)
            line = self._scene.addLine(x, top, x, top + ROW_HEIGHT, pen)
            line.setZValue(1)
            label = self._scene.addSimpleText(f"NSRT {format_nsrt_phase(segment.phase)}")
            label.setBrush(QBrush(QColor(ACCENT)))
            label.setFont(_small_font())
            label.setPos(x + 3, top + ROW_HEIGHT - 15)
            label.setZValue(1)

    def _draw_cross(self, pos: QPointF, z: float) -> None:
        pen = QPen(QColor(ERROR))
        pen.setWidth(2)
        for x1, y1, x2, y2 in ((0, 0, ICON_SIZE, ICON_SIZE), (0, ICON_SIZE, ICON_SIZE, 0)):
            line = self._scene.addLine(pos.x() + x1, pos.y() + y1, pos.x() + x2, pos.y() + y2, pen)
            line.setZValue(z)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def _tooltip(
        self, spell_name: str, cast: Cast, segments: tuple[PhaseSegment, ...], disabled: bool
    ) -> str:
        segment = next(
            (s for s in reversed(segments) if s.start_ms <= max(cast.time_ms, 0)), segments[0]
        )
        action = tr("Clic : réactiver ce cast") if disabled else tr("Clic : désactiver ce cast")
        return "\n".join(
            [
                spell_name,
                tr("{time} depuis le pull").format(time=format_mrt_time(cast.time_ms)),
                tr("NSRT : ph {phase}, {time} s").format(
                    phase=format_nsrt_phase(segment.phase),
                    time=format_nsrt_time(cast.time_ms - segment.start_ms),
                ),
                action,
            ]
        )

    # --- pinned name column -------------------------------------------------------

    def drawForeground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        if not self._rows:
            return
        painter.save()
        painter.resetTransform()  # viewport coordinates from here on
        ruler_top = self.mapFromScene(QPointF(0, 0)).y()
        painter.fillRect(QRectF(0, ruler_top, LABEL_WIDTH, RULER_HEIGHT), QColor(SURFACE))
        small = _small_font()
        bold = QFont(painter.font())
        bold.setBold(True)
        for row, entry in enumerate(self._rows):
            top = self.mapFromScene(QPointF(0, RULER_HEIGHT + row * ROW_HEIGHT)).y()
            painter.fillRect(QRectF(0, top, LABEL_WIDTH, ROW_HEIGHT), QColor(BACKGROUND))
            painter.fillRect(QRectF(0, top + 4, 4, ROW_HEIGHT - 8), QColor(entry.color))
            player = entry.track.player
            painter.setFont(bold)
            painter.setPen(class_color(player.sub_type))
            painter.drawText(
                QRectF(10, top + 6, LABEL_WIDTH - 14, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                player.name,
            )
            painter.setFont(small)
            painter.setPen(QColor(TEXT_DIM))
            painter.drawText(
                QRectF(10, top + 28, LABEL_WIDTH - 14, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{spec_label(player)} · {format_duration(entry.track.fight.duration_ms)}",
            )
        painter.setPen(QColor(BORDER))
        painter.drawLine(LABEL_WIDTH - 1, 0, LABEL_WIDTH - 1, self.viewport().height())
        painter.restore()


def _small_font() -> QFont:
    font = QFont()
    font.setPointSize(8)
    return font
