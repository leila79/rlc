from typing import Dict, Tuple, List, Optional, Any
from .layout import Layout, Direction, FIT, FIXED, GROW, Padding
from .text import Text
from ctypes import c_long, Array, c_bool


# For non-square, could add more logic (e.g., check nested arrays for 2D)

class SceneNode:
    def __init__(self, kind: str, children: Optional[List['SceneNode']] = None, value: Any = None, label: str = "", meta: dict = None):
        self.kind = kind          
        self.children = children if children is not None else []
        self.value = value                 
        self.meta = meta or {} 

    def add_child(self, child: 'SceneNode'):
        self.children.append(child)

def detect_array_dimensions(typ) -> Optional[Tuple[int, ...]]:
    """
    Recursively detect ctypes.Array grid dimensions.
    Works for nested arrays like Array[3][3], Array[2][3][4], etc.

    Returns:
        A tuple of dimensions (e.g., (3, 3) or (2, 3, 4)).
        Returns None if not an Array.
    """
    if not issubclass(typ, Array):
        return None

    dims = [typ._length_]
    inner = typ._type_
    while issubclass(inner, Array):
        dims.append(inner._length_)
        inner = inner._type_
    return tuple(dims)


def state_to_scene(state, typ, context: dict = None) -> SceneNode:
    """Recursively transform game state into a generic, reusable scene graph.
    
    Args:
        state: The game state or value to transform.
        typ: The RLC type of the state.
        context: Optional dictionary for configuration (e.g., field names).
    
    Returns:
        A SceneNode representing the state.
    """
    context = context or {}
    if hasattr(typ, "_fields_"):  # Struct
        node = SceneNode("struct", label=typ.__name__, meta={"context": context.get("struct_meta", {})})
        for field_name, field_type in typ._fields_:
            field_value = getattr(state, field_name)
            child_context = context.copy()
            child_context["field_name"] = field_name
            child = state_to_scene(field_value, field_type, child_context)
            label_node = SceneNode("label", value=field_name)
            label_node.add_child(child=child)
            node.add_child(label_node)
        return node
    elif issubclass(typ, Array):  # Array
        array_dimensions = detect_array_dimensions(typ)
        node = SceneNode("array", label=typ.__name__, meta={
            "context": context.get("array_meta", {}),
            "dims": array_dimensions})
        for i in range(typ._length_):
            child_context = {**context, "index": i}
            child = state_to_scene(state[i], typ._type_, child_context)
            node.add_child(child)
        return node
    if typ == c_bool:
        print("primitive state of bool --> ", state)
        node = SceneNode(kind="value", value="True" if state else "False", meta={"context": context})
        print("primitive state --> ", node.value)
        return node
    if typ == c_long:
        print("primitive state of long --> ", state)
        node = SceneNode(kind="value", value=str(state), meta={"context": context})
        print("primitive state --> ", node.value)
        return node
    else:  # Primitive (int, bool, str)
        print("primitive state --> ", state)
        node = SceneNode(kind="value", value=state, meta={"context": context.get("value_meta", {})})
        if context.get("editable", False):
            node.meta["editable"] = True  # Flag for editing interfaces
        print("primitive state --> ", node.value)
        return node
    

def array_to_layout(node: SceneNode, state_path: Tuple[str, ...] = (), direction: Direction = Direction.ROW):
    layout = Layout(sizing=(FIT(), FIT()), direction=direction, child_gap=5, padding=Padding(5,5,5,5), color="pink", border=2)
    for i, child in enumerate(node.children):
        if child.kind == "array":
            layout.add_child(array_to_layout(node=child,
                                              state_path=(state_path + (i,)),
                                                direction=(Direction.COLUMN if direction == Direction.ROW else Direction.ROW)))
        else:
            layout.add_child(scene_to_layout(node=child, state_path=(state_path + (i,))))
    return layout


def scene_to_layout(node: SceneNode, state_path: Tuple[str, ...] = ()) -> Layout:
    """Transform a generic scene graph into a concrete layout for rendering."""
    if node.kind == "array":
        return array_to_layout(node, state_path, Direction.ROW)
    elif node.kind == "struct":
        layout = Layout(sizing=(FIT(), FIT()), direction=Direction.ROW, child_gap=5, border=2, color="lightgray")
        for i, child in enumerate(node.children):  # Process label and value pairs
            layout.add_child(scene_to_layout(child, state_path + (i, )))
        return layout
    elif node.kind == "label":
        layout = Layout(sizing=(FIT(), FIT()), direction=Direction.ROW, color="pink")
        label_text = Text(str(node.value) + ": ", "Arial", 26, "black")
        child_layout = scene_to_layout(node.children[0], state_path + (1,))
        layout.add_child(label_text)
        layout.add_child(child_layout)
        return layout
    elif node.kind == "value":
        return Text(str(node.value), "Arial", 26, "black")
    else:
        # Fallback for unrecognized kinds
        return Layout(sizing=(FIT(), FIT()))
    

    
def print_scene(node: SceneNode, depth: int = 0, prefix: str = ""):
    """Print the scene graph in a hierarchical, readable format.
    
    Args:
        node: The SceneNode to print.
        depth: The current indentation level.
        prefix: The prefix for the current node (e.g., for multi-line values).
    """
    indent = "  " * depth
    meta_str = f", meta={node.meta}" if node.meta else ""
    print(f"{indent}{prefix}{node.kind} (value={node.value}{meta_str})")
    for child in node.children:
        print_scene(child, depth + 1)