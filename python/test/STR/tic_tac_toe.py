from command_line import load_program_from_args, make_rlc_argparse
from rlc import Program
from rlc.renderer.factory import RendererFactory
from rlc.serialization.renderer_serializer import save_renderer
from test.red_board_renderer import RedBoard
from test.tic_tac_toe_board import TicTacToeBoardRenderer
from rlc.layout import  Direction
import os
import pygame, time, random
from test.display_layout import  render, PygameRenderer
from rlc import LayoutLogConfig, LayoutLogger
from rlc.serialization.renderer_serializer import load_renderer
from test.event_dispatcher import EventDispatcher
from simulate import new_timing_bucket, relayout, any_child_dirty, print_timings
from rlc.renderer.config_parser import  action, ACTION_REGISTRY

@action("mark_cell")
def mark_cell(program, state, x, y):
    print("calling mark", x , y)
    mod = program.module if program else getattr(state, "program", None).module
    pos_r = mod.make_pos(x)
    pos_c = mod.make_pos(y)
    if hasattr(state.state, "can_mark") and not state.state.can_mark(pos_r, pos_c):
        return False
    state.state.mark(pos_r, pos_c)
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
        

        config = {
            'Board' : {
                # "renderer" : TicTacToeBoardRenderer,
            }
        }
        interaction_config = {
            "Game/board/slots/$x/$y/on_click": "mark_cell"
        }
        renderer = RendererFactory.from_rlc_type(program.module.Game, config)


        pygame.init()  
        screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        screen.fill("white")
        clock = pygame.time.Clock()
        backend = PygameRenderer(screen)
        running = True
        
        # renderer.print_tree()
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
            # layout.propagate_interactive()
            layout.print_path()
            
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
                            meta = target.on_click
                            if meta:
                                handler = meta["handler"]
                                args = meta["args"]
                                changed = ACTION_REGISTRY[handler](program, state, **args)
                                if changed:
                                    layout.is_dirty = True
                                if layout.is_dirty or any_child_dirty(layout):
                                    relayout(screen, backend, layout, logger, compute_times, layout_times, scroll)

                elapsed = clock.tick(60) / 1000.0
                accumulated_time += elapsed
                
                if accumulated_time >= STEP_DELAY:
                    accumulated_time = 0.0
                    if not state.is_done():
                        # Auto-play when it's not the player's turn
                        if hasattr(state.state.board ,'playerTurn') and state.state.board.playerTurn == False:
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
        