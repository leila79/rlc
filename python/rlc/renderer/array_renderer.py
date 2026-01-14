from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import Layout, Direction, FIT, Padding
from dataclasses import dataclass

@register_renderer
@dataclass
class ArrayRenderer(Renderable):
    length: int
    element_renderer: Renderable

    def build_layout(self, obj, parent_path, direction=Direction.ROW, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(2,2,2,2), index_bindings=None):
        if index_bindings is None:
            index_bindings = {}

        layout = self.make_layout(sizing=sizing, direction=direction, color=color, padding=padding, border=3, child_gap=5)
        layout.binding = {"type": "array"}
        layout.render_path = parent_path

        # Apply pre-computed interactions for the array container
        self._apply_interaction_mappings(layout, index_bindings)

        color = 'lightgray'
        if self.element_renderer is not None:
            # Determine which index variable to bind at this array level
            # Search recursively for interaction mappings in child elements
            index_var_name = None
            deepest_mappings = self.element_renderer._get_deepest_interaction_mappings()
            if deepest_mappings:
                # Use the first mapping's index_vars
                mapping = deepest_mappings[0]
                # Determine which variable to bind based on how many are already bound
                num_bound = len(index_bindings)
                if num_bound < len(mapping.index_vars):
                    index_var_name = mapping.index_vars[num_bound]

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
                    index_bindings=child_index_bindings
                )

                layout.add_child(child)
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

