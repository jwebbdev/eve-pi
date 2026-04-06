"""BFS-based jump distance calculation using local stargate data."""
from collections import deque
from typing import Dict, List, Optional


def jump_distance(
    origin_id: int,
    destination_id: int,
    adjacency: Dict[str, List[str]],
    max_jumps: int = 0,
) -> Optional[int]:
    """Calculate jump distance between two systems using BFS.

    Args:
        origin_id: Source system ID
        destination_id: Destination system ID
        adjacency: Dict mapping system_id (str) -> list of connected system_ids (str)
        max_jumps: Stop searching after this many jumps (0 = unlimited)

    Returns:
        Number of jumps, or None if no route exists or max_jumps exceeded.
    """
    if origin_id == destination_id:
        return 0

    origin = str(origin_id)
    dest = str(destination_id)

    if origin not in adjacency or dest not in adjacency:
        return None

    visited = {origin}
    queue = deque([(origin, 0)])

    while queue:
        current, dist = queue.popleft()
        for neighbor in adjacency.get(current, []):
            if neighbor == dest:
                return dist + 1
            if neighbor not in visited:
                if max_jumps > 0 and dist + 1 >= max_jumps:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))

    return None
