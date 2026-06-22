from io import BytesIO

import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont


def build_etiquette_bague_png(produit):
    # 30mm x 25mm à 203 DPI ≈ 240 x 200 px
    width = 240
    height = 200

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    font_title = ImageFont.load_default()
    font_text = ImageFont.load_default()

    purete = str(produit.purete) if produit.purete else ""
    poids = produit.poids or ""
    sku = produit.sku or f"P-{produit.id}"

    draw.text((95, 10), "RIO GOLD", fill="black", font=font_title)
    draw.text((105, 45), purete, fill="black", font=font_text)
    draw.text((95, 70), f"{poids} g", fill="black", font=font_text)

    code128 = barcode.get("code128", sku, writer=ImageWriter())
    barcode_buffer = BytesIO()
    code128.write(
        barcode_buffer,
        options={
            "module_height": 8,
            "module_width": 0.25,
            "quiet_zone": 1,
            "font_size": 0,
            "write_text": False,
        },
    )
    barcode_buffer.seek(0)

    barcode_img = Image.open(barcode_buffer).convert("RGB")
    barcode_img = barcode_img.resize((210, 55))

    img.paste(barcode_img, (15, 105))

    draw.text((70, 165), sku, fill="black", font=font_text)

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return output


