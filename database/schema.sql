-- =====================================================================
-- DATABASE DESIGN FOR FARELENS (3rd Normal Form - 3NF)
-- Project: Airfare Price Estimation and Fare Pattern Analysis-II
-- DBMS: MySQL 8.0+ / MariaDB (5 Marks Evaluation Deliverable)
-- =====================================================================

CREATE DATABASE IF NOT EXISTS flight_fare_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE flight_fare_db;

-- 1. Stakeholders / Users Table (Authentication & Role-Based Access)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('traveler', 'analyst', 'admin') NOT NULL DEFAULT 'traveler',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Master Lookup Table: Airports
CREATE TABLE IF NOT EXISTS airports_master (
    airport_code VARCHAR(10) PRIMARY KEY,
    city_name VARCHAR(100) NOT NULL UNIQUE,
    state_name VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO airports_master (airport_code, city_name, state_name) VALUES
('BLR', 'Banglore', 'Karnataka'),
('CCU', 'Kolkata', 'West Bengal'),
('DEL', 'Delhi', 'National Capital Region'),
('MAA', 'Chennai', 'Tamil Nadu'),
('BOM', 'Mumbai', 'Maharashtra'),
('COK', 'Cochin', 'Kerala'),
('HYD', 'Hyderabad', 'Telangana')
ON DUPLICATE KEY UPDATE city_name = VALUES(city_name), state_name = VALUES(state_name);

-- 3. Master Lookup Table: Airlines Catalog
CREATE TABLE IF NOT EXISTS airlines_master (
    airline_id INT AUTO_INCREMENT PRIMARY KEY,
    airline_name VARCHAR(100) NOT NULL UNIQUE,
    carrier_code VARCHAR(16) NOT NULL,
    airline_tier VARCHAR(40) NOT NULL DEFAULT 'Full-Service',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO airlines_master (airline_name, carrier_code, airline_tier) VALUES
('IndiGo', '6E', 'Low-Cost Carrier'),
('Air India', 'AI', 'Full-Service'),
('Jet Airways', '9W', 'Full-Service (Historical 2019)'),
('SpiceJet', 'SG', 'Low-Cost Carrier'),
('Multiple carriers', 'MC', 'Interline'),
('Vistara', 'UK', 'Full-Service'),
('Air Asia', 'I5', 'Low-Cost Carrier'),
('GoAir', 'G8', 'Low-Cost (Historical 2019)'),
('Multiple carriers Premium economy', 'MC-PE', 'Premium Economy'),
('Jet Airways Business', '9W-BUS', 'Business Class'),
('Vistara Premium economy', 'UK-PE', 'Premium Economy'),
('Trujet', '2T', 'Regional (Historical 2019)')
ON DUPLICATE KEY UPDATE carrier_code = VALUES(carrier_code), airline_tier = VALUES(airline_tier);

-- 4. Core Transaction Table: Flight Fare Prediction Logs (3NF via FKs)
CREATE TABLE IF NOT EXISTS flight_predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    airline_id INT NOT NULL,
    source_code VARCHAR(10) NOT NULL,
    dest_code VARCHAR(10) NOT NULL,
    route_str VARCHAR(150) NOT NULL,
    additional_info VARCHAR(100) NOT NULL DEFAULT 'No info',
    journey_date VARCHAR(20) NOT NULL,
    dep_time VARCHAR(10) NOT NULL,
    arrival_time VARCHAR(10) NOT NULL,
    duration_mins INT NOT NULL,
    total_stops INT NOT NULL DEFAULT 0,
    predicted_fare DECIMAL(10, 2) NOT NULL,
    fare_lower DECIMAL(10, 2) NOT NULL,
    fare_upper DECIMAL(10, 2) NOT NULL,
    fare_category VARCHAR(20) NOT NULL DEFAULT 'Standard',
    model_name VARCHAR(100) NOT NULL DEFAULT 'Random Forest (Tuned Final)',
    model_r2_score DECIMAL(5, 4) NOT NULL DEFAULT 0.9031,
    notes VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pred_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT fk_pred_airline FOREIGN KEY (airline_id) REFERENCES airlines_master(airline_id),
    CONSTRAINT fk_pred_source FOREIGN KEY (source_code) REFERENCES airports_master(airport_code),
    CONSTRAINT fk_pred_dest FOREIGN KEY (dest_code) REFERENCES airports_master(airport_code),
    CONSTRAINT chk_stops_range CHECK (total_stops >= 0 AND total_stops <= 4),
    CONSTRAINT chk_duration_pos CHECK (duration_mins > 0),
    CONSTRAINT chk_fare_pos CHECK (predicted_fare > 0),
    INDEX idx_pred_route (source_code, dest_code),
    INDEX idx_pred_user (user_id),
    INDEX idx_pred_airline (airline_id)
);

-- 5. User Price Watchlist & Alerts Table (Full CRUD Deliverable)
CREATE TABLE IF NOT EXISTS fare_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    prediction_id INT NULL,
    airline_id INT NOT NULL,
    source_code VARCHAR(10) NOT NULL,
    dest_code VARCHAR(10) NOT NULL,
    journey_date VARCHAR(20) NOT NULL,
    target_price DECIMAL(10, 2) NOT NULL,
    estimated_price DECIMAL(10, 2) NOT NULL,
    status ENUM('watching', 'target_met', 'paused') NOT NULL DEFAULT 'watching',
    notes VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_alert_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_alert_pred FOREIGN KEY (prediction_id) REFERENCES flight_predictions(id) ON DELETE SET NULL,
    CONSTRAINT fk_alert_airline FOREIGN KEY (airline_id) REFERENCES airlines_master(airline_id),
    CONSTRAINT fk_alert_source FOREIGN KEY (source_code) REFERENCES airports_master(airport_code),
    CONSTRAINT fk_alert_dest FOREIGN KEY (dest_code) REFERENCES airports_master(airport_code),
    CONSTRAINT chk_target_pos CHECK (target_price > 0)
);

-- 6. ML Benchmark Auditing Table
CREATE TABLE IF NOT EXISTS model_benchmarks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL UNIQUE,
    r2_score DECIMAL(6, 4) NOT NULL,
    mae DECIMAL(10, 2) NOT NULL,
    rmse DECIMAL(10, 2) NOT NULL,
    cv_r2_mean DECIMAL(6, 4) NULL,
    training_samples INT NOT NULL,
    feature_count INT NOT NULL,
    is_selected BOOLEAN NOT NULL DEFAULT FALSE,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
