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
                     color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(2,2,2,2), index_bindings=None, mapping=None):
        if index_bindings is None:
            index_bindings = {}

        value = getattr(obj, "_data", None)

        return self.vector_renderer(
            value,
            parent_path=parent_path,
            direction=direction,
            color=color,
            sizing=sizing,
            logger=logger,
            padding=padding,
            index_bindings=index_bindings,
            mapping=mapping,
        )

    def update(self, layout, obj, elapsed_time=0.0):
        value = getattr(obj, "_data")
        self.vector_renderer.update(layout, value, elapsed_time)

    def _iter_children(self) :
        return [self.vector_renderer]
