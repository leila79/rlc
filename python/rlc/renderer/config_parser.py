from dataclasses import dataclass
from typing import List, Any, Dict, Optional
from enum import Enum
import yaml
import os

ACTION_REGISTRY = {}

# Global config cache - loaded once and reused
_INTERACTION_CONFIG_CACHE = None
_INTERACTION_RULES_CACHE = None

def action(name):
    def wrapper(fn):
        ACTION_REGISTRY[name] = fn
        return fn
    return wrapper


class SegmentKind(str, Enum):
    ROOT = "root"
    FIELD = "field"
    INDEX_WILDCARD = "index_wildcard"
    INDEX_VAR = "index_var"
    EVENT = "event"
    PARAM_VAR = "param_var"  # NEW: for parameters like $value in on_key/$value

@dataclass(frozen=True)
class PathSegment:
    kind: SegmentKind
    value: str  # field name, var name, event name, root name

@dataclass(frozen=True)
class ParsedPath:
    raw: str
    segments: List[PathSegment]

    @property
    def event(self) -> str:
        """Returns the event name (on_click, on_key, etc.)"""
        for seg in self.segments:
            if seg.kind == SegmentKind.EVENT:
                return seg.value
        raise ValueError(f"ParsedPath has no EVENT segment: {self.raw}")

    @property
    def param_vars(self) -> List[str]:
        """Returns list of parameter variable names like ['value', 'modifiers']"""
        return [seg.value for seg in self.segments if seg.kind == SegmentKind.PARAM_VAR]

    @property
    def index_vars(self) -> List[str]:
        """Returns list of index variable names like ['x', 'y']"""
        return [seg.value for seg in self.segments if seg.kind == SegmentKind.INDEX_VAR]
    
@dataclass
class InteractionRule:
    path: ParsedPath
    handler_name: str


_VALID_EVENTS = {"on_click", "on_hover", "on_key"}  # extend later


def parse_config_path(path: str) -> ParsedPath:
    """
    Parse a user config path like:
        Game/board/slots/$row/$col/on_click
        Game/board/slots/$x/$y/on_key/$value
        Game/board/slots/$x/$y/on_key/$value/$modifiers

    Returns ParsedPath with typed segments.
    """
    raw = path
    path = path.strip().strip("/")  # normalize

    if not path:
        raise ValueError("Empty config path")

    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"Path too short: '{raw}'")

    # Find the event segment
    event_index = None
    for i, part in enumerate(parts):
        if part in _VALID_EVENTS:
            event_index = i
            break

    if event_index is None:
        raise ValueError(
            f"No valid event found in '{raw}'. "
            f"Allowed: {sorted(_VALID_EVENTS)}"
        )

    root = parts[0]
    event = parts[event_index]
    middle = parts[1:event_index]  # Between root and event
    params = parts[event_index + 1:]  # After event

    segments: List[PathSegment] = [PathSegment(SegmentKind.ROOT, root)]

    # Process middle segments (fields and index vars)
    for seg in middle:
        if seg.startswith("$"):
            var = seg[1:]
            if not var:
                raise ValueError(f"Empty variable segment in '{raw}'")
            segments.append(PathSegment(SegmentKind.INDEX_VAR, var))
            continue

        # Otherwise treat as a struct field name
        segments.append(PathSegment(SegmentKind.FIELD, seg))

    # Add the event
    segments.append(PathSegment(SegmentKind.EVENT, event))

    # Process parameter segments (must start with $)
    for seg in params:
        if not seg.startswith("$"):
            raise ValueError(
                f"Parameter '{seg}' must start with '$' in '{raw}'"
            )
        var = seg[1:]
        if not var:
            raise ValueError(f"Empty parameter segment in '{raw}'")
        segments.append(PathSegment(SegmentKind.PARAM_VAR, var))

    return ParsedPath(raw=raw, segments=segments)

def format_parsed_path(pp: ParsedPath) -> str:
    return " -> ".join(f"{s.kind}:{s.value}" for s in pp.segments)


def match_parsed_path(
    parsed: ParsedPath,
    runtime_path: List[Any],
) -> Optional[Dict[str, int]]:
    """
    Match a ParsedPath against a runtime render path.

    runtime_path example:
        ["Game", "board", "slots", 1, 2]

    Returns:
        dict of variable bindings if match succeeds
        None if match fails
    """

    segments = parsed.segments

    # Last segment is EVENT → not part of runtime path
    expected_len = len(segments) - 1
    if len(runtime_path) != expected_len:
        return None

    bindings: Dict[str, int] = {}
    for i, seg in enumerate(segments[:-1]):
        value = runtime_path[i]

        if seg.kind == SegmentKind.ROOT:
            if value != seg.value:
                return None

        elif seg.kind == SegmentKind.FIELD:
            if value != seg.value:
                return None

        elif seg.kind == SegmentKind.INDEX_VAR:
            if not isinstance(value, int):
                return None
            bindings[seg.value] = value

        else:
            raise AssertionError(f"Unexpected segment kind: {seg.kind}")

    return bindings

def match_parsed_path_with_params(
    parsed: ParsedPath,
    runtime_path: List[Any],
    event_params: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Match a ParsedPath against a runtime render path and merge with event parameters.

    Args:
        parsed: The parsed configuration path
        runtime_path: The actual render path like ["Game", "board", "slots", 1, 2]
        event_params: Event-specific parameters like {"value": pygame.K_5}

    Returns:
        Combined dict of bindings if match succeeds, e.g., {x: 1, y: 2, value: pygame.K_5}
        None if match fails

    Example:
        parsed path: Game/board/slots/$x/$y/on_key/$value
        runtime_path: ["Game", "board", "slots", 1, 2]
        event_params: {"value": pygame.K_5}
        returns: {"x": 1, "y": 2, "value": pygame.K_5}
    """
    if event_params is None:
        event_params = {}

    segments = parsed.segments

    # Find where EVENT segment is
    event_index = None
    for i, seg in enumerate(segments):
        if seg.kind == SegmentKind.EVENT:
            event_index = i
            break

    if event_index is None:
        return None

    # Everything before EVENT should match runtime_path
    expected_len = event_index
    if len(runtime_path) != expected_len:
        return None

    bindings: Dict[str, Any] = {}

    # Match path segments
    for i, seg in enumerate(segments[:event_index]):
        value = runtime_path[i]

        if seg.kind == SegmentKind.ROOT:
            if value != seg.value:
                return None

        elif seg.kind == SegmentKind.FIELD:
            if value != seg.value:
                return None

        elif seg.kind == SegmentKind.INDEX_VAR:
            if not isinstance(value, int):
                return None
            bindings[seg.value] = value

        else:
            raise AssertionError(f"Unexpected segment kind before EVENT: {seg.kind}")

    # Bind event parameters (optional during config application)
    for param_name in parsed.param_vars:
        if param_name in event_params:
            bindings[param_name] = event_params[param_name]
        # If param not in event_params, that's OK - it will be filled in later during event handling

    return bindings

def _load_interaction_rules(cfg: dict) -> list[InteractionRule]:
    rules = []
    for path_str, handler in cfg.items():
        parsed = parse_config_path(path_str)
        rules.append(InteractionRule(parsed, handler))
    return rules

def _load_config_file(config_path: Optional[str] = None) -> dict:
    """
    Load interaction configuration from a YAML file.

    Args:
        config_path: Path to the YAML config file. If None, searches for 'interactions.yaml'
                     in multiple standard locations.

    Returns:
        Dictionary mapping path patterns to handler names
    """
    if config_path is None:
        # Try multiple possible locations
        search_paths = [
            "interactions.yaml",  # Current directory
            "test/STR/interactions.yaml",  # From python/ directory
            "python/test/STR/interactions.yaml",  # From repo root
            os.path.join(os.path.dirname(__file__), "../../../test/STR/interactions.yaml"),  # Relative to this file
        ]

        for path in search_paths:
            if os.path.exists(path):
                config_path = path
                break
        else:
            # No config file found, return empty config
            return {}

    if not os.path.exists(config_path):
        print(f"Warning: Config file not found at {config_path}")
        return {}

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    return config if config else {}

def set_interaction_config(config_path: Optional[str] = None):
    """
    Load and cache the interaction configuration globally.

    Call this once at the start of your program to set the config path.
    If not called, apply_config will search for the config file automatically.

    Args:
        config_path: Path to the YAML config file. If None, searches standard locations.
    """
    global _INTERACTION_CONFIG_CACHE, _INTERACTION_RULES_CACHE

    _INTERACTION_CONFIG_CACHE = _load_config_file(config_path)
    _INTERACTION_RULES_CACHE = _load_interaction_rules(_INTERACTION_CONFIG_CACHE)

def apply_config(layout):
        """
        Apply all matching rules to this layout node.

        Uses the globally cached configuration set by set_interaction_config().
        If not set, will auto-load from standard locations on first call.

        Args:
            layout: The layout node to apply config to
        """
        global _INTERACTION_CONFIG_CACHE, _INTERACTION_RULES_CACHE

        # Lazy load config on first use if not explicitly set
        if _INTERACTION_RULES_CACHE is None:
            set_interaction_config()

        rules = _INTERACTION_RULES_CACHE

        if not hasattr(layout, "render_path"):
            return

        for rule in rules:
            bindings = match_parsed_path_with_params(rule.path, layout.render_path, event_params={})
            if bindings is not None:
                # Attach interaction metadata based on event type
                layout.interactive = True
                event_type = rule.path.event

                metadata = {
                    "handler": rule.handler_name,
                    "args": bindings,
                    "params": rule.path.param_vars  # List of parameter names like ['value']
                }

                # Attach to the appropriate event attribute
                if event_type == "on_click":
                    layout.on_click = metadata
                elif event_type == "on_key":
                    layout.on_key = metadata
                elif event_type == "on_hover":
                    layout.on_hover = metadata
                else:
                    # Generic fallback
                    setattr(layout, event_type, metadata)

    


