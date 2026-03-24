from rlc.text import Text
from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import  Direction, FIT, Padding
from dataclasses import dataclass

@register_renderer
@dataclass
class BoundedVectorRenderer(Renderable):
    """
    Renderer for bounded integer structs like BIntT1T10T.
    """
    vector_renderer: Renderable

    def build_layout(self, obj, parent_path, direction=Direction.COLUMN,
                     color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(2,2,2,2), index_bindings=None, mapping=None, byte_offset=0, rlc_type=None):
        if index_bindings is None:
            index_bindings = {}

        value = getattr(obj, "_data", None)

        # Compute inner _data field offset and type for mapping
        data_rlc_type = None
        data_byte_offset = byte_offset
        if rlc_type:
            field_types = {fname: ftype for fname, ftype in getattr(rlc_type, "_fields_", [])}
            if "_data" in field_types:
                data_rlc_type = field_types["_data"]
                data_byte_offset = byte_offset + getattr(rlc_type, "_data").offset

        value_layout = self.vector_renderer(
            value,
            parent_path=parent_path,
            direction=direction,
            color=color,
            sizing=sizing,
            logger=logger,
            padding=padding,
            index_bindings=index_bindings,
            mapping=mapping,
            byte_offset=data_byte_offset,
            rlc_type=data_rlc_type
        )
        # Register in sim↔renderer mapping
        if mapping is not None and rlc_type is not None:
            import ctypes
            mapping.add_entry(tuple(parent_path), byte_offset,
                              ctypes.sizeof(rlc_type), self, value_layout)
        return value_layout

    def update(self, layout, obj, elapsed_time=0.0):
        value = getattr(obj, "_data")
        self.vector_renderer.update(layout, value, elapsed_time)

    def _iter_children(self) :
        return [self.vector_renderer]
