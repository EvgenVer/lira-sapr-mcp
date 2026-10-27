"""Model pictures: PNG encoding, white border cropping and the tool."""

import struct
import zlib

import pytest
from mcp import Client

from fakes import fake_session
from lira_sapr_mcp.adapters.picture import crop, encode_png
from lira_sapr_mcp.server import build_server

W, K = b"\xff\xff\xff\xff", b"\x00\x00\x00\xff"  # white and black BGRA pixels


def decode(png: bytes) -> tuple[int, int, bytes]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    pos, idat = 8, b""
    while pos < len(png):
        (size,) = struct.unpack(">I", png[pos : pos + 4])
        kind, data = png[pos + 4 : pos + 8], png[pos + 8 : pos + 8 + size]
        crc = struct.unpack(">I", png[pos + 8 + size : pos + 12 + size])[0]
        assert zlib.crc32(kind + data) == crc
        idat += data if kind == b"IDAT" else b""
        pos += 12 + size
    return width, height, zlib.decompress(idat)


def test_png_holds_the_pixels_in_rgb():
    blue_red = b"\xff\x00\x00\xff" + b"\x00\x00\xff\xff"  # BGRA blue, red
    width, height, raw = decode(encode_png(2, 1, blue_red))
    assert (width, height) == (2, 1)
    assert raw == b"\x00" + b"\x00\x00\xff" + b"\xff\x00\x00"


def test_crop_keeps_the_drawing_and_a_margin():
    # 6 x 5 white picture with one black pixel at (3, 2).
    pixels = bytearray(W * 30)
    pixels[(2 * 6 + 3) * 4 : (2 * 6 + 3) * 4 + 4] = K
    width, height, out = crop(6, 5, bytes(pixels), margin=1)
    assert (width, height) == (3, 3)
    assert out[4 * 4 : 5 * 4] == K  # the centre of the 3 x 3 result


def test_crop_leaves_a_blank_picture_as_it_is():
    assert crop(2, 2, W * 4) == (2, 2, W * 4)


@pytest.mark.anyio
async def test_picture_tool_returns_an_image_and_saves_it(tmp_path):
    session, _ = fake_session(tmp_path)
    model = tmp_path / "frame.lir"
    model.write_bytes(b"lir")
    target = tmp_path / "pics" / "frame.png"
    async with Client(build_server(session)) as client:
        await client.call_tool("lira_open_model", {"path": str(model)})
        res = await client.call_tool("lira_model_picture", {"save_path": str(target)})
        bad = await client.call_tool("lira_model_picture", {"save_path": "frame.png"})
    assert not res.is_error, res.content
    image = res.content[0]
    assert image.type == "image" and image.mime_type == "image/png"
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "saved to" in res.content[1].text
    assert bad.is_error and "absolute .png" in bad.content[0].text
