/**************************************************************************/
/*  runtime_node_select.cpp                                               */
/**************************************************************************/
/*                         This file is part of:                          */
/*                             GODOT ENGINE                               */
/*                        https://godotengine.org                         */
/**************************************************************************/
/* Copyright (c) 2014-present Godot Engine contributors (see AUTHORS.md). */
/* Copyright (c) 2007-2014 Juan Linietsky, Ariel Manzur.                  */
/*                                                                        */
/* Permission is hereby granted, free of charge, to any person obtaining  */
/* a copy of this software and associated documentation files (the        */
/* "Software"), to deal in the Software without restriction, including    */
/* without limitation the rights to use, copy, modify, merge, publish,    */
/* distribute, sublicense, and/or sell copies of the Software, and to     */
/* permit persons to whom the Software is furnished to do so, subject to  */
/* the following conditions:                                              */
/*                                                                        */
/* The above copyright notice and this permission notice shall be         */
/* included in all copies or substantial portions of the Software.        */
/*                                                                        */
/* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,        */
/* EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF     */
/* MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. */
/* IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY   */
/* CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,   */
/* TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE      */
/* SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                 */
/**************************************************************************/

#include "runtime_node_select.h"

#ifdef DEBUG_ENABLED
#include "scene/2d/canvas_item.h"
#include "scene/2d/collision_shape_2d.h"
#include "scene/gui/control.h"
#include "scene/main/viewport.h"
#include "servers/visual_server.h"
#ifndef _3D_DISABLED
#include "scene/3d/collision_shape.h"
#include "scene/3d/visual_instance.h"
#include "scene/resources/material.h"
#include "scene/resources/mesh.h"
#endif

Error RuntimeNodeSelect::select(ObjectID p_id, bool p_visible) {
	if (p_id != 0 && !Object::cast_to<Node>(ObjectDB::get_instance(p_id))) {
		clear();
		return ERR_DOES_NOT_EXIST;
	}
	selected_id = p_id;
	visible = p_visible;
	dirty = true;
	update();
	return OK;
}

void RuntimeNodeSelect::_free_visuals() {
	VisualServer *vs = VisualServer::get_singleton();
	if (vs) {
		if (canvas_item.is_valid()) {
			vs->free(canvas_item);
			vs->free(canvas);
		}
#ifndef _3D_DISABLED
		if (box_instance.is_valid()) {
			vs->free(box_instance);
		}
#endif
	}
	canvas_item = RID();
	canvas = RID();
	viewport = RID();
#ifndef _3D_DISABLED
	box_instance = RID();
	scenario = RID();
	box_mesh.unref();
#endif
	selection_kind = "none";
	dirty = true;
}

void RuntimeNodeSelect::clear() {
	selected_id = 0;
	_free_visuals();
}

void RuntimeNodeSelect::update() {
	if (!selected_id || !visible) {
		if (canvas_item.is_valid()
#ifndef _3D_DISABLED
				|| box_instance.is_valid()
#endif
		) {
			_free_visuals();
		}
		return;
	}
	Node *node = Object::cast_to<Node>(ObjectDB::get_instance(selected_id));
	if (!node) {
		clear();
		return;
	}
	if (!node->is_inside_tree()) {
		_free_visuals();
		return;
	}
	VisualServer *vs = VisualServer::get_singleton();
	CanvasItem *ci = Object::cast_to<CanvasItem>(node);
	if (ci) {
		const RID target_viewport = ci->get_viewport()->get_viewport_rid();
		if (viewport != target_viewport) {
			_free_visuals();
			viewport = target_viewport;
			canvas = vs->canvas_create();
			canvas_item = vs->canvas_item_create();
			vs->viewport_attach_canvas(viewport, canvas);
			vs->viewport_set_canvas_stacking(viewport, canvas, 0x7fffffff, 0);
			vs->canvas_item_set_parent(canvas_item, canvas);
			vs->canvas_item_set_light_mask(canvas_item, 0);
		}
		Rect2 rect(Vector2(), Vector2(10, 10));
		Control *control = Object::cast_to<Control>(ci);
		if (control) {
			rect = Rect2(Vector2(), control->get_size());
		} else {
#ifdef TOOLS_ENABLED
			if (ci->_edit_use_rect()) {
				rect = ci->_edit_get_rect();
			} else
#endif
			{
				CollisionShape2D *collision = Object::cast_to<CollisionShape2D>(ci);
				if (collision && collision->get_shape().is_valid()) {
					rect = collision->get_shape()->get_rect();
				}
			}
		}
		const Transform2D transform = ci->get_global_transform_with_canvas();
		if (!dirty && transform == last_transform_2d && rect == last_rect) {
			return;
		}
		last_transform_2d = transform;
		last_rect = rect;
		const Vector2 corners[4] = {
			transform.xform(rect.position),
			transform.xform(rect.position + Vector2(rect.size.x, 0)),
			transform.xform(rect.position + rect.size),
			transform.xform(rect.position + Vector2(0, rect.size.y)),
		};
		vs->canvas_item_clear(canvas_item);
		for (int i = 0; i < 4; i++) {
			vs->canvas_item_add_line(canvas_item, corners[i], corners[(i + 1) % 4], Color(1, 0.6, 0.4, 0.9), 2.0, true);
		}
		selection_kind = "2d";
		dirty = false;
		return;
	}
#ifndef _3D_DISABLED
	Spatial *spatial = Object::cast_to<Spatial>(node);
	if (spatial && spatial->is_inside_world()) {
		const RID target_scenario = spatial->get_world()->get_scenario();
		if (scenario != target_scenario) {
			_free_visuals();
			scenario = target_scenario;
			Ref<SpatialMaterial> material;
			material.instance();
			material->set_albedo(Color(1, 0.6, 0.4));
			material->set_flag(SpatialMaterial::FLAG_UNSHADED, true);
			material->set_flag(SpatialMaterial::FLAG_DISABLE_DEPTH_TEST, true);
			PoolVector<Vector3> vertices;
			const AABB unit_box(Vector3(), Vector3(1, 1, 1));
			for (int i = 0; i < 12; i++) {
				Vector3 from, to;
				unit_box.get_edge(i, from, to);
				vertices.push_back(from);
				vertices.push_back(to);
			}
			Array arrays;
			arrays.resize(Mesh::ARRAY_MAX);
			arrays[Mesh::ARRAY_VERTEX] = vertices;
			box_mesh.instance();
			box_mesh->add_surface_from_arrays(Mesh::PRIMITIVE_LINES, arrays);
			box_mesh->surface_set_material(0, material);
			box_instance = vs->instance_create2(box_mesh->get_rid(), scenario);
			vs->instance_set_layer_mask(box_instance, 0xffffffff);
			vs->instance_geometry_set_cast_shadows_setting(box_instance, VisualServer::SHADOW_CASTING_SETTING_OFF);
			vs->instance_set_portal_mode(box_instance, VisualServer::INSTANCE_PORTAL_MODE_GLOBAL);
		}
		AABB bounds(Vector3(-0.5, -0.5, -0.5), Vector3(1, 1, 1));
		VisualInstance *visual = Object::cast_to<VisualInstance>(spatial);
		if (visual) {
			bounds = visual->get_aabb();
		} else {
			CollisionShape *collision = Object::cast_to<CollisionShape>(spatial);
			if (collision && collision->get_shape().is_valid()) {
				bounds = collision->get_shape()->get_debug_mesh()->get_aabb();
			}
		}
		const Transform global_transform = spatial->get_global_transform();
		if (!dirty && global_transform == last_transform_3d && bounds == last_aabb) {
			return;
		}
		last_transform_3d = global_transform;
		last_aabb = bounds;
		Transform transform = global_transform;
		const Vector3 margin(0.01, 0.01, 0.01);
		transform.translate(bounds.position - margin * 0.5);
		Basis scale;
		scale.scale(bounds.size + margin);
		transform.basis = transform.basis * scale;
		vs->instance_set_transform(box_instance, transform);
		selection_kind = "3d";
		dirty = false;
		return;
	}
#endif
	_free_visuals();
}

RuntimeNodeSelect::~RuntimeNodeSelect() {
	_free_visuals();
}
#endif // DEBUG_ENABLED
