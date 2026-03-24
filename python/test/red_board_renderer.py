from rlc.renderer.struct_renderer import ContainerRenderer
from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import Layout, Direction, FIT, Padding
from rlc.text import Text
from dataclasses import dataclass

@register_renderer
@dataclass
class RedBoard(ContainerRenderer):
    
    @staticmethod
    def create_fields(factory, rlc_type, rlc_path, config, interaction_ctx):
        fields = ContainerRenderer.create_fields(factory, rlc_type, rlc_path, config, interaction_ctx)
        del fields['resume_index']
        # Transform display names by adding 'red' prefix while keeping actual field names
        return {'red_' + key: value for key, value in fields.items()}
    def build_layout(self, obj, parent_path, direction=Direction.COLUMN, color="red", sizing=(FIT(), FIT()), logger=None, padding=Padding(7,7,7,7), index_bindings=None, mapping=None):
        if index_bindings is None:
            index_bindings = {}

        layout = self.make_layout(sizing=sizing, direction=direction, child_gap=5, color=color, border=5, padding=padding)
        layout.binding = {"type": "struct"}
        layout.render_path = parent_path

        # Apply pre-computed interactions
        self._apply_interaction_mappings(layout, index_bindings)

        for display_name, field_data in self.field_renderers.items():
            if field_data is None:
                continue

            actual_field_name, field_renderer = field_data

            # Check if the actual field exists on the object
            if not hasattr(obj, actual_field_name):
                raise AttributeError(
                    f"Field '{actual_field_name}' does not exist on object of type {type(obj).__name__}. "
                    f"Display name: '{display_name}'. "
                    f"Available fields: {', '.join(f for f, _ in getattr(type(obj), '_fields_', []))}"
                )

            value = getattr(obj, actual_field_name)
            row_layout = self.make_layout(sizing=(FIT(), FIT()), direction=Direction.ROW, child_gap=5, color=None, border=5, padding=Padding(10,10,10,10))
            row_layout.render_path = parent_path
            label = self.make_text(display_name + ": ", "Arial", 16, "black")
            label.render_path = parent_path
            value_layout = field_renderer(
                value,
                parent_path=parent_path + [actual_field_name],
                index_bindings=index_bindings,
                mapping=mapping)
            row_layout.add_child(label)
            row_layout.add_child(value_layout)
            layout.add_child(row_layout)

        return layout

