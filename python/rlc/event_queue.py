import ctypes
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


def _copy_state(state_obj):
    """Deep copy of the state object via RLC's generated clone() method.
    clone() uses rl_m_assign which allocates independent heap storage for
    Vector fields, preventing double-free and allowing diff to detect changes.
    """
    return state_obj.clone()


def _rlc_string_to_python(rlc_str) -> str:
    """Convert an RLC String object to a Python str."""
    vec = rlc_str._data       # Vector<Byte>
    size = vec._size           # includes null terminator
    data = vec._data           # pointer to bytes
    return bytes(
        data[i] if isinstance(data[i], int) else data[i].value
        for i in range(size - 1)  # -1 to skip null terminator
    ).decode('ascii')


class UpdateController:
    """
    Guarded Update Protocol controller.

    Decouples event collection from state mutation from UI update.
    Prevents reentrancy by processing in strict phases:

    Phase 1 (COLLECT): Accumulate UpdateSignals from input events
    Phase 2 (MUTATE):  Execute all action handlers
    Phase 3 (UPDATE):  Call RLC diff against last known state,
                       update only the renderers whose sim fields changed
    Phase 4 (RELAYOUT): If dirty, recompute sizes and positions once
    """

    def __init__(self, renderer, layout, relayout_fn: Callable, dispatch_fn: Callable,
                 mapping=None, state_obj=None, program_module=None):
        """
        Args:
            renderer: The root renderer (Renderable subclass)
            layout: The root layout node
            relayout_fn: Callable that recomputes layout sizes and positions
            dispatch_fn: Callable(handler_name, args) -> bool that executes
                         an action handler and returns True if state changed.
            mapping: Optional SimRendererMapping for targeted updates.
                     If None, falls back to full renderer.update().
            state_obj: The initial state object. Required if mapping is provided.
            program_module: The compiled RLC module. Required for targeted updates
                            (provides the `diff` function from algorithms/diff.rl).
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
        self._program_module = program_module
        if mapping is not None and state_obj is not None:
            self._last_state = _copy_state(state_obj)
        else:
            self._last_state = None

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
                can_target = (self._mapping is not None
                              and self._last_state is not None
                              and self._program_module is not None
                              and hasattr(self._program_module, 'diff')
                              and hasattr(self._program_module, 'VectorTStringT'))
                
                if can_target:
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
        Call RLC diff to find changed fields, update only those renderers.
        Uses stdlib/algorithms/diff.rl via program_module.diff().
        """
        from rlc.sim_renderer_mapping import SimRendererMapping

        changed = self._program_module.VectorTStringT()
        self._program_module.diff(self._last_state, state_obj, changed)

        num_changed = changed.size() if hasattr(changed, 'size') else changed._data._size
        for i in range(num_changed):
            path_str = _rlc_string_to_python(changed.get(i).contents)
            sim_path = tuple(
                int(p) if p.isdigit() else p
                for p in path_str.split('.')
                if p
            )
            entry = self._mapping.get_entry(sim_path)
            if entry:
                value = SimRendererMapping.resolve_value(state_obj, sim_path)
                entry.renderer.update(entry.layout_node, value, elapsed)

        self._last_state = _copy_state(state_obj)
        if num_changed > 0:
            self._needs_relayout = True
        else:
            # Shallow copy shares heap with original — diff may miss heap-resident
            # changes (e.g. Vector elements without size change). Fall back to
            # full update so the renderer stays consistent.
            self.renderer.update(self.layout, state_obj, elapsed)
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
