import pygame
import math
import csv
import requests
import threading
import os
from pathlib import Path

# Config 
WIDTH, HEIGHT = 1000, 800
FPS = 60
START_LAT, START_LON = 47.6386, 6.8631
START_ZOOM = 13

# URL & Dossiers
TILE_URL = "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"
BG_COLOR = (240, 240, 240)
LINE_COLOR = (200, 0, 0)
STOP_COLOR = (0, 50, 200)
GTFS_DIR = "gtfs"
CACHE_DIR = "cache_tiles"

# 
def project(lat, lon):
    sin_y = math.sin(lat * math.pi / 180)
    sin_y = min(max(sin_y, -0.9999), 0.9999)
    x = 0.5 + lon / 360
    y = 0.5 - math.log((1 + sin_y) / (1 - sin_y)) / (4 * math.pi)
    return x, y

# frames
class TileManager:
    def __init__(self, workers=4):
        self.cache = {}
        self.queue = []
        self.lock = threading.Lock()
        self.session = requests.Session() # Connexion persistante (Boost vitesse)
        self.session.headers.update({"User-Agent": "OptymoMap/Turbo"})
        
        Path(CACHE_DIR).mkdir(exist_ok=True)
        
        # Lancer plusieurs workers (4 téléchargements en parallèle)
        self.workers = []
        for _ in range(workers):
            t = threading.Thread(target=self.worker, daemon=True)
            t.start()
            self.workers.append(t)

    def get_tile(self, x, y, z):
        key = (x, y, z)
        
        # 1. RAM
        if key in self.cache:
            return self.cache[key]
        
        filename = f"{CACHE_DIR}/{z}_{x}_{y}.png"
        
        # 2. DISQUE
        if os.path.exists(filename):
            try:
                img = pygame.image.load(filename).convert()
                self.cache[key] = img
                return img
            except:
                pass 

        # 3. FILE D'ATTENTE (Ajouter en priorité haute)
        with self.lock:
            if key not in self.queue:
                # On insert au début pour que ce soit traité tout de suite (LIFO)
                self.queue.append(key)
        
        return None

    def worker(self):
        while True:
            task = None
            with self.lock:
                if self.queue:
                    # On prend le DERNIER élément ajouté (le plus récent demandé par la caméra)
                    task = self.queue.pop(-1)
            
            if not task:
                pygame.time.wait(20)
                continue
            
            x, y, z = task
            filename = f"{CACHE_DIR}/{z}_{x}_{y}.png"
            
            # Double check si fichier existe (au cas où un autre worker l'a fait)
            if os.path.exists(filename):
                continue

            try:
                # Utilisation de self.session pour aller plus vite
                r = self.session.get(TILE_URL.format(x=x, y=y, z=z), timeout=5)
                if r.status_code == 200:
                    with open(filename, "wb") as f:
                        f.write(r.content)
            except Exception as e:
                pass

# ================= LOAD GTFS SUPPORT DATA =================
def load_trips_routes_calendar():
    """Load trips, routes, and calendar data"""
    trips = {}  # {trip_id: {route_id, service_id}}
    routes = {}  # {route_id: {short_name, color}}
    calendar = {}  # {service_id: {mon-sun days}}
    
    try:
        with open(f"{GTFS_DIR}/trips.txt", encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                trips[row['trip_id']] = {
                    'route_id': row['route_id'],
                    'service_id': row['service_id']
                }
    except Exception as e:
        print(f"Error loading trips.txt: {e}")
    
    try:
        with open(f"{GTFS_DIR}/routes.txt", encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                color = row.get('route_color', 'FF0000')
                if not color.startswith('#'):
                    color = '#' + color
                routes[row['route_id']] = {
                    'short_name': row['route_short_name'],
                    'color': color
                }
    except Exception as e:
        print(f"Error loading routes.txt: {e}")
    
    try:
        with open(f"{GTFS_DIR}/calendar.txt", encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                calendar[row['service_id']] = {
                    'monday': row.get('monday', '0'),
                    'tuesday': row.get('tuesday', '0'),
                    'wednesday': row.get('wednesday', '0'),
                    'thursday': row.get('thursday', '0'),
                    'friday': row.get('friday', '0'),
                    'saturday': row.get('saturday', '0'),
                    'sunday': row.get('sunday', '0')
                }
    except Exception as e:
        print(f"Error loading calendar.txt: {e}")
    
    return trips, routes, calendar

# ================= LOAD STOP TIMES =================
def load_stop_times(trips, calendar):
    """Load stop times indexed by stop_id, organized by route and day"""
    stop_times = {}  # {stop_id: {route_id: {day_type: [times]}}}
    try:
        with open(f"{GTFS_DIR}/stop_times.txt", encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                stop_id = row['stop_id']
                trip_id = row['trip_id']
                
                if trip_id not in trips:
                    continue
                
                trip_info = trips[trip_id]
                route_id = trip_info['route_id']
                service_id = trip_info['service_id']
                
                if service_id not in calendar:
                    continue
                
                service = calendar[service_id]
                departure_time = row['departure_time']
                
                if stop_id not in stop_times:
                    stop_times[stop_id] = {}
                if route_id not in stop_times[stop_id]:
                    stop_times[stop_id][route_id] = {'weekday': [], 'saturday': [], 'sunday': []}
                
                # Determine day type
                is_weekday = any(service[day] == '1' for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'])
                is_saturday = service['saturday'] == '1'
                is_sunday = service['sunday'] == '1'
                
                if is_weekday:
                    stop_times[stop_id][route_id]['weekday'].append(departure_time)
                if is_saturday:
                    stop_times[stop_id][route_id]['saturday'].append(departure_time)
                if is_sunday:
                    stop_times[stop_id][route_id]['sunday'].append(departure_time)
    
    except Exception as e:
        print(f"Error loading stop_times.txt: {e}")
    
    # Sort times for each route/day combo
    for stop_id in stop_times:
        for route_id in stop_times[stop_id]:
            for day_type in ['weekday', 'saturday', 'sunday']:
                stop_times[stop_id][route_id][day_type].sort()
    
    return stop_times

# ================= FORMAT TIMES TABLE =================
def format_times_table(times_list):
    """Convert list of times (HH:MM:SS) into a grid format {hour: [minutes]}"""
    grid = {h: [] for h in range(6, 23)}
    for time_str in times_list:
        try:
            h, m, s = map(int, time_str.split(':'))
            if 6 <= h <= 22:
                grid[h].append(m)
        except:
            pass
    # Sort and deduplicate minutes for each hour
    for h in grid:
        grid[h] = sorted(list(set(grid[h])))
    return grid

# ================= CHARGEMENT GTFS =================
def load_gtfs_data():
    shapes = []
    stops = []
    stop_info = {}  # {stop_id: {name, lat, lon, world_x, world_y}}
    print("Chargement GTFS...")
    try:
        with open(f"{GTFS_DIR}/shapes.txt", encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            current_shape_id = None
            pts = []
            for row in sorted(list(reader), key=lambda r: (r['shape_id'], int(r['shape_pt_sequence']))):
                sid = row['shape_id']
                x, y = project(float(row['shape_pt_lat']), float(row['shape_pt_lon']))
                if sid != current_shape_id:
                    if pts: shapes.append(pts)
                    current_shape_id = sid
                    pts = []
                pts.append((x, y))
            if pts: shapes.append(pts)
    except: print("Pas de shapes.txt")

    try:
        with open(f"{GTFS_DIR}/stops.txt", encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                stop_id = row['stop_id']
                lat, lon = float(row['stop_lat']), float(row['stop_lon'])
                x, y = project(lat, lon)
                stops.append((x, y, stop_id))
                stop_info[stop_id] = {
                    'name': row['stop_name'],
                    'lat': lat,
                    'lon': lon,
                    'x': x,
                    'y': y
                }
    except: pass
    return shapes, stops, stop_info

# ================= MAIN =================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Optymo Bus - Turbo Mode")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 16, bold=True)
    small_font = pygame.font.SysFont("Arial", 11)
    tiny_font = pygame.font.SysFont("Arial", 9)

    # 4 Workers pour télécharger vite !
    tile_manager = TileManager(workers=4)
    trips, routes, calendar = load_trips_routes_calendar()
    gtfs_shapes, gtfs_stops_raw, stop_info = load_gtfs_data()
    stop_times = load_stop_times(trips, calendar)
    
    # Filter stops - only keep those with bus times
    gtfs_stops = [(sx, sy, sid) for sx, sy, sid in gtfs_stops_raw if sid in stop_times]
    print(f"Loaded {len(gtfs_stops)} stops with service (filtered from {len(gtfs_stops_raw)})")

    cam_x, cam_y = project(START_LAT, START_LON)
    zoom = START_ZOOM
    dragging = False
    last_mouse_pos = (0, 0)
    selected_stop_id = None  # Track selected stop

    # MARGE DE PRÉ-CHARGEMENT (Combien de tuiles hors écran on charge ?)
    # 1 = charge une rangée de plus autour. 2 = deux rangées (plus sûr, un peu plus lourd)
    PRELOAD_MARGIN = 2 
    TILE_SIZE = 256
    STOP_RADIUS = 8  # Larger stops for better clickability

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: 
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    # Check if clicking on a stop
                    mouse_x, mouse_y = event.pos
                    
                    # Check if clicking in the right panel area (panel is 400px wide)
                    if mouse_x < WIDTH - 400:
                        # Clicked on map - try to select a stop
                        n = 2 ** zoom
                        world_size = n * TILE_SIZE
                        screen_tl_x = (cam_x * world_size) - (WIDTH / 2)
                        screen_tl_y = (cam_y * world_size) - (HEIGHT / 2)
                        
                        selected_stop_id = None
                        for sx, sy, stop_id in gtfs_stops:
                            px = int((sx * world_size) - screen_tl_x)
                            py = int((sy * world_size) - screen_tl_y)
                            dist = math.sqrt((px - mouse_x)**2 + (py - mouse_y)**2)
                            if dist <= STOP_RADIUS + 5:  # 5px tolerance
                                selected_stop_id = stop_id
                                break
                    else:
                        # Clicked in panel area - deselect
                        selected_stop_id = None
                    dragging, last_mouse_pos = True, event.pos
                elif event.button == 4: zoom = min(zoom + 1, 19)
                elif event.button == 5: zoom = max(zoom - 1, 10)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1: dragging = False
            elif event.type == pygame.MOUSEMOTION and dragging:
                dx, dy = event.pos[0] - last_mouse_pos[0], event.pos[1] - last_mouse_pos[1]
                world_scale = 2 ** zoom * TILE_SIZE
                cam_x -= dx / world_scale
                cam_y -= dy / world_scale
                last_mouse_pos = event.pos

        screen.fill(BG_COLOR)

        n = 2 ** zoom
        world_size = n * TILE_SIZE
        screen_tl_x = (cam_x * world_size) - (WIDTH / 2)
        screen_tl_y = (cam_y * world_size) - (HEIGHT / 2)

        # Calcul des indices visibles + MARGE
        start_col = int(screen_tl_x / TILE_SIZE) - PRELOAD_MARGIN
        end_col = int((screen_tl_x + WIDTH) / TILE_SIZE) + 1 + PRELOAD_MARGIN
        start_row = int(screen_tl_y / TILE_SIZE) - PRELOAD_MARGIN
        end_row = int((screen_tl_y + HEIGHT) / TILE_SIZE) + 1 + PRELOAD_MARGIN

        # Boucle d'affichage
        for col in range(start_col, end_col):
            for row in range(start_row, end_row):
                tile_col = col % n
                tile_row = row 
                
                if 0 <= tile_row < n:
                    # Demande la tuile (si elle est dans la marge, elle sera téléchargée en background)
                    img = tile_manager.get_tile(tile_col, tile_row, zoom)
                    
                    # On ne dessine QUE ce qui est réellement sur l'écran (pas la marge)
                    draw_x = (col * TILE_SIZE) - screen_tl_x
                    draw_y = (row * TILE_SIZE) - screen_tl_y
                    
                    if -TILE_SIZE < draw_x < WIDTH and -TILE_SIZE < draw_y < HEIGHT:
                        if img:
                            screen.blit(img, (draw_x, draw_y))
                        else:
                            # Placeholder plus discret
                            pygame.draw.rect(screen, BG_COLOR, (draw_x, draw_y, TILE_SIZE, TILE_SIZE))

        # Lignes & Arrêts (Code identique, juste condensé pour lisibilité)
        line_width = max(1, int(zoom / 4))
        if gtfs_shapes:
            for shape in gtfs_shapes:
                points_px = [((sx * world_size) - screen_tl_x, (sy * world_size) - screen_tl_y) for sx, sy in shape]
                # Culling simple
                if any(-50 < p[0] < WIDTH+50 and -50 < p[1] < HEIGHT+50 for p in points_px):
                    if len(points_px) > 1: pygame.draw.aalines(screen, LINE_COLOR, False, points_px)

        if zoom >= 14:
            for sx, sy, stop_id in gtfs_stops:
                px, py = int((sx * world_size) - screen_tl_x), int((sy * world_size) - screen_tl_y)
                if -STOP_RADIUS < px < WIDTH + STOP_RADIUS and -STOP_RADIUS < py < HEIGHT + STOP_RADIUS:
                    color = (255, 200, 0) if stop_id == selected_stop_id else STOP_COLOR
                    pygame.draw.circle(screen, color, (px, py), STOP_RADIUS)

        # Draw right panel with stop info
        panel_width = 400
        panel_x = WIDTH - panel_width
        pygame.draw.rect(screen, (30, 30, 50), (panel_x, 0, panel_width, HEIGHT))
        pygame.draw.line(screen, (100, 100, 150), (panel_x, 0), (panel_x, HEIGHT), 2)
        
        if selected_stop_id and selected_stop_id in stop_info:
            stop = stop_info[selected_stop_id]
            routes_data = stop_times.get(selected_stop_id, {})
            
            # Draw stop name
            title = pygame.font.SysFont("Arial", 13, bold=True).render(stop['name'][:35], True, (255, 255, 255))
            screen.blit(title, (panel_x + 8, 8))
            
            # Draw routes and times
            y_offset = 28
            for route_id in sorted(routes_data.keys()):
                if y_offset > HEIGHT - 180:
                    break
                
                route_info = routes.get(route_id, {'short_name': route_id, 'color': '#FF0000'})
                route_name = route_info['short_name']
                route_color_hex = route_info['color'].lstrip('#')
                route_color = tuple(int(route_color_hex[i:i+2], 16) for i in (0, 2, 4))
                
                times_data = routes_data[route_id]
                
                # Draw route header with colored background
                header_rect = pygame.Rect(panel_x + 6, y_offset, panel_width - 12, 18)
                pygame.draw.rect(screen, route_color, header_rect)
                route_label = small_font.render(f"Line {route_name}", True, (255, 255, 255))
                screen.blit(route_label, (panel_x + 10, y_offset + 2))
                y_offset += 20
                
                # Draw times by day type in table format
                day_types = [('Weekdays', 'weekday'), ('Saturday', 'saturday'), ('Sunday', 'sunday')]
                for day_label, day_key in day_types:
                    times_list = times_data[day_key]
                    if times_list:
                        day_text = tiny_font.render(day_label + ":", True, (200, 200, 220))
                        screen.blit(day_text, (panel_x + 10, y_offset))
                        y_offset += 12
                        
                        # Create table
                        grid = format_times_table(times_list)
                        
                        # Draw hours header
                        x_pos = panel_x + 12
                        col_width = 28
                        for h in range(6, 23):
                            h_text = tiny_font.render(str(h), True, (150, 150, 200))
                            screen.blit(h_text, (x_pos + (h - 6) * col_width, y_offset))
                        y_offset += 12
                        
                        # Draw minutes for each hour (vertical columns)
                        max_mins_in_column = max(len(grid[h]) for h in range(6, 23)) if grid else 0
                        for row in range(max_mins_in_column):
                            x_pos = panel_x + 12
                            for h in range(6, 23):
                                if row < len(grid[h]):
                                    min_val = grid[h][row]
                                    min_text = tiny_font.render(f"{min_val:02d}", True, (100, 200, 100))
                                    screen.blit(min_text, (x_pos + (h - 6) * col_width, y_offset))
                            y_offset += 10
                        
                        y_offset += 4
                
                y_offset += 3
        else:
            no_select = small_font.render("Click a stop", True, (150, 150, 180))
            screen.blit(no_select, (panel_x + 10, 20))
            no_select2 = small_font.render("for details", True, (150, 150, 180))
            screen.blit(no_select2, (panel_x + 10, 40))

        screen.blit(font.render(f"Z: {zoom} | FPS: {int(clock.get_fps())}", True, (50, 50, 50)), (10, 10))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == '__main__':
    main()