from flask import Flask, request, jsonify
from rembg import remove
from PIL import Image, ImageSequence, ExifTags
import base64
import io
import re
from flask_cors import CORS
import cv2
import numpy as np
import tempfile
from moviepy import VideoFileClip, ImageSequenceClip, concatenate_videoclips, CompositeVideoClip
import os


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Maximum image size
Image.MAX_IMAGE_PIXELS = None


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
    return tuple(int(hex_color[i : i + lv // 3], 16) for i in range(0, lv, lv // 3)) + (
        255,
    )


@app.route("/")
def hello_world():
    return "Hi, Welcome to VizXpress"

@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
    return response



@app.route("/remove-bg-video", methods=["POST"])
def remove_bg_video():
    temp_video_path = None
    temp_output_path = None
    try:
        data = request.get_json()
        video_data = base64.b64decode(data["video"])
        file_extension = data.get('extension', 'mp4')

        # Save video data to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_video_file:
            temp_video_file.write(video_data)
            temp_video_path = temp_video_file.name

        # Load video using moviepy
        video_clip = VideoFileClip(temp_video_path)
        fps = video_clip.fps

        # Process each frame to remove background
        def process_frame(frame):
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            output_image = remove(pil_image)
            output_frame = cv2.cvtColor(np.array(output_image), cv2.COLOR_RGBA2BGR)
            print("Processed frame")
            return output_frame

        processed_frames = [process_frame(frame) for frame in video_clip.iter_frames()]

        # Create a new video clip with the processed frames
        output_clip = ImageSequenceClip(processed_frames, fps=fps)

        # Save the output video to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_output_file:
            output_clip.write_videofile(temp_output_file.name, codec='libx264', audio_codec='aac')
            temp_output_path = temp_output_file.name

        # Read the output video into a BytesIO object
        output_video_file = io.BytesIO()
        with open(temp_output_path, 'rb') as f:
            output_video_file.write(f.read())
        output_video_file.seek(0)

        # Remove the temporary files
        os.remove(temp_video_path)
        os.remove(temp_output_path)

        # Encode the output video to base64
        output_video_base64 = base64.b64encode(output_video_file.read()).decode('utf-8')

        # Return the base64 encoded video
        return jsonify({"video": output_video_base64}), 200
    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        # Ensure temporary files are removed in case of an error
        if temp_video_path and os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        if temp_output_path and os.path.exists(temp_output_path):
            os.remove(temp_output_path)

# Endpoint to remove background from an image
@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    try:
        data = request.get_json()
        image_data = base64.b64decode(data["image"])
        input_image = Image.open(io.BytesIO(image_data))
        # Preserve color profile
        color_profile = input_image.info.get("icc_profile")

        # Correct orientation based on EXIF data
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == "Orientation":
                    break
            exif = dict(input_image._getexif().items())
            if exif[orientation] == 3:
                input_image = input_image.rotate(180, expand=True)
            elif exif[orientation] == 6:
                input_image = input_image.rotate(270, expand=True)
            elif exif[orientation] == 8:
                input_image = input_image.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError):
            # cases: image don't have getexif
            pass

        # Strip metadata by saving and reopening the image
        buffer = io.BytesIO()
        input_image.save(buffer, format="PNG", optimize=True, icc_profile=color_profile)
        buffer.seek(0)
        input_image = Image.open(buffer)

        if input_image.format == "GIF":
            frames = []
            for frame in ImageSequence.Iterator(input_image):
                frame = frame.convert("RGBA")
                try:
                    output_frame = remove(frame)
                except ZeroDivisionError:
                    return (
                        jsonify(
                            {
                                "error": "Division by zero occurred while processing the image."
                            }
                        ),
                        500,
                    )
                frames.append(output_frame)

            output_image = io.BytesIO()
            frames[0].save(
                output_image,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                loop=0,
                optimize=True,
                icc_profile=color_profile,  # Preserve color profile
            )
            output_image_base64 = base64.b64encode(output_image.getvalue()).decode(
                "utf-8"
            )
            return jsonify({"image": output_image_base64})
        else:
            try:
                output_image = remove(input_image)
            except ZeroDivisionError:
                return (
                    jsonify(
                        {
                            "error": "Division by zero occurred while processing the image."
                        }
                    ),
                    500,
                )
            buffered = io.BytesIO()
            output_image.save(
                buffered, format="PNG", optimize=True, icc_profile=color_profile
            )  # Preserve color profile
            output_image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return jsonify({"image": output_image_base64})
    except Exception as e:
        print("Error:", str(e))
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

        # Preserve color profile
        color_profile = input_image.info.get("icc_profile")

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
            output_image_base64 = base64.b64encode(output_image.getvalue()).decode(
                "utf-8"
            )
            return jsonify({"image": output_image_base64})
        else:
            output_image = apply_background(input_image, background_image)
            buffered = io.BytesIO()
            output_image.save(
                buffered, format="PNG", optimize=True, icc_profile=color_profile
            )  # Preserve color profile
            output_image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
            return jsonify({"image": output_image_base64})
    except Exception as e:
        print(e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
