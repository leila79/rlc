from command_line import load_program_from_args, make_rlc_argparse
import os
from rlc import Program
from rlc.renderer.factory import RendererFactory
import pygame, time, random
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from rlc.renderer.config_parser import  action, ACTION_REGISTRY
from simulate import new_timing_bucket, relayout, any_child_dirty, print_timings
from rlc.renderer.interaction_context import InteractionContext
from rlc.serialization.renderer_serializer import save_renderer

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
                        print(f"target node: render_path={target.render_path}, has on_click={hasattr(target, 'on_click')}, on_click={getattr(target, 'on_click', None)}")
                        if target and hasattr(target, "on_click"):
                            meta = target.on_click
                            
                            if meta:
                                handler = meta["handler"]
                                args = meta["args"]
                                changed = ACTION_REGISTRY[handler](state, **args)
                                if changed:
                                    print(changed)
                                    renderer.update(layout, state.state, elapsed)
                                    layout.is_dirty = True
                                if layout.is_dirty or any_child_dirty(layout):
                                    relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)

                elapsed = clock.tick(60) / 1000.0
                accumulated_time += elapsed
                
                if accumulated_time >= STEP_DELAY:
                    accumulated_time = 0.0
                    if not state.is_done():
                        if state.state.shuffling.to_shuffle > 0:
                            if play_random_turn(elapsed, state, renderer, layout):
                                relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)
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
        