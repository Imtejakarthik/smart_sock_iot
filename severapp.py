
import requests
import time
import csv
import os
import matplotlib.pyplot as plt
from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Blynk API configuration
BLYNK_TOKEN = "H9fLE7xlcNq305fBf_NhbHOQ9Z9dzKFD"  # Same token as in your ESP32 code
BLYNK_SERVER = "blynk.cloud"  # Blynk cloud server
API_BASE_URL = f"https://{BLYNK_SERVER}/external/api/"

# Thresholds (same as ESP32 code)
TEMPERATURE_THRESHOLD = 37.0
HUMIDITY_THRESHOLD = 60.0
PRESSURE_THRESHOLD = 500

# Data storage
data_file = "insole_data.csv"
latest_readings = {
    "temperature": 0.0,
    "humidity": 0.0,
    "heel_pressure": 0,
    "meta_pressure": 0,
    "timestamp": None
}

# Create or check for data file
def initialize_data_file():
    if not os.path.exists(data_file):
        with open(data_file, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Timestamp', 'Temperature', 'Humidity', 'Heel_Pressure', 'Meta_Pressure'])
        print(f"Created new data file: {data_file}")

# Get data from Blynk
def get_data_from_blynk():
    try:
        # Get data for each virtual pin
        temp_url = f"{API_BASE_URL}get?token={BLYNK_TOKEN}&v0"
        humidity_url = f"{API_BASE_URL}get?token={BLYNK_TOKEN}&v1"
        heel_pressure_url = f"{API_BASE_URL}get?token={BLYNK_TOKEN}&v2"
        meta_pressure_url = f"{API_BASE_URL}get?token={BLYNK_TOKEN}&v3"
        
        # Make requests
        temp_response = requests.get(temp_url)
        humidity_response = requests.get(humidity_url)
        heel_pressure_response = requests.get(heel_pressure_url)
        meta_pressure_response = requests.get(meta_pressure_url)
        
        # Parse responses
        if all(response.status_code == 200 for response in [temp_response, humidity_response, heel_pressure_response, meta_pressure_response]):
            latest_readings["temperature"] = float(temp_response.text.strip('[]"'))
            latest_readings["humidity"] = float(humidity_response.text.strip('[]"'))
            latest_readings["heel_pressure"] = int(float(heel_pressure_response.text.strip('[]"')))
            latest_readings["meta_pressure"] = int(float(meta_pressure_response.text.strip('[]"')))
            latest_readings["timestamp"] = datetime.now()
            
            # Save data to CSV
            save_data_to_csv()
            
            return True
        else:
            print("Error getting data from Blynk.")
            return False
    except Exception as e:
        print(f"Error in get_data_from_blynk: {e}")
        return False

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

# Analyze data for potential issues
def analyze_data():
    alerts = []
    
    if latest_readings["temperature"] > TEMPERATURE_THRESHOLD:
        alerts.append(f"⚠️ High Temperature: {latest_readings['temperature']}°C")
    
    if latest_readings["humidity"] > HUMIDITY_THRESHOLD:
        alerts.append(f"⚠️ High Humidity: {latest_readings['humidity']}%")
    
    if latest_readings["heel_pressure"] > PRESSURE_THRESHOLD:
        alerts.append(f"⚠️ High Heel Pressure: {latest_readings['heel_pressure']}")
    
    if latest_readings["meta_pressure"] > PRESSURE_THRESHOLD:
        alerts.append(f"⚠️ High Metatarsal Pressure: {latest_readings['meta_pressure']}")
    
    return alerts

# Plot historical data
def plot_data():
    try:
        timestamps = []
        temperatures = []
        humidities = []
        heel_pressures = []
        meta_pressures = []
        
        with open(data_file, 'r') as file:
            reader = csv.reader(file)
            next(reader)  # Skip header
            
            # Get last 50 readings at most
            rows = list(reader)[-50:]
            
            for row in rows:
                timestamps.append(datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S"))
                temperatures.append(float(row[1]))
                humidities.append(float(row[2]))
                heel_pressures.append(int(float(row[3])))
                meta_pressures.append(int(float(row[4])))
        
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(10, 8))
        
        # Plot temperature
        ax1.plot(timestamps, temperatures, 'r-')
        ax1.set_title('Temperature (°C)')
        ax1.axhline(y=TEMPERATURE_THRESHOLD, color='r', linestyle='--', alpha=0.7)
        ax1.set_ylim(min(temperatures)-1 if temperatures else 20, max(temperatures)+1 if temperatures else 40)
        ax1.tick_params(axis='x', rotation=45)
        
        # Plot humidity
        ax2.plot(timestamps, humidities, 'b-')
        ax2.set_title('Humidity (%)')
        ax2.axhline(y=HUMIDITY_THRESHOLD, color='r', linestyle='--', alpha=0.7)
        ax2.set_ylim(min(humidities)-5 if humidities else 30, max(humidities)+5 if humidities else 80)
        ax2.tick_params(axis='x', rotation=45)
        
        # Plot heel pressure
        ax3.plot(timestamps, heel_pressures, 'g-')
        ax3.set_title('Heel Pressure')
        ax3.axhline(y=PRESSURE_THRESHOLD, color='r', linestyle='--', alpha=0.7)
        ax3.set_ylim(0, max(heel_pressures)+100 if heel_pressures else 1000)
        ax3.tick_params(axis='x', rotation=45)
        
        # Plot metatarsal pressure
        ax4.plot(timestamps, meta_pressures, 'y-')
        ax4.set_title('Metatarsal Pressure')
        ax4.axhline(y=PRESSURE_THRESHOLD, color='r', linestyle='--', alpha=0.7)
        ax4.set_ylim(0, max(meta_pressures)+100 if meta_pressures else 1000)
        ax4.tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        return fig
    except Exception as e:
        print(f"Error plotting data: {e}")
        return None

# GUI Class
class SmartInsoleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Insole Monitoring")
        self.root.geometry("1000x800")
        self.root.configure(bg="#f0f0f0")
        
        # Configure style
        style = ttk.Style()
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabel", background="#f0f0f0", font=("Arial", 12))
        style.configure("Header.TLabel", font=("Arial", 16, "bold"))
        style.configure("Value.TLabel", font=("Arial", 14))
        style.configure("Alert.TLabel", foreground="red", font=("Arial", 12, "bold"))
        
        # Main frame
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_label = ttk.Label(main_frame, text="Diabetic Foot Ulcer Monitoring System", style="Header.TLabel")
        title_label.pack(pady=10)
        
        # Readings frame
        readings_frame = ttk.Frame(main_frame)
        readings_frame.pack(fill=tk.X, pady=10)
        
        # Temperature
        temp_frame = ttk.Frame(readings_frame)
        temp_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(temp_frame, text="Temperature:").pack()
        self.temp_value = ttk.Label(temp_frame, text="--°C", style="Value.TLabel")
        self.temp_value.pack()
        
        # Humidity
        humidity_frame = ttk.Frame(readings_frame)
        humidity_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(humidity_frame, text="Humidity:").pack()
        self.humidity_value = ttk.Label(humidity_frame, text="--%", style="Value.TLabel")
        self.humidity_value.pack()
        
        # Heel Pressure
        heel_frame = ttk.Frame(readings_frame)
        heel_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(heel_frame, text="Heel Pressure:").pack()
        self.heel_value = ttk.Label(heel_frame, text="--", style="Value.TLabel")
        self.heel_value.pack()
        
        # Metatarsal Pressure
        meta_frame = ttk.Frame(readings_frame)
        meta_frame.pack(side=tk.LEFT, padx=20)
        ttk.Label(meta_frame, text="Metatarsal Pressure:").pack()
        self.meta_value = ttk.Label(meta_frame, text="--", style="Value.TLabel")
        self.meta_value.pack()
        
        # Last update time
        self.update_time = ttk.Label(main_frame, text="Last update: Never")
        self.update_time.pack(pady=5)
        
        # Alerts frame
        alerts_frame = ttk.Frame(main_frame)
        alerts_frame.pack(fill=tk.X, pady=10)
        ttk.Label(alerts_frame, text="Alerts:", style="Header.TLabel").pack(anchor=tk.W)
        self.alerts_text = tk.Text(alerts_frame, height=5, width=80, bg="#ffe6e6", fg="#990000")
        self.alerts_text.pack(fill=tk.X, pady=5)
        
        # Graph canvas container
        self.graph_frame = ttk.Frame(main_frame)
        self.graph_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Action buttons
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(buttons_frame, text="Refresh Data", command=self.refresh_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="View Historical Data", command=self.view_historical_data).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Export Data", command=self.export_data).pack(side=tk.LEFT, padx=5)
        
        # Update data every 10 seconds
        self.update_data()
    
    def update_data(self):
        """Update displayed data with latest readings"""
        if get_data_from_blynk():
            # Update display values
            self.temp_value.config(text=f"{latest_readings['temperature']}°C", 
                                  foreground="red" if latest_readings['temperature'] > TEMPERATURE_THRESHOLD else "green")
            
            self.humidity_value.config(text=f"{latest_readings['humidity']}%",
                                     foreground="red" if latest_readings['humidity'] > HUMIDITY_THRESHOLD else "green")
            
            self.heel_value.config(text=f"{latest_readings['heel_pressure']}",
                                 foreground="red" if latest_readings['heel_pressure'] > PRESSURE_THRESHOLD else "green")
            
            self.meta_value.config(text=f"{latest_readings['meta_pressure']}",
                                 foreground="red" if latest_readings['meta_pressure'] > PRESSURE_THRESHOLD else "green")
            
            # Update timestamp
            self.update_time.config(text=f"Last update: {latest_readings['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Check for alerts
            alerts = analyze_data()
            self.alerts_text.delete(1.0, tk.END)
            if alerts:
                for alert in alerts:
                    self.alerts_text.insert(tk.END, f"{alert}\n")
            else:
                self.alerts_text.insert(tk.END, "No alerts - all readings normal.")
            
            # Update graphs
            for widget in self.graph_frame.winfo_children():
                widget.destroy()
            
            fig = plot_data()
            if fig:
                canvas = FigureCanvasTkAgg(fig, self.graph_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Schedule next update
        self.root.after(10000, self.update_data)
    
    def refresh_data(self):
        """Manual refresh of data"""
        self.update_data()
        messagebox.showinfo("Refresh", "Data refreshed from Blynk")
    
    def view_historical_data(self):
        """Open a new window with historical data"""
        history_window = tk.Toplevel(self.root)
        history_window.title("Historical Data")
        history_window.geometry("800x600")
        
        # Show data in a table
        data_frame = ttk.Frame(history_window)
        data_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        columns = ("Time", "Temperature", "Humidity", "Heel Pressure", "Meta Pressure")
        tree = ttk.Treeview(data_frame, columns=columns, show="headings")
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(data_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True)
        
        # Load data
        try:
            with open(data_file, 'r') as file:
                reader = csv.reader(file)
                next(reader)  # Skip header
                
                for i, row in enumerate(reader):
                    tree.insert("", "end", values=row)
        except Exception as e:
            messagebox.showerror("Error", f"Could not load historical data: {e}")
    
    def export_data(self):
        """Export data to a new CSV file with timestamp"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_filename = f"insole_data_export_{timestamp}.csv"
            
            with open(data_file, 'r') as source, open(export_filename, 'w', newline='') as dest:
                reader = csv.reader(source)
                writer = csv.writer(dest)
                for row in reader:
                    writer.writerow(row)
            
            messagebox.showinfo("Export Successful", f"Data exported to {export_filename}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not export data: {e}")

# Main function
def main():
    initialize_data_file()
    
    root = tk.Tk()
    app = SmartInsoleApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()