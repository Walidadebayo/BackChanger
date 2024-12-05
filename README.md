# BackChanger

BackChanger is a Flask-based web application that provides endpoints to remove the background from images and videos, and apply a new background. It supports both static images and animated GIFs.

## Features

- Remove background from images and videos.
- Apply a new background to images.
- Supports both static images and animated GIFs.
- Accepts background as either a hex color or a base64-encoded image.

## Requirements

- Python 3.6+
- Flask
- rembg
- Pillow
- gradio

## Installation

1. Clone the repository:

    ```sh
    git clone https://github.com/Walidadebayo/BackChanger.git
    cd BackChanger
    ```

2. Create a virtual environment and activate it:

    ```sh
    python -m venv .venv
    .venv\Scripts\activate  # On Windows
    # source .venv/bin/activate  # On macOS/Linux
    ```

3. Install the required packages:

    ```sh
    pip install -r requirements.txt
    ```

## Usage

1. Run the Flask application:

    ```sh
    python app.py
    ```

2. The application will be available at `http://127.0.0.1:5000`.

## Endpoints

### `GET /`

Returns a welcome message.

### `POST /remove-bg`

Removes the background from an image.

- **Request Body**: JSON object with a base64-encoded image.
  
  ```json
  {
    "image": "base64-encoded-image-string"
  }
  ```

- **Response**: JSON object with the base64-encoded image with the background removed.
  
  ```json
  {
    "image": "base64-encoded-image-string"
  }
  ```

### `POST /remove-bg-video`

Removes the background from a video.

- **Request Body**: JSON object with a base64-encoded video.
  
  ```json
  {
    "video": "base64-encoded-video-string"
  }
  ```

- **Response**: JSON object with the base64-encoded video with the background removed.
  
  ```json
  {
    "video": "base64-encoded-video-string"
  }
  ```

### `POST /apply-bg`

Applies a new background to an image.

- **Request Body**: JSON object with a base64-encoded image and a background (either a hex color or a base64-encoded image).
  
  ```json
  {
    "image": "base64-encoded-image-string",
    "background": "#hexcolor" or "base64-encoded-background-image-string"
  }
  ```

- **Response**: JSON object with the base64-encoded image with the new background applied.
  
  ```json
  {
    "image": "base64-encoded-image-string"
  }
  ```

## Example

### Remove Background from Image

```sh
curl -X POST http://127.0.0.1:5000/remove-bg -H "Content-Type: application/json" -d '{"image": "base64-encoded-image-string"}'
```

### Remove Background from Video

```sh
curl -X POST http://127.0.0.1:5000/remove-bg-video -H "Content-Type: application/json" -d '{"video": "base64-encoded-video-string"}'
```

### Apply Background to Image or GIF

```sh
curl -X POST http://127.0.0.1:5000/apply-bg -H "Content-Type: application/json" -d '{"image": "base64-encoded-image-string", "background": "#1f7bd0"}'
```

## License

This project is licensed under the MIT License. See the LICENSE file for details.

## Acknowledgements

- [Flask](https://flask.palletsprojects.com/)
- [rembg](https://github.com/danielgatis/rembg)
- [Pillow](https://python-pillow.org/)
- [gradio](https://gradio.app/)

---

Feel free to customize this `README.md` file according to your needs.