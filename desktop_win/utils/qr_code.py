"""
QR Code Generation for Device Connections
==========================================
Handles QR code creation and reading for initial device pairing.
"""

import qrcode
from PIL import Image
import io


def generate_connection_qr(sender_id: str, port: int = 8000) -> bytes:
    """
    Generate QR code for device connection.
    
    Args:
        sender_id: Unique identifier of the sending device
        port: Server port to connect to
        
    Returns:
        QR code image as bytes (PNG format)
    """
    # Format: http://<sender_id>:{port}
    # This will be opened in browser to initiate connection
    connection_url = f"http://{sender_id}:{port}"
    
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    qr.add_data(connection_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to PNG bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr.getvalue()


def save_qr_to_file(qr_data: bytes, filepath: str):
    """Save QR code image to file"""
    import os
    
    if not os.path.exists(os.path.dirname(filepath)):
        os.makedirs(os.path.dirname(filepath))
    
    with open(filepath, 'wb') as f:
        f.write(qr_data)


def read_qr_from_file(filepath: str) -> bytes | None:
    """Read QR code image from file"""
    try:
        with open(filepath, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        return None


def decode_qr_data(qr_data: bytes) -> str | None:
    """
    Decode QR code data (extract URL).
    
    Args:
        qr_data: Raw QR code image bytes
        
    Returns:
        Decoded URL or None if decoding failed
    """
    try:
        from PIL import Image
        
        img = Image.open(io.BytesIO(qr_data))
        
        # Convert to RGB if necessary (handle RGBA)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Use qrcode.get_data to decode
        from qrcode.image.pil import QRCodeImage
        qr_img = QRCodeImage(img)
        
        # Simple approach: use zbarlight or open_url
        # For now, return the URL format we know
        return None  # Would need additional library for full decoding
        
    except Exception as e:
        print(f"QR decode error: {e}")
        return None


def create_connection_code(sender_id: str, port: int = 8000) -> tuple[bytes, str]:
    """
    Create QR code and return both bytes and URL string.
    
    Args:
        sender_id: Unique identifier of the sending device
        port: Server port
        
    Returns:
        Tuple of (QR_code_bytes, connection_url_string)
    """
    qr_data = generate_connection_qr(sender_id, port)
    connection_url = f"http://{sender_id}:{port}"
    
    return qr_data, connection_url


def display_qr_url(url: str):
    """Display URL in system browser (can be used for QR alternative)"""
    import webbrowser
    
    # Open URL in default browser
    webbrowser.open(url)