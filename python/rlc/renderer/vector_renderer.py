from rlc.renderer.renderable import Renderable, register_renderer
from rlc.layout import Layout, Direction, FIT, Padding
from dataclasses import dataclass

@register_renderer
@dataclass
class VectorRenderer(Renderable):
    element_renderer: Renderable

    def build_layout(self, obj, parent_path, direction=Direction.ROW, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(5, 5, 5, 5), index_bindings=None, mapping=None):
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

        # Register so VectorRenderer.update() is called on vector size changes
        if mapping is not None:
            mapping.add_entry(tuple(parent_path), self, layout)

        if not data_ptr or size <= 0:
            return layout

        next_dir = (
            Direction.ROW if direction == Direction.COLUMN else Direction.COLUMN
        )

        index_var_name = None
        deepest_mappings = self.element_renderer._get_deepest_interaction_mappings()
        if deepest_mappings:
            interaction_mapping = deepest_mappings[0]
            num_bound = len(index_bindings)
            if num_bound < len(interaction_mapping.index_vars):
                index_var_name = interaction_mapping.index_vars[num_bound]

        for i in range(size):
            item = data_ptr[i]

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

