from command_line import load_program_from_args, make_rlc_argparse
import os
from rlc import Program
from rlc.renderer.factory import RendererFactory
import pygame, time, random
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from rlc.renderer.config_parser import  action, ACTION_REGISTRY
from simulate import new_timing_bucket, relayout, print_timings
from rlc.renderer.interaction_context import InteractionContext
from rlc.serialization.renderer_serializer import save_renderer
from rlc.event_queue import UpdateController, UpdateSignal, SignalKind
from rlc.sim_renderer_mapping import SimRendererMapping

@action("hit")
def hit(state):
    print("calling hit")
    state.state.hit()
    return True

@action("stand")
def stand(state):
    print("calling stand")
    state.state.stand()
    return True

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

        source_file = args.source_file
        base_name = os.path.splitext(os.path.basename(source_file))[0] if source_file else "renderer"
        save_path = os.path.join("./logs", f"{base_name}.yaml")

        # Load interaction config at compile-time
        interaction_ctx = InteractionContext.from_config_file()

        config = {}

        # Build renderer tree with interaction mappings
        renderer = RendererFactory.from_rlc_type(
            program.module.Game,
            config,
            interaction_ctx=interaction_ctx,
            rlc_path=["Game"]
        )

        save_renderer(renderer, save_path)
        print(f"[saved] renderer -> {save_path}")

        print("\n" + "="*80)
        print("RENDERER TREE WITH INTERACTION MAPPINGS:")
        print("="*80)
        renderer.print_interaction_tree()
        print("="*80 + "\n")


        pygame.init()  
        screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        screen.fill("white")
        clock = pygame.time.Clock()
        backend = PygameRenderer(screen)
        running = True
        
        print(renderer)
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

            # Dispatch callback: blackjack handlers take (state, **args)
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

                # Phases 2-4: MUTATE, UPDATE, RELAYOUT (once per frame)
                elapsed = clock.tick(60) / 1000.0
                accumulated_time += elapsed

                if accumulated_time >= STEP_DELAY:
                    accumulated_time = 0.0
                    if not state.is_done():
                        if state.state.shuffling.to_shuffle > 0:
                            play_random_turn(state, controller)
                    else:
                        print("Game done.")
                        break

                controller.process(state.state, elapsed)

                # Phase 5: RENDER
                screen.fill("white")
                render(backend, layout)
                pygame.display.flip()
            current += 1
            print_timings(f"iteration {current}", compute_times, layout_times)
            time.sleep(1.0)
        
    pygame.quit()
        