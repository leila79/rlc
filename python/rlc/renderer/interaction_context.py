# rlc/renderer/interaction_context.py
"""
Interaction context for compile-time config processing.

This module handles loading interaction configs and mapping them to renderer nodes
during renderer tree construction, rather than at runtime during layout creation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from rlc.renderer.config_parser import parse_config_path, ParsedPath, SegmentKind
import yaml
import os


@dataclass
class InteractionMapping:
    """
    Stores interaction handler info for a specific renderer node.
    Pre-computed during renderer tree construction.
    """
    event_type: str  # "on_click", "on_key", etc.
    handler_name: str
    index_vars: List[str]  # e.g., ["x", "y"]
    param_vars: List[str]  # e.g., ["value"]
    rlc_path: List[str]  # The original RLC type path this was matched against


@dataclass
class InteractionContext:
    """
    Context for resolving interaction configs during renderer construction.

    This maps RLC type paths to interaction handlers, allowing us to annotate
    renderer nodes with their interactions at compile-time.
    """
    # Map: RLC type path pattern → list of interaction mappings
    # e.g., "Game/board/slots/$x/$y" → [InteractionMapping(...), ...]
    config_rules: List[tuple[ParsedPath, str]] = field(default_factory=list)

    # Map: renderer node id → path in RLC type tree
    # Built during renderer construction to track structural differences
    renderer_to_rlc_path: Dict[int, List[str]] = field(default_factory=dict)

    # Map: renderer node id → list of InteractionMappings
    # Pre-computed interactions for each renderer node
    renderer_interactions: Dict[int, List[InteractionMapping]] = field(default_factory=dict)

    @classmethod
    def from_config_file(cls, config_path: Optional[str] = None) -> 'InteractionContext':
        """
        Load interaction config from YAML file and create context.

        Args:
            config_path: Path to interactions.yaml. If None, searches standard locations.
        """
        from rlc.renderer.config_parser import _load_config_file

        config_dict = _load_config_file(config_path)

        rules = []
        for path_str, handler_name in config_dict.items():
            parsed_path = parse_config_path(path_str)
            rules.append((parsed_path, handler_name))

        return cls(config_rules=rules)

    def register_renderer_node(self, renderer_id: int, rlc_path: List[str]):
        """
        Register a renderer node with its corresponding RLC type path.

        Called during renderer tree construction to track the mapping.
        """
        self.renderer_to_rlc_path[renderer_id] = rlc_path

    def resolve_interactions(self, renderer_id: int, rlc_path: List[str]) -> List[InteractionMapping]:
        """
        Resolve all interaction rules that match this renderer node's RLC path.

        Returns a list of InteractionMappings that should be attached to this renderer.
        """
        mappings = []

        for parsed_path, handler_name in self.config_rules:
            # Try to match the RLC path against the config pattern
            if self._matches_pattern(parsed_path, rlc_path):
                event_type = parsed_path.event

                mapping = InteractionMapping(
                    event_type=event_type,
                    handler_name=handler_name,
                    index_vars=parsed_path.index_vars,
                    param_vars=parsed_path.param_vars,
                    rlc_path=rlc_path.copy()
                )
                mappings.append(mapping)

        if mappings:
            self.renderer_interactions[renderer_id] = mappings

        return mappings

    def _matches_pattern(self, parsed_path: ParsedPath, rlc_path: List[str]) -> bool:
        """
        Check if an RLC path matches a config pattern (ignoring event and params).

        Args:
            parsed_path: Parsed config path like "Game/board/slots/$x/$y/on_click"
            rlc_path: Actual RLC type path like ["Game", "board", "slots", 0, 1]

        Returns:
            True if the path matches the pattern structure
        """
        # Get segments before the EVENT
        segments = parsed_path.segments
        event_index = None
        for i, seg in enumerate(segments):
            if seg.kind == SegmentKind.EVENT:
                event_index = i
                break

        if event_index is None:
            return False

        pattern_segments = segments[:event_index]

        # Length must match
        if len(pattern_segments) != len(rlc_path):
            return False

        # Check each segment
        for seg, path_value in zip(pattern_segments, rlc_path):
            if seg.kind == SegmentKind.ROOT:
                if path_value != seg.value:
                    return False
            elif seg.kind == SegmentKind.FIELD:
                if path_value != seg.value:
                    return False
            elif seg.kind == SegmentKind.INDEX_VAR:
                # Variable matches any integer index OR the placeholder '$i'
                if not isinstance(path_value, int) and path_value != '$i':
                    return False
            # INDEX_WILDCARD would match any index too

        return True

    def get_interactions(self, renderer_id: int) -> List[InteractionMapping]:
        """Get pre-computed interactions for a renderer node."""
        return self.renderer_interactions.get(renderer_id, [])

    def apply_to_renderer_tree(self, renderer, rlc_path: Optional[List[str]] = None):
        """
        Recursively apply interaction mappings to a renderer tree.

        Used when loading a renderer from YAML to regenerate interaction_mappings.

        Args:
            renderer: Root renderer node
            rlc_path: Current path in RLC type tree (starts with [rlc_type_name])
        """
        if rlc_path is None:
            rlc_path = [renderer.rlc_type_name]

        # Resolve interactions for this node
        mappings = self.resolve_interactions(id(renderer), rlc_path)
        renderer.interaction_mappings = mappings

        # Recurse into children
        for child_renderer in renderer._iter_children():
            # Build child path - this is renderer-specific
            # For now, use child's type name
            child_path = rlc_path + [child_renderer.rlc_type_name]
            self.apply_to_renderer_tree(child_renderer, child_path)
