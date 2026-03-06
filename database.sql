CREATE DATABASE cybercrime_db;
USE cybercrime_db;

CREATE TABLE complaints (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(15),
    type VARCHAR(50),
    status VARCHAR(50) DEFAULT 'Pending'
);