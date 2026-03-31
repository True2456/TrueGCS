"""
Offline Tile Cache Manager for ISR Drone GCS.

Provides:
  - TileCacheDownloader: Pre-downloads Esri World Imagery tiles for a bounding box.
  - LocalTileServer: Lightweight HTTP server serving tiles from the local cache,
    with transparent CDN fallback on cache miss.

Usage (CLI):
  python -m core.tile_cache --download-nsw
  python -m core.tile_cache --serve
"""

import os
import sys
import math
import time
import threading
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ESRI_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

# Project-relative cache directory
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "tiles"

# NSW, Australia bounding box
NSW_BOUNDS = {
    "lat_min": -37.5,
    "lat_max": -28.0,
    "lon_min": 140.9,
    "lon_max": 154.0,
}

DEFAULT_ZOOM_RANGE = (6, 14)  # inclusive

LOCAL_SERVER_PORT = 9876

# 1x1 dark placeholder PNG (8x8 pixels, dark grey with subtle grid)
# Pre-generated minimal valid PNG bytes for offline fallback
_PLACEHOLDER_PNG = None


def _generate_placeholder_png():
    """Generate a minimal 8x8 dark placeholder PNG in pure Python (no PIL)."""
    import struct
    import zlib

    width, height = 8, 8
    # Build raw pixel data: each row starts with filter byte 0
    raw_data = b""
    for y in range(height):
        raw_data += b"\x00"  # filter: None
        for x in range(width):
            # Dark background with subtle grid lines
            if x == 0 or y == 0:
                raw_data += bytes([30, 38, 45])  # grid line - slightly lighter
            else:
                raw_data += bytes([14, 18, 23])  # dark fill matching BF3 bg

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)

    # IDAT chunk
    compressed = zlib.compress(raw_data)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)

    # IEND chunk
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)

    return signature + ihdr + idat + iend


def get_placeholder_png():
    global _PLACEHOLDER_PNG
    if _PLACEHOLDER_PNG is None:
        _PLACEHOLDER_PNG = _generate_placeholder_png()
    return _PLACEHOLDER_PNG


# ---------------------------------------------------------------------------
# Tile Math (WGS84 lat/lon → Slippy Map tile coordinates)
# ---------------------------------------------------------------------------

def lat_lon_to_tile(lat, lon, zoom):
    """Convert lat/lon to tile x, y at given zoom level."""
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_range_for_bbox(lat_min, lat_max, lon_min, lon_max, zoom):
    """Get the tile x/y range covering a bounding box at a zoom level."""
    x_min, y_max = lat_lon_to_tile(lat_min, lon_min, zoom)  # SW corner
    x_max, y_min = lat_lon_to_tile(lat_max, lon_max, zoom)  # NE corner
    return x_min, x_max, y_min, y_max


def count_tiles_for_bbox(lat_min, lat_max, lon_min, lon_max, zoom_min, zoom_max):
    """Count total tiles for a bounding box across zoom levels."""
    total = 0
    for z in range(zoom_min, zoom_max + 1):
        x_min, x_max, y_min, y_max = tile_range_for_bbox(
            lat_min, lat_max, lon_min, lon_max, z
        )
        total += (x_max - x_min + 1) * (y_max - y_min + 1)
    return total


# ---------------------------------------------------------------------------
# TileCacheDownloader
# ---------------------------------------------------------------------------

class TileCacheDownloader:
    """
    Downloads map tiles from Esri World Imagery for a given bounding box
    and saves them to the local cache directory.
    """

    def __init__(self, cache_dir=None, bounds=None, zoom_range=None):
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.bounds = bounds or NSW_BOUNDS
        self.zoom_range = zoom_range or DEFAULT_ZOOM_RANGE
        self._stop_event = threading.Event()

    def tile_path(self, z, x, y):
        return self.cache_dir / str(z) / str(x) / f"{y}.png"

    def is_cached(self, z, x, y):
        return self.tile_path(z, x, y).exists()

    def download_tile(self, z, x, y):
        """Download a single tile and save to cache. Returns True on success."""
        import requests

        path = self.tile_path(z, x, y)
        if path.exists():
            return True

        url = ESRI_TILE_URL.format(z=z, y=y, x=x)
        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "ISR-GCS-TileCache/1.0"
            })
            if resp.status_code == 200 and len(resp.content) > 100:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(resp.content)
                return True
            else:
                return False
        except Exception as e:
            print(f"  [WARN] Failed to download tile z={z} x={x} y={y}: {e}")
            return False

    def download_region(self, progress_callback=None):
        """
        Download all tiles for the configured bounding box and zoom range.
        
        Args:
            progress_callback: Optional callable(downloaded, total, z, failed)
        """
        b = self.bounds
        z_min, z_max = self.zoom_range

        total = count_tiles_for_bbox(
            b["lat_min"], b["lat_max"], b["lon_min"], b["lon_max"],
            z_min, z_max
        )

        print(f"\n{'='*60}")
        print(f"  ISR GCS — Tile Cache Downloader")
        print(f"  Region: NSW, Australia")
        print(f"  Zoom levels: {z_min} – {z_max}")
        print(f"  Total tiles: {total:,}")
        print(f"  Cache dir: {self.cache_dir}")
        print(f"{'='*60}\n")

        downloaded = 0
        skipped = 0
        failed = 0

        for z in range(z_min, z_max + 1):
            if self._stop_event.is_set():
                print("\n[STOPPED] Download cancelled.")
                break

            x_min, x_max, y_min, y_max = tile_range_for_bbox(
                b["lat_min"], b["lat_max"], b["lon_min"], b["lon_max"], z
            )

            level_total = (x_max - x_min + 1) * (y_max - y_min + 1)
            print(f"  Zoom {z:2d}: {level_total:,} tiles ", end="", flush=True)

            level_downloaded = 0
            level_skipped = 0

            for x in range(x_min, x_max + 1):
                if self._stop_event.is_set():
                    break
                for y in range(y_min, y_max + 1):
                    if self._stop_event.is_set():
                        break

                    if self.is_cached(z, x, y):
                        skipped += 1
                        level_skipped += 1
                    else:
                        success = self.download_tile(z, x, y)
                        if success:
                            level_downloaded += 1
                        else:
                            failed += 1
                        # Polite rate limiting
                        time.sleep(0.05)

                    downloaded += 1

                    if progress_callback:
                        progress_callback(downloaded, total, z, failed)

            print(f"[{level_downloaded} new, {level_skipped} cached]")

        print(f"\n{'='*60}")
        print(f"  Complete! Downloaded: {downloaded - skipped - failed}, "
              f"Cached: {skipped}, Failed: {failed}")
        print(f"{'='*60}\n")

    def stop(self):
        self._stop_event.set()


# ---------------------------------------------------------------------------
# LocalTileServer
# ---------------------------------------------------------------------------

class _TileRequestHandler(BaseHTTPRequestHandler):
    """Serves tiles from cache with transparent CDN fallback."""

    cache_dir = CACHE_DIR

    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass

    def do_GET(self):
        # Expected path: /{z}/{x}/{y}.png
        path = self.path.strip("/")
        parts = path.replace(".png", "").split("/")

        if len(parts) != 3:
            self.send_error(404, "Invalid tile path")
            return

        try:
            z, x, y = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            self.send_error(400, "Invalid tile coordinates")
            return

        tile_file = self.cache_dir / str(z) / str(x) / f"{y}.png"

        # Try serving from cache
        if tile_file.exists():
            self._serve_tile(tile_file.read_bytes())
            return

        # Cache miss — try fetching from CDN
        try:
            import requests
            url = ESRI_TILE_URL.format(z=z, y=y, x=x)
            resp = requests.get(url, timeout=10, headers={
                "User-Agent": "ISR-GCS-TileCache/1.0"
            })
            if resp.status_code == 200 and len(resp.content) > 100:
                # Save to cache
                tile_file.parent.mkdir(parents=True, exist_ok=True)
                tile_file.write_bytes(resp.content)
                self._serve_tile(resp.content)
                return
        except Exception:
            pass

        # Fallback: serve dark placeholder
        self._serve_tile(get_placeholder_png())

    def _serve_tile(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(data)


class _ThreadingTileServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server for parallel tile serving."""
    daemon_threads = True


class LocalTileServer:
    """
    Multi-threaded HTTP tile server running on localhost.
    Serves cached tiles and transparently fetches missing tiles from Esri CDN.
    """

    def __init__(self, port=LOCAL_SERVER_PORT, cache_dir=None):
        self.port = port
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._server = None
        self._thread = None

    def start(self):
        """Start the tile server in a daemon thread."""
        handler = _TileRequestHandler
        handler.cache_dir = self.cache_dir

        try:
            self._server = _ThreadingTileServer(("127.0.0.1", self.port), handler)
        except OSError as e:
            # Port already in use — likely another instance running, which is fine
            print(f"[TileServer] Port {self.port} already in use: {e}")
            return

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="TileServer"
        )
        self._thread.start()
        print(f"[TileServer] Serving tiles on http://127.0.0.1:{self.port}/")

    def stop(self):
        """Stop the tile server."""
        if self._server:
            self._server.shutdown()
            print("[TileServer] Stopped.")

    @property
    def tile_url_template(self):
        return f"http://127.0.0.1:{self.port}/{{z}}/{{x}}/{{y}}.png"


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ISR GCS Tile Cache Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m core.tile_cache --download-nsw
  python -m core.tile_cache --download-nsw --zoom-min 6 --zoom-max 12
  python -m core.tile_cache --serve
        """
    )
    parser.add_argument(
        "--download-nsw", action="store_true",
        help="Download Esri World Imagery tiles for NSW, Australia"
    )
    parser.add_argument(
        "--serve", action="store_true",
        help="Start the local tile server"
    )
    parser.add_argument(
        "--zoom-min", type=int, default=6,
        help="Minimum zoom level (default: 6)"
    )
    parser.add_argument(
        "--zoom-max", type=int, default=14,
        help="Maximum zoom level (default: 14)"
    )

    args = parser.parse_args()

    if args.download_nsw:
        downloader = TileCacheDownloader(
            zoom_range=(args.zoom_min, args.zoom_max)
        )
        try:
            downloader.download_region()
        except KeyboardInterrupt:
            downloader.stop()
            print("\nDownload interrupted by user.")

    elif args.serve:
        server = LocalTileServer()
        server.start()
        print("Press Ctrl+C to stop the tile server.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
