extends Node

var capture_file = "" setget capture
var capture_later = "" setget delayed_capture
var motion = 0 setget move_target
var rotated = false setget rotate_target
var delete_target = false setget remove_target
var pause_requested = false
var target: ColorRect
var nested_view: Viewport
var spatial_view: Viewport

func _ready():
	get_tree().set_screen_stretch(SceneTree.STRETCH_MODE_2D, SceneTree.STRETCH_ASPECT_KEEP, Vector2(320, 240))
	target = ColorRect.new()
	target.name = "Target"
	target.rect_position = Vector2(20, 30)
	target.rect_size = Vector2(100, 40)
	target.color = Color(0.12, 0.2, 0.3)
	add_child(target)
	var layer = CanvasLayer.new()
	layer.name = "UILayer"
	layer.layer = 10
	layer.offset = Vector2(20, 100)
	layer.scale = Vector2(1.5, 1.5)
	add_child(layer)
	var layer_control = ColorRect.new()
	layer_control.name = "LayerControl"
	layer_control.rect_position = Vector2(10, 10)
	layer_control.rect_size = Vector2(40, 20)
	layer_control.color = Color(0.1, 0.2, 0.3)
	layer.add_child(layer_control)
	var image = Image.new()
	image.create(20, 12, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.2, 0.3, 0.4))
	var texture = ImageTexture.new()
	texture.create_from_image(image, 0)
	var sprite = Sprite.new()
	sprite.name = "SpriteTarget"
	sprite.texture = texture
	sprite.position = Vector2(155, 85)
	add_child(sprite)
	var body = Area2D.new()
	body.name = "Body"
	add_child(body)
	var collision = CollisionShape2D.new()
	collision.name = "ShapeTarget"
	collision.position = Vector2(130, 170)
	collision.shape = RectangleShape2D.new()
	collision.shape.extents = Vector2(12, 8)
	body.add_child(collision)
	nested_view = make_viewport("Nested", Vector2(190, 140), Vector2(100, 80))
	var nested_control = ColorRect.new()
	nested_control.name = "NestedControl"
	nested_control.rect_position = Vector2(10, 15)
	nested_control.rect_size = Vector2(40, 20)
	nested_control.color = Color(0.1, 0.2, 0.3)
	nested_view.add_child(nested_control)
	spatial_view = make_viewport("SpatialView", Vector2(200, 10), Vector2(100, 100))
	spatial_view.own_world = true
	var camera = Camera.new()
	camera.name = "Camera"
	camera.translation = Vector3(0, 0, 4)
	spatial_view.add_child(camera)
	camera.current = true
	var cube = MeshInstance.new()
	cube.name = "CubeTarget"
	cube.mesh = CubeMesh.new()
	cube.mesh.size = Vector3(1, 1, 1)
	var material = SpatialMaterial.new()
	material.flags_unshaded = true
	material.albedo_color = Color(0.1, 0.2, 0.3)
	cube.material_override = material
	spatial_view.add_child(cube)

func make_viewport(label: String, pos: Vector2, size: Vector2) -> Viewport:
	var container = ViewportContainer.new()
	container.name = label
	container.rect_position = pos
	container.rect_size = size
	container.stretch = true
	add_child(container)
	var view = Viewport.new()
	view.name = "Viewport"
	view.size = size
	view.render_target_update_mode = Viewport.UPDATE_ALWAYS
	container.add_child(view)
	return view

func capture(value):
	if value.empty():
		return
	for item in [[get_viewport(), value], [nested_view, value + "-nested.png"], [spatial_view, value + "-3d.png"]]:
		var image = item[0].get_texture().get_data()
		image.flip_y()
		image.save_png(item[1])

func delayed_capture(value):
	yield(get_tree().create_timer(0.6), "timeout")
	capture(value)

func move_target(value):
	motion = value
	if is_instance_valid(target):
		target.rect_position = Vector2(20 + value * 10, 30)

func rotate_target(value):
	rotated = value
	if is_instance_valid(target):
		target.rect_rotation = 90 if value else 0
		target.rect_scale = Vector2(1.5, 0.5) if value else Vector2.ONE

func remove_target(value):
	if value and is_instance_valid(target):
		target.queue_free()

func _process(_delta):
	if pause_requested:
		pause_requested = false
		breakpoint
