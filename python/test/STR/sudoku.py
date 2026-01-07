from command_line import load_program_from_args, make_rlc_argparse
from rlc import Program
from rlc.renderer.factory import RendererFactory
import pygame, time, random
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from simulate import new_timing_bucket, relayout, any_child_dirty, print_timings
from rlc.renderer.config_parser import action, ACTION_REGISTRY

@action("select_cell")
def select_cell(program, state, x, y):
    """Handler for clicking a cell - just returns True to indicate success"""
    print(f"Selected cell at ({x}, {y})")
    return True

@action("input_value")
def input_value(program, state, x, y, value):
    """Handler for keyboard input on a focused cell"""
    # Convert pygame keycode to digit
    if pygame.K_1 <= value <= pygame.K_9:
        digit = value - pygame.K_0
    else:
        print(f"Invalid key: {value}")
        return False

    print(f"Input {digit} at cell ({x}, {y})")

    # Apply the move
    mod = program.module
    pos_r = mod.make_pos(x)
    pos_c = mod.make_pos(y)
    num = mod.make_num(digit)

    if hasattr(state.state, "can_place") and not state.state.can_place(num, pos_r, pos_c):
        print(f"Cannot place {digit} at ({x}, {y})")
        return False

    state.state.place(num, pos_r, pos_c)
    return True

if __name__ == "__main__":
    parser = make_rlc_argparse("game_display", description="Display game state")
    args = parser.parse_args()
    with load_program_from_args(args, optimize=True) as program:

        config = {}
        renderer = RendererFactory.from_rlc_type(program.module.Game, config)

        pygame.init()  
        screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        screen.fill("white")
        clock = pygame.time.Clock()
        backend = PygameRenderer(screen)
        running = True
        
        # renderer.print_tree()
        iterations = 1
        current = 0
        STEP_DELAY = 0.9  # seconds per state
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
            # layout.propagate_interactive()
            # layout.print_path()
            actions = state.legal_actions
            relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)

            if logger:
                logger.record_final_tree(root=layout)
        
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

                        if target and hasattr(target, "on_click"):
                            # Execute click handler
                            meta = target.on_click
                            handler = meta["handler"]
                            args = meta["args"]
                            changed = ACTION_REGISTRY[handler](program, state, **args)

                            # Auto-focus the clicked cell
                            layout.set_focus(target)

                            if changed:
                                layout.is_dirty = True
                            if layout.is_dirty or any_child_dirty(layout):
                                relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)
                        else:
                            # Clicking elsewhere unfocuses
                            layout.set_focus(None)

                    if event.type == pygame.KEYDOWN:
                        # Find the focused node
                        focused = layout.find_focused_node()

                        if focused:
                            print(f"Focused node: render_path={focused.render_path}, has on_key={hasattr(focused, 'on_key')}, on_key={getattr(focused, 'on_key', None)}")

                        if focused and hasattr(focused, "on_key") and focused.on_key is not None:
                            # Execute keyboard handler with event parameters
                            meta = focused.on_key
                            handler = meta["handler"]
                            args = meta["args"]
                            params = meta["params"]

                            # Build event_params dict with the key value
                            event_params = {}
                            for param_name in params:
                                if param_name == "value":
                                    event_params["value"] = event.key
                                # Add more parameter mappings here if needed

                            # Merge args with event_params
                            all_args = {**args, **event_params}
                            changed = ACTION_REGISTRY[handler](program, state, **all_args)
                            print(changed)

                            if changed:
                                renderer.update(layout, state.state, elapsed)
                                layout.is_dirty = True
                            if layout.is_dirty or any_child_dirty(layout):
                                print("relayout")
                                relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)

                elapsed = clock.tick(60) / 1000.0
                accumulated_time += elapsed
                
                if accumulated_time >= STEP_DELAY:
                    accumulated_time = 0.0
                    if not state.is_done():
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
        