from command_line import load_program_from_args, make_rlc_argparse
from rlc import Program
from typing import Type
from typing import Dict
from ctypes import c_long, Array, c_bool
from rlc.renderer.factory import RendererFactory
from rlc.serialization.renderer_serializer import save_renderer
from rlc.renderer.interaction_context import InteractionContext
import os
# from red_board_renderer import RedBoard


def make_array_accessor(index):
    def access(obj):
        return obj[index]
    return access

def make_object_accessor(name):
    def access(obj):
        return getattr(obj, name)
    return access

def make_single_element_container_accessor(rlc_type, name=None):
    if not hasattr(rlc_type, "_fields_") or len(rlc_type._fields_) == 0:
        if name is None:
            return (rlc_type, lambda x: x)
        return (rlc_type, make_object_accessor(name))
    if len(rlc_type._fields_) > 1:  # Multi-field struct, return original
        return (rlc_type, lambda x: x)
    (name, typ) = rlc_type._fields_[0]
    accessor = make_object_accessor(name)
    while hasattr(typ, "_fields_") and len(typ._fields_) == 1:
        rlc_type = typ
        (name, typ) = rlc_type._fields_[0]
        newacc = lambda obj: make_object_accessor(name)(accessor(obj))
        accessor = newacc
    return (typ, accessor)

def dump_rlc_type(rlc_type: Type, depth=0):
    print("-" * depth, rlc_type.__name__)
    
    
    if rlc_type == c_bool:
        return
    if rlc_type == c_long:
        return
    if hasattr(rlc_type, "_length_") and hasattr(rlc_type, "_type_"):
        return dump_rlc_type(rlc_type._type_, depth+1)
    if hasattr(rlc_type, "_type_"):
        (typ, accessor) = make_single_element_container_accessor(rlc_type._type_)
        dump_rlc_type(accessor(typ), depth+1)
    if hasattr(rlc_type, "_fields_") :
        for field in rlc_type._fields_:
            dump_rlc_type(field[1], depth+1)



if __name__ == "__main__":
    parser = make_rlc_argparse("game_display", description="Display game state")
    args = parser.parse_args()
    with load_program_from_args(args, optimize=True) as program:
        # derive a save path from the input file name
        source_file = args.source_file
        base_name = os.path.splitext(os.path.basename(source_file))[0] if source_file else "renderer"
        save_path = os.path.join("./logs", f"{base_name}.yaml")

        # dump_rlc_type(program.module.Game)

        # Load interaction config at compile-time
        interaction_ctx = InteractionContext.from_config_file()

        config = {
            # 'Board' : {
            #     'renderer' : RedBoard
            # }
        }  # Custom renderer overrides (e.g., {Board: RedBoard})

        # Build renderer tree with interaction mappings
        # Start with rlc_path=['Game'] so the root type name is in the path
        renderer = RendererFactory.from_rlc_type(
            program.module.Game,
            config,
            interaction_ctx=interaction_ctx,
            rlc_path=['Game']
        )

        # Save renderer with interaction mappings to YAML
        save_renderer(renderer, save_path)
        print(f"[saved] renderer -> {save_path}")
