-- DDL for new `excel_raw_data` table in `bundleBuilder` database

USE `bundleBuilder`;

-- Drop the table if it already exists to ensure a clean creation
DROP TABLE IF EXISTS `excel_raw_data`;

-- Create the `excel_raw_data` table
CREATE TABLE `excel_raw_data` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `UID` VARCHAR(255) NOT NULL,
    `department` VARCHAR(255) NULL,
    `Attribute_Value_Name` VARCHAR(255) NULL,
    `Access_Source_Name` VARCHAR(255) NULL,
    `type` VARCHAR(255) NULL,            -- Corresponds to 'type' display attribute
    `Is_Manager` VARCHAR(255) NULL,      -- Corresponds to 'Is Manager' display attribute
    `country` VARCHAR(255) NULL,         -- Corresponds to 'country' display attribute
    `jobTitle` VARCHAR(255) NULL,        -- Corresponds to 'jobTitle' display attribute
    `location` VARCHAR(255) NULL,        -- Corresponds to 'location' display attribute
    `upload_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- To track when the row was uploaded
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Add indexes for columns that might be frequently queried
CREATE INDEX `idx_erd_uid` ON `excel_raw_data`(`UID`);
CREATE INDEX `idx_erd_department` ON `excel_raw_data`(`department`);
CREATE INDEX `idx_erd_attr_value_name` ON `excel_raw_data`(`Attribute_Value_Name`);
CREATE INDEX `idx_erd_access_source_name` ON `excel_raw_data`(`Access_Source_Name`);
