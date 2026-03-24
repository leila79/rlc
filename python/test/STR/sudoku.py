from command_line import load_program_from_args, make_rlc_argparse
from rlc import Program
from rlc.renderer.factory import RendererFactory
import pygame, time, random
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from simulate import new_timing_bucket, relayout, print_timings
import os
from rlc.renderer.config_parser import action, ACTION_REGISTRY
from rlc.serialization.renderer_serializer import load_renderer, save_renderer
from rlc.renderer.interaction_context import InteractionContext
from test.red_board_renderer import RedBoard
from rlc.event_queue import UpdateController, UpdateSignal, SignalKind
from rlc.sim_renderer_mapping import SimRendererMapping

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

        source_file = args.source_file
        base_name = os.path.splitext(os.path.basename(source_file))[0] if source_file else "renderer"
        save_path = os.path.join("./logs", f"{base_name}.yaml")

        # Load interaction context from config file
        interaction_ctx = InteractionContext.from_config_file()

        config = {
            'Game' : {
                'renderer' : RedBoard
            }
        }
        renderer = RendererFactory.from_rlc_type(
            program.module.Game,
            config,
            interaction_ctx=interaction_ctx,
            rlc_path=['Game']
        )

        save_renderer(renderer, save_path)
        print(f"[saved] renderer -> {save_path}")

        # source_file = args.source_file
        # base_name = os.path.splitext(os.path.basename(source_file))[0] if source_file else "renderer"
        # load_path = os.path.join("./logs", f"{base_name}.yaml")

        # renderer = load_renderer(load_path)

        pygame.init()  
        screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        screen.fill("white")
        clock = pygame.time.Clock()
        backend = PygameRenderer(screen)
        running = True
        
        iterations = 1
        current = 0
        STEP_DELAY = 0.9  # seconds per state
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
            actions = state.legal_actions
            mapping.print_mapping()

            # Dispatch callback: sudoku handlers take (program, state, **args)
            def dispatch_action(handler_name, args):
                return ACTION_REGISTRY[handler_name](program, state, **args)

            # Relayout callback
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
                # Phase 1: COLLECT - translate pygame events into signals
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

                        # Focus the clicked target (or unfocus if None)
                        controller.enqueue(UpdateSignal(
                            kind=SignalKind.FOCUS,
                            target=target if target else None))

                    elif event.type == pygame.KEYDOWN:
                        focused = layout.find_focused_node()
                        if focused and hasattr(focused, "on_key") and focused.on_key is not None:
                            meta = focused.on_key
                            # Build event params from pygame event
                            event_params = {}
                            for param_name in meta.get("params", []):
                                if param_name == "value":
                                    event_params["value"] = event.key

                            all_args = {**meta["args"], **event_params}
                            controller.enqueue(UpdateSignal(
                                kind=SignalKind.ACTION,
                                handler_name=meta["handler"],
                                args=all_args))

                # Phases 2-4: MUTATE, UPDATE, RELAYOUT (once per frame)
                elapsed = clock.tick(60) / 1000.0
                controller.process(state.state, elapsed)

                accumulated_time += elapsed
                if accumulated_time >= STEP_DELAY:
                    accumulated_time = 0.0
                    if state.is_done():
                        print("Game done.")
                        break

                # Phase 5: RENDER
                screen.fill("white")
                render(backend, layout)
                pygame.display.flip()
            current += 1
            print_timings(f"iteration {current}", compute_times, layout_times)
            time.sleep(1.0)

    pygame.quit()
        