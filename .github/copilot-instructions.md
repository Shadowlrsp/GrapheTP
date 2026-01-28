# AI Coding Guidelines for GrapheTP

## Project Overview
This is a Pygame-based interactive map viewer for GTFS (General Transit Feed Specification) public transit data. The application displays bus routes and stops overlaid on map tiles, with smooth zooming and panning.

## Architecture
- **Single-file application**: All logic in `main.py`
- **TileManager class**: Handles asynchronous downloading and caching of map tiles using 4 worker threads with LIFO queue for recent requests
- **GTFS data loading**: Parses `gtfs/shapes.txt` for route geometries and `gtfs/stops.txt` for stop locations
- **Mercator projection**: Converts lat/lon coordinates to screen coordinates using `project()` function
- **Interactive display**: Pygame event loop handling mouse drag, zoom, and rendering

## Key Components
- **Tile caching hierarchy**: RAM → Disk → Network (with persistent requests.Session for speed)
- **Coordinate systems**: World coordinates (0-1 normalized) → Screen pixels via zoom scaling
- **Preloading**: Loads tiles beyond viewport edges for smooth scrolling
- **Culling**: Only renders visible elements to maintain performance

## Development Workflow
- **Run**: `python main.py` (requires pygame, requests installed)
- **Data**: Place GTFS .txt files in `gtfs/` directory
- **Cache**: Map tiles stored in `cache_tiles/` directory
- **Debug**: FPS counter displayed in top-left corner

## Code Patterns
- **Threading**: Use `threading.Lock` for queue synchronization, daemon threads for workers
- **File I/O**: UTF-8-sig encoding for GTFS CSV files, error handling with try/except
- **Pygame rendering**: `pygame.draw.aalines()` for smooth route lines, `pygame.draw.circle()` for stops
- **Coordinate math**: World size = 2^zoom * 256, screen position calculations for tile placement

## Dependencies
- `pygame` for graphics and input
- `requests` for tile downloading (with persistent session)
- GTFS data files in `gtfs/` directory

## Performance Optimizations
- Multi-threaded tile downloading with configurable worker count
- LIFO queue prioritizes recently requested tiles
- Viewport culling for routes and stops
- Preloading margin around visible area
- RAM and disk caching layers</content>
<parameter name="filePath">/home/flaily/Documents/Coding/graphs-projet/GrapheTP/.github/copilot-instructions.md