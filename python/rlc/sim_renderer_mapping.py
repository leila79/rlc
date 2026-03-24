from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class MappingEntry:
    """A single leaf mapping between a simulation field and its renderer+layout node."""
    sim_path: tuple   # e.g., ("board", "slots", 0, 0)
    renderer: Any     # the Renderable that renders this field
    layout_node: Any  # the live Layout node to update


class SimRendererMapping:
    """
    Bidirectional mapping between simulation type tree and renderer type tree.

    Built inline during layout creation: each renderer's build_layout()
    registers its own MappingEntry via the `mapping` parameter.

    Diffing is done by the RLC `diff` function (stdlib/algorithms/diff.rl),
    which compares two state instances recursively and returns the dot-separated
    paths of every changed leaf field as a Vector<String>.
    """

    def __init__(self):
        self.entries: List[MappingEntry] = []
        self._path_to_entry = {}       # sim_path tuple → MappingEntry
        self._renderer_to_entries = {}  # id(renderer) → [MappingEntry]

    def add_entry(self, sim_path, renderer, layout_node):
        entry = MappingEntry(sim_path, renderer, layout_node)
        self.entries.append(entry)
        self._path_to_entry[sim_path] = entry
        rid = id(renderer)
        if rid not in self._renderer_to_entries:
            self._renderer_to_entries[rid] = []
        self._renderer_to_entries[rid].append(entry)

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

    def print_mapping(self):
        """Debug helper: print all mapping entries."""
        print(f"SimRendererMapping: {len(self.entries)} entries")
        for entry in self.entries:
            path_str = ".".join(str(s) for s in entry.sim_path)
            print(f"  {path_str:40s}  renderer={entry.renderer.__class__.__name__}")
