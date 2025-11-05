from geopy.distance import geodesic

class AutoSimulator:
     
    #    route_coords: lista (lat, lon) koordinata rute
    #    speed_kmh: brzina automobila u km/h
    #    interval: interval u sekundama između pomeraja
    def __init__(self, route_coords, speed_kmh=60, interval=1.0):
       
        self.route_coords = route_coords
        self.speed_kmh = speed_kmh
        self.interval = interval
        self.running = False
        
        # Trenutna pozicija između dva čvora
        self.current_segment = 0  # Indeks trenutnog segmenta
        self.progress = 0.0  # Progres duž trenutnog segmenta (0.0 do 1.0)
        
        # Izračunaj koliko metara se pomera po svakom koraku
        self.distance_per_step = (self.speed_kmh * 1000 / 3600) * self.interval  # u metrima
        

    # Vraća trenutnu poziciju automobila (lat, lon) 
    def get_current_position(self):
        
        if self.current_segment >= len(self.route_coords) - 1:
            return self.route_coords[-1]  # Kraj rute
        
        # Interpolacija između dva čvora
        start = self.route_coords[self.current_segment]
        end = self.route_coords[self.current_segment + 1]
        
        lat = start[0] + (end[0] - start[0]) * self.progress
        lon = start[1] + (end[1] - start[1]) * self.progress
        
        return (lat, lon)
    
    # Vraća indeks trenutnog segmenta
    def get_current_segment(self):
        return self.current_segment
    
    # Pomera automobil za jedan korak duž rute"""
    def move(self, debug_print=False):
       
        if self.current_segment >= len(self.route_coords) - 1:
            self.running = False
            return self.get_current_position()
            

        # Trenutni segment
        start = self.route_coords[self.current_segment]
        end = self.route_coords[self.current_segment + 1]
        
        # Dužina trenutnog segmenta u metrima
        segment_length = geodesic(start, end).meters
        
        if segment_length == 0:
            # Ako su dva čvora na istom mestu, pređi na sledeći
            
            if debug_print:
                print(f"Trenutni segment: {self.current_segment}, Duzina: {segment_length}")
            
            self.current_segment += 1
            self.progress = 0.0
    
            return self.get_current_position()
        
        # Koliko progresa napraviti duž ovog segmenta
        progress_increment = self.distance_per_step / segment_length   
        self.progress += progress_increment

        if debug_print:
            print(f"Trenutni segment: {self.current_segment}, Duzina Segmenta: {segment_length}, Step_distance: {self.distance_per_step}, Progres: {self.progress:.2f}, Increment: {progress_increment:.2f}")
        
        # Ako smo prešli trenutni segment, pređi na sledeći
        if self.progress >= 1.0 and self.current_segment < len(self.route_coords) - 1:
            self.progress = 0.0 #-= 1.0
            self.current_segment += 1
            
            # Ponovo izračunaj za novi segment
            if self.current_segment < len(self.route_coords) - 1:
                start = self.route_coords[self.current_segment]
                end = self.route_coords[self.current_segment + 1]
                segment_length = geodesic(start, end).meters
                
                if segment_length > 0:
                    progress_increment = segment_length / self.distance_per_step 
                else:
                    self.current_segment += 1
                    self.progress = 0.0
        
        return self.get_current_position()
    
    # Povećaj brzinu za 10 km/h"""
    def increase_speed(self):
        
        self.speed_kmh += 10
        self.distance_per_step = (self.speed_kmh * 1000 / 3600) * self.interval
        print(f"Brzina povećana: {self.speed_kmh} km/h")
    
    # Smanji brzinu za 10 km/h"""
    def decrease_speed(self):
        
        if self.speed_kmh > 10:
            self.speed_kmh -= 10
            self.distance_per_step = (self.speed_kmh * 1000 / 3600) * self.interval
            print(f"Brzina smanjena: {self.speed_kmh} km/h")
    
    # Proveri da li je automobil stigao na kraj 
    def is_finished(self):
        
        return self.current_segment >= len(self.route_coords) - 1 and self.progress >= 1.0
   
    # Vraća informacije o napretku voznje 
    def get_progress_info(self):
        
        total_segments = len(self.route_coords) - 1
        overall_progress = (self.current_segment + self.progress) / total_segments * 100
        return {
            'segment': self.current_segment,
            'total_segments': total_segments,
            'segment_progress': self.progress * 100,
            'overall_progress': overall_progress,
            'speed_kmh': self.speed_kmh
        }