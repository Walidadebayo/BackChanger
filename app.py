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
from moviepy import (
    VideoFileClip,
    ImageSequenceClip,
    concatenate_videoclips,
    CompositeVideoClip,
)
import os
import warnings

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
    return "Hello, Welcome to VizXpress"


@app.after_request
def add_cors_headers(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
    return response


@app.route("/remove-bg-video", methods=["POST"])
def remove_bg_video():
    if request.content_type != 'application/json':
        return jsonify({"error": "Content-Type must be application/json"}), 415

    temp_video_path = None
    temp_output_paths = []
    try:
        data = request.get_json()
        video_data = base64.b64decode(data["video"])
        file_extension = data.get('extension', 'mp4')

        # Check video file size
        max_file_size = 60 * 1024 * 1024  # 60 MB
        if len(video_data) > max_file_size:
            return jsonify({"error": "Video file size exceeds the allowed limit. 😢"}), 400

        # Save video data to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_video_file:
            temp_video_file.write(video_data)
            temp_video_path = temp_video_file.name

        # Load video using moviepy
        video_clip = VideoFileClip(temp_video_path)
        fps = video_clip.fps

        # Limit video resolution and length
        max_resolution = (1280, 720)  # 720p resolution
        max_duration = 60  # 1 minute

        if video_clip.size[0] > max_resolution[0] or video_clip.size[1] > max_resolution[1]:
            return jsonify({"error": "Video resolution exceeds the allowed limit. 😢"}), 400

        if video_clip.duration > max_duration:
            return jsonify({"error": "Video duration exceeds the allowed limit. 😢"}), 400

        # Calculate number of frames in the video
        num_frames = int(video_clip.duration * fps)
        print(f"Number of frames in the video: {num_frames}")

        # Process each frame to remove background
        def process_frame(frame):
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            output_image = remove(pil_image)
            output_frame = cv2.cvtColor(np.array(output_image), cv2.COLOR_RGBA2BGR)
            return output_frame

        batch_size = 5  # Adjust batch size based on memory constraints
        processed_frames = []
        for i, frame in enumerate(video_clip.iter_frames()):
            try:
                processed_frame = process_frame(frame)
                processed_frames.append(processed_frame)
            except Exception as e:
                print(f"Warning: Skipping frame due to error: {e}")
                processed_frames.append(frame)

            # Process and release frames in batches
            if (i + 1) % batch_size == 0 or (i + 1) == num_frames:
                # Create a new video clip with the processed frames
                output_clip = ImageSequenceClip(processed_frames, fps=fps)

                # Determine the codec based on the file extension
                if file_extension == 'webm':
                    codec = 'libvpx-vp9'
                else:
                    codec = 'libx264'

                # Save the output video to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_output_file:
                    output_clip.write_videofile(temp_output_file.name, codec=codec, audio_codec='aac')
                    temp_output_paths.append(temp_output_file.name)

                # Clear processed frames to release memory
                processed_frames.clear()

        # Concatenate all the temporary video files
        clips = [VideoFileClip(path) for path in temp_output_paths]
        final_clip = concatenate_videoclips(clips)

        # Save the final output video to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as final_output_file:
            final_clip.write_videofile(final_output_file.name, codec=codec, audio_codec='aac')
            final_output_path = final_output_file.name

        # Read the final output video into a BytesIO object
        output_video_file = io.BytesIO()
        with open(final_output_path, 'rb') as f:
            output_video_file.write(f.read())
        output_video_file.seek(0)

        # Remove the temporary files
        if video_clip.reader:
            video_clip.reader.close()
        if video_clip.audio and video_clip.audio.reader:
            video_clip.audio.reader.close()
        try:
            os.remove(temp_video_path)
        except PermissionError:
            print(f"PermissionError: Could not remove {temp_video_path}")
            
        for path in temp_output_paths:
            clip = VideoFileClip(path)
            if clip.reader:
                clip.reader.close()
            if clip.audio and clip.audio.reader:
                clip.audio.reader.close()
            clip.close()
            try:
                os.remove(path)
            except PermissionError:
                print(f"PermissionError: Could not remove {path}")
        try:
            os.remove(final_output_path)
        except PermissionError:
            print(f"PermissionError: Could not remove {final_output_path}")

        # Encode the output video to base64
        output_video_base64 = base64.b64encode(output_video_file.read()).decode('utf-8')

        # Return the base64 encoded video
        return jsonify({"video": output_video_base64}), 200
    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": "Failed to process video. 😢"}), 500
    finally:
        # Ensure temporary files are removed in case of an error
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                if video_clip.reader:
                    video_clip.reader.close()
                if video_clip.audio and video_clip.audio.reader:
                    video_clip.audio.reader.close()
            except Exception as e:
                print(f"Error closing video clip: {e}")
            try:
                os.remove(temp_video_path)
            except PermissionError:
                print(f"PermissionError: Could not remove {temp_video_path}")
        for path in temp_output_paths:
            if os.path.exists(path):
                try:
                    clip = VideoFileClip(path)
                    if clip.reader:
                        clip.reader.close()
                    if clip.audio and clip.audio.reader:
                        clip.audio.reader.close()
                    clip.close()
                except Exception as e:
                    print(f"Error closing clip: {e}")
                try:
                    os.remove(path)
                except PermissionError:
                    print(f"PermissionError: Could not remove {path}")


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
