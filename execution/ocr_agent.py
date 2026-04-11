import os
import io
from PIL import Image, ImageDraw
import fitz

def prepare_images_from_file(filepath: str) -> tuple[list[Image.Image], str]:
    """
    Takes a file path (PDF, JPEG, PNG, TXT).
    Returns a tuple: (list of PIL Images for vision/thumbnails, raw_text_if_txt).
    """
    _, ext = os.path.splitext(filepath.lower())
    
    if ext == '.pdf':
        try:
            doc = fitz.open(filepath)
            images = []
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                images.append(img)
            return images, ""
        except Exception as e:
            raise RuntimeError(f"Failed to convert PDF to images: {e}")
            
    elif ext in ['.png', '.jpg', '.jpeg']:
        try:
            img = Image.open(filepath)
            return [img], ""
        except Exception as e:
            raise RuntimeError(f"Failed to open image file: {e}")
            
    elif ext == '.txt':
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()

            img = Image.new('RGB', (600, 800), color=(250, 250, 250))
            d = ImageDraw.Draw(img)

            d.text((30, 30), text[:1500] + ("..." if len(text)>1200 else ""), fill=(40,40,40))
            return [img], text
        except Exception as e:
            raise RuntimeError(f"Failed to read TXT file: {e}")
            
    else:
        raise ValueError(f"Unsupported file format: {ext}")
