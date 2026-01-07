from rlc.renderer.renderable import Renderable

def save_renderer(renderable, path):
    """
    Save a renderer to a YAML file.

    Uses the Renderable.to_yaml() method which properly serializes
    the renderer tree with type information.
    """
    with open(path, "w") as f:
        if renderable is not None:
            yaml_str = renderable.to_yaml()
            f.write(yaml_str)

def load_renderer(path):
    """
    Load a renderer from a YAML file.

    Uses the Renderable.from_yaml() method which reconstructs
    the renderer tree with proper types.
    """
    with open(path, 'r') as f:
        yaml_str = f.read()
    return Renderable.from_yaml(yaml_str)