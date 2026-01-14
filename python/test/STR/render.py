from command_line import load_program_from_args, make_rlc_argparse
from rlc import Program
from typing import Type
from typing import Dict
from ctypes import c_long, Array, c_bool
from rlc.renderer.factory import RendererFactory
from test.red_board_renderer import RedBoard
from test.tic_tac_toe_board import TicTacToeBoardRenderer
from rlc.layout import  Direction
import os
import pygame, time, random
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from rlc.renderer.config_parser import ACTION_REGISTRY


  
def any_child_dirty(layout):
    if getattr(layout, "is_dirty", False):
        layout.is_dirty = False
        return True
    return any(any_child_dirty(c) for c in layout.children if hasattr(c, "children"))

def new_timing_bucket():
    # count, total_seconds, max_seconds
    return {"count": 0, "total": 0.0, "max": 0.0}

def _record_timing(bucket, elapsed):
    bucket["count"] += 1
    bucket["total"] += elapsed
    bucket["max"] = max(bucket["max"], elapsed)

def print_timings(label, compute_bucket, layout_bucket):
    def fmt(b):
        if b["count"] == 0:
            return "0 runs"
        avg = (b["total"] / b["count"]) * 1000
        return f"{b['count']} runs | avg {avg:.3f} ms | max {b['max']*1000:.3f} ms"
    print(f"[timing] {label} | compute_size: {fmt(compute_bucket)} | layout: {fmt(layout_bucket)}")

def _clamp_scroll(layout, screen, scroll, margin):
    view_w = max(0, screen.get_width() - 2 * margin)
    view_h = max(0, screen.get_height() - 2 * margin)
    max_x = max(0, layout.width - view_w)
    max_y = max(0, layout.height - view_h)
    scroll["x"] = min(0, max(-max_x, scroll["x"]))
    scroll["y"] = min(0, max(-max_y, scroll["y"]))

def relayout(screen, backend, layout, logger, compute_times, layout_times, scroll, margin=20):
    """Resize-aware layout: fit inside the window minus a margin and apply scroll offsets."""
    avail_w = max(0, screen.get_width() - 2 * margin)
    avail_h = max(0, screen.get_height() - 2 * margin)
    t0 = time.perf_counter()
    layout.compute_size(available_width=avail_w, available_height=avail_h, logger=logger, backend=backend)
    _record_timing(compute_times, time.perf_counter() - t0)
    _clamp_scroll(layout, screen, scroll, margin)
    t0 = time.perf_counter()
    layout.layout(margin + scroll["x"], margin + scroll["y"], logger=logger)
    _record_timing(layout_times, time.perf_counter() - t0)

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

def play_random_turn(elapsed_time, state, renderer, layout):
        actions = state.legal_actions or []
        if not actions:
            return False
        action = random.choice(actions)
        print(action)
        state.step(action)
        renderer.update(layout, state.state, elapsed_time)
        layout.is_dirty = True
        return True

if __name__ == "__main__":
    parser = make_rlc_argparse("game_display", description="Display game state")
    args = parser.parse_args()
    with load_program_from_args(args, optimize=True) as program:

        # dump_rlc_type(program.module.Game)

        config = {}
        
        
        renderer = RendererFactory.from_rlc_type(program.module.Game, config)
        # print(renderer)
        pygame.init()  
        screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        screen.fill("white")
        clock = pygame.time.Clock()
        backend = PygameRenderer(screen)
        running = True
        iterations = 1
        current = 0
        STEP_DELAY = 2  # seconds per state
        logger = LayoutLogger(LayoutLogConfig())
        logger = None
        state = None
        scroll = {"x": 0, "y": 0}


        while running and current < iterations:
            compute_times = new_timing_bucket()
            layout_times = new_timing_bucket()
            print(f"\n=== Iteration {current + 1}/{iterations} ===")
            if hasattr(state, "reset"):
                state.reset()
            else:
                state = program.start()
            layout = renderer(state.state)
            layout.print_path()
            actions = state.legal_actions
            relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)

            if logger: 
                logger.record_final_tree(root=layout)
                # print(logger.to_text_tree(layout))
        
            last_update = time.time()
            accumulated_time = 0.0
            elapsed = 0.0
            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    if event.type == pygame.VIDEORESIZE:
                        screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                        backend = PygameRenderer(screen)
                        relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)
                    if event.type == pygame.MOUSEWHEEL:
                        # y is vertical wheel, x is horizontal wheel; positive y = scroll up
                        scroll["y"] += event.y * 30
                        scroll["x"] += event.x * 30
                        relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        mx, my = pygame.mouse.get_pos()
                        target = layout.find_target(mx, my)
                        # print(target.render_path,  hasattr(target, "on_click"))
                        
                        if target and hasattr(target, "on_click"):
                            meta = target.on_click
                            if meta:
                                handler = meta["handler"]
                                args = meta["args"]
                                print(handler, ACTION_REGISTRY)
                                changed = ACTION_REGISTRY[handler](state, **args)
                                if changed:
                                    layout.is_dirty = True
                                if layout.is_dirty or any_child_dirty(layout):
                                    relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)

                elapsed = clock.tick(60) / 1000.0
                accumulated_time += elapsed
                
                if accumulated_time >= STEP_DELAY:
                    accumulated_time = 0.0
                    if not state.is_done():
                        # if state.state.shuffling.to_shuffle > 0:
                        if play_random_turn(elapsed, state, renderer, layout):
                            relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)
                        else:
                            pass
                    else:
                        print("Game done.")
                        break
                screen.fill("white")
                render(backend, layout)
                pygame.display.flip()
            current += 1
            print_timings(f"iteration {current}", compute_times, layout_times)
            time.sleep(1.0)
        
    pygame.quit()
