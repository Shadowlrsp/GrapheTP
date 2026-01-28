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

# ================= CHARGEMENT GTFS =================
def load_gtfs_data():
    shapes = []
    stops = []
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
                stops.append(project(float(row['stop_lat']), float(row['stop_lon'])))
    except: pass
    return shapes, stops

# ================= MAIN =================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Optymo Bus - Turbo Mode")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 16, bold=True)

    # 4 Workers pour télécharger vite !
    tile_manager = TileManager(workers=4)
    gtfs_shapes, gtfs_stops = load_gtfs_data()

    cam_x, cam_y = project(START_LAT, START_LON)
    zoom = START_ZOOM
    dragging = False
    last_mouse_pos = (0, 0)

    # MARGE DE PRÉ-CHARGEMENT (Combien de tuiles hors écran on charge ?)
    # 1 = charge une rangée de plus autour. 2 = deux rangées (plus sûr, un peu plus lourd)
    PRELOAD_MARGIN = 2 
    TILE_SIZE = 256

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: dragging, last_mouse_pos = True, event.pos
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
            for sx, sy in gtfs_stops:
                px, py = int((sx * world_size) - screen_tl_x), int((sy * world_size) - screen_tl_y)
                if 0 <= px <= WIDTH and 0 <= py <= HEIGHT:
                    pygame.draw.circle(screen, STOP_COLOR, (px, py), 3)

        screen.blit(font.render(f"Z: {zoom} | FPS: {int(clock.get_fps())}", True, (50, 50, 50)), (10, 10))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == '__main__':
    main()