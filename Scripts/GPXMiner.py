import gpxpy
import folium
import re
import os
import pandas as pd
import numpy as np

from datetime import timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
from haversine import haversine


class GPXminer:
    def __init__(self, gpx_file_path):
        self.project_name = gpx_file_path[::-1][:gpx_file_path[::-1].index('/')][::-1][:-4]
        self.gpx_file_path = gpx_file_path
        self.logo_path = self.file_founder("Strava_idOGsGeeO9_1.png")
        self.font_path_value = self.file_founder("Outfit-SemiBold.ttf")
        self.font_path_title = self.file_founder("Roboto-Bold.ttf")
        self.img_save_path = self.file_founder("Hasil")

        self.gpx = self.load_gpx()
        self.df = self.Miner()
        self.all_summary, self.post_summary = self.SummaryMaker()

        self.logo_img = Image.open(self.logo_path).resize((331, 136))
        self.map_img = self.render_track()

        self.PostPNG = Image.new('RGB', (988, 1317), color=(0, 0, 0))
        self.draw = ImageDraw.Draw(self.PostPNG)

    def load_gpx(self):
        with open(self.gpx_file_path, 'r') as f:
            return gpxpy.parse(f)
    
    def file_founder(self, target_filename):
        base_folder = os.path.join("..")  # karena script ada di 'Scripts', '..' berarti keluar ke atasnya

        # Cari file secara rekursif
        for root, dirs, files in os.walk(base_folder):
            for dire in dirs:
                if dire == target_filename:
                    full_path = os.path.join(root, dire)
                    return full_path
            for file in files:
                if file == target_filename:
                    full_path = os.path.join(root, file)
                    return full_path

    def CountTimeMaker(self, dt_timedelta):
        total_seconds = int(dt_timedelta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            result = f"{hours}h {minutes}m {seconds}s"
        if hours == 0:
            result = f"{minutes}m {seconds}s"
        return result
    
    def PaceMaker(self, pace_detik):
        menit = int(pace_detik // 60)
        detik = int(pace_detik % 60)
        return f"{menit}:{str(detik).zfill(2)} /km"
    
    # Fungsi bantu untuk mengecek apakah string mengandung angka
    def is_number_like(self, text):
        return bool(re.search(r'[\d]', text))

    def Miner(self):
        data = []

        for track in self.gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    data.append({
                        'latitude': point.latitude,
                        'longitude': point.longitude,
                        'elevation': point.elevation,
                        'time': point.time.astimezone(timezone(timedelta(hours=7)))
                    })

        df = pd.DataFrame(data)
        df['time'] = pd.to_datetime(df['time'])
        df['delta_time'] = df['time'].diff().dt.total_seconds().fillna(0)

        # Hitung jarak antar titik (dalam meter)
        df['distance'] = [0] + [haversine(
            (df.iloc[i-1]['latitude'], df.iloc[i-1]['longitude']),
            (df.iloc[i]['latitude'], df.iloc[i]['longitude'])
        ) * 1000 for i in range(1, len(df))]
        df['cum_distance'] = df['distance'].cumsum()

        # Deteksi jeda (pause): waktu antar titik > 30 detik (asumsi bahwa GPS direkam tiap 1 atau 2 detik jika tidak dipause)
        pause_threshold_sec = 30
        df['is_pause'] = (df['delta_time'] > pause_threshold_sec)

        # Hitung kecepatan
        df['speed_mps'] = df['distance'] / df['delta_time'].replace(0, 1)
        df['speed_kph'] = df['speed_mps'] * 3.6
        return df

    def SummaryMaker(self):
        start_time = self.df['time'].iloc[0]
        end_time = self.df['time'].iloc[-1]
        duration_with_pause = end_time - start_time
        total_distance_km = self.df['cum_distance'].iloc[-1] / 1000
        total_distance_km_pause = total_distance_km - self.df[self.df['is_pause'] == True]['distance'].sum()/1000

        # Waktu hanya saat bergerak
        moving_time_sec = self.df.loc[~self.df['is_pause'], 'delta_time'].sum()
        pause_time_sec = self.df.loc[self.df['is_pause'], 'delta_time'].sum()
        moving_time = timedelta(seconds=moving_time_sec)
        pause_time = timedelta(seconds=pause_time_sec)

        # Kecepatan rata-rata
        speed_with_pause = total_distance_km / duration_with_pause.total_seconds() * 3600
        speed_without_pause = total_distance_km / moving_time_sec * 3600

        # Hitung pace
        pace_dengan_pause = duration_with_pause.total_seconds() / total_distance_km
        pace_tanpa_pause = moving_time_sec / total_distance_km_pause

        all_summary = {
            'Start Time': [start_time],
            'End Time': [end_time],
            'Elapsed Time': [duration_with_pause],
            'Moving Time': [moving_time],
            'Pause Time': [pause_time],
            # 'Jarak Total (Dengan Pause) (km)':[ round(total_distance_km, 2)],
            'Distance (km)': [round(total_distance_km_pause, 2)],
            # 'Kecepatan Rata-rata (km/jam) [dengan pause]': [round(speed_with_pause, 2)],
            # 'Kecepatan Rata-rata (km/jam) [tanpa pause]': [round(speed_without_pause, 2)],
            "Avg Elapsed Pace": [self.PaceMaker(pace_dengan_pause)],
            "Avg Pace": [self.PaceMaker(pace_tanpa_pause)],
                }

        post_summary = {
            'Waktu Mulai': start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'Waktu Selesai': end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'Distance': str(round(total_distance_km_pause, 2)) + " km",
            "Pace": self.PaceMaker(pace_tanpa_pause),
            'Time': self.CountTimeMaker(moving_time),
            # 'Kecepatan Rata-rata (km/jam)': str(round(speed_without_pause, 2)) + " km/h",
        }
        return pd.DataFrame(all_summary), post_summary
    
    def TrackViewer(self):
        midpoint = self.df.iloc[len(self.df)//2]
        run_map = folium.Map(location=[midpoint.latitude, midpoint.longitude], zoom_start=15)
        folium.PolyLine(self.df[['latitude', 'longitude']].values, color='blue').add_to(run_map)
        folium.Marker(location=[self.df.iloc[0]['latitude'], self.df.iloc[0]['longitude']], popup='Start', icon=folium.Icon(color='green')).add_to(run_map)
        folium.Marker(location=[self.df.iloc[-1]['latitude'], self.df.iloc[-1]['longitude']], popup='End', icon=folium.Icon(color='red')).add_to(run_map)
        return run_map
    
    # Fungsi bantu untuk teks rata tengah dengan pemilihan font
    def draw_centered_text(self, text, y, font_big, font_small, fill="white"):
        font = font_big if self.is_number_like(text) else font_small
        bbox = self.draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (self.PostPNG.width - text_width) / 2
        self.draw.text((x, y), text, font=font, fill=fill)

    def draw_mixed_text(self, text, y, font_big, font_small, fill="white"):
        # Pisahkan teks menjadi bagian-bagian angka dan non-angka
        parts = re.findall(r'\d+|\D+', text)

        # Hitung total lebar teks untuk posisi tengah
        total_width = 0
        for part in parts:
            font = font_big if part.strip().isdigit() else font_small
            bbox = self.draw.textbbox((0, 0), part, font=font)
            total_width += bbox[2] - bbox[0]

        # Hitung posisi x untuk mulai menggambar dari tengah
        x = (self.PostPNG.width - total_width) / 2

        # Gambar tiap bagian dengan font sesuai
        for part in parts:
            font = font_big if part.strip().isdigit() else font_small
            bbox = self.draw.textbbox((0, 0), part, font=font)
            self.draw.text((x, y), part, font=font, fill=fill)
            x += bbox[2] - bbox[0]


    def render_track(self, width=964, height=680):
        img = Image.new('RGB', (width, height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Normalize koordinat lintasan ke dalam canvas
        lats = self.df['latitude']
        lons = self.df['longitude']
        min_lat, max_lat = lats.min(), lats.max()
        min_lon, max_lon = lons.min(), lons.max()

        # Hitung skala agar lintasan responsive dan proporsional
        lat_range = max_lat - min_lat
        lon_range = max_lon - min_lon
        scale = min((width - 40) / lon_range, (height - 40) / lat_range)

        # Gambar lintasan dengan padding tengah
        points = []
        for _, row in self.df.iterrows():
            x = int((row['longitude'] - min_lon) * scale + (width - (lon_range * scale)) / 2)
            y = int((max_lat - row['latitude']) * scale + (height - (lat_range * scale)) / 2)
            points.append((x, y))

        draw.line(points, fill='#f45105', width=3)
        return img.resize((654, 370))

    def PostPNGMaker(self):
        # Memuat font Roboto Bold
        try:
            value_font_big = ImageFont.truetype(self.font_path_value, 110)
            value_font_small = ImageFont.truetype(self.font_path_title, 50)
            title_font = ImageFont.truetype(self.font_path_title, 110)
        except IOError:
            value_font_big = ImageFont.load_default()
            value_font_small = ImageFont.load_default()
        
        PostPNG = Image.new('RGB', (988, 1317), color=(0, 0, 0))
        draw = ImageDraw.Draw(PostPNG)

        start_title = 70
        start_value = 135
        different = 225
        # Menambahkan teks di bagian atas
        self.draw_centered_text("Distance", start_title, value_font_big, value_font_small)
        self.draw_mixed_text(self.post_summary['Distance'], start_value, value_font_big, title_font)

        self.draw_centered_text("Pace", start_title + different, value_font_big, value_font_small)
        self.draw_mixed_text(self.post_summary['Pace'], start_value + different, value_font_big, title_font)

        self.draw_centered_text("Time", start_title + 2*different, value_font_big, value_font_small)
        self.draw_mixed_text(self.post_summary['Time'], start_value + 2*different, value_font_big, title_font)

        # Menempelkan peta di bagian bawah
        self.PostPNG.paste(self.map_img, ((self.PostPNG.width - self.map_img.width)//2, 765))

        # Menempelkan Logo di bagian bawah
        self.PostPNG.paste(self.logo_img, ((self.PostPNG.width - self.logo_img.width)//2, 1150))

        data = np.array(self.PostPNG.convert("RGBA"))
        # Pisahkan channel warna
        r, g, b, a = data[:, :, 0], data[:, :, 1], data[:, :, 2], data[:, :, 3]

        # Buat masker: background hitam → transparan
        mask_hitam = (r == 0) & (g == 0) & (b == 0)
        data[mask_hitam, 3] = 0  # Set alpha jadi 0 (transparan)

        # Simpan hasilnya
        self.PostPNG = Image.fromarray(data)

        # Menyimpan atau menampilkan gambar
        self.PostPNG.save(f"{self.img_save_path}/{self.project_name}.PNG", format="PNG", bbox_inches='tight', pad_inches=0, facecolor='black')
        self.PostPNG.show()