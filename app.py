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
from moviepy.editor import (
    VideoFileClip,
    ImageSequenceClip,
    concatenate_videoclips,
    vfx,
)
from transformers import AutoModelForImageSegmentation
import torch
from torchvision import transforms
import time
import os
from concurrent.futures import ThreadPoolExecutor


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Maximum image size
Image.MAX_IMAGE_PIXELS = None

torch.set_float32_matmul_precision("high")
device = "cuda" if torch.cuda.is_available() else "cpu"
birefnet = AutoModelForImageSegmentation.from_pretrained(
    "ZhengPeng7/BiRefNet", trust_remote_code=True
)
birefnet.to(device)
birefnet_lite = AutoModelForImageSegmentation.from_pretrained(
    "ZhengPeng7/BiRefNet_lite", trust_remote_code=True
)
birefnet_lite.to(device)

transform_image = transforms.Compose(
    [
        transforms.Resize((1024, 1024)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)

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


def process_frame(frame, bg_type, bg, fast_mode, bg_frame_index, background_frames, color):
    try:
        pil_image = Image.fromarray(frame)
        if bg_type == "Color":
            processed_image = process_video_frame(pil_image, color, fast_mode)
        elif bg_type == "Image":
            processed_image = process_video_frame(pil_image, bg, fast_mode)
        elif bg_type == "Video":
            background_frame = background_frames[bg_frame_index]  # Access the correct background frame
            bg_frame_index += 1
            background_image = Image.fromarray(background_frame)
            processed_image = process_video_frame(pil_image, background_image, fast_mode)
        else:
            processed_image = process_video_frame(pil_image, fast_mode)
        return cv2.cvtColor(np.array(processed_image), cv2.COLOR_RGBA2BGR)
    except Exception as e:
        print("Error:", str(e))
        return frame, bg_frame_index

@app.route("/remove-bg-video", methods=["POST"])
def remove_bg_video():
    if request.content_type != 'application/json':
        return jsonify({"error": "Content-Type must be application/json"}), 415

    temp_video_path = None
    temp_output_paths = []
    try:
        start_time = time.time()
        data = request.get_json()
        video_data = base64.b64decode(data["video"])
        bg_type = data.get('bg_type', None)
        bg_color = data.get('bg_color', None)
        bg_video = data.get('bg_video', None)
        bg_image = data.get('bg_image', None)

        # Check video file size
        max_file_size = 60 * 1024 * 1024  # 60 MB
        if len(video_data) > max_file_size:
            return jsonify({"error": "Video file size exceeds the allowed limit. 😢"}), 400
        
        

        # Save video data to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.mp4') as temp_video_file:
            temp_video_file.write(video_data)
            temp_video_path = temp_video_file.name

        # Load video using moviepy
        video = VideoFileClip(temp_video_path)
        fps = video.fps
        audio = video.audio
        frames = list(video.iter_frames(fps=fps))

        # Limit video resolution and length
        max_resolution = (1280, 720)  # 720p resolution
        max_duration = 60  # 1 minute

        if video.size[0] > max_resolution[0] or video.size[1] > max_resolution[1]:
            return jsonify({"error": "Video resolution exceeds the allowed limit. 😢"}), 400

        if video.duration > max_duration:
            return jsonify({"error": "Video duration exceeds the allowed limit. 😢"}), 400

        processed_frames = []

        if bg_type == "Video":
            background_video = VideoFileClip(bg_video)
            if background_video.duration < video.duration:
                background_video = background_video.fx(vfx.speedx, factor=video.duration / background_video.duration)
            background_frames = list(background_video.iter_frames(fps=fps))
        else:
            background_frames = None
        
        bg_frame_index = 0  # Initialize background frame index
        
        with ThreadPoolExecutor(max_workers=6) as executor:
            # Pass bg_frame_index as part of the function arguments
            futures = [executor.submit(process_frame, frames[i], bg_type, bg_image, bg_frame_index + i, background_frames, bg_color) for i in range(len(frames))] 
            for i, future in enumerate(futures):
                result, _ = future.result() #  No need to update bg_frame_index here
                processed_frames.append(result)
                elapsed_time = time.time() - start_time
                yield result, None, f"Processing frame {i+1}/{len(frames)}... Elapsed time: {elapsed_time:.2f} seconds"

        processed_video = ImageSequenceClip(processed_frames, fps=fps)
        processed_video.audio = processed_video.set_audio(audio)
       

        # Save the final output video to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.mp4') as temp_file:
            temp_filepath = temp_file.name
            processed_video.write_videofile(temp_filepath, codec="libx264")
        
        elapsed_time = time.time() - start_time
        # Read the final output video into a BytesIO object
        output_video_file = io.BytesIO()
        # Encode the output video to base64
        output_video_base64 = base64.b64encode(output_video_file.read()).decode('utf-8')
        # Return the base64 encoded video
        return jsonify({"video": "data:video/mp4;base64," + output_video_base64, elapsed_time: elapsed_time})
    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": "Failed to process video. 😢"}), 500

def process_video_frame(image, bg=None, fast_mode=True):
    image_size = image.size
    input_images = transform_image(image).unsqueeze(0).to(device)
    model = birefnet_lite if fast_mode else birefnet
    
    with torch.no_grad():
        preds = model(input_images)[-1].sigmoid().cpu()
    pred = preds[0].squeeze()
    pred_pil = transforms.ToPILImage()(pred)
    mask = pred_pil.resize(image_size)
    
    if isinstance(bg, str) and bg.startswith("#"):
        color_rgba = hex_to_rgba(bg)
        background = Image.new("RGBA", image_size, color_rgba)
    elif isinstance(bg, Image.Image):
        background = bg.convert("RGBA").resize(image_size)
    else:
        background = Image.open(bg).convert("RGBA").resize(image_size)
    
    image = Image.composite(image, background, mask)
    return image

# Endpoint to remove background from an image
@app.route("/remove-bg", methods=["POST"])
def remove_bg():

    try:
        start_time = time.time()
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
                    output_frame = process_image(frame)
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
                output_image = process_image(input_image)
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
            print("Time taken:", time.time() - start_time) # in seconds
            return jsonify({"image": output_image_base64})
    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": str(e)}), 500

def process_image(image, fast_mode=True):
    image_size = image.size
    input_images = transform_image(image).unsqueeze(0).to(device)
    
    # Use the lite model if fast_mode is enabled
    model = birefnet_lite if fast_mode else birefnet

    # Prediction with mixed precision
    with torch.no_grad():
        preds = model(input_images)[-1].sigmoid().cpu()
    
    pred = preds[0].squeeze()
    pred_pil = transforms.ToPILImage()(pred)
    mask = pred_pil.resize(image_size)
    image.putalpha(mask)
    return image

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
