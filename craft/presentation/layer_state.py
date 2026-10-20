"""One interpretation of layer colours and inherited visibility for UI controls."""

from dataclasses import replace

from craft.presentation.crystal_layers import (
    default_crystal_layer_style, enable_crystal_layer, layer_options,
)


def _inherits(option, parent):
    if option.kind != "polyhedra":
        return False
    if option.ring_id:
        return option.ring_id == parent.key
    return (bool(option.component_id)
            and option.component_id == parent.component_id
            and option.representation_id == parent.representation_id
            and set(option.polyhedron_orbit_ids) <= set(parent.polyhedron_orbit_ids))


def resolved_layer_style(document, key, ancestor_keys=(), *, options=None):
    options = options if options is not None else {row.key: row for row in layer_options(document)}
    option = options.get(key)
    if option is None:
        return None
    visual = document.visual
    saved = visual.crystal_layers.get(key)
    style = saved or replace(default_crystal_layer_style(document, option, tuple(options.values())), visible=False)
    if not style.visible:
        for parent_key in ancestor_keys:
            parent_option = options.get(parent_key)
            parent_style = visual.crystal_layers.get(parent_key)
            if (parent_option is None or parent_style is None or not parent_style.visible
                    or not _inherits(option, parent_option)):
                continue
            visible = (key not in parent_style.hidden_member_orbit_ids
                       and not set(option.polyhedron_orbit_ids) <= parent_style.hidden_member_orbit_ids)
            style = replace(style, color=parent_style.color if visible or saved is None else style.color,
                            visible=visible)
            break
    if option.kind == "atom":
        style = replace(style, color=visual.atom_orbit_colors.get(option.site_id, style.color),
                        visible=style.visible and option.site_id not in visual.hidden_atom_orbit_ids)
    if option.polyhedron_orbit_ids and set(option.polyhedron_orbit_ids) <= visual.hidden_polyhedron_orbit_ids:
        style = replace(style, visible=False)
    return style


def set_layer_visibility(document, key, visible, ancestor_keys=()):
    options = {row.key: row for row in layer_options(document)}
    option = options.get(key)
    if option is None:
        return False
    effective = resolved_layer_style(document, key, ancestor_keys, options=options)
    visual = document.visual
    for parent_key in ancestor_keys:
        parent_option = options.get(parent_key)
        parent_style = visual.crystal_layers.get(parent_key)
        if parent_style is None or parent_option is None or not _inherits(option, parent_option):
            continue
        members = frozenset((option.key,)) if option.ring_id else frozenset(option.polyhedron_orbit_ids)
        excluded = parent_style.hidden_member_orbit_ids
        if visible and option.ring_id:
            # Older projects excluded the entire orbit. Preserve its other
            # images when one constituent is restored from the compact tree.
            legacy = excluded & frozenset(option.polyhedron_orbit_ids)
            if legacy:
                excluded = (excluded - legacy) | frozenset(
                    candidate.key for candidate in options.values()
                    if candidate.ring_id == option.ring_id
                    and legacy & frozenset(candidate.polyhedron_orbit_ids)
                )
        visual.crystal_layers[parent_key] = replace(
            parent_style, hidden_member_orbit_ids=excluded - members if visible else excluded | members,
        )
    saved = visual.crystal_layers.get(key)
    if visible:
        enable_crystal_layer(document, key)
        if saved is None:
            visual.crystal_layers[key] = replace(visual.crystal_layers[key], color=effective.color)
        if option.kind == "atom":
            visual.hidden_atom_orbit_ids.discard(option.site_id)
        visual.hidden_polyhedron_orbit_ids.difference_update(option.polyhedron_orbit_ids)
    elif saved is not None:
        visual.crystal_layers[key] = replace(saved, visible=False)
    return True


def set_layer_color(document, key, color, ancestor_keys=()):
    style = resolved_layer_style(document, key, ancestor_keys)
    if style is None:
        return False
    document.visual.crystal_layers[key] = replace(style, color=color)
    option = next(row for row in layer_options(document) if row.key == key)
    if option.kind == "atom":
        document.visual.atom_orbit_colors[option.site_id] = color
    return True
