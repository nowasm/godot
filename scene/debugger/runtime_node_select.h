/**************************************************************************/
/*  runtime_node_select.h                                                 */
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

#ifndef RUNTIME_NODE_SELECT_H
#define RUNTIME_NODE_SELECT_H

#ifdef DEBUG_ENABLED

#include "core/math/aabb.h"
#include "core/math/transform.h"
#include "core/math/transform_2d.h"
#include "core/reference.h"
#include "core/rid.h"

class ArrayMesh;

// Bounds rendering backported from Godot 4 RuntimeNodeSelect. This object is
// owned by the debugger, never enters the scene tree, and never handles input.
class RuntimeNodeSelect {
	ObjectID selected_id = 0;
	bool visible = true;
	bool dirty = true;
	String selection_kind = "none";
	RID canvas;
	RID canvas_item;
	RID viewport;
	Transform2D last_transform_2d;
	Rect2 last_rect;

#ifndef _3D_DISABLED
	Ref<ArrayMesh> box_mesh;
	RID box_instance;
	RID scenario;
	Transform last_transform_3d;
	AABB last_aabb;
#endif

	void _free_visuals();

public:
	Error select(ObjectID p_id, bool p_visible);
	void update();
	void clear();
	String get_selection_kind() const { return selection_kind; }
	~RuntimeNodeSelect();
};

#endif // DEBUG_ENABLED
#endif // RUNTIME_NODE_SELECT_H
