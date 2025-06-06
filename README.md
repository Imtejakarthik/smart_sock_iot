# smart_sock_iot
# 🧦 Smart Socks: Diabetic Foot Ulcer Detection System

Smart Socks is an open-access, full-stack system designed to monitor foot health in diabetic patients by detecting early signs of foot ulcers. It uses sensors to track bilateral foot temperature, pressure, and humidity, alerting users in real-time if anomalies are detected. The system is ideal for remote health monitoring and preventive care.

## 🚀 Features

- 🔥 **Bilateral Temperature Analysis** using MLX90614
- 🧭 **Pressure Monitoring** via BMP280 sensor
- 💧 **Humidity Tracking** with DHT11 sensor
- 📡 **Bluetooth-Based Real-Time Data Transmission**
- 📈 **Live Visualization** of sensor data in graphs
- ⚠️ **Threshold-Based Alerting System**
- 🌐 **Open Access Dashboard** (No login/auth required)
- 🏥 **Integration-Ready** for Remote Healthcare Systems

## 🧠 Use Case

This project targets early detection of **Diabetic Foot Ulcers (DFUs)**, a common complication in diabetic patients. Continuous monitoring and alerting can significantly reduce the risk of severe infections and amputations.

---

## 🧰 Tech Stack

### 🎛️ Hardware
- **Arduino-compatible microcontroller**
- **MLX90614** (Infrared Temperature Sensor)
- **BMP280** (Pressure Sensor)
- **DHT11** (Humidity Sensor)
- **Bluetooth Module** (e.g., HC-05)

### 💻 Software
- **Backend**: Python Flask + PostgreSQL
- **Frontend**: HTML, CSS, JS (Bootstrap/Vanilla)
- **Data Transmission**: Bluetooth Serial Communication
- **Graphing**: Chart.js / D3.js

---

## ⚙️ Setup Instructions

### 1. Hardware Setup
- Connect sensors to the Arduino as follows:
  - `MLX90614` → I2C pins
  - `BMP280` → I2C or SPI
  - `DHT11` → Digital pin
  - `Bluetooth Module` → TX/RX

- Upload the Arduino firmware (`firmware/smartsocks.ino`) to the board.

### 2. Backend Setup
```bash
# Clone the repo
git clone https://github.com/your-username/smart-socks.git
cd smart-socks/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt

# Setup database
psql -U postgres
CREATE DATABASE smartsocks;

# Start server
python app.py
