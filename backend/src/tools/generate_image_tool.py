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
def create_image_from_prompt(prompt: str) -> str:
    """
    Generates an image from a text prompt using the Google Gemini API and saves it to the specified directory.

    Args:
        prompt (str): The text prompt to generate the image.

    Returns:
        str: The path to the saved image file.
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[prompt],
    )

    for part in response.parts:
        if part.inline_data is not None:
            image = part.as_image()
            image_name = create_hash_timestamp() + ".png"
            image_path = SPECIFY_DIR / image_name
            os.makedirs(SPECIFY_DIR, exist_ok=True)
            image.save(image_path)
            return image_path
