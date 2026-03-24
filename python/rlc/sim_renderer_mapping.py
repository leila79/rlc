import ctypes
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass
class MappingEntry:
    """A single leaf mapping between a simulation field and its renderer+layout node."""
    sim_path: tuple       # e.g., ("board", "slots", 0, 0)
    byte_offset: int      # offset from struct base in bytes
    byte_size: int        # size of this field in bytes
    renderer: Any         # the Renderable that renders this field
    layout_node: Any      # the live Layout node to update
    heap_dependent: bool = False  # True for vectors: data lives on heap, not in struct


class SimRendererMapping:
    """
    Bidirectional mapping between simulation type tree and renderer type tree.

    Built inline during layout creation: each renderer's build_layout()
    registers its own MappingEntry via the `mapping` parameter. This avoids
    a separate tree walk and ensures new renderer types only need one code path.

    Each leaf renderer gets a MappingEntry recording its byte offset in the
    simulation state, enabling:

    1. Snapshot diff: compare byte ranges to detect which fields changed
    2. Targeted update: call renderer.update() only on dirty fields
    """

    def __init__(self):
        self.entries: List[MappingEntry] = []
        self._path_to_entry = {}       # sim_path tuple → MappingEntry
        self._renderer_to_entries = {}  # id(renderer) → [MappingEntry]

    def add_entry(self, sim_path, byte_offset, byte_size, renderer, layout_node,
                  heap_dependent=False):
        entry = MappingEntry(sim_path, byte_offset, byte_size, renderer, layout_node,
                             heap_dependent=heap_dependent)
        self.entries.append(entry)
        self._path_to_entry[sim_path] = entry
        rid = id(renderer)
        if rid not in self._renderer_to_entries:
            self._renderer_to_entries[rid] = []
        self._renderer_to_entries[rid].append(entry)

    def diff(self, before: bytes, after: bytes) -> List[MappingEntry]:
        """Compare two snapshots and return list of dirty MappingEntries.

        Heap-dependent entries (vectors) are always considered dirty because
        their data lives on the heap, outside the struct snapshot.
        """
        dirty = []
        for entry in self.entries:
            if entry.heap_dependent:
                dirty.append(entry)
                continue
            s = entry.byte_offset
            e = s + entry.byte_size
            if before[s:e] != after[s:e]:
                dirty.append(entry)
        return dirty

    def get_entry(self, sim_path: tuple) -> Optional[MappingEntry]:
        return self._path_to_entry.get(sim_path)

    @staticmethod
    def resolve_value(state_obj, sim_path: tuple):
        """Walk the state object following sim_path to get the leaf value."""
        obj = state_obj
        for seg in sim_path:
            if isinstance(seg, int):
                target = obj
                while hasattr(target, '_data'):
                    target = target._data
                obj = target[seg]
            else:
                obj = getattr(obj, seg)
        return obj

    @staticmethod
    def take_snapshot(state_obj) -> bytes:
        """Capture the raw ctypes memory of state_obj as bytes."""
        size = ctypes.sizeof(type(state_obj))
        return bytes((ctypes.c_char * size).from_address(ctypes.addressof(state_obj)))

    def print_mapping(self):
        """Debug helper: print all mapping entries."""
        heap_count = sum(1 for e in self.entries if e.heap_dependent)
        print(f"SimRendererMapping: {len(self.entries)} entries "
              f"({heap_count} heap-dependent)")
        for entry in self.entries:
            path_str = ".".join(str(s) for s in entry.sim_path)
            flags = " [HEAP]" if entry.heap_dependent else ""
            print(f"  {path_str:40s}  offset={entry.byte_offset:4d}  "
                  f"size={entry.byte_size:3d}  "
                  f"renderer={entry.renderer.__class__.__name__}{flags}")
