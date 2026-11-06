-- DDL for MySQL Database 'bundleBuilder'

-- Optional: Drop the database if it already exists, for fresh creation
DROP DATABASE IF EXISTS `bundleBuilder`;

-- Create the new database
CREATE DATABASE `bundleBuilder`;
-- DDL for MySQL Database 'bundleBuilder'

-- IMPORTANT: These DROP statements will DELETE ALL DATA from your tables if they exist.
-- Proceed with caution.
USE `bundleBuilder`;

-- Re-ordering drop for foreign key dependencies:
-- Drop tables that depend on others first.
DROP TABLE IF EXISTS `near_match_differing_uids`;
DROP TABLE IF EXISTS `attr_value_near_match_differing_uids`;
DROP TABLE IF EXISTS `exact_correlations`;
DROP TABLE IF EXISTS `attr_value_exact_correlations`;
DROP TABLE IF EXISTS `near_identical_correlations`;
DROP TABLE IF EXISTS `attr_value_near_correlations`;


-- 1. Table to store exact correlations (primary_grouping_column vs attribute)
CREATE TABLE `exact_correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `primary_grouping_column` VARCHAR(255) NOT NULL,
    `primary_value` VARCHAR(255) NOT NULL,
    `attribute_value` VARCHAR(255) NOT NULL,
    `access_source_name` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Table to store near identical correlations (primary_grouping_column vs attribute)
CREATE TABLE `near_identical_correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `primary_grouping_column` VARCHAR(255) NOT NULL,
    `primary_value` VARCHAR(255) NOT NULL,
    `attribute_value` VARCHAR(255) NOT NULL,
    `access_source_name` VARCHAR(255) NOT NULL,
    `jaccard_score` DECIMAL(5, 4) NOT NULL,
    `primary_population_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Table to store details of UIDs that differ in near_identical_correlations
CREATE TABLE `near_match_differing_uids` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `near_match_correlation_id` INT NOT NULL,  -- Foreign key to near_identical_correlations
    `uid` VARCHAR(255) NOT NULL,
    `is_in_primary_only` BOOLEAN NOT NULL,
    `is_in_attribute_only` BOOLEAN NOT NULL,
    `type` VARCHAR(255) NULL,
    `is_manager` VARCHAR(255) NULL,
    `country` VARCHAR(255) NULL,
    `department` VARCHAR(255) NULL,
    `jobTitle` VARCHAR(255) NULL,
    `location` VARCHAR(255) NULL,
    
    CONSTRAINT `fk_nmdu_correlation_id`
        FOREIGN KEY (`near_match_correlation_id`) REFERENCES `near_identical_correlations`(`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 4. Table to store exact correlations between two Attribute Value Names
-- CORRECTED: UNIQUE constraint removed. Uniqueness will be enforced by Python script.
CREATE TABLE `attr_value_exact_correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `attribute_A_value` VARCHAR(255) NOT NULL,
    `access_source_A_name` VARCHAR(255) NOT NULL,
    `attribute_B_value` VARCHAR(255) NOT NULL,
    `access_source_B_name` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Table to store near identical correlations between two Attribute Value Names
-- CORRECTED: UNIQUE constraint removed. Uniqueness will be enforced by Python script.
CREATE TABLE `attr_value_near_correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `attribute_A_value` VARCHAR(255) NOT NULL,
    `access_source_A_name` VARCHAR(255) NOT NULL,
    `attribute_B_value` VARCHAR(255) NOT NULL,
    `access_source_B_name` VARCHAR(255) NOT NULL,
    `jaccard_score` DECIMAL(5, 4) NOT NULL,
    `population_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Table to store details of UIDs that differ in attr_value_near_correlations
CREATE TABLE `attr_value_near_match_differing_uids` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `near_match_correlation_id` INT NOT NULL,  -- Foreign key to attr_value_near_correlations
    `uid` VARCHAR(255) NOT NULL,
    `is_in_A_only` BOOLEAN NOT NULL,
    `is_in_B_only` BOOLEAN NOT NULL,
    `type` VARCHAR(255) NULL,
    `is_manager` VARCHAR(255) NULL,
    `country` VARCHAR(255) NULL,
    `department` VARCHAR(255) NULL,
    `jobTitle` VARCHAR(255) NULL,
    `location` VARCHAR(255) NULL,
    
    CONSTRAINT `fk_avnmd_correlation_id`
        FOREIGN KEY (`near_match_correlation_id`) REFERENCES `attr_value_near_correlations`(`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Optional: Add indexes for faster lookups on common query fields
-- Note: Indexes on the full VARCHAR columns can still be beneficial for searches,
-- but a UNIQUE constraint on long VARCHAR combinations is what caused the issue.
-- MySQL might add warnings if an index on VARCHAR(255) is created without a prefix
-- if the combined length exceeds its internal limits, but it won't be an error.
CREATE INDEX `idx_exact_primary_value` ON `exact_correlations`(`primary_value`);
CREATE INDEX `idx_near_primary_value` ON `near_identical_correlations`(`primary_value`);
CREATE INDEX `idx_near_jaccard_score` ON `near_identical_correlations`(`jaccard_score`);
CREATE INDEX `idx_nmdu_uid` ON `near_match_differing_uids`(`uid`);
CREATE INDEX `idx_nmdu_near_match_id` ON `near_match_differing_uids`(`near_match_correlation_id`);

CREATE INDEX `idx_attr_exact_A_val` ON `attr_value_exact_correlations`(`attribute_A_value`);
CREATE INDEX `idx_attr_near_A_val` ON `attr_value_near_correlations`(`attribute_A_value`);
CREATE INDEX `idx_attr_near_jaccard_score` ON `attr_value_near_correlations`(`jaccard_score`);
CREATE INDEX `idx_avnmd_uid` ON `attr_value_near_match_differing_uids`(`uid`);
CREATE INDEX `idx_avnmd_near_match_id` ON `attr_value_near_match_differing_uids`(`near_match_correlation_id`);

