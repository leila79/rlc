# rlc/renderer/factory.py
from typing import Dict
from ctypes import c_long, c_bool
from rlc.renderer.renderable import Renderable
from rlc.renderer.primitive_renderer import PrimitiveRenderer
from rlc.renderer.bint_renderer import BoundedIntRenderer
from rlc.renderer.array_renderer import ArrayRenderer
from rlc.renderer.vector_renderer import VectorRenderer
from rlc.renderer.struct_renderer import ContainerRenderer
from rlc.renderer.bounded_vector_renderer import BoundedVectorRenderer


class RendererFactory:
    """
    Stateless renderer factory used for:
    - building renderers from RLC ctypes 
    - rebuilding renderers from JSON 
    """

    _cache = {}
    @classmethod
    def from_rlc_type(cls, rlc_type, config : Dict[type, type], interaction_ctx=None, rlc_path=None):
        """
        Build a renderer tree from RLC types with optional interaction config.

        Args:
            rlc_type: The RLC ctypes structure to create renderer for
            config: { rlc_type : RendererClass } for user overrides
            interaction_ctx: InteractionContext for compile-time interaction resolution
            rlc_path: Current path in RLC type tree for interaction mapping
        """
        if config is None:
            config = {}

        if rlc_path is None:
            rlc_path = []

        # Note: Cache disabled to avoid stale interaction mappings
        # if rlc_type in cls._cache:
        #     return cls._cache[rlc_type]

        name = getattr(rlc_type, "__name__", str(rlc_type))

        # Helper to apply interactions after creating a renderer
        def _apply_interactions(renderer, current_path):
            if interaction_ctx:
                mappings = interaction_ctx.resolve_interactions(id(renderer), current_path)
                renderer.interaction_mappings = mappings
            return renderer

        # 1. User-specified renderer override (for custom classes)
        custom_conf = config.get(name, {})
        custom_renderer_class = custom_conf.get("renderer")
        print(name, custom_conf, custom_renderer_class)
        # if custom_renderer_class is not None:
        #     custom_conf = {}

        def _container_renderer(renderer_cls):
            fields = renderer_cls.create_fields(cls.from_rlc_type, rlc_type, rlc_path, config, interaction_ctx)
            renderer = renderer_cls(rlc_type.__name__, fields)
            # cls._cache[rlc_type] = renderer
            # Containers themselves don't add their type name to the path
            return _apply_interactions(renderer, rlc_path)

        if "Hidden" in name and hasattr(rlc_type, "_fields_"):
            return None
            # renderer_cls = custom_renderer_class or ContainerRenderer
            # return _container_renderer(renderer_cls)
            
        # 2. BoundedVector (check before general vector to use correct renderer)
        if "Bounded" in name and cls._is_vector(rlc_type):
            renderer_cls = custom_renderer_class or BoundedVectorRenderer
            field = None
            for fname, ftype in getattr(rlc_type, "_fields_", []):
                child_path = rlc_path
                candidate = cls.from_rlc_type(ftype, config, interaction_ctx, child_path)
                if candidate is not None:
                    field = candidate
                    break
            renderer = renderer_cls(rlc_type.__name__, field)
            # cls._cache[rlc_type] = renderer
            return _apply_interactions(renderer, rlc_path)

        # 3. Vector-like containers (Vector, Dictionary, etc.)
        # Uses structural detection: types with _data and _size fields
        if cls._is_vector(rlc_type):
            if custom_renderer_class:
                renderer_cls = custom_renderer_class
            else:
                renderer_cls = VectorRenderer
            element = cls._extract_vector_element(rlc_type)
            # Vector elements use index variables in path
            element_renderer = cls.from_rlc_type(element, config, interaction_ctx, rlc_path + ["$i"])
            renderer = renderer_cls(rlc_type.__name__, element_renderer)
            # cls._cache[rlc_type] = renderer
            return _apply_interactions(renderer, rlc_path)

        # 4. Array
        if hasattr(rlc_type, "_length_") and hasattr(rlc_type, "_type_"):
            if custom_renderer_class:
                renderer_cls = custom_renderer_class
            else:
                renderer_cls = ArrayRenderer
            element_renderer = cls.from_rlc_type(rlc_type._type_, config, interaction_ctx, rlc_path + ["$i"])
            renderer = renderer_cls(
                rlc_type.__name__,
                rlc_type._length_,
                element_renderer
            )
            # cls._cache[rlc_type] = renderer
            return _apply_interactions(renderer, rlc_path)

        # 5. Bounded int
        if name.startswith("BInt"):
            if custom_renderer_class:
                renderer_cls = custom_renderer_class
            else:
                renderer_cls = BoundedIntRenderer
            renderer = renderer_cls(rlc_type.__name__)
            # cls._cache[rlc_type] = renderer
            # Check interactions at the current path (without adding type name)
            return _apply_interactions(renderer, rlc_path)

        # 6. Primitive
        if rlc_type in (c_long, c_bool):
            if custom_renderer_class:
                renderer_cls = custom_renderer_class
            else:
                renderer_cls = PrimitiveRenderer
            renderer = renderer_cls(rlc_type.__name__)
            # cls._cache[rlc_type] = renderer
            # Check interactions at the current path (without adding type name)
            return _apply_interactions(renderer, rlc_path)

        # 7. Struct (object with fields)
        if hasattr(rlc_type, "_fields_"):
            renderer_cls = custom_renderer_class or ContainerRenderer
            return _container_renderer(renderer_cls)

        # 8. Fallback: treat as primitive
        renderer = PrimitiveRenderer(rlc_type.__name__)
        # cls._cache[rlc_type] = renderer
        # Check interactions at the current path (without adding type name)
        return _apply_interactions(renderer, rlc_path)

    @staticmethod
    def _is_vector(rlc_type) -> bool:
        """
        Check if type is vector by structure or name.

        Uses hybrid approach:
        1. First checks for vector structure (_data + _size fields)
        2. Falls back to name pattern matching for backward compatibility
        """
        name = getattr(rlc_type, "__name__", "")
        fields = getattr(rlc_type, "_fields_", [])
        field_names = {fname for fname, _ in fields}

        # Check structure first (preferred for generalization)
        if "_data" in field_names and "_size" in field_names:
            return True

        # Fallback to name patterns for backward compatibility
        return "Vector" in name and hasattr(rlc_type, "_fields_")

    # Extract element type from Vector<T>
    @staticmethod
    def _extract_vector_element(rlc_type):
        visited = set()
        current = rlc_type

        while True:
            if current in visited:
                raise ValueError(f"Cannot resolve vector element type for {rlc_type}")
            visited.add(current)

            name = getattr(current, "__name__", "")

            # --- Case 1: Hidden<T> wrapper ---------------------------------------
            if name.startswith("HiddenT"):
                fields = getattr(current, "_fields_", [])
                if len(fields) != 1:
                    raise ValueError(f"Hidden type {current} has {len(fields)} fields, expected 1")
                _, underlying = fields[0]
                current = underlying
                continue

            # --- Case 2: Find _data pointer inside vector-like struct ------------
            for field_name, field_type in getattr(current, "_fields_", []):
                if field_name == "_data":
                    # Direct pointer to element = element type found
                    elem = getattr(field_type, "_type_", None)
                    if elem is not None:
                        return elem

                    # Otherwise the field is another wrapper: descend into it
                    current = field_type
                    break
            else:
                raise ValueError(f"Cannot determine element type for vector-like type: {current}")

    @staticmethod
    def from_json_file(path: str):
        import json
        with open(path, "r") as f:
            data = json.load(f)
        return Renderable.from_dict(data)

    @staticmethod
    def from_json_string(text: str):
        import json
        return Renderable.from_dict(json.loads(text))
