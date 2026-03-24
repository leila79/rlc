from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import Layout, FIT, Direction, Padding
from rlc.text import Text
from dataclasses import dataclass




@register_renderer
@dataclass
class ContainerRenderer(Renderable):
    field_renderers: dict  # {display_name: (actual_field_name, renderer)}


    @staticmethod
    def create_fields(factory, rlc_type, rlc_path, config, interaction_ctx):
        """
        Create field renderers for a struct type.

        Returns:
            Dict mapping display_name -> (actual_field_name, renderer)
            By default, display_name == actual_field_name, but subclasses
            can transform the display name while preserving the actual field name.
        """
        fields = {}
        for fname, ftype in getattr(rlc_type, "_fields_", []):
            # Child paths include only the field name, not type names
            child_path = rlc_path + [fname]
            child_renderer = factory(ftype, config, interaction_ctx, child_path)
            if child_renderer is None:
                continue
            # Store as (actual_field_name, renderer) tuple
            fields[fname] = (fname, child_renderer)
        return fields

    def build_layout(self, obj, parent_path, direction=Direction.COLUMN, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(7,7,7,7), index_bindings=None, mapping=None, byte_offset=0, rlc_type=None):
        if index_bindings is None:
            index_bindings = {}

        layout = self.make_layout(sizing=sizing, direction=direction, child_gap=5, color=color, border=5, padding=padding)
        layout.binding = {"type": "struct"}
        layout.render_path = parent_path

        # Apply pre-computed interactions
        self._apply_interaction_mappings(layout, index_bindings)

        # Build field type lookup for byte offset computation
        field_types = {fname: ftype for fname, ftype in getattr(rlc_type, "_fields_", [])} if rlc_type else {}

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

            # Compute child byte offset and type for mapping
            child_rlc_type = field_types.get(actual_field_name)
            child_byte_offset = byte_offset
            if rlc_type and child_rlc_type:
                field_desc = getattr(rlc_type, actual_field_name, None)
                if field_desc and hasattr(field_desc, 'offset'):
                    child_byte_offset = byte_offset + field_desc.offset

            # Create a row for "name: value"
            value = getattr(obj, actual_field_name)
            row_layout = self.make_layout(sizing=(FIT(), FIT()), direction=Direction.ROW, child_gap=5, color=None, border=5, padding=Padding(10,10,10,10))
            row_layout.render_path = parent_path
            label = self.make_text(display_name + ": ", "Arial", 16, "black")
            label.render_path = parent_path
            value_layout = field_renderer(
                value,
                parent_path= parent_path + [actual_field_name],
                index_bindings=index_bindings,
                mapping=mapping,
                byte_offset=child_byte_offset,
                rlc_type=child_rlc_type)
            row_layout.add_child(label)
            row_layout.add_child(value_layout)
            layout.add_child(row_layout)
        # Register in sim↔renderer mapping
        if mapping is not None and rlc_type is not None:
            import ctypes
            mapping.add_entry(tuple(parent_path), byte_offset,
                              ctypes.sizeof(rlc_type), self, layout)
        return layout

    def update(self, layout, obj, elapsed_time=0.0):
        for (display_name, field_data), child_layout in zip(self.field_renderers.items(), layout.children):
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
            field_renderer.update(child_layout.children[-1], value, elapsed_time)

    def _iter_children(self):
        # Only return child renderers (extract from tuples)
        return [renderer for field_data in self.field_renderers.values() if field_data is not None for _, renderer in [field_data]]

