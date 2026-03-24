from dataclasses import dataclass, field
from typing import Optional, Any, Callable, Dict
from enum import Enum


class SignalKind(Enum):
    ACTION = "action"
    RESIZE = "resize"
    SCROLL = "scroll"
    FOCUS = "focus"


@dataclass
class UpdateSignal:
    """
    Represents a single event that may require state mutation and/or relayout.

    The queue accumulates these during event polling, then processes them
    in batch: all mutations first, then a single update+relayout pass.
    """
    kind: SignalKind
    handler_name: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    target: Any = None
    width: int = 0
    height: int = 0
    dx: int = 0
    dy: int = 0


class UpdateController:
    """
    Guarded Update Protocol controller.

    Decouples event collection from state mutation from UI update.
    Prevents reentrancy by processing in strict phases:

    Phase 1 (COLLECT): Accumulate UpdateSignals from input events
    Phase 2 (MUTATE):  Execute all action handlers
    Phase 3 (UPDATE):  Diff state snapshot against last known state,
                       update only the renderers whose sim fields changed
    Phase 4 (RELAYOUT): If dirty, recompute sizes and positions once

    Uses a SimRendererMapping to map byte offsets in the simulation state
    to specific renderer+layout_node pairs. A persistent snapshot tracks the
    last known state; diffing against it naturally deduplicates and buffers
    all changes regardless of how many handlers ran or whether state was
    modified externally (e.g., auto-play).
    """

    def __init__(self, renderer, layout, relayout_fn: Callable, dispatch_fn: Callable,
                 mapping=None, state_obj=None):
        """
        Args:
            renderer: The root renderer (Renderable subclass)
            layout: The root layout node
            relayout_fn: Callable that recomputes layout sizes and positions
            dispatch_fn: Callable(handler_name, args) -> bool that executes
                         an action handler and returns True if state changed.
            mapping: Optional SimRendererMapping for targeted updates.
                     If None, falls back to full renderer.update().
            state_obj: The initial state object. Required if mapping is provided
                       (used to take the initial snapshot).
        """
        self.renderer = renderer
        self.layout = layout
        self.relayout_fn = relayout_fn
        self.dispatch_fn = dispatch_fn

        self._queue = []
        self._processing = False
        self._state_changed = False
        self._needs_relayout = False

        self.scroll = {"x": 0, "y": 0}

        # Targeted update support
        self._mapping = mapping
        if mapping is not None and state_obj is not None:
            from rlc.sim_renderer_mapping import SimRendererMapping
            self._last_snapshot = SimRendererMapping.take_snapshot(state_obj)
        else:
            self._last_snapshot = None

    def enqueue(self, signal: UpdateSignal):
        """Add a signal to the queue. Safe to call from handlers."""
        self._queue.append(signal)

    def process(self, state_obj, elapsed: float):
        """
        Process all queued signals. Called once per frame after all events collected.

        Args:
            state_obj: The simulation state object (e.g., state.state)
            elapsed: Time since last frame in seconds
        """
        if self._processing:
            return

        self._processing = True
        self._needs_relayout = False

        try:
            # Phase 2: MUTATE - execute all queued signals
            while self._queue:
                signal = self._queue.pop(0)
                self._handle_signal(signal)

            # Phase 3: UPDATE
            if self._state_changed:
                if self._mapping is not None and self._last_snapshot is not None:
                    self._targeted_update(state_obj, elapsed)
                else:
                    self.renderer.update(self.layout, state_obj, elapsed)
                    self._needs_relayout = True

            # Phase 4: RELAYOUT - recompute sizes/positions (once)
            if self._needs_relayout or _any_child_dirty(self.layout):
                self.relayout_fn()

        finally:
            self._processing = False
            self._state_changed = False

    def _targeted_update(self, state_obj, elapsed: float):
        """
        Diff current state against last snapshot.
        Update only the renderers whose simulation fields changed.
        Heap-dependent entries (vectors) are always updated since their
        data lives outside the struct snapshot.
        """
        from rlc.sim_renderer_mapping import SimRendererMapping

        current = SimRendererMapping.take_snapshot(state_obj)

        # diff() handles both struct-level byte comparison AND heap-dependent
        # entries (which are always considered dirty)
        dirty_entries = self._mapping.diff(self._last_snapshot, current)
        if dirty_entries:
            print(f"[targeted_update] {len(dirty_entries)} dirty entries:")
            for entry in dirty_entries:
                path_str = ".".join(str(s) for s in entry.sim_path)
                value = SimRendererMapping.resolve_value(state_obj, entry.sim_path)
                print(f"  {path_str} -> {value}")
                entry.renderer.update(entry.layout_node, value, elapsed)
        else:
            print("[targeted_update] no dirty entries found (snapshots identical)")

        self._last_snapshot = current
        if dirty_entries:
            self._needs_relayout = True

    def notify_state_changed(self):
        """Call after programmatic state mutations (e.g., auto-play)."""
        self._state_changed = True

    def _handle_signal(self, signal: UpdateSignal):
        if signal.kind == SignalKind.ACTION:
            changed = self.dispatch_fn(signal.handler_name, signal.args)
            if changed:
                self._state_changed = True

        elif signal.kind == SignalKind.FOCUS:
            self.layout.set_focus(signal.target)
            self._needs_relayout = True

        elif signal.kind == SignalKind.RESIZE:
            self._needs_relayout = True

        elif signal.kind == SignalKind.SCROLL:
            self.scroll["x"] += signal.dx
            self.scroll["y"] += signal.dy
            self._needs_relayout = True


def _any_child_dirty(layout):
    """Check and clear dirty flags recursively."""
    if getattr(layout, "is_dirty", False):
        layout.is_dirty = False
        return True
    return any(
        _any_child_dirty(c)
        for c in layout.children
        if hasattr(c, "children")
    )
