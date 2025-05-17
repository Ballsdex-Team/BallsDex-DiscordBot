from PIL import Image, ImageOps
import io
import discord

async def merge_images(background_attachment: discord.Attachment, image_attachment: discord.Attachment) -> io.BytesIO:
    background_bytes = await background_attachment.read()
    image_bytes = await image_attachment.read()

    background = Image.open(io.BytesIO(background_bytes)).convert("RGBA")
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Force background to exactly 1360x730 by resizing and cropping center
    target_size = (1360, 730)
    background = ImageOps.fit(background, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))

    bg_w, bg_h = background.size
    img_w, img_h = image.size

    # Resize image if it gets too close to the borders (with 10% margin)
    margin = 0.1
    max_img_w = bg_w * (1 - margin)
    max_img_h = bg_h * (1 - margin)

    scale_factor = min(max_img_w / img_w, max_img_h / img_h, 1)
    new_size = (int(img_w * scale_factor), int(img_h * scale_factor))
    image = image.resize(new_size, Image.LANCZOS)

    # Center the image
    pos = ((bg_w - new_size[0]) // 2, (bg_h - new_size[1]) // 2)

    # Merge
    merged = background.copy()
    merged.paste(image, pos, image)

    # Output to BytesIO
    output_buffer = io.BytesIO()
    merged.save(output_buffer, format="PNG")
    output_buffer.seek(0)
    return output_buffer

