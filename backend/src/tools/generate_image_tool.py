import os
import datetime
from dotenv import load_dotenv
from google import genai
from langchain_core.tools import tool
from pathlib import Path

SPECIFY_DIR = Path(__file__).parent.parent.parent / "outputs" / "images"

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

def create_hash_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d%H%M%S")

@tool
def create_image_from_prompt(prompt: str) -> dict:
    """
    Generates an image from a text prompt using the Google Gemini API and saves it to the specified directory.

    Args:
        prompt (str): The text prompt to generate the image.

    Returns:
        dict: A dictionary containing:
            - path: The local filesystem path (internal use only, do NOT show to user).
            - url: The frontend-accessible URL that should be used in markdown messages to display the image.
              Example: {"path": "/app/backend/outputs/images/20260705091430.png", "url": "/api/images/20260705091430.png"}
              IMPORTANT: Always use the "url" field when writing markdown to display images to the user.
    """
    response = client.models.generate_content(
        model="gemini-3.1-flash-image",
        contents=[prompt],
    )

    for part in response.parts:
        if part.inline_data is not None:
            image = part.as_image()
            image_name = create_hash_timestamp() + ".png"
            image_path = SPECIFY_DIR / image_name
            os.makedirs(SPECIFY_DIR, exist_ok=True)
            image.save(image_path)
            return {
                "path": str(image_path),
                "url": f"/api/images/{image_name}",
            }
