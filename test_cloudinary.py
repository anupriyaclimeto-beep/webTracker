"""
test_cloudinary.py
Quick test: create a small image locally and upload it to Cloudinary.
"""
import sys
import os
from pathlib import Path

# ── load storage (reads .env automatically) ──────────────────────────
import storage

def main():
    print("USE_CLOUDINARY :", storage.USE_CLOUDINARY)
    print("USE_SUPABASE   :", storage.USE_SUPABASE)

    if not storage.USE_CLOUDINARY:
        print("\nERROR: Cloudinary is NOT configured.")
        print("Check that .env has CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET")
        sys.exit(1)

    # Create a tiny test image (red square, no Pillow required)
    # We use a minimal valid 1x1 red PNG in bytes
    import struct, zlib

    def create_red_png(path):
        def chunk(name, data):
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(c[4:]) & 0xFFFFFFFF)

        png  = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", 100, 100, 8, 2, 0, 0, 0))
        raw  = b"".join(b"\x00" + b"\xff\x00\x00" * 100 for _ in range(100))
        png += chunk(b"IDAT", zlib.compress(raw))
        png += chunk(b"IEND", b"")
        with open(path, "wb") as f:
            f.write(png)

    test_img = Path("tmp_cloudinary_test.png")
    create_red_png(str(test_img))
    print(f"\nTest image created: {test_img} ({test_img.stat().st_size} bytes)")

    # Upload to Cloudinary
    print("Uploading to Cloudinary ...")
    url = storage.upload_to_cloudinary(str(test_img), resource_type="image")

    # Cleanup local test file
    test_img.unlink(missing_ok=True)

    if url:
        print(f"\nSUCCESS! Cloudinary URL:\n  {url}")
        print("\nOpen that URL in your browser to see the red image.")
    else:
        print("\nFAILED. Check the error log above for details.")

if __name__ == "__main__":
    main()
