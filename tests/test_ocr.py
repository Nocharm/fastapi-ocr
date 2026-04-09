from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_unsupported_type():
    response = client.post(
        "/ocr/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_upload_image(tmp_path):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (200, 50), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Hello OCR", fill="black")

    img_path = tmp_path / "test.png"
    img.save(img_path)

    with open(img_path, "rb") as f:
        response = client.post(
            "/ocr/upload",
            files={"file": ("test.png", f, "image/png")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "markdown" in data
    assert "filename" in data
