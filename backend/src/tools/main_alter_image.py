import os
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

def create_hash_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d%H%M%S")

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
client = genai.Client(api_key=api_key)

client = genai.Client()

# Base image prompt: "A photorealistic picture of a fluffy ginger cat sitting on a wooden floor, looking directly at the camera. Soft, natural light from a window."
image_input = Image.open('./my_images/logo_320_132.png')
text_input = """Aproveite a logo da empresa e crie uma imagem, com fundo branco, para uma campanha publicitária 'Pare de perder vendas trocando de WhatsApp, Instagram e site'"""

# Generate an image from a text prompt
response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents=[text_input, image_input],
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif part.inline_data is not None:
        image = part.as_image()
        image_name = create_hash_timestamp() + ".png"
        image.save("./images/"+image_name)