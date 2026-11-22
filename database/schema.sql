-- =====================================================================
-- DATABASE DESIGN FOR AIRFARE PRICE ESTIMATION & FARE PATTERN ANALYSIS
-- DBMS: MySQL 8.0+ / MariaDB (5 Marks Evaluation Deliverable)
-- =====================================================================

CREATE DATABASE IF NOT EXISTS flight_fare_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE flight_fare_db;

-- 1. Master Table: Airports & Cities
CREATE TABLE IF NOT EXISTS airports_master (
    airport_code VARCHAR(10) PRIMARY KEY,
    city_name VARCHAR(100) NOT NULL,
    state_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed initial Airport lookup data
INSERT INTO airports_master (airport_code, city_name, state_name) VALUES
('BLR', 'Banglore', 'Karnataka'),
('CCU', 'Kolkata', 'West Bengal'),
('DEL', 'Delhi', 'National Capital Region'),
('MAA', 'Chennai', 'Tamil Nadu'),
('BOM', 'Mumbai', 'Maharashtra'),
('COK', 'Cochin', 'Kerala'),
('HYD', 'Hyderabad', 'Telangana')
ON DUPLICATE KEY UPDATE city_name=VALUES(city_name);

-- 2. Master Table: Airlines Catalog
CREATE TABLE IF NOT EXISTS airlines_master (
    airline_id INT AUTO_INCREMENT PRIMARY KEY,
    airline_name VARCHAR(100) NOT NULL UNIQUE,
    carrier_code VARCHAR(10),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed Airlines
INSERT INTO airlines_master (airline_name, carrier_code) VALUES
('IndiGo', '6E'),
('Air India', 'AI'),
('Jet Airways', '9W'),
('SpiceJet', 'SG'),
('Multiple carriers', 'MC'),
('Vistara', 'UK'),
('Air Asia', 'I5'),
('GoAir', 'G8')
ON DUPLICATE KEY UPDATE carrier_code=VALUES(carrier_code);

-- 3. Core Transaction Table: Prediction Logs & Flight Queries
CREATE TABLE IF NOT EXISTS flight_predictions (
    prediction_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    airline_name VARCHAR(100) NOT NULL,
    source_city VARCHAR(100) NOT NULL,
    destination_city VARCHAR(100) NOT NULL,
    journey_date DATE NOT NULL,
    departure_time VARCHAR(10) NOT NULL,
    arrival_time VARCHAR(10) NOT NULL,
    duration_mins INT NOT NULL,
    total_stops INT NOT NULL DEFAULT 0,
    predicted_fare DECIMAL(10, 2) NOT NULL,
    fare_category ENUM('Budget', 'Standard', 'Premium', 'Surge') DEFAULT 'Standard',
    model_name VARCHAR(100) DEFAULT 'RandomForestRegressor_Tuned',
    model_r2_score DECIMAL(5, 4) DEFAULT 0.8177,
    client_ip VARCHAR(50) DEFAULT '127.0.0.1',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source_dest (source_city, destination_city),
    INDEX idx_airline (airline_name),
    INDEX idx_journey_date (journey_date)
);

-- 4. Benchmark & Model Performance Auditing Table
CREATE TABLE IF NOT EXISTS model_benchmarks (
    benchmark_id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    r2_score DECIMAL(5, 4) NOT NULL,
    mean_absolute_error DECIMAL(10, 2) NOT NULL,
    root_mean_squared_error DECIMAL(10, 2) NOT NULL,
    training_sample_count INT NOT NULL,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed initial benchmark evaluations
INSERT INTO model_benchmarks (model_name, r2_score, mean_absolute_error, root_mean_squared_error, training_sample_count) VALUES
('Linear Regression', 0.5746, 2029.57, 3028.56, 8545),
('Ridge Regression', 0.5743, 2029.49, 3029.59, 8545),
('Decision Tree', 0.7575, 1223.48, 2286.80, 8545),
('Random Forest (Default)', 0.8112, 1168.80, 2017.86, 8545),
('Random Forest (Tuned)', 0.8177, 1131.59, 1982.37, 8545);
