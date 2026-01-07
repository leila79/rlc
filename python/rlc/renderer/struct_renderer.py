from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import Layout, FIT, Direction, Padding
from rlc.text import Text
from dataclasses import dataclass
from typing import List
from .config_parser import apply_config

@register_renderer
@dataclass
class ContainerRenderer(Renderable):
    field_renderers: List[Renderable]

    def build_layout(self, obj, parent_path, direction=Direction.COLUMN, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(7,7,7,7)):
        layout = self.make_layout(sizing=sizing, direction=direction, child_gap=5, color=color, border=5, padding=padding)
        layout.binding = {"type": "struct"}
        layout.render_path = parent_path
        apply_config(layout)
        for field_name, field_renderer in self.field_renderers.items():
            if field_renderer is None:
                continue
            # Create a row for "name: value"
            value = getattr(obj, field_name)
            row_layout = self.make_layout(sizing=(FIT(), FIT()), direction=Direction.ROW, child_gap=5, color=None, border=5, padding=Padding(10,10,10,10))
            row_layout.render_path = parent_path
            apply_config(row_layout)
            label = self.make_text(field_name + ": ", "Arial", 16, "black")
            label.render_path = parent_path
            apply_config(label)
            binding_item = {
                "type": "struct_field",
                "field_name": field_name,
                "parent": layout.binding
            }
            value_layout = field_renderer(
                value, 
                parent_binding=binding_item,
                parent_path= parent_path + [field_name])
            value_layout.binding = binding_item
            apply_config(value_layout)
            row_layout.add_child(label)
            row_layout.add_child(value_layout)
            layout.add_child(row_layout)

        return layout

    def update(self, layout, obj, elapsed_time=0.0):
        for (field_name, field_renderer), child_layout in zip(self.field_renderers.items(), layout.children):
            if field_renderer is None:
                continue
            value = getattr(obj, field_name)
            field_renderer.update(child_layout.children[-1], value, elapsed_time)

    def _iter_children(self):
        # Only return child renderers (ignore field names)
        return [r for r in self.field_renderers.values() if r is not None]

