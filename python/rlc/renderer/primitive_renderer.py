
from rlc.renderer.renderable import Renderable, register_renderer
from ctypes import c_long, c_bool
from rlc.text import Text
from rlc.layout import  Direction, FIT, Padding
import time
from dataclasses import dataclass

@register_renderer
@dataclass
class PrimitiveRenderer(Renderable):
    def build_layout(self, obj, parent_path, direction=Direction.COLUMN, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(2,2,2,2), index_bindings=None, mapping=None, byte_offset=0, rlc_type=None):
        if index_bindings is None:
            index_bindings = {}

        if self.rlc_type_name == "c_bool":
            text = "True" if obj else "False"
        if self.rlc_type_name == "c_long":
            text = str(obj if isinstance(obj, int) else obj.value)
        else:
            text = str(obj)

        layout = self.make_text(text, "Arial", 16, "black")
        layout.render_path = parent_path

        # Apply pre-computed interactions with index bindings
        self._apply_interaction_mappings(layout, index_bindings)

        # Register in sim↔renderer mapping
        if mapping is not None and rlc_type is not None:
            import ctypes
            mapping.add_entry(tuple(parent_path), byte_offset,
                              ctypes.sizeof(rlc_type), self, layout)

        return layout

    def update(self, layout, obj, elapsed_time=0.0):
        """Update the text node if the value changed."""
        if isinstance(layout, Text):
            new_value = self._extract_value(obj)
            layout.update_text(new_value)

    def _extract_value(self, obj):
        if self.rlc_type_name == "c_bool":
            text = "True" if obj else "False"
        if self.rlc_type_name == "c_long":
            text = str(obj if isinstance(obj, int) else obj.value)
        else:
            text = str(obj)
        return text

