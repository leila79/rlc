
from abc import ABC, abstractmethod
from copy import deepcopy
from rlc.layout import Layout, Direction, FIT, Padding
from typing import Dict
from dataclasses import dataclass, field, fields, is_dataclass, MISSING
from rlc.text import Text
import yaml

_renderer_registry = {}  # maps class name → class

class RenderableDumper(yaml.SafeDumper):
    index = 0
    def generate_anchor(self, node: yaml.Node):

        self.index = self.index + 1
        return str(self.index)

class RenderableLoader(yaml.FullLoader):
    pass

def renderable_representer(dumper: RenderableDumper, obj: 'Renderable'):
    tag = obj.yaml_tag()
    mapping = []
    for f in fields(obj):
        value = getattr(obj, f.name)

        # Serialize interaction_mappings if present
        if f.name == "interaction_mappings":
            if value:  # Only add if not empty
                # Convert InteractionMapping objects to dicts for serialization
                from dataclasses import asdict
                mappings_as_dicts = [asdict(m) for m in value]
                mapping.append((f.name, mappings_as_dicts))
            continue

        if f.default is not MISSING and value == f.default:
            continue

        if f.default_factory is not MISSING:
            try:
                default = f.default_factory()
                if value == default:
                    continue
            except TypeError:
                pass

        mapping.append((f.name, value))
    return dumper.represent_mapping(tag, mapping)


def renderable_multi_constructor(loader: RenderableLoader, tag_suffix: str, node):
    """
    tag_suffix is the part after the '!' when using add_multi_constructor("!", ...")
    e.g. YAML tag `!FooRenderer` → tag_suffix == "FooRenderer"
    """
    cls = _renderer_registry[tag_suffix]  # look up the class
    data = loader.construct_mapping(node, deep=True)

    # Handle interaction_mappings separately since it has init=False
    interaction_mappings = None
    if "interaction_mappings" in data:
        from rlc.renderer.interaction_context import InteractionMapping
        mappings_data = data.pop("interaction_mappings")  # Remove from data dict
        interaction_mappings = [InteractionMapping(**m) for m in mappings_data]

    # Create instance without interaction_mappings
    instance = cls(**data)

    # Set interaction_mappings after creation
    if interaction_mappings is not None:
        instance.interaction_mappings = interaction_mappings

    return instance

yaml.add_multi_constructor("!", renderable_multi_constructor, Loader=RenderableLoader)

def register_renderer(cls):
    _renderer_registry[cls.__name__] = cls
    return cls

@dataclass
class Renderable(ABC):
    """
    Base abstract renderer type.
    Each subclasss knows how to convert its types object into a Layout tree.
    """
    rlc_type_name: str
    interaction_mappings: list = field(default_factory=list, repr=False, compare=False, init=False)

    def make_layout(self, direction=Direction.COLUMN, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(2,2,2,2), border=3, child_gap=5) -> Layout:
        layout = Layout(sizing=sizing, direction=direction, color=color, padding=padding, border=border, child_gap=child_gap)

        return layout

    def make_text(self, txt, font_name, font_size, color) -> Text:
        text = Text(txt, font_name, font_size, color)
        return text

    @abstractmethod
    def build_layout(self, obj, direction=Direction.ROW, color="white", sizing=(FIT(), FIT()), logger=None, padding=Padding(2,2,2,2)) -> Layout:
        """Construct and return a Layout tree for the given object."""
        pass

    def apply_interactivity(self, layout_child, index=None, parent_obj=None):
        pass

    def _get_deepest_interaction_mappings(self):
        """
        Recursively find the deepest renderer with interaction mappings.
        Used by containers/arrays to determine which index variables to bind.
        """
        if self.interaction_mappings:
            return self.interaction_mappings

        # Check children recursively
        for child in self._iter_children():
            child_mappings = child._get_deepest_interaction_mappings()
            if child_mappings:
                return child_mappings

        return []

    def _apply_interaction_mappings(self, layout, index_bindings=None):
        """
        Apply pre-computed interaction mappings to a layout node.

        Args:
            layout: The layout node to apply interactions to
            index_bindings: Dict of index variable bindings (e.g., {"x": 4, "y": 5})
        """
        if index_bindings is None:
            index_bindings = {}

        for mapping in self.interaction_mappings:
            metadata = {
                "handler": mapping.handler_name,
                "args": index_bindings.copy(),  # Index vars from array/vector context
                "params": mapping.param_vars  # Event params to be filled at runtime
            }

            # Attach to the appropriate event attribute
            if mapping.event_type == "on_click":
                layout.on_click = metadata
            elif mapping.event_type == "on_key":
                layout.on_key = metadata
            elif mapping.event_type == "on_hover":
                layout.on_hover = metadata
            else:
                # Generic fallback
                setattr(layout, mapping.event_type, metadata)

            # Mark as interactive
            layout.interactive = True

    def update(self, layout, obj, elapsed_time: float = 0.0):
        """
        Update the existing layout tree in place using new data from obj.
        Optionally, use elapsed_time for animations (interpolation).
        """
        pass

    def __call__(self, obj, parent_path=None, **kwds):

        if parent_path is None:
            current_path = [self.rlc_type_name]
        else:
            current_path = list(parent_path)

        layout = self.build_layout(obj=obj, parent_path=current_path, **kwds)

        return layout

    def post_order_types(self):
        frontier = [self]
        seen = set()
        output = []
        while len(frontier) != 0:
            current = frontier.pop(0)
            if id(current) in seen:
                continue
            output.append(current)
            seen.add(id(current))
            for child in current._iter_children():
                frontier.append(child)
        return [x for x in reversed(output)]


    def to_yaml(self):
        return yaml.dump(self.post_order_types(), Dumper=RenderableDumper, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_text):
        return yaml.load(yaml_text, Loader=RenderableLoader)[-1]

    @classmethod
    def yaml_tag(cls) -> str:
        return f"!{cls.__name__}"

    def _iter_children(self):
        """Return iterable of child renderers, if any. Override per subclass."""
        return []

    def print_interaction_tree(self, indent=0):
        """Print the renderer tree with interaction mappings for debugging."""
        prefix = "  " * indent
        has_interactions = len(self.interaction_mappings) > 0
        marker = " ✓" if has_interactions else ""
        print(f"{prefix}{self.__class__.__name__}('{self.rlc_type_name}'){marker}")

        if has_interactions:
            for mapping in self.interaction_mappings:
                print(f"{prefix}  → {mapping.event_type}: {mapping.handler_name}")
                if mapping.index_vars:
                    print(f"{prefix}    index_vars={mapping.index_vars}")
                if mapping.param_vars:
                    print(f"{prefix}    param_vars={mapping.param_vars}")

        for child in self._iter_children():
            child.print_interaction_tree(indent + 1)

yaml.add_multi_representer(Renderable, renderable_representer, Dumper=RenderableDumper)
