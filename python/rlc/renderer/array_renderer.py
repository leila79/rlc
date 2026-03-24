from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import Layout, Direction, FIT, Padding
from dataclasses import dataclass
import ctypes

@register_renderer
@dataclass
class ArrayRenderer(Renderable):
    length: int
    element_renderer: Renderable

    def build_layout(self, obj, parent_path, direction=Direction.ROW, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(2,2,2,2), index_bindings=None, mapping=None, byte_offset=0, rlc_type=None):
        if index_bindings is None:
            index_bindings = {}

        layout = self.make_layout(sizing=sizing, direction=direction, color=color, padding=padding, border=3, child_gap=5)
        layout.binding = {"type": "array"}
        layout.render_path = parent_path

        # Apply pre-computed interactions for the array container
        self._apply_interaction_mappings(layout, index_bindings)

        # Compute element type and size for mapping
        elem_rlc_type = rlc_type._type_ if rlc_type and hasattr(rlc_type, '_type_') else None
        elem_size = ctypes.sizeof(elem_rlc_type) if elem_rlc_type else 0

        color = 'lightgray'
        if self.element_renderer is not None:
            # Determine which index variable to bind at this array level
            # Search recursively for interaction mappings in child elements
            index_var_name = None
            deepest_mappings = self.element_renderer._get_deepest_interaction_mappings()
            if deepest_mappings:
                # Use the first mapping's index_vars
                interaction_mapping = deepest_mappings[0]
                # Determine which variable to bind based on how many are already bound
                num_bound = len(index_bindings)
                if num_bound < len(interaction_mapping.index_vars):
                    index_var_name = interaction_mapping.index_vars[num_bound]

            for i in range(self.length):
                item = obj[i]
                # Alternate direction for the next depth
                next_dir = (
                    Direction.ROW if direction == Direction.COLUMN else Direction.COLUMN
                )
                next_color = 'lightblue'

                # Extend index bindings for this array level
                child_index_bindings = index_bindings.copy()
                if index_var_name:
                    child_index_bindings[index_var_name] = i

                child = self.element_renderer(
                    item,
                    parent_path= parent_path + [i],
                    direction=next_dir,
                    logger=logger,
                    color=next_color,
                    sizing=(FIT(), FIT()),
                    padding=Padding(2,2,2,2),
                    index_bindings=child_index_bindings,
                    mapping=mapping,
                    byte_offset=byte_offset + i * elem_size,
                    rlc_type=elem_rlc_type
                )

                layout.add_child(child)
        # Register in sim↔renderer mapping
        if mapping is not None and rlc_type is not None:
            mapping.add_entry(tuple(parent_path), byte_offset,
                              ctypes.sizeof(rlc_type), self, layout)
        return layout

    def update(self, layout, obj, elapsed_time=0.0):
        for i, child in enumerate(layout.children):
            item = obj[i]
            self.element_renderer.update(child, item, elapsed_time)

    def _iter_children(self):
        return [self.element_renderer]

    def apply_interactivity(self, layout_child, index=None, parent_obj=None):
        """Hook for subclasses to mark children interactive."""
        return None

