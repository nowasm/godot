# Compact visibility metadata for Godot 3 scene snapshots

The protocol v2 frontend cannot show initial or script-driven visibility using the original four-field scene records. Full object inspection per node would unnecessarily duplicate properties and increase debugger data traffic.

`scene_snapshot_result` now returns `[revision, tree, visibility]`:

- `revision` and `tree` retain the existing format. `tree` still contains flattened `[child_count, name, native_class, object_id]` records.
- Optional `visibility` is a flat `[object_id, flags, ...]` list covering that same snapshot. Bits match Godot 4: 2 = native visibility property supported, 4 = local visible, 8 = visible in the scene. Ordinary Nodes/root Viewports have 0.
- CanvasItem/Spatial effective visibility uses their native `is_visible_in_tree()` methods. CanvasLayer has independent canvas visibility; its local and effective bits agree. Script methods/getters are never invoked to collect this metadata.

Old clients can continue reading payload[1] and ignore the extra field. New clients accept snapshots from old binaries but show an explicit unknown state until more information is available. No protocol generation/version change is needed.

Verification must include initially hidden controls, visible descendants under hidden parents/CanvasLayers, top-level CanvasItems, Spatial inheritance, and snapshots after changes made by game code without Inspector interaction. Build to a separate candidate, verify, then back up and replace the user's configured executable without stopping unrelated processes.
