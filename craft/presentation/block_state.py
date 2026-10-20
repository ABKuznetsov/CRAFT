"""Synchronize a native block's display flags and automatic constituent hiding."""


def auto_hidden_members(state, attribute):
    active = set(getattr(state, "shown_block_ids", ())) - set(getattr(state, "hidden_block_ids", ()))
    return frozenset(member for key, members in getattr(state, attribute, {}).items()
                     if key in active for member in members)


def set_block_visibility(state, presentation, block_id, visible):
    try:
        block = presentation.block(str(block_id))
    except KeyError:
        return False
    key = block.block_id
    if visible:
        state.shown_block_ids.add(key)
        state.hidden_block_ids.discard(key)
        state.block_auto_hidden_atom_ids[key] = block.internal_atom_ids
        state.block_auto_hidden_polyhedron_orbit_ids[key] = frozenset(block.polyhedron_orbit_ids)
    else:
        state.shown_block_ids.discard(key)
        state.hidden_block_ids.add(key)
        state.block_auto_hidden_atom_ids.pop(key, None)
        state.block_auto_hidden_polyhedron_orbit_ids.pop(key, None)
    return True
