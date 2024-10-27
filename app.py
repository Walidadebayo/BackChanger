from flask import Flask, request, jsonify
from rembg import remove
from PIL import Image, ImageSequence
import base64
import io
import re

app = Flask(__name__)

# Function to apply background to an image
def apply_background(image, background):
    if background.mode != "RGBA":
        background = background.convert("RGBA")
    image = image.convert("RGBA")
    combined = Image.alpha_composite(background, image)
    return combined

# Function to convert hex color to RGBA
def hex_to_rgba(hex_color):
    hex_color = hex_color.lstrip("#")
    lv = len(hex_color)
    return tuple(int(hex_color[i : i + lv // 3], 16) for i in range(0, lv, lv // 3)) + (255,)

@app.route("/")
def hello_world():
    return "Hi, Welcome to VizXpress"

# Endpoint to remove background from an image
@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    try:
        data = request.get_json()
        image_data = base64.b64decode(data["image"])
        input_image = Image.open(io.BytesIO(image_data))

        if input_image.format == "GIF":
            frames = []
            for frame in ImageSequence.Iterator(input_image):
                frame = frame.convert("RGBA")
                output_frame = remove(frame)
                frames.append(output_frame)

            output_image = io.BytesIO()
            frames[0].save(
                output_image,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                loop=0,
            )
            output_image_base64 = base64.b64encode(output_image.getvalue()).decode("utf-8")
            return jsonify({"image": output_image_base64})
        else:
            output_image = remove(input_image)
            buffered = io.BytesIO()
            output_image.save(buffered, format="PNG")
            output_image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return jsonify({"image": output_image_base64})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Endpoint to apply background to an image
@app.route("/apply-bg", methods=["POST"])
def apply_bg():
    try:
        data = request.get_json()

        # Function to add padding to base64 strings
        def add_padding(base64_string):
            return base64_string + "=" * (-len(base64_string) % 4)

        image_data = base64.b64decode(add_padding(data["image"]))
        input_image = Image.open(io.BytesIO(image_data))

        background_data = data.get("background")

        if background_data:
            # Check if background_data is a hex color
            if re.match(r"^#(?:[0-9a-fA-F]{3}){1,2}$", background_data):
                # Convert hex color to RGBA
                background_color = Image.new(
                    "RGBA", input_image.size, hex_to_rgba(background_data)
                )
                background_image = background_color
            else:
                # Assume it's base64 and decode it
                background_image_data = base64.b64decode(add_padding(background_data))
                background_image = Image.open(io.BytesIO(background_image_data))
        else:
            background_image = Image.new(
                "RGBA", input_image.size, (255, 255, 255, 255)
            )  # Default to white background

        # Resize background image to match input image size
        if background_image.size != input_image.size:
            background_image = background_image.resize(input_image.size)

        if input_image.format == "GIF":
            frames = []
            for frame in ImageSequence.Iterator(input_image):
                frame = frame.convert("RGBA")
                output_frame = apply_background(frame, background_image)
                frames.append(output_frame)

            output_image = io.BytesIO()
            frames[0].save(
                output_image,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                loop=0,
            )
            output_image_base64 = base64.b64encode(output_image.getvalue()).decode("utf-8")
            return jsonify({"image": output_image_base64})
        else:
            output_image = apply_background(input_image, background_image)
            buffered = io.BytesIO()
            output_image.save(buffered, format="PNG")
            output_image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return jsonify({"image": output_image_base64})
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)