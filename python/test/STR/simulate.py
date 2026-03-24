import os
from command_line import load_program_from_args, make_rlc_argparse
from rlc import Program
import pygame, time, random
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from rlc.serialization.renderer_serializer import load_renderer
from rlc.renderer.config_parser import  action, ACTION_REGISTRY
from rlc.event_queue import UpdateController, UpdateSignal, SignalKind
from rlc.sim_renderer_mapping import SimRendererMapping

  
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

def play_random_turn(state, controller):
        actions = state.legal_actions or []
        if not actions:
            return False
        action = random.choice(actions)
        print(action)
        state.step(action)
        controller.notify_state_changed()
        return True

if __name__ == "__main__":
    parser = make_rlc_argparse("game_display", description="Display game state")
    args = parser.parse_args()
    with load_program_from_args(args, optimize=True) as program:

        pygame.init()
        screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        screen.fill("white")
        clock = pygame.time.Clock()
        backend = PygameRenderer(screen)
        running = True
        source_file = args.source_file
        base_name = os.path.splitext(os.path.basename(source_file))[0] if source_file else "renderer"
        load_path = os.path.join("./logs", f"{base_name}.yaml")

        renderer = load_renderer(load_path)
        print(renderer)
        iterations = 1
        current = 0
        STEP_DELAY = 2  # seconds per state
        logger = LayoutLogger(LayoutLogConfig())
        logger = None
        state = None

        while running and current < iterations:
            compute_times = new_timing_bucket()
            layout_times = new_timing_bucket()
            print(f"\n=== Iteration {current + 1}/{iterations} ===")
            if hasattr(state, "reset"):
                state.reset()
            else:
                state = program.start()
            mapping = SimRendererMapping()
            layout = renderer(state.state, parent_path=[], mapping=mapping)
            layout.print_path()
            actions = state.legal_actions
            mapping.print_mapping()

            # Dispatch callback: simulate handlers take (state, **args) only
            def dispatch_action(handler_name, args):
                return ACTION_REGISTRY[handler_name](state, **args)

            def do_relayout():
                relayout(screen, backend, layout, logger, compute_times, layout_times, controller.scroll)

            controller = UpdateController(renderer, layout, do_relayout, dispatch_action,
                                          mapping=mapping, state_obj=state.state,
                                          program_module=program.module)
            do_relayout()

            if logger:
                logger.record_final_tree(root=layout)

            accumulated_time = 0.0
            elapsed = 0.0
            while running:
                # Phase 1: COLLECT
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False

                    elif event.type == pygame.VIDEORESIZE:
                        screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                        backend = PygameRenderer(screen)
                        controller.enqueue(UpdateSignal(kind=SignalKind.RESIZE))

                    elif event.type == pygame.MOUSEWHEEL:
                        controller.enqueue(UpdateSignal(
                            kind=SignalKind.SCROLL,
                            dy=event.y * 30,
                            dx=event.x * 30))

                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        mx, my = pygame.mouse.get_pos()
                        target = layout.find_target(mx, my)
                        if target and hasattr(target, "on_click") and target.on_click:
                            meta = target.on_click
                            controller.enqueue(UpdateSignal(
                                kind=SignalKind.ACTION,
                                handler_name=meta["handler"],
                                args=meta["args"]))

                # Auto-play on timer
                elapsed = clock.tick(60) / 1000.0
                accumulated_time += elapsed

                if accumulated_time >= STEP_DELAY:
                    accumulated_time = 0.0
                    if not state.is_done():
                        play_random_turn(state, controller)
                    else:
                        print("Game done.")
                        break

                # Phases 2-4: MUTATE, UPDATE, RELAYOUT (once per frame)
                controller.process(state.state, elapsed)

                # Phase 5: RENDER
                screen.fill("white")
                render(backend, layout)
                pygame.display.flip()
            current += 1
            print_timings(f"iteration {current}", compute_times, layout_times)
            time.sleep(1.0)

    pygame.quit()
