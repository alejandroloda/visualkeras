import traceback
from PIL import Image, ImageDraw, ImageFont
import aggdraw
from math import ceil
from .utils import *
from .layer_utils import *


def layered_view(model, to_file: str = None, min_z: int = 20, min_xy: int = 20, max_z: int = 400,
                 max_xy: int = 2000,
                 scale_z: float = 0.1, scale_xy: float = 4, type_ignore: list = [], index_ignore: list = [],
                 color_map: dict = {}, one_dim_orientation: str = 'z',
                 background_fill: Any = 'white', draw_volume: bool = True, padding: int = 10,
                 spacing: int = 10, draw_funnel: bool = True, shade_step=10, legend: bool = False,
                 font_size: int = 24, font_path: str = 'arial.ttf') -> Image:
    """
    Generates a architecture visualization for a given linear keras model (i.e. one input and output tensor for each
    layer) in layered style (great for CNN).

    :param model: A keras model that will be visualized.
    :param to_file: Path to the file to write the created image to. If the image does not exist yet it will be created, else overwritten. Image type is inferred from the file ending. Providing None will disable writing.
    :param min_z: Minimum z size in pixel a layer will have.
    :param min_xy: Minimum x and y size in pixel a layer will have.
    :param max_z: Maximum z size in pixel a layer will have.
    :param max_xy: Maximum x and y size in pixel a layer will have.
    :param scale_z: Scalar multiplier for the z size of each layer.
    :param scale_xy: Scalar multiplier for the x and y size of each layer.
    :param type_ignore: List of layer types in the keras model to ignore during drawing.
    :param index_ignore: List of layer indexes in the keras model to ignore during drawing.
    :param color_map: Dict defining fill and outline for each layer by class type. Will fallback to default values for not specified classes.
    :param one_dim_orientation: Axis on which one dimensional layers should be drawn. Can  be 'x', 'y' or 'z'.
    :param background_fill: Color for the image background. Can be str or (R,G,B,A).
    :param draw_volume: Flag to switch between 3D volumetric view and 2D box view.
    :param padding: Distance in pixel before the first and after the last layer.
    :param spacing: Spacing in pixel between two layers
    :param draw_funnel: If set to True, a funnel will be drawn between consecutive layers
    :param shade_step: Deviation in lightness for drawing shades (only in volumetric view)
    :param legend: Add to the image a color layer legend
    :param font_size: Font size for legend

    :return: Generated architecture image.
    """

    # Iterate over the model to compute bounds and generate boxes

    boxes = list()
    layer_y = list()
    color_wheel = ColorWheel()
    current_z = padding
    x_off = -1

    img_height = 0
    max_right = 0

    for index, layer in enumerate(model.layers):

        # Ignore layers that the use has opted out to
        if type(layer) in type_ignore or index in index_ignore:
            continue

        # Do no render the SpacingDummyLayer, just increase the pointer
        if type(layer) == SpacingDummyLayer:
            current_z += layer.spacing
            continue

        x = min_xy
        y = min_xy
        z = min_z

        if isinstance(layer.output_shape, tuple):
            shape = layer.output_shape
        elif isinstance(layer.output_shape, list) and len(
                layer.output_shape) == 1:  # drop dimension for non seq. models
            shape = layer.output_shape[0]
        else:
            raise RuntimeError(f"not supported tensor shape {layer.output_shape}")

        if len(shape) >= 4:
            x = min(max(shape[1] * scale_xy, x), max_xy)
            y = min(max(shape[2] * scale_xy, y), max_xy)
            z = min(max(self_multiply(shape[3:]) * scale_z, z), max_z)
        elif len(shape) == 3:
            x = min(max(shape[1] * scale_xy, x), max_xy)
            y = min(max(shape[2] * scale_xy, y), max_xy)
            z = min(max(z), max_z)
        elif len(shape) == 2:
            if one_dim_orientation == 'x':
                x = min(max(shape[1] * scale_xy, x), max_xy)
            elif one_dim_orientation == 'y':
                y = min(max(shape[1] * scale_xy, y), max_xy)
            elif one_dim_orientation == 'z':
                z = min(max(shape[1] * scale_z, z), max_z)
            else:
                raise ValueError(f"unsupported orientation {one_dim_orientation}")
        else:
            raise RuntimeError(f"not supported tensor shape {layer.output_shape}")

        box = Box()

        box.de = 0
        if draw_volume:
            box.de = x / 3

        if x_off == -1:
            x_off = box.de / 2

        # top left coordinate
        box.x1 = current_z - box.de / 2
        box.y1 = box.de

        # bottom right coordinate
        box.x2 = box.x1 + z
        box.y2 = box.y1 + y

        box.fill = color_map.get(type(layer).__name__, {}).get('fill', color_wheel.get_color(type(layer)))
        box.outline = color_map.get(type(layer).__name__, {}).get('outline', 'black')
        color_map[type(layer).__name__] = {'fill': box.fill, 'outline': box.outline}

        box.shade = shade_step
        boxes.append(box)
        layer_y.append(box.y2 - (box.y1 - box.de))

        # Update image bounds
        hh = box.y2 - (box.y1 - box.de)
        if hh > img_height:
            img_height = hh

        if box.x2 + box.de > max_right:
            max_right = box.x2 + box.de

        current_z += z + spacing

    # Generate image
    img_width = max_right + x_off + padding
    img = Image.new('RGBA', (int(ceil(img_width)), int(ceil(img_height))), background_fill)
    draw = aggdraw.Draw(img)

    # x, y correction (centering)
    for i, node in enumerate(boxes):
        y_off = (img.height - layer_y[i]) / 2
        node.y1 += y_off
        node.y2 += y_off

        node.x1 += x_off
        node.x2 += x_off

    # Draw created boxes

    last_box = None

    for box in boxes:

        pen = aggdraw.Pen(get_rgba_tuple(box.outline))

        if last_box is not None and draw_funnel:
            draw.line([last_box.x2 + last_box.de, last_box.y1 - last_box.de,
                       box.x1 + box.de, box.y1 - box.de], pen)

            draw.line([last_box.x2 + last_box.de, last_box.y2 - last_box.de,
                       box.x1 + box.de, box.y2 - box.de], pen)

            draw.line([last_box.x2, last_box.y2,
                       box.x1, box.y2], pen)

            draw.line([last_box.x2, last_box.y1,
                       box.x1, box.y1], pen)

        box.draw(draw)

        last_box = box

    draw.flush()

    # Create layer color legend
    if legend:
        legend_height = len(color_map.keys()) * (20 + padding)
        img_box = Image.new('RGBA', (int(ceil(img_width)), legend_height + padding), background_fill)
        img_text = Image.new('RGBA', (int(ceil(img_width)), legend_height + padding), (0, 0, 0, 0))
        draw_box = aggdraw.Draw(img_box)
        draw_text = ImageDraw.Draw(img_text)

        try:
            font = ImageFont.truetype(font_path, font_size)
            default_font = False
        except OSError:
            font = ImageFont.load_default()
            default_font = True
            traceback.print_exc()
            print("Font cannot be open, loading default font")
            print("Please check the path: ", font_path)

        last_box = Box()
        last_box.y2 = 0

        for layer in color_map.keys():
            box = Box()
            box.x1 = 10
            box.x2 = 20
            box.y1 = 10 + padding + last_box.y2
            box.y2 = 10 + box.y1
            box.de = 5
            box.shade = 0
            box.fill = color_map[layer].get('fill', "#000000")
            box.outline = color_map[layer].get('outline', "#000000")
            last_box = box
            box.draw(draw_box)
            if not default_font:
                draw_text.text((box.x2 + 10, box.y1 - (font_size / 2)), layer, font=font, fill='black')
            else:
                draw_text.text((box.x2 + 10, box.y1 - 8/2), layer, font=font, fill='black')


        draw_box.flush()
        img_box.paste(img_text, mask=img_text)
        img = get_concat_v(img, img_box)

    if to_file is not None:
        img.save(to_file)

    return img
