from command_line import load_program_from_args, make_rlc_argparse
from typing import Type
from ctypes import c_long, Array, c_bool
import pygame
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from rlc.scene_graph import state_to_scene, scene_to_layout, print_scene


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

def dump_python_type(rlc_type: Type, depth=0):
    print(" " * depth, rlc_type.__name__)
    for type in rlc_type.child_types:
        dump_python_type(type, depth+1)

def dump_rlc_type(rlc_type: Type, depth=0):
    print(" " * depth, rlc_type.__name__)
    if issubclass(rlc_type, Array):
        return dump_rlc_type(rlc_type._type_, depth+1)
    if rlc_type == c_bool:
        return
    if rlc_type == c_long:
        return
    for field in rlc_type._fields_:
        dump_rlc_type(field[1], depth+1)

if __name__ == "__main__":
    parser = make_rlc_argparse("game_display", description="Display game state")
    args = parser.parse_args()
    with load_program_from_args(args, optimize=True) as program:
        state = program.start()
        dump_rlc_type(program.module.Game)
        print(f"State object: {state.state}")

        logger = LayoutLogger(LayoutLogConfig())
        logger = None
        scene_root = state_to_scene(state=state.state, typ=program.module.Game)
        print("=== Abstract Scene Graph (Reusable Structure) ===")
        print_scene(scene_root)
        print("=== End Scene Graph ===\n")
        root = scene_to_layout(scene_root)
        root.print_layout()
        
        
        pygame.init()  # Already done at module level, but kept for clarity
        screen = pygame.display.set_mode((1280, 720))
        screen.fill("white")
        clock = pygame.time.Clock()
        running = True
        backend = PygameRenderer(screen)

        root.compute_size(logger=logger, backend=backend)
        print(f"Root size: {root.width}x{root.height}, children={[c.height for c in root.children]}")
        root.layout(20, 20, logger=logger)
        print(f"Root size: {root.width}x{root.height}, children={[c.height for c in root.children]}")
        if logger: 
            logger.record_final_tree(root=root)
            print(logger.to_text_tree(root))
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            
            render(backend, root)
            pygame.display.flip()
            clock.tick(60)
        
        pygame.quit()

