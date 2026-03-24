from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import Layout, Direction, FIT, Padding
from dataclasses import dataclass

@register_renderer
@dataclass
class VectorRenderer(Renderable):
    element_renderer: Renderable

    def build_layout(self, obj, parent_path, direction=Direction.ROW, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(5, 5, 5, 5), index_bindings=None, mapping=None, byte_offset=0, rlc_type=None):
        if index_bindings is None:
            index_bindings = {}

        data_ptr = getattr(obj, "_data", None)
        size = getattr(obj, "_size", None)

        if size is None and hasattr(obj, "_length_"):
            size = obj._length_
        size = size or 0

        layout = self.make_layout(
            sizing=sizing,
            direction=direction,
            child_gap=5,
            padding=padding,
            color=color
        )
        layout.render_path = parent_path

        # Apply pre-computed interactions for the vector container
        self._apply_interaction_mappings(layout, index_bindings)

        # Register as heap_dependent: vector data lives on the heap,
        # so struct-level snapshot diffs can't detect changes
        if mapping is not None and rlc_type is not None:
            import ctypes
            mapping.add_entry(tuple(parent_path), byte_offset,
                              ctypes.sizeof(rlc_type), self, layout,
                              heap_dependent=True)

        if not data_ptr or size <= 0:
            return layout

        # Alternate direction for the next nesting level
        next_dir = (
            Direction.ROW if direction == Direction.COLUMN else Direction.COLUMN
        )

        # Determine which index variable to bind at this vector level
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

        # Iterate over elements
        for i in range(size):
            item = data_ptr[i]

            # Extend index bindings for this vector level
            child_index_bindings = index_bindings.copy()
            if index_var_name:
                child_index_bindings[index_var_name] = i

            child_layout = self.element_renderer(
                item,
                parent_path=parent_path + [i],
                direction=next_dir,
                color="lightgray",
                sizing=(FIT(), FIT()),
                logger=logger,
                index_bindings=child_index_bindings,
                mapping=mapping,
                byte_offset=byte_offset,
                rlc_type=rlc_type
            )

            layout.add_child(child_layout)

        return layout

    def update(self, layout, obj, elapsed_time=0.0):
        new_size = obj.size()
        old_size = len(layout.children)

        if new_size > old_size:
            for i in range(old_size, new_size):
                item = obj.get(i).contents
                child_layout = self.element_renderer(
                    item,
                    direction=layout.direction,
                    color="lightgray",
                    sizing=(FIT(), FIT()),
                )
                layout.add_child(child_layout)
            layout.is_dirty = True
        elif new_size < old_size:
            layout.children = layout.children[:new_size]
            layout.is_dirty = True

        for i in range(min(new_size, old_size)):
            item = obj.get(i).contents
            self.element_renderer.update(layout.children[i], item, elapsed_time)

    def _iter_children(self):
        return [self.element_renderer]

