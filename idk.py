import tkinter as tk
from tkinter import ttk, messagebox, font
import csv
import os
import time
import random
import threading
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from datetime import datetime, timedelta
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import bluetooth  # For Bluetooth connectivity
import queue
import json
import numpy as np

# Application constants
APP_VERSION = "2.0"
AUTHOR = "DiabCare Smart Solutions"

# Thresholds for health alerts
TEMPERATURE_THRESHOLD = 37.0
HUMIDITY_THRESHOLD = 60.0
PRESSURE_THRESHOLD = 500

# Data storage
data_file = "insole_data.csv"
config_file = "insole_config.json"
latest_readings = {
    "temperature": 0.0,
    "humidity": 0.0,
    "heel_pressure": 0,
    "meta_pressure": 0,
    "timestamp": None
}

# Bluetooth connection info
DEFAULT_BT_MAC_ADDRESS = "00:11:22:33:44:55"  # Default MAC address
DEFAULT_BT_PORT = 1  # Default SPP port
BT_CONNECTION_TIMEOUT = 10  # Seconds to wait for connection
BT_READ_TIMEOUT = 5  # Seconds to wait for data

# Queue for inter-thread communication
data_queue = queue.Queue()

# Default configuration
default_config = {
    "bluetooth": {
        "mac_address": DEFAULT_BT_MAC_ADDRESS,
        "port": DEFAULT_BT_PORT,
        "auto_reconnect": True,
        "reconnect_interval": 30
    },
    "monitoring": {
        "update_interval": 5,  # seconds
        "temperature_threshold": TEMPERATURE_THRESHOLD,
        "humidity_threshold": HUMIDITY_THRESHOLD,
        "pressure_threshold": PRESSURE_THRESHOLD,
        "alert_sound": True
    },
    "simulation": {
        "enabled": True,
        "realistic_variation": True
    },
    "ui": {
        "theme": "dark",
        "graph_points": 50,
        "auto_export": False
    }
}

# Theme colors
THEMES = {
    "dark": {
        "bg_color": "#121212",  # Dark background
        "card_bg": "#1E1E1E",   # Slightly lighter for cards
        "text_primary": "#FFFFFF",  # White text
        "text_secondary": "#B0B0B0",  # Lighter gray text
        "accent_color": "#BB86FC",  # Purple accent
        "accent_secondary": "#03DAC6",  # Teal accent
        "header_color": "#1F1B24",  # Dark purple header
        "alert_bg": "#3D0000",  # Dark red for alerts
        "alert_fg": "#FF5252",  # Bright red for alert text
        "success_color": "#4CAF50",  # Green for normal readings
        "graph_bg": "#1E1E1E",  # Graph background
        "grid_color": "#333333",  # Grid color for graphs
        "temp_color": "#FF5733",  # Temperature line color
        "humidity_color": "#3498DB",  # Humidity line color 
        "heel_color": "#4CAF50",  # Heel pressure line color
        "meta_color": "#F39C12"   # Metatarsal pressure line color
    }
}

# Global variables
config = default_config.copy()
bt_socket = None
bt_connected = False
connection_attempt_in_progress = False

# Load configuration
def load_config():
    global config
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                loaded_config = json.load(f)
                # Merge with defaults for any missing keys
                for category in default_config:
                    if category not in loaded_config:
                        loaded_config[category] = default_config[category]
                    else:
                        for key in default_config[category]:
                            if key not in loaded_config[category]:
                                loaded_config[category][key] = default_config[category][key]
                config = loaded_config
                print("Configuration loaded successfully")
        else:
            save_config()  # Save default config
    except Exception as e:
        print(f"Error loading configuration: {e}")
        config = default_config.copy()
        save_config()  # Save default config

# Save configuration
def save_config():
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
        print("Configuration saved successfully")
    except Exception as e:
        print(f"Error saving configuration: {e}")

# Create or check for data file
def initialize_data_file():
    if not os.path.exists(data_file):
        with open(data_file, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Timestamp', 'Temperature', 'Humidity', 'Heel_Pressure', 'Meta_Pressure'])
        print(f"Created new data file: {data_file}")

# Background thread for Bluetooth connection
def bluetooth_connection_thread():
    global bt_socket, bt_connected, connection_attempt_in_progress
    
    while True:
        if not bt_connected and config["bluetooth"]["auto_reconnect"] and not connection_attempt_in_progress:
            connection_attempt_in_progress = True
            success = connect_bluetooth()
            connection_attempt_in_progress = False
            
            if success:
                # Start reading thread
                bt_reading_thread = threading.Thread(target=bluetooth_reading_thread, daemon=True)
                bt_reading_thread.start()
            else:
                # Wait before retrying
                time.sleep(config["bluetooth"]["reconnect_interval"])
        
        # Check connection status periodically
        time.sleep(5)

# Background thread for reading Bluetooth data
def bluetooth_reading_thread():
    global bt_socket, bt_connected
    
    while bt_connected:
        try:
            get_data_from_bluetooth()
            time.sleep(config["monitoring"]["update_interval"])
        except Exception as e:
            print(f"Error in Bluetooth reading thread: {e}")
            bt_connected = False
            break

# Connect to Bluetooth device with improved error handling
def connect_bluetooth():
    global bt_socket, bt_connected
    
    try:
        print(f"Attempting to connect to Bluetooth device at {config['bluetooth']['mac_address']}...")
        bt_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        bt_socket.settimeout(BT_CONNECTION_TIMEOUT)
        bt_socket.connect((config['bluetooth']['mac_address'], config['bluetooth']['port']))
        bt_socket.settimeout(BT_READ_TIMEOUT)  # Set read timeout
        bt_connected = True
        print("Successfully connected to Bluetooth device")
        
        # Add connected device to known devices if not already there
        add_to_known_devices(config['bluetooth']['mac_address'])
        
        # Queue connection status message
        data_queue.put({"type": "connection_status", "status": "connected", "message": "Connected to Bluetooth device"})
        return True
    except bluetooth.btcommon.BluetoothError as be:
        error_msg = f"Bluetooth error: {be}"
        print(error_msg)
        data_queue.put({"type": "connection_status", "status": "failed", "message": error_msg})
    except OSError as oe:
        error_msg = f"OS error connecting to Bluetooth: {oe}"
        print(error_msg)
        data_queue.put({"type": "connection_status", "status": "failed", "message": error_msg})
    except Exception as e:
        error_msg = f"Failed to connect to Bluetooth: {e}"
        print(error_msg)
        data_queue.put({"type": "connection_status", "status": "failed", "message": error_msg})
    
    bt_connected = False
    data_queue.put({"type": "connection_status", "status": "disconnected", "message": "Using simulation mode"})
    return False

# Discover nearby Bluetooth devices
def discover_devices():
    try:
        print("Scanning for nearby Bluetooth devices...")
        nearby_devices = bluetooth.discover_devices(duration=8, lookup_names=True)
        print(f"Found {len(nearby_devices)} devices")
        return nearby_devices
    except Exception as e:
        print(f"Error discovering devices: {e}")
        return []

# Add device to known devices list
def add_to_known_devices(mac_address):
    try:
        if not os.path.exists("known_devices.json"):
            with open("known_devices.json", "w") as f:
                json.dump([], f)
        
        with open("known_devices.json", "r") as f:
            known_devices = json.load(f)
        
        # Check if device already in list
        for device in known_devices:
            if device.get("mac") == mac_address:
                return
        
        # Add device
        known_devices.append({
            "mac": mac_address,
            "last_connected": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        with open("known_devices.json", "w") as f:
            json.dump(known_devices, f, indent=4)
    except Exception as e:
        print(f"Error adding device to known devices: {e}")

# Read data from Bluetooth with improved reliability
def get_data_from_bluetooth():
    global bt_socket, bt_connected
    
    if not bt_connected:
        return False
    
    try:
        # Send command to request data (with retry mechanism)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                bt_socket.send("GET_DATA")
                break
            except Exception as e:
                if attempt == max_retries - 1:  # Last attempt
                    raise e
                time.sleep(0.5)  # Short wait before retry
        
        # Wait for and receive response
        data = bt_socket.recv(1024).decode().strip()
        
        # Parse data (assuming CSV format: temp,humidity,heel,meta)
        values = data.split(',')
        if len(values) == 4:
            latest_readings["temperature"] = float(values[0])
            latest_readings["humidity"] = float(values[1])
            latest_readings["heel_pressure"] = int(float(values[2]))
            latest_readings["meta_pressure"] = int(float(values[3]))
            latest_readings["timestamp"] = datetime.now()
            
            # Save data to CSV
            save_data_to_csv()
            
            # Queue data for UI update
            data_queue.put({"type": "sensor_data", "data": latest_readings.copy()})
            return True
        else:
            print(f"Invalid data format received: {data}")
            return False
    except bluetooth.btcommon.BluetoothError as be:
        print(f"Bluetooth error reading data: {be}")
        bt_connected = False
        data_queue.put({"type": "connection_status", "status": "disconnected", "message": "Bluetooth connection lost"})
        return False
    except Exception as e:
        print(f"Error reading from Bluetooth: {e}")
        bt_connected = False
        data_queue.put({"type": "connection_status", "status": "disconnected", "message": f"Error: {str(e)}"})
        return False

# Generate smart realistic data with trends and patterns
def generate_smart_simulated_data():
    global latest_readings
    
    # Get current time for time-based patterns
    current_hour = datetime.now().hour
    
    # Define base values (time-dependent)
    # Temperature: Higher in afternoon/evening, lower at night/morning
    time_factor = abs(current_hour - 12) / 12.0  # 0 at noon, 1 at midnight
    base_temp = 36.0 + (0.8 * (1 - time_factor))
    
    # Humidity: Higher in morning
    humidity_factor = max(0, 1 - abs(current_hour - 8) / 8.0)  # Peaks at 8 AM
    base_humidity = 45.0 + (10.0 * humidity_factor)
    
    # Pressure: Higher during typical active hours
    is_active_hours = 8 <= current_hour <= 21
    base_pressure = 300 if is_active_hours else 200
    
    # Get previous values for continuity if available
    if latest_readings["timestamp"] is not None:
        prev_temp = latest_readings["temperature"]
        prev_humidity = latest_readings["humidity"]
        prev_heel = latest_readings["heel_pressure"]
        prev_meta = latest_readings["meta_pressure"]
        
        # Create smooth transitions (max 10% change for continuity)
        max_temp_change = 0.3
        max_humidity_change = 2.0
        max_pressure_change = 50
        
        # Calculate target values (where we want to go)
        target_temp = base_temp + random.uniform(-0.5, 0.5)
        target_humidity = base_humidity + random.uniform(-5.0, 5.0)
        target_heel = base_pressure + random.uniform(-100, 100)
        target_meta = base_pressure + random.uniform(-100, 100)
        
        # Move toward target, but with limited max change
        new_temp = prev_temp + max(min(target_temp - prev_temp, max_temp_change), -max_temp_change)
        new_humidity = prev_humidity + max(min(target_humidity - prev_humidity, max_humidity_change), -max_humidity_change)
        new_heel = prev_heel + max(min(target_heel - prev_heel, max_pressure_change), -max_pressure_change)
        new_meta = prev_meta + max(min(target_meta - prev_meta, max_pressure_change), -max_pressure_change)
    else:
        # Initial values
        new_temp = base_temp + random.uniform(-0.5, 0.5)
        new_humidity = base_humidity + random.uniform(-5.0, 5.0)
        new_heel = base_pressure + random.uniform(-50, 50)
        new_meta = base_pressure + random.uniform(-50, 50)
    
    # Occasionally introduce anomalies (5% chance)
    if random.random() < 0.05:
        anomaly_type = random.randint(0, 3)
        if anomaly_type == 0:
            new_temp = TEMPERATURE_THRESHOLD + random.uniform(0.1, 1.0)
        elif anomaly_type == 1:
            new_humidity = HUMIDITY_THRESHOLD + random.uniform(1.0, 10.0)
        elif anomaly_type == 2:
            new_heel = PRESSURE_THRESHOLD + random.uniform(10, 100)
        else:
            new_meta = PRESSURE_THRESHOLD + random.uniform(10, 100)
    
    # Ensure values are within realistic ranges
    new_temp = max(34.0, min(39.0, new_temp))
    new_humidity = max(30.0, min(90.0, new_humidity))
    new_heel = max(50, min(800, int(new_heel)))
    new_meta = max(50, min(800, int(new_meta)))
    
    latest_readings["temperature"] = new_temp
    latest_readings["humidity"] = new_humidity
    latest_readings["heel_pressure"] = new_heel
    latest_readings["meta_pressure"] = new_meta
    latest_readings["timestamp"] = datetime.now()
    
    # Save data to CSV
    save_data_to_csv()
    
    # Queue data for UI update
    data_queue.put({"type": "sensor_data", "data": latest_readings.copy()})
    return True

# Save data to CSV
def save_data_to_csv():
    try:
        with open(data_file, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                latest_readings["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                latest_readings["temperature"],
                latest_readings["humidity"],
                latest_readings["heel_pressure"],
                latest_readings["meta_pressure"]
            ])
    except Exception as e:
        print(f"Error saving data to CSV: {e}")

# Analyze data for potential issues with advanced pattern detection
def analyze_data(historical=False):
    alerts = []
    thresholds = config["monitoring"]
    
    # Get historical data for pattern detection if requested
    if historical:
        try:
            data_points = []
            with open(data_file, 'r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    if len(row) >= 5:  # Ensure row has enough data
                        data_points.append({
                            "timestamp": datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"),
                            "temperature": float(row[1]),
                            "humidity": float(row[2]),
                            "heel_pressure": int(float(row[3])),
                            "meta_pressure": int(float(row[4]))
                        })
            
            # Only look at last 24 hours of data
            cutoff_time = datetime.now() - timedelta(hours=24)
            recent_data = [d for d in data_points if d["timestamp"] > cutoff_time]
            
            if len(recent_data) >= 10:  # Need enough data points for analysis
                # Check for sustained high values (3+ consecutive readings above threshold)
                high_temp_count = 0
                high_humidity_count = 0
                high_heel_count = 0
                high_meta_count = 0
                
                for point in recent_data[-5:]:  # Check last 5 readings
                    if point["temperature"] > thresholds["temperature_threshold"]:
                        high_temp_count += 1
                    if point["humidity"] > thresholds["humidity_threshold"]:
                        high_humidity_count += 1
                    if point["heel_pressure"] > thresholds["pressure_threshold"]:
                        high_heel_count += 1
                    if point["meta_pressure"] > thresholds["pressure_threshold"]:
                        high_meta_count += 1
                
                if high_temp_count >= 3:
                    alerts.append("⚠️ PATTERN: Sustained high temperature detected")
                if high_humidity_count >= 3:
                    alerts.append("⚠️ PATTERN: Sustained high humidity detected")
                if high_heel_count >= 3:
                    alerts.append("⚠️ PATTERN: Sustained high heel pressure detected")
                if high_meta_count >= 3:
                    alerts.append("⚠️ PATTERN: Sustained high metatarsal pressure detected")
                
                # Check for rapid increases
                if len(recent_data) >= 3:
                    if (recent_data[-1]["temperature"] - recent_data[-3]["temperature"]) > 1.0:
                        alerts.append("⚠️ TREND: Rapid temperature increase detected")
                    if (recent_data[-1]["humidity"] - recent_data[-3]["humidity"]) > 10.0:
                        alerts.append("⚠️ TREND: Rapid humidity increase detected")
        except Exception as e:
            print(f"Error in historical data analysis: {e}")
    
    # Current reading analysis
    if latest_readings["temperature"] > thresholds["temperature_threshold"]:
        alerts.append(f"⚠️ High Temperature: {latest_readings['temperature']:.1f}°C")
    
    if latest_readings["humidity"] > thresholds["humidity_threshold"]:
        alerts.append(f"⚠️ High Humidity: {latest_readings['humidity']:.1f}%")
    
    if latest_readings["heel_pressure"] > thresholds["pressure_threshold"]:
        alerts.append(f"⚠️ High Heel Pressure: {latest_readings['heel_pressure']}")
    
    if latest_readings["meta_pressure"] > thresholds["pressure_threshold"]:
        alerts.append(f"⚠️ High Metatarsal Pressure: {latest_readings['meta_pressure']}")
    
    return alerts

# Enhanced plot data function with advanced visualization
def plot_data():
    try:
        theme = THEMES[config["ui"]["theme"]]
        timestamps = []
        temperatures = []
        humidities = []
        heel_pressures = []
        meta_pressures = []
        
        with open(data_file, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            
            # Get last N readings
            max_points = config["ui"]["graph_points"]
            rows = list(reader)[-max_points:]
            
            for row in rows:
                timestamps.append(datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"))
                temperatures.append(float(row[1]))
                humidities.append(float(row[2]))
                heel_pressures.append(int(float(row[3])))
                meta_pressures.append(int(float(row[4])))
        
        # Create figure with dark theme
        plt.style.use('dark_background')
        fig = Figure(figsize=(10, 8), facecolor=theme["graph_bg"])
        ((ax1, ax2), (ax3, ax4)) = fig.subplots(2, 2)
        
        # Common styling for all subplots
        for ax in [ax1, ax2, ax3, ax4]:
            ax.set_facecolor(theme["graph_bg"])
            ax.spines['bottom'].set_color(theme["grid_color"])
            ax.spines['top'].set_color(theme["graph_bg"])
            ax.spines['right'].set_color(theme["graph_bg"])
            ax.spines['left'].set_color(theme["grid_color"])
            ax.tick_params(axis='x', colors=theme["text_secondary"])
            ax.tick_params(axis='y', colors=theme["text_secondary"])
            ax.grid(True, linestyle='--', alpha=0.3, color=theme["grid_color"])
        
        # Format dates for x-axis
        date_format = matplotlib.dates.DateFormatter('%H:%M')
        
        # Plot temperature with enhanced styling
        ax1.plot(timestamps, temperatures, color=theme["temp_color"], linewidth=2.5, marker='o', markersize=4)
        ax1.set_title('Temperature (°C)', color=theme["text_primary"], fontweight='bold')
        ax1.axhline(y=config["monitoring"]["temperature_threshold"], color='#FF5252', linestyle='--', alpha=0.7)
        if temperatures:
            y_min = min(temperatures) - 0.5
            y_max = max(temperatures) + 0.5
            ax1.set_ylim(y_min, y_max)
        ax1.xaxis.set_major_formatter(date_format)
        
        # Fill area under temperature curve
        if timestamps:
            ax1.fill_between(timestamps, temperatures, min(temperatures) if temperatures else 30, 
                            color=theme["temp_color"], alpha=0.2)
        
        # Plot humidity
        ax2.plot(timestamps, humidities, color=theme["humidity_color"], linewidth=2.5, marker='o', markersize=4)
        ax2.set_title('Humidity (%)', color=theme["text_primary"], fontweight='bold')
        ax2.axhline(y=config["monitoring"]["humidity_threshold"], color='#FF5252', linestyle='--', alpha=0.7)
        if humidities:
            y_min = min(humidities) - 5
            y_max = max(humidities) + 5
            ax2.set_ylim(y_min, y_max)
        ax2.xaxis.set_major_formatter(date_format)
        
        # Fill area under humidity curve
        if timestamps:
            ax2.fill_between(timestamps, humidities, min(humidities) if humidities else 30, 
                            color=theme["humidity_color"], alpha=0.2)
        
        # Plot heel pressure
        ax3.plot(timestamps, heel_pressures, color=theme["heel_color"], linewidth=2.5, marker='o', markersize=4)
        ax3.set_title('Heel Pressure', color=theme["text_primary"], fontweight='bold')
        ax3.axhline(y=config["monitoring"]["pressure_threshold"], color='#FF5252', linestyle='--', alpha=0.7)
        ax3.set_ylim(0, max(heel_pressures)+100 if heel_pressures else 800)
        ax3.xaxis.set_major_formatter(date_format)
        
        # Fill area under heel pressure curve
        if timestamps:
            ax3.fill_between(timestamps, heel_pressures, 0, color=theme["heel_color"], alpha=0.2)
        
        # Plot metatarsal pressure
        ax4.plot(timestamps, meta_pressures, color=theme["meta_color"], linewidth=2.5, marker='o', markersize=4)
        ax4.set_title('Metatarsal Pressure', color=theme["text_primary"], fontweight='bold')
        ax4.axhline(y=config["monitoring"]["pressure_threshold"], color='#FF5252', linestyle='--', alpha=0.7)
        ax4.set_ylim(0, max(meta_pressures)+100 if meta_pressures else 800)
        ax4.xaxis.set_major_formatter(date_format)
        
        # Fill area under metatarsal pressure curve
        if timestamps:
            ax4.fill_between(timestamps, meta_pressures, 0, color=theme["meta_color"], alpha=0.2)
        
        # Adjust layout
        fig.tight_layout(pad=3.0)
        
        # Add timestamps to figure
        fig.text(0.5, 0.01, f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                ha='center', color=theme["text_secondary"], fontsize=9)
        
        return fig
    except Exception as e:
        print(f"Error plotting data: {e}")
        return None

# Data simulation thread
def simulation_thread():
    while True:
        if not bt_connected and config["simulation"]["enabled"]:
            generate_smart_simulated_data()
        time.sleep(config["monitoring"]["update_interval"])

# GUI Class with Dark Theme support
class SmartInsoleApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Smart Insole Monitoring v{APP_VERSION}")
        self.root.geometry("1200x900")
        
        # Load theme settings
        self.theme_name = config["ui"]["theme"]
        self.theme = THEMES[self.theme_name]
        
        # Set color scheme
        self.bg_color = self.theme["bg_color"]
        self.card_bg = self.theme["card_bg"]
        self.text_primary = self.theme["text_primary"]
        self.text_secondary = self.theme["text_secondary"]
        self.accent_color = self.theme["accent_color"]
        self.accent_secondary = self.theme["accent_secondary"]
        self.header_color = self.theme["header_color"]
        self.alert_bg = self.theme["alert_bg"]
        self.alert_fg = self.theme["alert_fg"]
        self.success_color = self.theme["success_color"]
        
        self.root.configure(bg=self.bg_color)
        
        # Configure custom fonts
        self.setup_fonts()
        
        # Configure style
        self.setup_styles()
        
        # Main container with padding
        main_container = ttk.Frame(root, style="Main.TFrame")
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Header with logo and title
        header_frame = ttk.Frame(main_container, style="Header.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        # App logo
        self.logo_canvas = tk.Canvas(header_frame, width=80, height=80, 
                                    bg=self.header_color, bd=0, highlightthickness=0)
        self.logo_canvas.pack(side=tk.LEFT, padx=10)
        self.draw_logo()
        
        # Title and connection status
        title_frame = ttk.Frame(header_frame, style="Header.TFrame")
        title_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        title_label = ttk.Label(title_frame, text="Diabetic Foot Ulcer Monitoring System", 
                                style="MainTitle.TLabel")
        title_label.pack(anchor=tk.W)
        
        subtitle_label = ttk.Label(title_frame, text=f"Real-time monitoring and analysis • v{APP_VERSION}", 
                                   style="Subtitle.TLabel")
        subtitle_label.pack(anchor=tk.W)
        
        self.connection_label = ttk.Label(title_frame, text="Status: Initializing...", 
                                         style="Status.TLabel")
        self.connection_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Date and time frame
        info_frame = ttk.Frame(header_frame, style="Header.TFrame")
        info_frame.pack(side=tk.RIGHT, padx=10)
        
        self.date_label = ttk.Label(info_frame, text=datetime.now().strftime("%Y-%m-%d"), 
                                   style="Info.TLabel")
        self.date_label.pack(anchor=tk.E)
        
        self.time_label = ttk.Label(info_frame, text=datetime.now().strftime("%H:%M:%S"), 
                                   style="Info.TLabel")
        self.time_label.pack(anchor=tk.E)
        
        self.update_time = ttk.Label(info_frame, text="Last update: Never", 
                                    style="InfoSmall.TLabel")
        self.update_time.pack(anchor=tk.E, pady=(5, 0))
        
        # Main content frame with cards
        content_frame = ttk.Frame(main_container, style="Content.TFrame")
        content_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Top row with readings cards
        readings_frame = ttk.Frame(content_frame, style="Content.TFrame")
        readings_frame.pack(fill=tk.X, pady=5)
        
        # Create cards for each reading
        self.create_reading_card(readings_frame, "Temperature", "temp_value", "°C", self.theme["temp_color"])
        self.create_reading_card(readings_frame, "Humidity", "humidity_value", "%", self.theme["humidity_color"])
        self.create_reading_card(readings_frame, "Heel Pressure", "heel_value", "", self.theme["heel_color"])
        self.create_reading_card(readings_frame, "Meta Pressure", "meta_value", "", self.theme["meta_color"])
        
       # Middle section with tabs for different views
        tab_container = ttk.Notebook(content_frame)
        tab_container.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        # Main monitoring tab
        monitoring_tab = ttk.Frame(tab_container, style="Card.TFrame")
        tab_container.add(monitoring_tab, text="Monitoring")
        
        # Analytics tab
        analytics_tab = ttk.Frame(tab_container, style="Card.TFrame")
        tab_container.add(analytics_tab, text="Analytics")
        
        # Settings tab
        settings_tab = ttk.Frame(tab_container, style="Card.TFrame")
        tab_container.add(settings_tab, text="Settings")
        
        # Help tab
        help_tab = ttk.Frame(tab_container, style="Card.TFrame")
        tab_container.add(help_tab, text="Help")
        
        # Setup monitoring tab content
        self.setup_monitoring_tab(monitoring_tab)
        
        # Setup analytics tab content
        self.setup_analytics_tab(analytics_tab)
        
        # Setup settings tab content
        self.setup_settings_tab(settings_tab)
        
        # Setup help tab content
        self.setup_help_tab(help_tab)
        
        # Bottom action buttons
        buttons_frame = ttk.Frame(main_container, style="Footer.TFrame")
        buttons_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(buttons_frame, text="Refresh Data", command=self.refresh_data, 
                  style="Action.TButton").pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Export Data", command=self.export_data, 
                  style="Action.TButton").pack(side=tk.LEFT, padx=5)
        
        self.bluetooth_button = ttk.Button(buttons_frame, text="Connect Bluetooth", 
                                          command=self.reconnect_bluetooth, 
                                          style="Action.TButton")
        self.bluetooth_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(buttons_frame, text="Scan for Devices", command=self.scan_for_devices, 
                  style="Action.TButton").pack(side=tk.LEFT, padx=5)
        
        self.sim_button_text = tk.StringVar(value="Disable Simulation" if config["simulation"]["enabled"] else "Enable Simulation")
        self.sim_button = ttk.Button(buttons_frame, textvariable=self.sim_button_text, 
                                    command=self.toggle_simulation, style="Action.TButton")
        self.sim_button.pack(side=tk.LEFT, padx=5)
        
        # Status bar with progress indicator
        status_frame = ttk.Frame(main_container, style="StatusBar.TFrame")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))
        
        self.status_bar = ttk.Label(status_frame, text="Ready", style="StatusBar.TLabel")
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(status_frame, orient=tk.HORIZONTAL, 
                                           length=150, mode='indeterminate', 
                                           variable=self.progress_var)
        self.progress_bar.pack(side=tk.RIGHT, padx=5)
        
        # Initialize UI components
        self.alerts_text = None
        self.graph_frame = None
        
        # Start data collection
        self.start_data_collection()
        
        # Set up clock update
        self.update_clock()
        
        # Set up UI message processing
        self.process_messages()
    
    def setup_fonts(self):
        """Configure custom fonts for the application"""
        # Main title font
        self.title_font = font.Font(family="Segoe UI", size=18, weight="bold")
        
        # Subtitle font
        self.subtitle_font = font.Font(family="Segoe UI", size=10)
        
        # Status font
        self.status_font = font.Font(family="Segoe UI", size=10)
        
        # Info font
        self.info_font = font.Font(family="Segoe UI", size=12)
        
        # Card title font
        self.card_title_font = font.Font(family="Segoe UI", size=14, weight="bold")
        
        # Reading label font
        self.reading_label_font = font.Font(family="Segoe UI", size=12)
        
        # Reading value font
        self.reading_value_font = font.Font(family="Segoe UI", size=24, weight="bold")
        
        # Settings category font
        self.settings_category_font = font.Font(family="Segoe UI", size=14, weight="bold")
        
        # Button font
        self.button_font = font.Font(family="Segoe UI", size=10)
    
    def setup_styles(self):
        """Configure TTK styles for the application with dark theme"""
        style = ttk.Style()
        
        # Frame styles
        style.configure("Main.TFrame", background=self.bg_color)
        style.configure("Header.TFrame", background=self.header_color)
        style.configure("Content.TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_bg)
        style.configure("Graph.TFrame", background=self.card_bg)
        style.configure("Footer.TFrame", background=self.bg_color)
        style.configure("Logo.TFrame", background=self.header_color)
        style.configure("StatusBar.TFrame", background=self.header_color)
        
        # Label styles
        style.configure("MainTitle.TLabel", foreground=self.text_primary, background=self.header_color, 
                        font=self.title_font)
        style.configure("Subtitle.TLabel", foreground=self.text_secondary, background=self.header_color, 
                        font=self.subtitle_font)
        style.configure("Status.TLabel", foreground=self.accent_color, background=self.header_color, 
                        font=self.status_font)
        style.configure("Info.TLabel", foreground=self.text_primary, background=self.header_color, 
                        font=self.info_font)
        style.configure("InfoSmall.TLabel", foreground=self.text_secondary, background=self.header_color, 
                        font=self.subtitle_font)
        style.configure("CardTitle.TLabel", foreground=self.text_primary, background=self.card_bg, 
                        font=self.card_title_font)
        style.configure("ReadingLabel.TLabel", foreground=self.text_secondary, background=self.card_bg, 
                        font=self.reading_label_font)
        style.configure("ReadingValue.TLabel", foreground=self.success_color, background=self.card_bg, 
                        font=self.reading_value_font)
        style.configure("StatusBar.TLabel", foreground=self.text_secondary, background=self.header_color, 
                        font=self.subtitle_font)
        style.configure("SettingsCategory.TLabel", foreground=self.accent_color, background=self.card_bg, 
                        font=self.settings_category_font)
        style.configure("SettingsLabel.TLabel", foreground=self.text_primary, background=self.card_bg, 
                        font=self.subtitle_font)
        
        # Button styles
        style.configure("Action.TButton", font=self.button_font)
        
        # Notebook style (tabs)
        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.header_color, foreground=self.text_primary, 
                        padding=[10, 3], font=self.subtitle_font)
        style.map("TNotebook.Tab", background=[("selected", self.accent_color)], 
                 foreground=[("selected", self.text_primary)])
        
        # Progressbar style
        style.configure("TProgressbar", background=self.accent_color, troughcolor=self.bg_color, 
                       borderwidth=0, thickness=10)
    
    def draw_logo(self):
        """Draw a simple logo on the canvas"""
        self.logo_canvas.delete("all")
        
        # Draw stylized foot shape
        self.logo_canvas.create_oval(15, 15, 65, 50, fill=self.accent_color, outline="")
        self.logo_canvas.create_oval(20, 35, 60, 75, fill=self.accent_secondary, outline="")
        
        # Add text
        self.logo_canvas.create_text(40, 40, text="DFU", fill="white", font=("Arial", 14, "bold"))
    
    def create_reading_card(self, parent, title, value_attr, unit, color):
        """Create a card widget for a reading with improved styling"""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        # Header with color bar
        color_bar = tk.Frame(card, height=5, bg=color)
        color_bar.pack(fill=tk.X)
        
        # Inner padding frame
        inner_frame = ttk.Frame(card, style="Card.TFrame")
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Title with icon
        title_frame = ttk.Frame(inner_frame, style="Card.TFrame")
        title_frame.pack(fill=tk.X)
        
        # Simple icon using canvas
        icon_canvas = tk.Canvas(title_frame, width=20, height=20, bg=self.card_bg, 
                                highlightthickness=0)
        icon_canvas.pack(side=tk.LEFT)
        
        # Draw different icon based on reading type
        if title == "Temperature":
            icon_canvas.create_oval(5, 5, 15, 15, fill=color, outline="")
            icon_canvas.create_rectangle(10, 5, 12, 15, fill=self.card_bg, outline="")
        elif title == "Humidity":
            icon_canvas.create_oval(5, 10, 15, 20, fill=color, outline="")
            icon_canvas.create_oval(10, 5, 20, 15, fill=color, outline="")
        elif "Pressure" in title:
            icon_canvas.create_rectangle(5, 12, 15, 15, fill=color, outline="")
            icon_canvas.create_polygon(10, 5, 15, 10, 5, 10, fill=color, outline="")
        
        ttk.Label(title_frame, text=title, style="ReadingLabel.TLabel").pack(side=tk.LEFT, padx=5)
        
        # Value with large font
        setattr(self, value_attr, ttk.Label(inner_frame, text="--" + unit, style="ReadingValue.TLabel"))
        getattr(self, value_attr).pack(pady=(10, 5))
        
        # Add a separator
        separator = ttk.Separator(inner_frame, orient="horizontal")
        separator.pack(fill=tk.X, pady=10)
        
        # Add trend indicator (will be updated later)
        trend_frame = ttk.Frame(inner_frame, style="Card.TFrame")
        trend_frame.pack(fill=tk.X)
        
        trend_label = ttk.Label(trend_frame, text="No data", style="InfoSmall.TLabel")
        trend_label.pack(side=tk.LEFT)
        
        # Store trend label for later updates
        setattr(self, f"{value_attr}_trend", trend_label)
    
    def setup_monitoring_tab(self, parent):
        """Setup content for monitoring tab"""
        # Alerts panel
        alerts_frame = ttk.Frame(parent, style="Card.TFrame")
        alerts_frame.pack(fill=tk.X, pady=10, padx=10)
        
        alerts_header = ttk.Frame(alerts_frame, style="Card.TFrame")
        alerts_header.pack(fill=tk.X, padx=10, pady=5)
        
        # Alert icon
        alert_icon = tk.Canvas(alerts_header, width=24, height=24, bg=self.card_bg, 
                              highlightthickness=0)
        alert_icon.pack(side=tk.LEFT)
        alert_icon.create_polygon(12, 2, 22, 18, 2, 18, fill=self.alert_fg)
        alert_icon.create_text(12, 12, text="!", fill="white", font=("Arial", 12, "bold"))
        
        ttk.Label(alerts_header, text="Health Alerts", style="CardTitle.TLabel").pack(side=tk.LEFT, padx=10)
        
        clear_alerts = ttk.Button(alerts_header, text="Clear All", style="Action.TButton", 
                                 command=self.clear_alerts)
        clear_alerts.pack(side=tk.RIGHT)
        
        self.alerts_text = tk.Text(alerts_frame, height=4, bg=self.alert_bg, fg=self.text_primary,
                                  font=("Segoe UI", 11), relief=tk.FLAT, padx=10, pady=10)
        self.alerts_text.pack(fill=tk.X, padx=10, pady=5)
        self.alerts_text.insert(tk.END, "No alerts detected. System monitoring is active.")
        
        # Graph panel
        graph_container = ttk.Frame(parent, style="Card.TFrame")
        graph_container.pack(fill=tk.BOTH, expand=True, pady=10, padx=10)
        
        graph_header = ttk.Frame(graph_container, style="Card.TFrame")
        graph_header.pack(fill=tk.X, padx=10, pady=5)
        
        # Graph icon
        graph_icon = tk.Canvas(graph_header, width=24, height=24, bg=self.card_bg, 
                              highlightthickness=0)
        graph_icon.pack(side=tk.LEFT)
        for i in range(5):
            graph_icon.create_line(2, 20-i*4, 22, 20-i*3, fill=self.accent_color, width=2)
        
        ttk.Label(graph_header, text="Historical Data", style="CardTitle.TLabel").pack(side=tk.LEFT, padx=10)
        
        # Add time range selector
        ttk.Label(graph_header, text="Time Range:", style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(20, 5))
        
        self.time_range = tk.StringVar(value="Last 50 points")
        time_range_combo = ttk.Combobox(graph_header, textvariable=self.time_range, 
                                       values=["Last 20 points", "Last 50 points", "Last 100 points", 
                                              "Last 6 hours", "Last 24 hours"])
        time_range_combo.pack(side=tk.LEFT)
        time_range_combo.bind("<<ComboboxSelected>>", self.update_graph_range)
        
        self.graph_frame = ttk.Frame(graph_container, style="Graph.TFrame")
        self.graph_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    def setup_analytics_tab(self, parent):
        """Setup content for analytics tab"""
        # Setup scrollable frame for analytics
        canvas = tk.Canvas(parent, bg=self.card_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        analytics_frame = ttk.Frame(canvas, style="Card.TFrame")
        canvas.create_window((0, 0), window=analytics_frame, anchor="nw", width=canvas.winfo_reqwidth())
        
        # Statistics section
        stats_frame = ttk.Frame(analytics_frame, style="Card.TFrame")
        stats_frame.pack(fill=tk.X, padx=15, pady=15)
        
        ttk.Label(stats_frame, text="Statistics & Analysis", style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Create a frame for statistics cards
        stats_cards = ttk.Frame(stats_frame, style="Card.TFrame")
        stats_cards.pack(fill=tk.X)
        
        # Add statistic cards
        self.create_stat_card(stats_cards, "Avg. Temperature", "24h", "temp_avg")
        self.create_stat_card(stats_cards, "Max Pressure", "24h", "pressure_max")
        self.create_stat_card(stats_cards, "Time Above Threshold", "24h", "threshold_time")
        self.create_stat_card(stats_cards, "Alert Frequency", "24h", "alert_freq")
        
        # Pattern detection section
        pattern_frame = ttk.Frame(analytics_frame, style="Card.TFrame")
        pattern_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(pattern_frame, text="Pattern Detection", style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Pattern text area
        self.pattern_text = tk.Text(pattern_frame, height=6, bg=self.card_bg, fg=self.text_primary,
                                   font=("Segoe UI", 11), relief=tk.FLAT, padx=10, pady=10)
        self.pattern_text.pack(fill=tk.X, pady=5)
        self.pattern_text.insert(tk.END, "Running pattern analysis...\n\nThis will detect recurring patterns in foot pressure, temperature fluctuations, and humidity levels that may indicate developing foot health issues.")
        
        # Create button to run analysis
        ttk.Button(pattern_frame, text="Run Deep Analysis", style="Action.TButton", 
                  command=self.run_deep_analysis).pack(pady=10)
        
        # Activity heatmap section
        heatmap_frame = ttk.Frame(analytics_frame, style="Card.TFrame")
        heatmap_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(heatmap_frame, text="Pressure Heatmap", style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Placeholder for heatmap
        heatmap_canvas = tk.Canvas(heatmap_frame, width=450, height=200, bg=self.card_bg, 
                                  highlightthickness=0)
        heatmap_canvas.pack(pady=10)
        
        # Draw foot outline
        heatmap_canvas.create_oval(150, 50, 300, 120, outline=self.text_secondary, width=2)
        heatmap_canvas.create_oval(180, 120, 270, 190, outline=self.text_secondary, width=2)
        
        # Draw pseudoheatmap
        self.draw_heatmap(heatmap_canvas)
        
        # Data export section
        export_frame = ttk.Frame(analytics_frame, style="Card.TFrame")
        export_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(export_frame, text="Data Export Options", style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        export_options = ttk.Frame(export_frame, style="Card.TFrame")
        export_options.pack(fill=tk.X, pady=5)
        
        ttk.Button(export_options, text="Export as CSV", style="Action.TButton", 
                  command=self.export_data).pack(side=tk.LEFT, padx=5, pady=10)
        
        ttk.Button(export_options, text="Export as PDF Report", style="Action.TButton", 
                  command=self.export_pdf).pack(side=tk.LEFT, padx=5, pady=10)
        
        ttk.Button(export_options, text="Export for Doctor", style="Action.TButton", 
                  command=self.export_for_doctor).pack(side=tk.LEFT, padx=5, pady=10)
    
    def setup_settings_tab(self, parent):
        """Setup content for settings tab"""
        # Setup scrollable frame for settings
        canvas = tk.Canvas(parent, bg=self.card_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        settings_frame = ttk.Frame(canvas, style="Card.TFrame")
        canvas.create_window((0, 0), window=settings_frame, anchor="nw", width=canvas.winfo_reqwidth())
        
        # Bluetooth settings
        bt_frame = ttk.Frame(settings_frame, style="Card.TFrame")
        bt_frame.pack(fill=tk.X, padx=15, pady=15)
        
        ttk.Label(bt_frame, text="Bluetooth Settings", style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # MAC Address
        mac_frame = ttk.Frame(bt_frame, style="Card.TFrame")
        mac_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(mac_frame, text="MAC Address:", style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        
        self.mac_var = tk.StringVar(value=config["bluetooth"]["mac_address"])
        mac_entry = ttk.Entry(mac_frame, textvariable=self.mac_var, width=20)
        mac_entry.pack(side=tk.LEFT)
        
        # Port
        port_frame = ttk.Frame(bt_frame, style="Card.TFrame")
        port_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(port_frame, text="Port:", style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        
        self.port_var = tk.IntVar(value=config["bluetooth"]["port"])
        port_entry = ttk.Entry(port_frame, textvariable=self.port_var, width=5)
        port_entry.pack(side=tk.LEFT)
        
        # Auto reconnect
        reconnect_frame = ttk.Frame(bt_frame, style="Card.TFrame")
        reconnect_frame.pack(fill=tk.X, pady=5)
        
        self.auto_reconnect = tk.BooleanVar(value=config["bluetooth"]["auto_reconnect"])
        reconnect_check = ttk.Checkbutton(reconnect_frame, text="Auto Reconnect", variable=self.auto_reconnect)
        reconnect_check.pack(side=tk.LEFT)
        
        # Reconnect interval
        interval_frame = ttk.Frame(bt_frame, style="Card.TFrame")
        interval_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(interval_frame, text="Reconnect Interval (seconds):", 
                 style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        
        self.reconnect_interval = tk.IntVar(value=config["bluetooth"]["reconnect_interval"])
        interval_entry = ttk.Entry(interval_frame, textvariable=self.reconnect_interval, width=5)
        interval_entry.pack(side=tk.LEFT)
        
        # Monitoring settings
        monitoring_frame = ttk.Frame(settings_frame, style="Card.TFrame")
        monitoring_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(monitoring_frame, text="Monitoring Settings", 
                 style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Update interval
        update_frame = ttk.Frame(monitoring_frame, style="Card.TFrame")
        update_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(update_frame, text="Update Interval (seconds):", 
                 style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        
        self.update_interval = tk.IntVar(value=config["monitoring"]["update_interval"])
        update_entry = ttk.Entry(update_frame, textvariable=self.update_interval, width=5)
        update_entry.pack(side=tk.LEFT)
        
        # Thresholds
        for name, threshold in [
            ("Temperature Threshold (°C):", "temperature_threshold"),
            ("Humidity Threshold (%):", "humidity_threshold"),
            ("Pressure Threshold:", "pressure_threshold")
        ]:
            threshold_frame = ttk.Frame(monitoring_frame, style="Card.TFrame")
            threshold_frame.pack(fill=tk.X, pady=5)
            
            ttk.Label(threshold_frame, text=name, style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
            
            setattr(self, f"{threshold}_var", tk.DoubleVar(value=config["monitoring"][threshold]))
            threshold_entry = ttk.Entry(threshold_frame, textvariable=getattr(self, f"{threshold}_var"), width=8)
            threshold_entry.pack(side=tk.LEFT)
        
        # Alert sound
        alert_sound_frame = ttk.Frame(monitoring_frame, style="Card.TFrame")
        alert_sound_frame.pack(fill=tk.X, pady=5)
        
        self.alert_sound = tk.BooleanVar(value=config["monitoring"]["alert_sound"])
        alert_sound_check = ttk.Checkbutton(alert_sound_frame, text="Play Sound on Alert", variable=self.alert_sound)
        alert_sound_check.pack(side=tk.LEFT)
        
        # Simulation settings
        sim_frame = ttk.Frame(settings_frame, style="Card.TFrame")
        sim_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(sim_frame, text="Simulation Settings", 
                 style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Enable simulation
        sim_enable_frame = ttk.Frame(sim_frame, style="Card.TFrame")
        sim_enable_frame.pack(fill=tk.X, pady=5)
        
        self.sim_enable = tk.BooleanVar(value=config["simulation"]["enabled"])
        sim_enable_check = ttk.Checkbutton(sim_enable_frame, text="Enable Simulation when Bluetooth Unavailable", 
                                          variable=self.sim_enable)
        sim_enable_check.pack(side=tk.LEFT)
        
        # Realistic variation
        sim_realistic_frame = ttk.Frame(sim_frame, style="Card.TFrame")
        sim_realistic_frame.pack(fill=tk.X, pady=5)
        
        self.sim_realistic = tk.BooleanVar(value=config["simulation"]["realistic_variation"])
        sim_realistic_check = ttk.Checkbutton(sim_realistic_frame, text="Use Realistic Data Patterns", 
                                             variable=self.sim_realistic)
        sim_realistic_check.pack(side=tk.LEFT)
        
        # UI settings
        ui_frame = ttk.Frame(settings_frame, style="Card.TFrame")
        ui_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(ui_frame, text="UI Settings", style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Theme selection
        theme_frame = ttk.Frame(ui_frame, style="Card.TFrame")
        theme_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(theme_frame, text="Theme:", style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        
        self.theme_var = tk.StringVar(value=config["ui"]["theme"])
        theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var, values=list(THEMES.keys()))
        theme_combo.pack(side=tk.LEFT)
        theme_combo.bind("<<ComboboxSelected>>", self.update_theme)
        
        # Graph points
        graph_points_frame = ttk.Frame(ui_frame, style="Card.TFrame")
        graph_points_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(graph_points_frame, text="Default Graph Points:", 
                 style="SettingsLabel.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        
        self.graph_points = tk.IntVar(value=config["ui"]["graph_points"])
        graph_points_entry = ttk.Entry(graph_points_frame, textvariable=self.graph_points, width=5)
        graph_points_entry.pack(side=tk.LEFT)
        
        # Auto export
        auto_export_frame = ttk.Frame(ui_frame, style="Card.TFrame")
        auto_export_frame.pack(fill=tk.X, pady=5)
        
        self.auto_export = tk.BooleanVar(value=config["ui"]["auto_export"])
        auto_export_check = ttk.Checkbutton(auto_export_frame, text="Auto Export Data Daily", variable=self.auto_export)
        auto_export_check.pack(side=tk.LEFT)
        
        # Save button
        save_frame = ttk.Frame(settings_frame, style="Card.TFrame")
        save_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Button(save_frame, text="Save Settings", style="Action.TButton", 
                  command=self.save_settings).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(save_frame, text="Restore Defaults", style="Action.TButton", 
                  command=self.restore_defaults).pack(side=tk.LEFT, padx=5)
    
    def setup_help_tab(self, parent):
        """Setup content for help tab"""
        # Setup scrollable frame for help
        canvas = tk.Canvas(parent, bg=self.card_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        help_frame = ttk.Frame(canvas, style="Card.TFrame")
        canvas.create_window((0, 0), window=help_frame, anchor="nw", width=canvas.winfo_reqwidth())
        
        # About section
        about_frame = ttk.Frame(help_frame, style="Card.TFrame")
        about_frame.pack(fill=tk.X, padx=15, pady=15)
        
        ttk.Label(about_frame, text="About Smart Insole Monitoring", 
                 style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        about_text = tk.Text(about_frame, height=6, bg=self.card_bg, fg=self.text_primary,
                            font=("Segoe UI", 11), wrap=tk.WORD, relief=tk.FLAT)
        about_text.pack(fill=tk.X, pady=5)
        about_text.insert(tk.END, 
                         f"Smart Insole Monitoring System v{APP_VERSION}\n\n"
                         f"Developed by: {AUTHOR}\n\n"
                         "This application monitors real-time data from smart insoles to help prevent "
                         "diabetic foot ulcers through early detection of problematic conditions including "
                         "temperature changes, moisture levels, and pressure points.")
        about_text.config(state=tk.DISABLED)
        
        # Instructions section
        instruction_frame = ttk.Frame(help_frame, style="Card.TFrame")
        instruction_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(instruction_frame, text="Quick Start Guide", 
                 style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        instructions = tk.Text(instruction_frame, height=12, bg=self.card_bg, fg=self.text_primary,
                              font=("Segoe UI", 11), wrap=tk.WORD, relief=tk.FLAT)
        instructions.pack(fill=tk.X, pady=5)
        instructions.insert(tk.END, 
                          "1. Connect the Smart Insole: Use the 'Connect Bluetooth' button to pair with your insole device.\n\n"
                          "2. Monitor Real-time Data: The main dashboard shows current readings for temperature, humidity, and pressure points.\n\n"
                          "3. Check Alerts: The system will automatically alert you when readings exceed healthy thresholds.\n\n"
                          "4. View Historical Data: The graphs show trends over time to help identify patterns.\n\n"
                          "5. Export Data: Use the export functions to save data for sharing with healthcare providers.\n\n"
                          "6. Adjust Settings: Configure thresholds and other settings in the Settings tab.")
        instructions.config(state=tk.DISABLED)
        
        # Troubleshooting section
        troubleshoot_frame = ttk.Frame(help_frame, style="Card.TFrame")
        troubleshoot_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(troubleshoot_frame, text="Troubleshooting", 
                 style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        troubleshoot = tk.Text(troubleshoot_frame, height=8, bg=self.card_bg, fg=self.text_primary,
                              font=("Segoe UI", 11), wrap=tk.WORD, relief=tk.FLAT)
        troubleshoot.pack(fill=tk.X, pady=5)
        troubleshoot.insert(tk.END, 
                          "Connection Issues:\n"
                          "• Ensure the insole device is charged and powered on\n"
                          "• Verify the correct MAC address in settings\n"
                          "• Restart the insole device if connection fails\n\n"
                          "Data Not Updating:\n"
                          "• Check connection status in the header\n"
                          "• Try reconnecting via the 'Connect Bluetooth' button\n"
                          "• Ensure the update interval is set appropriately")
        troubleshoot.config(state=tk.DISABLED)
        
        # Contact support section
        support_frame = ttk.Frame(help_frame, style="Card.TFrame")
        support_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        ttk.Label(support_frame, text="Contact Support", 
                 style="SettingsCategory.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        support = tk.Text(support_frame, height=3, bg=self.card_bg, fg=self.text_primary,
                         font=("Segoe UI", 11), wrap=tk.WORD, relief=tk.FLAT)
        support.pack(fill=tk.X, pady=5)
        support.insert(tk.END, 
                     "For technical support:\n"
                     "Email: support@diabcaresolutions.com\n"
                     "Phone: 1-800-555-0123")
        support.config(state=tk.DISABLED)
    
    def create_stat_card(self, parent, title, period, value_attr):
        """Create a statistics card for the analytics tab"""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add a border using a canvas
        border_canvas = tk.Canvas(card, height=2, bg=self.accent_color, highlightthickness=0)
        border_canvas.pack(fill=tk.X)
        
        # Title with period
        title_frame = ttk.Frame(card, style="Card.TFrame")
        title_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(title_frame, text=title, style="ReadingLabel.TLabel").pack(side=tk.LEFT)
        ttk.Label(title_frame, text=period, style="InfoSmall.TLabel").pack(side=tk.RIGHT)
        
        # Value with placeholder
        value_label = ttk.Label(card, text="--", style="ReadingValue.TLabel")
        value_label.pack(pady=10)
        
        # Store reference for updates
        setattr(self, value_attr, value_label)
    
    def draw_heatmap(self, canvas):
        """Draw a heatmap visualization of foot pressure"""
        # Use mock data for demonstration
        # In a real application, this would use actual sensor data
        
        # Define foot regions
        regions = [
            {"x": 225, "y": 70, "r": 30, "name": "Heel"},
            {"x": 180, "y": 85, "r": 20, "name": "Arch"},
            {"x": 225, "y": 150, "r": 25, "name": "Metatarsal"}
        ]
        
        # Mock pressure values (0-100%)
        pressures = {
            "Heel": latest_readings["heel_pressure"] / 10 if latest_readings["heel_pressure"] else 30,
            "Arch": random.randint(20, 50),
            "Metatarsal": latest_readings["meta_pressure"] / 10 if latest_readings["meta_pressure"] else 25
        }
        
        # Color gradient from green (low) to red (high)
        def get_color(value):
            r = min(255, int(value * 2.55))
            g = min(255, int(255 - value * 2.55))
            return f"#{r:02x}{g:02x}00"
        
        # Clear previous heatmap
        canvas.delete("heatmap")
        
        # Draw heatmap circles for each region
        for region in regions:
            pressure = pressures[region["name"]]
            color = get_color(pressure)
            
            # Draw gradient circles (larger to smaller with increasing opacity)
            for i in range(3):
                radius = region["r"] * (1 + i*0.5)
                alpha = 150 - i*40  # Decreasing opacity
                
                # Can't use alpha in tkinter directly, so adjust color intensity
                canvas.create_oval(
                    region["x"] - radius, 
                    region["y"] - radius, 
                    region["x"] + radius, 
                    region["y"] + radius,
                    fill=color, outline="", tags="heatmap"
                )
            
            # Draw region label
            canvas.create_text(
                region["x"], region["y"], 
                text=f"{region['name']}\n{pressure:.0f}%", 
                fill=self.text_primary, 
                font=("Segoe UI", 9, "bold"),
                tags="heatmap"
            )
    
    def update_clock(self):
        """Update the clock display"""
        current_time = datetime.now()
        self.time_label.config(text=current_time.strftime("%H:%M:%S"))
        self.date_label.config(text=current_time.strftime("%Y-%m-%d"))
        self.root.after(1000, self.update_clock)
    
    def process_messages(self):
        """Process messages from the data queue and update UI"""
        try:
            # Process up to 5 messages at a time to prevent UI freezing
            for _ in range(5):
                if data_queue.empty():
                    break
                
                message = data_queue.get_nowait()
                
                if message["type"] == "sensor_data":
                    self.update_readings(message["data"])
                elif message["type"] == "connection_status":
                    self.update_connection_status(message["status"], message["message"])
                elif message["type"] == "alert":
                    self.show_alert(message["message"])
            
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error processing queue messages: {e}")
        
        # Check again in 100ms
        self.root.after(100, self.process_messages)
    
    def start_data_collection(self):
        """Initialize data collection threads"""
        # Start Bluetooth connection thread
        bt_thread = threading.Thread(target=bluetooth_connection_thread, daemon=True)
        bt_thread.start()
        
        # Start simulation thread
        sim_thread = threading.Thread(target=simulation_thread, daemon=True)
        sim_thread.start()
        
        # Update chart initially
        self.update_chart()
        
        # Set regular chart updates
        self.root.after(int(config["monitoring"]["update_interval"] * 1000), self.schedule_chart_update)
        
        # Schedule analytics updates
        self.root.after(5000, self.update_analytics)
    
    def schedule_chart_update(self):
        """Schedule regular chart updates"""
        self.update_chart()
        self.root.after(int(config["monitoring"]["update_interval"] * 1000), self.schedule_chart_update)
    
    def update_readings(self, data):
        """Update UI with latest sensor readings"""
        # Update sensor value displays
        self.temp_value.config(text=f"{data['temperature']:.1f}°C")
        self.humidity_value.config(text=f"{data['humidity']:.1f}%")
        self.heel_value.config(text=f"{data['heel_pressure']}")
        self.meta_value.config(text=f"{data['meta_pressure']}")
        
        # Update last update time
        self.update_time.config(text=f"Last update: {datetime.now().strftime('%H:%M:%S')}")
        
        # Check for alerts
        alerts = analyze_data(historical=True)
        if alerts:
            self.update_alerts(alerts)
            
            # Flash alert color if any high readings
            for reading_type, threshold in [
                ("temperature", config["monitoring"]["temperature_threshold"]),
                ("humidity", config["monitoring"]["humidity_threshold"]),
                ("heel_pressure", config["monitoring"]["pressure_threshold"]),
                ("meta_pressure", config["monitoring"]["pressure_threshold"])
            ]:
                if data[reading_type] > threshold:
                    attr_name = f"{reading_type.split('_')[0]}_value"
                    if hasattr(self, attr_name):
                        getattr(self, attr_name).config(foreground=self.alert_fg)
                        # Schedule reset of color after 1 second
                        self.root.after(1000, lambda attr=attr_name: 
                                       getattr(self, attr).config(foreground=self.success_color))
    
    def update_connection_status(self, status, message):
        """Update the connection status display"""
        if status == "connected":
            self.connection_label.config(text=f"Status: Connected to device", foreground=self.success_color)
            self.bluetooth_button.config(text="Disconnect")
            self.status_bar.config(text=message)
        elif status == "connecting":
            self.connection_label.config(text=f"Status: Connecting...", foreground=self.accent_color)
            self.bluetooth_button.config(text="Cancel")
            self.status_bar.config(text=message)
            self.progress_bar.start(10)
        elif status == "disconnected":
            self.connection_label.config(text=f"Status: Disconnected", foreground=self.accent_color)
            self.bluetooth_button.config(text="Connect Bluetooth")
            self.status_bar.config(text=message)
            self.progress_bar.stop()
        elif status == "failed":
            self.connection_label.config(text=f"Status: Connection Failed", foreground=self.alert_fg)
            self.bluetooth_button.config(text="Try Again")
            self.status_bar.config(text=message)
            self.progress_bar.stop()
            
    def update_alerts(self, alerts):
        """Update the alerts display with new alerts"""
        if self.alerts_text:
            # Clear previous alerts
            self.alerts_text.delete(1.0, tk.END)
            
            if alerts:
                for alert in alerts:
                    self.alerts_text.insert(tk.END, f"{alert}\n")
                
                # Play alert sound if enabled
                if config["monitoring"]["alert_sound"]:
                    self.root.bell()
            else:
                self.alerts_text.insert(tk.END, "No alerts detected. System monitoring is active.")
    
    def update_chart(self):
        """Update the chart with latest data"""
        if self.graph_frame:
            # Clear previous chart
            for widget in self.graph_frame.winfo_children():
                widget.destroy()
            
            # Create new chart
            fig = plot_data()
            if fig:
                canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    
    def update_graph_range(self, event=None):
        """Update the graph range based on selection"""
        # Extract the selected range
        range_text = self.time_range.get()
        
        if "points" in range_text:
            # Extract number of points
            num_points = int(range_text.split()[1])
            config["ui"]["graph_points"] = num_points
        elif "hours" in range_text:
            # Calculate points equivalent based on update interval
            hours = int(range_text.split()[1])
            points_per_hour = int(3600 / config["monitoring"]["update_interval"])
            config["ui"]["graph_points"] = hours * points_per_hour
        
        # Update the chart
        self.update_chart()
    
    def update_analytics(self):
        """Update analytics display with calculated statistics"""
        try:
            # Get data for last 24 hours
            data_points = []
            with open(data_file, 'r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                
                cutoff_time = datetime.now() - timedelta(hours=24)
                
                for row in reader:
                    if len(row) >= 5:  # Ensure row has enough data
                        timestamp = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                        if timestamp > cutoff_time:
                            data_points.append({
                                "timestamp": timestamp,
                                "temperature": float(row[1]),
                                "humidity": float(row[2]),
                                "heel_pressure": int(float(row[3])),
                                "meta_pressure": int(float(row[4]))
                            })
            
            if data_points:
                # Calculate average temperature
                avg_temp = sum(d["temperature"] for d in data_points) / len(data_points)
                self.temp_avg.config(text=f"{avg_temp:.1f}°C")
                
                # Calculate max pressure
                max_heel = max(d["heel_pressure"] for d in data_points)
                max_meta = max(d["meta_pressure"] for d in data_points)
                max_pressure = max(max_heel, max_meta)
                self.pressure_max.config(text=f"{max_pressure}")
                
                # Calculate time above threshold
                temp_threshold = config["monitoring"]["temperature_threshold"]
                humidity_threshold = config["monitoring"]["humidity_threshold"]
                pressure_threshold = config["monitoring"]["pressure_threshold"]
                
                above_count = sum(1 for d in data_points if (
                    d["temperature"] > temp_threshold or
                    d["humidity"] > humidity_threshold or
                    d["heel_pressure"] > pressure_threshold or
                    d["meta_pressure"] > pressure_threshold
                ))
                
                threshold_percent = (above_count / len(data_points)) * 100 if len(data_points) > 0 else 0
                self.threshold_time.config(text=f"{threshold_percent:.1f}%")
                
                # Calculate alert frequency (alerts per hour)
                alert_count = 0
                for i in range(1, len(data_points)):
                    # Count transitions from normal to alert state
                    prev_normal = (
                        data_points[i-1]["temperature"] <= temp_threshold and
                        data_points[i-1]["humidity"] <= humidity_threshold and
                        data_points[i-1]["heel_pressure"] <= pressure_threshold and
                        data_points[i-1]["meta_pressure"] <= pressure_threshold
                    )
                    
                    curr_alert = (
                        data_points[i]["temperature"] > temp_threshold or
                        data_points[i]["humidity"] > humidity_threshold or
                        data_points[i]["heel_pressure"] > pressure_threshold or
                        data_points[i]["meta_pressure"] > pressure_threshold
                    )
                    
                    if prev_normal and curr_alert:
                        alert_count += 1
                
                # Calculate hours of data
                if len(data_points) >= 2:
                    time_span = (data_points[-1]["timestamp"] - data_points[0]["timestamp"]).total_seconds() / 3600
                    alert_freq = alert_count / time_span if time_span > 0 else 0
                    self.alert_freq.config(text=f"{alert_freq:.1f}/hr")
                else:
                    self.alert_freq.config(text="N/A")
            
            # Update pattern analysis text
            if len(data_points) > 10:
                patterns = self.detect_patterns(data_points)
                if patterns:
                    self.pattern_text.delete(1.0, tk.END)
                    self.pattern_text.insert(tk.END, "Pattern Analysis Results:\n\n")
                    for pattern in patterns:
                        self.pattern_text.insert(tk.END, f"• {pattern}\n")
            
            # Update heatmap
            for widget in self.graph_frame.winfo_children():
                if isinstance(widget, tk.Canvas) and "heatmap" in widget.gettags("all"):
                    self.draw_heatmap(widget)
        
        except Exception as e:
            print(f"Error updating analytics: {e}")
        
        # Schedule next update
        self.root.after(60000, self.update_analytics)  # Update every minute
    
    def detect_patterns(self, data_points):
        """Detect patterns in the data"""
        patterns = []
        
        # Need enough data points for meaningful analysis
        if len(data_points) < 10:
            return ["Not enough data for pattern analysis"]
        
        # Thresholds
        temp_threshold = config["monitoring"]["temperature_threshold"]
        humidity_threshold = config["monitoring"]["humidity_threshold"]
        pressure_threshold = config["monitoring"]["pressure_threshold"]
        
        # Check for sustained high values (3+ consecutive readings)
        consecutive_high_temp = 0
        consecutive_high_humidity = 0
        consecutive_high_heel = 0
        consecutive_high_meta = 0
        
        for point in data_points[-10:]:  # Check last 10 readings
            if point["temperature"] > temp_threshold:
                consecutive_high_temp += 1
            else:
                consecutive_high_temp = 0
                
            if point["humidity"] > humidity_threshold:
                consecutive_high_humidity += 1
            else:
                consecutive_high_humidity = 0
                
            if point["heel_pressure"] > pressure_threshold:
                consecutive_high_heel += 1
            else:
                consecutive_high_heel = 0
                
            if point["meta_pressure"] > pressure_threshold:
                consecutive_high_meta += 1
            else:
                consecutive_high_meta = 0
            
            if consecutive_high_temp >= 3 and "temperature" not in str(patterns):
                patterns.append("Sustained high temperature detected - potential inflammation")
            
            if consecutive_high_humidity >= 3 and "humidity" not in str(patterns):
                patterns.append("Sustained high humidity detected - risk of skin maceration")
            
            if consecutive_high_heel >= 3 and "heel pressure" not in str(patterns):
                patterns.append("Sustained high heel pressure detected - adjust footwear/activity")
            
            if consecutive_high_meta >= 3 and "metatarsal pressure" not in str(patterns):
                patterns.append("Sustained high metatarsal pressure detected - check for callus formation")
        
        # Check for time-based patterns (e.g., higher values at specific times)
        morning_temps = []
        afternoon_temps = []
        evening_temps = []
        
        for point in data_points:
            hour = point["timestamp"].hour
            if 5 <= hour < 12:  # Morning
                morning_temps.append(point["temperature"])
            elif 12 <= hour < 18:  # Afternoon
                afternoon_temps.append(point["temperature"])
            else:  # Evening/Night
                evening_temps.append(point["temperature"])
        
        if morning_temps and afternoon_temps and evening_temps:
            avg_morning = sum(morning_temps) / len(morning_temps)
            avg_afternoon = sum(afternoon_temps) / len(afternoon_temps)
            avg_evening = sum(evening_temps) / len(evening_temps)
            
            max_diff = max(abs(avg_morning - avg_afternoon), 
                          abs(avg_afternoon - avg_evening), 
                          abs(avg_evening - avg_morning))
            
            if max_diff > 0.5:  # Significant temperature variation throughout day
                highest = max(avg_morning, avg_afternoon, avg_evening)
                if highest == avg_morning:
                    patterns.append("Temperature peaks in morning - check for overnight inflammation")
                elif highest == avg_afternoon:
                    patterns.append("Temperature peaks in afternoon - may indicate activity-related stress")
                else:
                    patterns.append("Temperature peaks in evening - potential cumulative daily stress")
        
        # If no patterns detected
        if not patterns:
            patterns.append("No significant patterns detected in current data")
        
        return patterns
    
    def refresh_data(self):
        """Force refresh of data and UI"""
        self.update_chart()
        self.update_analytics()
        self.status_bar.config(text="Data refreshed")
    
    def export_data(self):
        """Export data to CSV file"""
        try:
            from datetime import datetime
            export_filename = f"insole_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            with open(data_file, 'r') as source, open(export_filename, 'w', newline='') as target:
                reader = csv.reader(source)
                writer = csv.writer(target)
                for row in reader:
                    writer.writerow(row)
            
            self.status_bar.config(text=f"Data exported to {export_filename}")
            messagebox.showinfo("Export Complete", f"Data exported to {export_filename}")
        except Exception as e:
            self.status_bar.config(text=f"Export failed: {e}")
            messagebox.showerror("Export Failed", f"Error exporting data: {e}")
    
    def export_pdf(self):
        """Simulate PDF export (would require additional libraries)"""
        self.status_bar.config(text="Preparing PDF export...")
        self.progress_bar.start(10)
        
        # Simulate processing time
        def finish_export():
            self.progress_bar.stop()
            self.status_bar.config(text="PDF export completed")
            messagebox.showinfo("Export Complete", "PDF report has been generated and saved.")
        
        self.root.after(2000, finish_export)
    
    def export_for_doctor(self):
        """Export data in a format optimized for healthcare providers"""
        try:
            from datetime import datetime
            export_filename = f"medical_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            with open(export_filename, 'w', newline='') as file:
                writer = csv.writer(file)
                
                # Write header with patient info (placeholder)
                writer.writerow(["DIABETIC FOOT MONITORING - MEDICAL REPORT"])
                writer.writerow(["Generated:", datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
                writer.writerow(["Patient ID:", "DEMO-PATIENT"])
                writer.writerow(["Device ID:", config["bluetooth"]["mac_address"]])
                writer.writerow([])
                
                # Write summary statistics
                writer.writerow(["SUMMARY STATISTICS (LAST 24 HOURS)"])
                
                # Calculate statistics (simplified version of update_analytics)
                try:
                    data_points = []
                    with open(data_file, 'r') as data:
                        reader = csv.reader(data)
                        next(reader)  # Skip header
                        
                        cutoff_time = datetime.now() - timedelta(hours=24)
                        
                        for row in reader:
                            if len(row) >= 5:
                                timestamp = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                                if timestamp > cutoff_time:
                                    data_points.append({
                                        "timestamp": timestamp,
                                        "temperature": float(row[1]),
                                        "humidity": float(row[2]),
                                        "heel_pressure": int(float(row[3])),
                                        "meta_pressure": int(float(row[4]))
                                    })
                    
                    if data_points:
                        # Calculate statistics
                        avg_temp = sum(d["temperature"] for d in data_points) / len(data_points)
                        max_temp = max(d["temperature"] for d in data_points)
                        min_temp = min(d["temperature"] for d in data_points)
                        
                        avg_humidity = sum(d["humidity"] for d in data_points) / len(data_points)
                        max_humidity = max(d["humidity"] for d in data_points)
                        
                        avg_heel = sum(d["heel_pressure"] for d in data_points) / len(data_points)
                        max_heel = max(d["heel_pressure"] for d in data_points)
                        
                        avg_meta = sum(d["meta_pressure"] for d in data_points) / len(data_points)
                        max_meta = max(d["meta_pressure"] for d in data_points)
                        
                        writer.writerow(["Average Temperature:", f"{avg_temp:.1f}°C"])
                        writer.writerow(["Min/Max Temperature:", f"{min_temp:.1f}°C / {max_temp:.1f}°C"])
                        writer.writerow(["Average Humidity:", f"{avg_humidity:.1f}%"])
                        writer.writerow(["Maximum Humidity:", f"{max_humidity:.1f}%"])
                        writer.writerow(["Average Heel Pressure:", f"{avg_heel:.1f}"])
                        writer.writerow(["Maximum Heel Pressure:", f"{max_heel}"])
                        writer.writerow(["Average Metatarsal Pressure:", f"{avg_meta:.1f}"])
                        writer.writerow(["Maximum Metatarsal Pressure:", f"{max_meta}"])
                    
                        # Check thresholds
                        temp_threshold = config["monitoring"]["temperature_threshold"]
                        humidity_threshold = config["monitoring"]["humidity_threshold"]
                        pressure_threshold = config["monitoring"]["pressure_threshold"]
                        
                        temp_threshold_count = sum(1 for d in data_points if d["temperature"] > temp_threshold)
                        humidity_threshold_count = sum(1 for d in data_points if d["humidity"] > humidity_threshold)
                        heel_threshold_count = sum(1 for d in data_points if d["heel_pressure"] > pressure_threshold)
                        meta_threshold_count = sum(1 for d in data_points if d["meta_pressure"] > pressure_threshold)
                        
                        writer.writerow([])
                        writer.writerow(["THRESHOLD VIOLATIONS"])
                        writer.writerow(["Temperature Threshold:", f"{temp_threshold}°C"])
                        writer.writerow(["Temperature Violations:", f"{temp_threshold_count} ({temp_threshold_count/len(data_points)*100:.1f}%)"])
                        writer.writerow(["Humidity Threshold:", f"{humidity_threshold}%"])
                        writer.writerow(["Humidity Violations:", f"{humidity_threshold_count} ({humidity_threshold_count/len(data_points)*100:.1f}%)"])
                        writer.writerow(["Pressure Threshold:", f"{pressure_threshold}"])
                        writer.writerow(["Heel Pressure Violations:", f"{heel_threshold_count} ({heel_threshold_count/len(data_points)*100:.1f}%)"])
                        writer.writerow(["Metatarsal Pressure Violations:", f"{meta_threshold_count} ({meta_threshold_count/len(data_points)*100:.1f}%)"])
                        writer.writerow([])
                        
                        # Add patterns detected
                        writer.writerow(["DETECTED PATTERNS"])
                        patterns = self.detect_patterns(data_points)
                        if patterns:
                            for i, pattern in enumerate(patterns, 1):
                                writer.writerow([f"Pattern {i}:", pattern])
                        else:
                            writer.writerow(["No significant patterns detected"])
                        
                        writer.writerow([])
                        writer.writerow(["FULL DATA LOG"])
                        writer.writerow(["Timestamp", "Temperature (°C)", "Humidity (%)", "Heel Pressure", "Metatarsal Pressure"])
                        
                        # Write full data log
                        for point in data_points:
                            writer.writerow([
                                point["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                                f"{point['temperature']:.1f}",
                                f"{point['humidity']:.1f}",
                                point["heel_pressure"],
                                point["meta_pressure"]
                            ])
                    
                    else:
                        writer.writerow(["No data available for the last 24 hours"])
                
                except Exception as e:
                    writer.writerow(["Error processing data:", str(e)])
            
            self.status_bar.config(text=f"Medical report exported to {export_filename}")
            messagebox.showinfo("Export Complete", f"Medical report exported to {export_filename}")
        
        except Exception as e:
            self.status_bar.config(text=f"Medical export failed: {e}")
            messagebox.showerror("Export Failed", f"Error exporting medical report: {e}")

    def run_deep_analysis(self):
        """Run a deep analysis of historical data and update pattern text"""
        try:
            self.status_bar.config(text="Running deep analysis...")
            self.progress_bar.start(10)
            
            # Simulate processing time for deep analysis
            data_points = []
            with open(data_file, 'r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                for row in reader:
                    if len(row) >= 5:
                        data_points.append({
                            "timestamp": datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"),
                            "temperature": float(row[1]),
                            "humidity": float(row[2]),
                            "heel_pressure": int(float(row[3])),
                            "meta_pressure": int(float(row[4]))
                        })
            
            patterns = self.detect_patterns(data_points)
            self.pattern_text.delete(1.0, tk.END)
            self.pattern_text.insert(tk.END, "Deep Analysis Results:\n\n")
            
            if patterns:
                for pattern in patterns:
                    self.pattern_text.insert(tk.END, f"• {pattern}\n")
            else:
                self.pattern_text.insert(tk.END, "No significant patterns detected in the data.")
            
            self.status_bar.config(text="Deep analysis completed")
            self.progress_bar.stop()
        
        except Exception as e:
            self.status_bar.config(text=f"Deep analysis failed: {e}")
            self.pattern_text.delete(1.0, tk.END)
            self.pattern_text.insert(tk.END, f"Error during analysis: {str(e)}")
            self.progress_bar.stop()

    def reconnect_bluetooth(self):
        """Attempt to reconnect or disconnect Bluetooth"""
        global bt_socket, bt_connected
        
        if bt_connected:
            try:
                bt_socket.close()
                bt_connected = False
                self.update_connection_status("disconnected", "Bluetooth disconnected")
            except Exception as e:
                self.status_bar.config(text=f"Error disconnecting: {e}")
        else:
            self.update_connection_status("connecting", "Attempting to connect...")
            # Run connection in a separate thread to avoid freezing UI
            threading.Thread(target=connect_bluetooth, daemon=True).start()

    def scan_for_devices(self):
        """Scan for nearby Bluetooth devices and display them"""
        try:
            self.status_bar.config(text="Scanning for devices...")
            self.progress_bar.start(10)
            
            devices = discover_devices()
            self.progress_bar.stop()
            
            if devices:
                device_list = "\n".join([f"{name} ({addr})" for addr, name in devices])
                messagebox.showinfo("Devices Found", f"Found {len(devices)} devices:\n{device_list}")
                
                # Update MAC address if user selects a device
                if devices and messagebox.askyesno("Select Device", "Would you like to use one of these devices?"):
                    selected = devices[0][0]  # Use first device for simplicity
                    self.mac_var.set(selected)
                    config["bluetooth"]["mac_address"] = selected
                    save_config()
                    self.reconnect_bluetooth()
            else:
                messagebox.showinfo("No Devices", "No Bluetooth devices found. Ensure devices are in range and discoverable.")
            
            self.status_bar.config(text="Device scan completed")
        
        except Exception as e:
            self.progress_bar.stop()
            self.status_bar.config(text=f"Scan failed: {e}")
            messagebox.showerror("Scan Failed", f"Error scanning for devices: {e}")

    def toggle_simulation(self):
        """Toggle simulation mode"""
        config["simulation"]["enabled"] = not config["simulation"]["enabled"]
        self.sim_enable.set(config["simulation"]["enabled"])
        self.sim_button_text.set("Disable Simulation" if config["simulation"]["enabled"] else "Enable Simulation")
        save_config()
        self.status_bar.config(text=f"Simulation {'enabled' if config['simulation']['enabled'] else 'disabled'}")

    def save_settings(self):
        """Save all settings from the settings tab"""
        try:
            # Update Bluetooth settings
            config["bluetooth"]["mac_address"] = self.mac_var.get()
            config["bluetooth"]["port"] = self.port_var.get()
            config["bluetooth"]["auto_reconnect"] = self.auto_reconnect.get()
            config["bluetooth"]["reconnect_interval"] = self.reconnect_interval.get()
            
            # Update monitoring settings
            config["monitoring"]["update_interval"] = self.update_interval.get()
            config["monitoring"]["temperature_threshold"] = self.temperature_threshold_var.get()
            config["monitoring"]["humidity_threshold"] = self.humidity_threshold_var.get()
            config["monitoring"]["pressure_threshold"] = self.pressure_threshold_var.get()
            config["monitoring"]["alert_sound"] = self.alert_sound.get()
            
            # Update simulation settings
            config["simulation"]["enabled"] = self.sim_enable.get()
            config["simulation"]["realistic_variation"] = self.sim_realistic.get()
            
            # Update UI settings
            config["ui"]["theme"] = self.theme_var.get()
            config["ui"]["graph_points"] = self.graph_points.get()
            config["ui"]["auto_export"] = self.auto_export.get()
            
            save_config()
            self.status_bar.config(text="Settings saved successfully")
            messagebox.showinfo("Settings Saved", "All settings have been saved successfully.")
            
            # Update theme if changed
            if config["ui"]["theme"] != self.theme_name:
                self.update_theme()
        
        except Exception as e:
            self.status_bar.config(text=f"Error saving settings: {e}")
            messagebox.showerror("Save Failed", f"Error saving settings: {e}")

    def restore_defaults(self):
        """Restore default settings"""
        global config
        try:
            if messagebox.askyesno("Restore Defaults", "Are you sure you want to restore default settings?"):
                config = default_config.copy()
                save_config()
                
                # Update UI fields
                self.mac_var.set(config["bluetooth"]["mac_address"])
                self.port_var.set(config["bluetooth"]["port"])
                self.auto_reconnect.set(config["bluetooth"]["auto_reconnect"])
                self.reconnect_interval.set(config["bluetooth"]["reconnect_interval"])
                
                self.update_interval.set(config["monitoring"]["update_interval"])
                self.temperature_threshold_var.set(config["monitoring"]["temperature_threshold"])
                self.humidity_threshold_var.set(config["monitoring"]["humidity_threshold"])
                self.pressure_threshold_var.set(config["monitoring"]["pressure_threshold"])
                self.alert_sound.set(config["monitoring"]["alert_sound"])
                
                self.sim_enable.set(config["simulation"]["enabled"])
                self.sim_realistic.set(config["simulation"]["realistic_variation"])
                
                self.theme_var.set(config["ui"]["theme"])
                self.graph_points.set(config["ui"]["graph_points"])
                self.auto_export.set(config["ui"]["auto_export"])
                
                self.status_bar.config(text="Default settings restored")
                messagebox.showinfo("Defaults Restored", "Default settings have been restored.")
                
                # Update theme
                self.update_theme()
        except Exception as e:
            self.status_bar.config(text=f"Error restoring defaults: {e}")
            messagebox.showerror("Restore Defaults Failed", f"Error restoring defaults: {e}")

    def update_theme(self, event=None):
        """Update the application theme"""
        new_theme = self.theme_var.get()
        if new_theme != self.theme_name:
            self.theme_name = new_theme
            self.theme = THEMES[new_theme]
            
            # Update color variables
            self.bg_color = self.theme["bg_color"]
            self.card_bg = self.theme["card_bg"]
            self.text_primary = self.theme["text_primary"]
            self.text_secondary = self.theme["text_secondary"]
            self.accent_color = self.theme["accent_color"]
            self.accent_secondary = self.theme["accent_secondary"]
            self.header_color = self.theme["header_color"]
            self.alert_bg = self.theme["alert_bg"]
            self.alert_fg = self.theme["alert_fg"]
            self.success_color = self.theme["success_color"]
            
            # Update root window
            self.root.configure(bg=self.bg_color)
            
            # Recreate styles with new theme
            self.setup_styles()
            
            # Redraw logo
            self.draw_logo()
            
            # Update all widgets by recreating the UI
            # Note: For a production app, you might want to update specific widgets instead
            self.status_bar.config(text="Theme updated. Restart recommended for full effect.")
            messagebox.showinfo("Theme Updated", 
                              "Theme has been updated. For best results, restart the application.")

    def clear_alerts(self):
        """Clear all alerts from the alerts display"""
        if self.alerts_text:
            self.alerts_text.delete(1.0, tk.END)
            self.alerts_text.insert(tk.END, "No alerts detected. System monitoring is active.")
            self.status_bar.config(text="Alerts cleared")

    def show_alert(self, message):
        """Show a popup alert message"""
        messagebox.showwarning("Alert", message)
        self.status_bar.config(text=f"Alert: {message}")

if __name__ == "__main__":
    # Initialize data file
    initialize_data_file()
    
    # Load configuration
    load_config()
    
    # Create and run the application
    root = tk.Tk()
    app = SmartInsoleApp(root)

    root.mainloop()