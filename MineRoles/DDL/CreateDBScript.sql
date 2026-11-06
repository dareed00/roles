-- DDL for MySQL Database 'bundleBuilder'

-- Optional: Drop the database if it already exists, for fresh creation
DROP DATABASE IF EXISTS `bundleBuilder`;

-- Create the new database
CREATE DATABASE `bundleBuilder`;
-- DDL for MySQL Database 'bundleBuilder'

-- IMPORTANT: These DROP statements will DELETE ALL DATA from your tables if they exist.
-- Proceed with caution.
USE `bundleBuilder`;



-- Drop dependent tables first to avoid foreign key errors
DROP TABLE IF EXISTS `IdentityRoleAssignments`;
DROP TABLE IF EXISTS `IdentityAccessProfileAssignments`;
DROP TABLE IF EXISTS `IdentityEntitlementAssignments`;


CREATE TABLE `entitlements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Auto-incrementing integer PK',
    `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'The unique string ID from SailPoint',
    `entitlement_name` VARCHAR(255) NOT NULL,
    `source_name` VARCHAR(255) NULL,
    `description` TEXT NULL,
    `owner_name` VARCHAR(255) NULL,
    `owner_id` VARCHAR(255) NULL,
    `population_size` INT NOT NULL DEFAULT 0,
    `is_correlated` BOOLEAN NOT NULL DEFAULT FALSE 
COMMENT 'Flag to indicate if an exact (Jaccard=1.0) correlation has been found for this entitlement',
    `last_add_date` DATETIME NULL COMMENT 'The timestamp of the most recent ADD_PASSED event for this entitlement',
   `last_add_date_eventId` VARCHAR(255) NULL COMMENT 'The event ID of the most recent ADD_PASSED event',
    `last_remove_date` DATETIME NULL COMMENT 'The timestamp of the most recent REMOVE_PASSED event for this entitlement',
   `last_remove_date_eventId` VARCHAR(255) NULL COMMENT 'The event ID of the most recent REMOVE_PASSED event',
    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this record was loaded into the database',
    `creation_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Optional: to track when the entitlement was added
    CONSTRAINT `uq_entitlement_id` UNIQUE (`entitlement_id`)  
    
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE INDEX `idx_entitlements_is_correlated` ON `entitlements`(`is_correlated`);




-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `CurrentRoleModel_Roles`;

CREATE TABLE `CurrentRoleModel_Roles` (
    `id` VARCHAR(255) PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL,
    `description` TEXT NULL,
    `enabled` BOOLEAN DEFAULT TRUE,
    `requestable` BOOLEAN DEFAULT TRUE,
    `owner_id` VARCHAR(255) NULL,
    `owner_name` VARCHAR(255) NULL,
    `created` DATETIME NULL,
    `modified` DATETIME NULL,
    `last_add_date` DATETIME NULL COMMENT 'The timestamp of the most recent ADD_PASSED event for this role',
     `last_add_date_eventId` VARCHAR(255) NULL COMMENT 'The event ID of the most recent ADD_PASSED event',
    `last_remove_date` DATETIME NULL COMMENT 'The timestamp of the most recent REMOVE_PASSED event for this role',
    `last_remove_date_eventId` VARCHAR(255) NULL COMMENT 'The event ID of the most recent REMOVE_PASSED event'


) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Add indexes for frequently queried columns to improve performance
CREATE INDEX `idx_crmr_name` ON `CurrentRoleModel_Roles`(`name`);
CREATE INDEX `idx_crmr_enabled` ON `CurrentRoleModel_Roles`(`enabled`);
CREATE INDEX `idx_crmr_requestable` ON `CurrentRoleModel_Roles`(`requestable`);
CREATE INDEX `idx_crmr_owner_id` ON `CurrentRoleModel_Roles`(`owner_id`);


-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `CurrentRoleModel_AccessProfiles`;

-- Create the CurrentRoleModel_AccessProfiles table
CREATE TABLE `CurrentRoleModel_AccessProfiles` (
    `id` VARCHAR(255) PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL,
    `description` TEXT NULL,
    `enabled` BOOLEAN DEFAULT TRUE,
    `requestable` BOOLEAN DEFAULT TRUE,
    `owner_id` VARCHAR(255) NULL,
    `owner_name` VARCHAR(255) NULL,
    `source_id` VARCHAR(255) NULL,
    `source_name` VARCHAR(255) NULL,
    `created` DATETIME NULL,
    `modified` DATETIME NULL,
    -- Complex/Array fields stored as JSON
    `entitlements` JSON NULL COMMENT 'JSON array of Entitlements included in this Access Profile',
    `segments` JSON NULL COMMENT 'JSON array of segment IDs if the Access Profile is assigned to any segments',
    `provisioningCriteria` JSON NULL COMMENT 'JSON object defining the provisioning criteria',
    `additionalOwners` JSON NULL COMMENT 'JSON array of additional Identities or Governance Groups that own this Access Profile',
    `last_add_date` DATETIME NULL COMMENT 'The timestamp of the most recent ADD_PASSED event for this AP',
    `last_add_date_eventId` VARCHAR(255) NULL COMMENT 'The event ID of the most recent ADD_PASSED event',
    `last_remove_date` DATETIME NULL COMMENT 'The timestamp of the most recent REMOVE_PASSED event for this AP',
    `last_remove_date_eventId` VARCHAR(255) NULL COMMENT 'The event ID of the most recent REMOVE_PASSED event'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


USE `bundleBuilder`;

-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `CurrentRoleModel_RoleSimilarity`;

-- Create the CurrentRoleModel_RoleSimilarity table
CREATE TABLE `CurrentRoleModel_RoleSimilarity` (
    `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for this similarity record',
    
    `role1_id` VARCHAR(255) NOT NULL COMMENT 'ID of the first role (from CurrentRoleModel_Roles)',
    `role1_name` VARCHAR(255) NOT NULL COMMENT 'Name of the first role',
    
    `role2_id` VARCHAR(255) NOT NULL COMMENT 'ID of the second role (from CurrentRoleModel_Roles)',
    `role2_name` VARCHAR(255) NOT NULL COMMENT 'Name of the second role',
    
    `jaccard_score` DECIMAL(5, 4) NOT NULL COMMENT 'Jaccard similarity score between Role 1 and Role 2 (0.0000 to 1.0000)',
    
	 `ignored` BOOLEAN DEFAULT TRUE COMMENT 'Whether the Access Profile can be requested by users',
     `state` BOOLEAN DEFAULT TRUE COMMENT 'Whether the Access Profile can be requested by users',
    -- Flattened Owner fields (assuming owner is a single identity)
    `owner_id` VARCHAR(255) NULL COMMENT 'ID of the Identity that owns this Access Profile',
    `owner_name` VARCHAR(255) NULL COMMENT 'Name of the Identity that owns this Access Profile',
    `additionalOwners` JSON NULL COMMENT 'JSON array of additional Identities or Governance Groups that own this Access Profile',
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this similarity record was created',

    -- Ensures that each pair of roles is unique, regardless of order (e.g., (A,B) is same as (B,A))
    -- This constraint is typically handled by ensuring role1_id < role2_id at application level,
    -- but this unique index on LEAST/GREATEST provides database-level enforcement.
    CONSTRAINT `uq_role_pair_similarity` UNIQUE (`role1_id`, `role2_id`),

    -- Optional: Foreign key constraints to link to CurrentRoleModel_Roles table
    -- These assume CurrentRoleModel_Roles.id exists and is the primary key
    CONSTRAINT `fk_role_similarity_role1`
        FOREIGN KEY (`role1_id`) REFERENCES `CurrentRoleModel_Roles`(`id`)
        ON DELETE CASCADE, -- Or ON DELETE RESTRICT/SET NULL, depending on desired behavior
    CONSTRAINT `fk_role_similarity_role2`
        FOREIGN KEY (`role2_id`) REFERENCES `CurrentRoleModel_Roles`(`id`)
        ON DELETE CASCADE -- Or ON DELETE RESTRICT/SET NULL, depending on desired behavior
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `CurrentRoleModel_AccessProfileSimilarity`;

-- Create the CurrentRoleModel_AccessProfileSimilarity table
CREATE TABLE `CurrentRoleModel_AccessProfileSimilarity` (
    `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for this similarity record',
    
    `access_profile1_id` VARCHAR(255) NOT NULL COMMENT 'ID of the first role (from CurrentRoleModel_Roles)',
    `access_profile1_name` VARCHAR(255) NOT NULL COMMENT 'Name of the first role',
    
    `access_profile2_id` VARCHAR(255) NOT NULL COMMENT 'ID of the second role (from CurrentRoleModel_Roles)',
    `access_profile2_name` VARCHAR(255) NOT NULL COMMENT 'Name of the second role',
    
    `jaccard_score` DECIMAL(5, 4) NOT NULL COMMENT 'Jaccard similarity score between Role 1 and Role 2 (0.0000 to 1.0000)',
    
	 `ignored` BOOLEAN DEFAULT TRUE COMMENT 'Whether the Access Profile can be requested by users',
     `state` BOOLEAN DEFAULT TRUE COMMENT 'Whether the Access Profile can be requested by users',
    -- Flattened Owner fields (assuming owner is a single identity)
    `owner_id` VARCHAR(255) NULL COMMENT 'ID of the Identity that owns this Access Profile',

    `owner_name` VARCHAR(255) NULL COMMENT 'Name of the Identity that owns this Access Profile',
    `additionalOwners` JSON NULL COMMENT 'JSON array of additional Identities or Governance Groups that own this Access Profile',
    `source_id` VARCHAR(255) NULL COMMENT 'Dource ID of the single application Access Profile',
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this similarity record was created',

    -- Ensures that each pair of roles is unique, regardless of order (e.g., (A,B) is same as (B,A))
    -- This constraint is typically handled by ensuring role1_id < role2_id at application level,
    -- but this unique index on LEAST/GREATEST provides database-level enforcement.
    CONSTRAINT `uq_access_profile_pair_similarity` UNIQUE (`access_profile1_id`, `access_profile2_id`),

    -- Optional: Foreign key constraints to link to CurrentRoleModel_Roles table
    -- These assume CurrentRoleModel_Roles.id exists and is the primary key
    CONSTRAINT `fk_access_profile_similarity_role1`
        FOREIGN KEY (`access_profile1_id`) REFERENCES `CurrentRoleModel_AccessProfiles`(`id`)
        ON DELETE CASCADE, -- Or ON DELETE RESTRICT/SET NULL, depending on desired behavior
    CONSTRAINT `fk_access_profile_similarity_role2`
        FOREIGN KEY (`access_profile2_id`) REFERENCES `CurrentRoleModel_AccessProfiles`(`id`)
        ON DELETE CASCADE -- Or ON DELETE RESTRICT/SET NULL, depending on desired behavior
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- Optional: Add indexes for faster lookups on individual role IDs
CREATE INDEX `idx_crs_access_profile1_id` ON `CurrentRoleModel_AccessProfileSimilarity`(`access_profile1_id`);
CREATE INDEX `idx_crs_access_profile2_id` ON `CurrentRoleModel_AccessProfileSimilarity`(`access_profile2_id`);
CREATE INDEX `idx_crs_jaccard_score` ON `CurrentRoleModel_AccessProfileSimilarity`(`jaccard_score`);
CREATE INDEX `idx_crs_access_profile1_state` ON `CurrentRoleModel_AccessProfileSimilarity`(`state`);
CREATE INDEX `idx_crs_access_profile1_ignored` ON `CurrentRoleModel_AccessProfileSimilarity`(`ignored`);
CREATE INDEX `idx_crs_access_profile1_owner_id` ON `CurrentRoleModel_AccessProfileSimilarity`(`owner_id`);
CREATE INDEX `idx_crs_access_profile1_owner_name` ON `CurrentRoleModel_AccessProfileSimilarity`(`owner_name`);

-- Optional: Add indexes for frequently queried columns to improve performance
CREATE INDEX `idx_crs_state` ON `CurrentRoleModel_RoleSimilarity`(`state`);
CREATE INDEX `idx_crs_ignored` ON `CurrentRoleModel_RoleSimilarity`(`ignored`);
CREATE INDEX `idx_crs_owner_id` ON `CurrentRoleModel_RoleSimilarity`(`owner_id`);
CREATE INDEX `idx_crs_owner_name` ON `CurrentRoleModel_RoleSimilarity`(`owner_name`);
CREATE INDEX `idx_crs_role1_id` ON `CurrentRoleModel_RoleSimilarity`(`role1_id`);
CREATE INDEX `idx_crs_role2_id` ON `CurrentRoleModel_RoleSimilarity`(`role2_id`);
CREATE INDEX `idx_crs_jaccard_score` ON `CurrentRoleModel_RoleSimilarity`(`jaccard_score`);

-- Optional: Add indexes for faster lookups on common query fields
-- Note: Indexes on the full VARCHAR columns can still be beneficial for searches,
-- but a UNIQUE constraint on long VARCHAR combinations is what caused the issue.
-- MySQL might add warnings if an index on VARCHAR(255) is created without a prefix
-- if the combined length exceeds its internal limits, but it won't be an error.



-- Optional: Add an index for faster lookups on owner_name if frequently queried
CREATE INDEX `idx_entitlement_owner` ON `entitlements`(`owner_name`);

-- Optional: Add indexes for individual entitlement_name and source_name if they are often searched independently
CREATE INDEX `idx_entitlement_name` ON `entitlements`(`entitlement_name`);
CREATE INDEX `idx_source_name` ON `entitlements`(`source_name`);
-- Optional: Add indexes for frequently queried columns




-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `CurrentRoleModel_RoleEntitlements`;
CREATE TABLE `CurrentRoleModel_RoleEntitlements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `role_id` VARCHAR(255) NOT NULL,
    `role_name` VARCHAR(255) NOT NULL,
    `entitlement_id` VARCHAR(255) NOT NULL,
    `entitlement_name` VARCHAR(255) NOT NULL,
    `mapping_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this mapping was created',
    CONSTRAINT `fk_cre_role_id` FOREIGN KEY (`role_id`) REFERENCES `CurrentRoleModel_Roles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Optional: Add indexes for faster lookups
CREATE INDEX `idx_cre_role_id` ON `CurrentRoleModel_RoleEntitlements`(`role_id`);
CREATE INDEX `idx_cre_entitlement_id` ON `CurrentRoleModel_RoleEntitlements`(`entitlement_id`);


-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `CurrentRoleModel_AccessProfileEntitlements`;
CREATE TABLE `CurrentRoleModel_AccessProfileEntitlements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `access_profile_id` VARCHAR(255) NOT NULL,
    `access_profile_name` VARCHAR(255) NOT NULL,
    `entitlement_id` VARCHAR(255) NOT NULL,
    `entitlement_name` VARCHAR(255) NOT NULL,
    `mapping_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this mapping was created',
    CONSTRAINT `fk_cape_access_profile_id` FOREIGN KEY (`access_profile_id`) REFERENCES `CurrentRoleModel_AccessProfiles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- Optional: Add indexes for faster lookups
CREATE INDEX `idx_cape_access_profile_id` ON `CurrentRoleModel_AccessProfileEntitlements`(`access_profile_id`);
CREATE INDEX `idx_cape_entitlement_id` ON `CurrentRoleModel_AccessProfileEntitlements`(`entitlement_id`);

-- Create the CurrentRoleModel_AccessProfileEntitlements table

CREATE TABLE `CurrentRoleModel_RoleAccessProfiles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `role_id` VARCHAR(255) NOT NULL,
    `role_name` VARCHAR(255) NOT NULL,
    `access_profile_id` VARCHAR(255) NOT NULL,
    `access_profile_name` VARCHAR(255) NOT NULL,
	`mapping_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this mapping was created',
    CONSTRAINT `fk_crap_role_id` FOREIGN KEY (`role_id`) REFERENCES `CurrentRoleModel_Roles`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_crap_access_profile_id` FOREIGN KEY (`access_profile_id`) REFERENCES `CurrentRoleModel_AccessProfiles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Add indexes for faster lookups
CREATE INDEX `idx_crap_access_profile_id` ON `CurrentRoleModel_RoleAccessProfiles`(`access_profile_id`);
CREATE INDEX `idx_crap_role_id` ON `CurrentRoleModel_RoleAccessProfiles`(`role_id`);

-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `IdentityEffectiveEntitlements`;

-- Create the CurrentRoleModel_RoleEffectiveEntitlements table
CREATE TABLE `IdentityEffectiveEntitlements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for this effective entitlement record',
    
    `identity_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Idenity (from Identity_Attributes_Filtered)',
    `identity_name` VARCHAR(255) NOT NULL COMMENT 'Name UID of the Identity',
    
    `access_profile_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Access Profile (from CurrentRoleModel_AccessProfiles) through which the entitlement is granted',
    `access_profile_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Access Profile',
    
    `role_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Role(from CurrentRoleModel_Roles) through which the entitlement is granted',
    `role_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Role',
    
    `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Entitlement (from entitlements table) that is effectively granted',
    `entitlement_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Entitlement',
    
    `mapping_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this effective entitlement mapping was created',

    -- Ensures that a unique combination of Role -> Access Profile -> Entitlement is recorded only once
    CONSTRAINT `uq_iee_role_ap_entitlement_map` UNIQUE (`identity_id`,`access_profile_id`, `entitlement_id`),
CONSTRAINT `uq_iee2_role_ap_entitlement_map` UNIQUE (`identity_id`,`role_id`,  `entitlement_id`),

    -- Foreign key constraint to link to CurrentRoleModel_AccessProfiles table
    CONSTRAINT `fk_iee_ap_id`
        FOREIGN KEY (`access_profile_id`) REFERENCES `CurrentRoleModel_AccessProfiles`(`id`)
        ON DELETE CASCADE, -- If an access profile is deleted, remove its effective entitlement mappings

 -- Foreign key constraint to link to CurrentRoleModel_Roles table
    CONSTRAINT `fk_iee_r_id`
        FOREIGN KEY (`role_id`) REFERENCES `CurrentRoleModel_Roles`(`id`)
        ON DELETE CASCADE, -- If a role is deleted, remove its effective entitlement mappings

    -- Foreign key constraint to link to entitlements table
    CONSTRAINT `fk_iee_entitlement_id`
        FOREIGN KEY (`entitlement_id`) REFERENCES `entitlements`(`entitlement_id`)
        ON DELETE CASCADE -- If an entitlement is deleted, remove its effective entitlement mappings
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Drop the table if it already exists, for fresh creation (Optional)
DROP TABLE IF EXISTS `CurrentRoleModel_RoleEffectiveEntitlements`;




-- Create the CurrentRoleModel_RoleEffectiveEntitlements table
CREATE TABLE `CurrentRoleModel_RoleEffectiveEntitlements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT 'Unique identifier for this effective entitlement record',
    
    `role_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Role (from CurrentRoleModel_Roles)',
    `role_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Role',
    
    `access_profile_id` VARCHAR(255)  NULL COMMENT 'ID of the AP (NULL if entitlement is direct)',
    `access_profile_name` VARCHAR(255)  NULL COMMENT 'Name of the AP (NULL if entitlement is direct)',
    `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'The string ID of the Entitlement from SailPoint',
    
    `entitlement_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Entitlement',
    `mapping_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this effective entitlement mapping was created',

    -- Ensures that a unique combination of Role -> Access Profile -> Entitlement is recorded only once
    CONSTRAINT `uq_role_ap_entitlement_map` UNIQUE (`role_id`, `access_profile_id`, `entitlement_id`),

    -- Foreign key constraint to link to CurrentRoleModel_Roles table
    CONSTRAINT `fk_crree_role_id`
        FOREIGN KEY (`role_id`) REFERENCES `CurrentRoleModel_Roles`(`id`)
        ON DELETE CASCADE, -- If a role is deleted, remove its effective entitlement mappings

    -- Foreign key constraint to link to CurrentRoleModel_AccessProfiles table
    CONSTRAINT `fk_crree_ap_id`
        FOREIGN KEY (`access_profile_id`) REFERENCES `CurrentRoleModel_AccessProfiles`(`id`)
        ON DELETE CASCADE, -- If an access profile is deleted, remove its effective entitlement mappings

    -- Foreign key constraint to link to entitlements table
    CONSTRAINT `fk_crree_entitlement_id`
        FOREIGN KEY (`entitlement_id`) REFERENCES `entitlements`(`entitlement_id`)
        ON DELETE CASCADE -- If an entitlement is deleted, remove its effective entitlement mappings
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @constraint_name := (SELECT CONSTRAINT_NAME 
                         FROM information_schema.KEY_COLUMN_USAGE 
                         WHERE TABLE_SCHEMA = 'bundleBuilder' 
                           AND TABLE_NAME = 'CurrentRoleModel_RoleEffectiveEntitlements' 
                           AND COLUMN_NAME = 'entitlement_id' 
                           AND REFERENCED_TABLE_NAME = 'entitlements');
-- Optional: Add indexes for faster lookups on foreign keys and other frequently queried columns
CREATE INDEX `idx_crree_role_id` ON `CurrentRoleModel_RoleEffectiveEntitlements`(`role_id`);
CREATE INDEX `idx_crree_ap_id` ON `CurrentRoleModel_RoleEffectiveEntitlements`(`access_profile_id`);
CREATE INDEX `idx_crree_entitlement_id` ON `CurrentRoleModel_RoleEffectiveEntitlements`(`entitlement_id`);
CREATE INDEX `idx_crree_role_ap_id` ON `CurrentRoleModel_RoleEffectiveEntitlements`(`role_id`, `access_profile_id`); -- For queries joining roles and APs



-- Drop the table if it exists to ensure a clean slate for regeneration
DROP TABLE IF EXISTS `Analysis_Results`;

-- ===================================================================
-- A unified table to store all computed statistics and analysis results
-- ===================================================================
CREATE TABLE `Analysis_Results` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `stat_name` VARCHAR(255) NOT NULL COMMENT 'The name of the statistic (e.g., "Total Roles", "Top Assigned Roles")',
    `category` VARCHAR(255) NOT NULL COMMENT 'A grouping for the stat (e.g., "Inventory", "Population", "Role Mining")',
    
    -- Columns to hold the data, most stats will only use a few of these
    `value_1` VARCHAR(255) NULL COMMENT 'Primary item name (e.g., Role Name, Status Flag)',
    `value_2` VARCHAR(255) NULL COMMENT 'Secondary item name (for similarity pairs)',
    `numeric_value_1` BIGINT NULL COMMENT 'For counts, populations, etc.',
    `numeric_value_2` DECIMAL(5, 4) NULL COMMENT 'For scores like Jaccard similarity',
    
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When this record was last calculated'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add indexes for faster querying of the results
CREATE INDEX `idx_ar_stat_name` ON `Analysis_Results`(`stat_name`);
CREATE INDEX `idx_ar_category` ON `Analysis_Results`(`category`);


-- Drop the new table if it exists to ensure a clean slate
DROP TABLE IF EXISTS `Entitlement_Analysis_Profile`;

-- ===================================================================
-- A dedicated table to store a detailed statistical profile
-- for EACH entitlement in the catalog.
-- ===================================================================
CREATE TABLE `Entitlement_Analysis_Profile` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Link back to the original entitlement
    `entitlement_id` INT NOT NULL COMMENT 'Foreign key to the entitlements table',
    `entitlement_name` VARCHAR(255) NOT NULL COMMENT 'Denormalized for easy querying',
    `source_name` VARCHAR(255) NULL,
    
    -- Core Statistics
    `total_population` INT NOT NULL DEFAULT 0 COMMENT 'Total number of unique users with this entitlement',
    `count_direct` INT NOT NULL DEFAULT 0 COMMENT 'Count of assignments that are direct',
    `count_via_ap_only` INT NOT NULL DEFAULT 0 COMMENT 'Count of assignments via an AP, but not a role',
    `count_via_role` INT NOT NULL DEFAULT 0 COMMENT 'Count of assignments via a Role (either directly or through a nested AP)',
    
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add indexes for performance
CREATE UNIQUE INDEX `uq_eap_entitlement_id` ON `Entitlement_Analysis_Profile`(`entitlement_id`);
CREATE INDEX `idx_eap_entitlement_name` ON `Entitlement_Analysis_Profile`(`entitlement_name`);


-- Drop the table if it exists to ensure a clean slate
DROP TABLE IF EXISTS `AuditEventLog`;

-- ===================================================================
-- A table to store access change events (add/remove) from SailPoint
-- ===================================================================
CREATE TABLE `AuditEventLog` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Core event details
    `event_id` VARCHAR(255) NOT NULL COMMENT 'The unique ID of the event itself from SailPoint',
    `technical_name` VARCHAR(255) NOT NULL COMMENT 'e.g., ROLE_ADD_PASSED, ENTITLEMENT_REMOVE_PASSED',
    `created_datetime` DATETIME NOT NULL COMMENT 'When the event occurred (UTC)',
    
    -- Who performed the action
    `actor_id` VARCHAR(255) NULL,
    `actor_name` VARCHAR(255) NULL,
    
    -- Who was the action performed on
    `target_id` VARCHAR(255) NULL,
    `target_name` VARCHAR(255) NULL,
    
    -- Details of the object that was added or removed
    `object_id` VARCHAR(255) NULL,
    `object_name` VARCHAR(255) NULL,
    `object_type` VARCHAR(100) NULL,
    
    -- A place to store all other attributes for future analysis
    `attributes_json` JSON NULL,
    
    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add indexes for faster querying
CREATE UNIQUE INDEX `uq_ael_event_id` ON `AuditEventLog`(`event_id`);
CREATE INDEX `idx_ael_technical_name` ON `AuditEventLog`(`technical_name`);
CREATE INDEX `idx_ael_created` ON `AuditEventLog`(`created_datetime`);
CREATE INDEX `idx_ael_target_name` ON `AuditEventLog`(`target_name`);
CREATE INDEX `idx_ael_object_name` ON `AuditEventLog`(`object_name`);


-- Drop the new table if it exists to ensure a clean slate
DROP TABLE IF EXISTS `AuditEventLog_Attributes`;

-- ===================================================================
-- A table to store the individual key-value pairs from the 'attributes'
-- JSON object of an audit event.
-- ===================================================================
CREATE TABLE `AuditEventLog_Attributes` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Link back to the parent event
    `event_id` VARCHAR(255) NOT NULL COMMENT 'The unique ID of the parent event in AuditEventLog',
    
    -- The key-value pair
    `attribute_key` VARCHAR(255) NOT NULL COMMENT 'The name of the attribute (e.g., "access.id", "comment")',
    `attribute_value` TEXT NULL COMMENT 'The value of the attribute, stored as TEXT to be flexible',
    
    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add indexes for performance
CREATE INDEX `idx_aeattr_event_id` ON `AuditEventLog_Attributes`(`event_id`);
CREATE INDEX `idx_aeattr_key_value` ON `AuditEventLog_Attributes`(`attribute_key`, `attribute_value`(255));


-- ===================================================================
-- Optional but recommended: Remove the now-redundant JSON column
-- from the main event log table to save space and avoid confusion.
-- ===================================================================

-- Drop tables if they exist for a clean refresh
DROP TABLE IF EXISTS `Role_Audit_Profile`;
DROP TABLE IF EXISTS `Entitlement_Audit_Profile`;
DROP TABLE IF EXISTS `AccessProfile_Audit_Profile`; -- Added this line

-- ===================================================================
-- A table for Role audit profiles
-- ===================================================================
CREATE TABLE `Role_Audit_Profile` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `role_id` VARCHAR(255) NOT NULL,
    `role_name` VARCHAR(255) NOT NULL,
    `last_add_date` DATETIME NULL,
    `last_remove_date` DATETIME NULL,
    `adds_last_30_days` INT NOT NULL DEFAULT 0,
    `removes_last_30_days` INT NOT NULL DEFAULT 0,
    `adds_last_90_days` INT NOT NULL DEFAULT 0,
    `removes_last_90_days` INT NOT NULL DEFAULT 0,
    `adds_last_365_days` INT NOT NULL DEFAULT 0,
    `removes_last_365_days` INT NOT NULL DEFAULT 0,
    `total_adds` INT NOT NULL DEFAULT 0,
    `total_removes` INT NOT NULL DEFAULT 0,
    `median_assignment_duration_days` INT NULL,
    `currently_active_assignments` INT NOT NULL DEFAULT 0,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE UNIQUE INDEX `uq_rap_role_id` ON `Role_Audit_Profile`(`role_id`);

-- ===================================================================
-- A table for Entitlement audit profiles
-- ===================================================================
CREATE TABLE `Entitlement_Audit_Profile` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'Using the string ID from the API now',
    `entitlement_name` VARCHAR(255) NOT NULL,
    `last_add_date` DATETIME NULL,
    `last_remove_date` DATETIME NULL,
    `adds_last_30_days` INT NOT NULL DEFAULT 0,
    `removes_last_30_days` INT NOT NULL DEFAULT 0,
    `adds_last_90_days` INT NOT NULL DEFAULT 0,
    `removes_last_90_days` INT NOT NULL DEFAULT 0,
    `adds_last_365_days` INT NOT NULL DEFAULT 0,
    `removes_last_365_days` INT NOT NULL DEFAULT 0,
    `total_adds` INT NOT NULL DEFAULT 0,
    `total_removes` INT NOT NULL DEFAULT 0,
    `median_assignment_duration_days` INT NULL,
    `currently_active_assignments` INT NOT NULL DEFAULT 0,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE UNIQUE INDEX `uq_eap_entitlement_id` ON `Entitlement_Audit_Profile`(`entitlement_id`);

-- ===================================================================
-- NEW: A dedicated table for Access Profile audit profiles
-- ===================================================================
CREATE TABLE `AccessProfile_Audit_Profile` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `access_profile_id` VARCHAR(255) NOT NULL,
    `access_profile_name` VARCHAR(255) NOT NULL,
    `last_add_date` DATETIME NULL,
    `last_remove_date` DATETIME NULL,
    `adds_last_30_days` INT NOT NULL DEFAULT 0,
    `removes_last_30_days` INT NOT NULL DEFAULT 0,
    `adds_last_90_days` INT NOT NULL DEFAULT 0,
    `removes_last_90_days` INT NOT NULL DEFAULT 0,
    `adds_last_365_days` INT NOT NULL DEFAULT 0,
    `removes_last_365_days` INT NOT NULL DEFAULT 0,
    `total_adds` INT NOT NULL DEFAULT 0,
    `total_removes` INT NOT NULL DEFAULT 0,
    `median_assignment_duration_days` INT NULL,
    `currently_active_assignments` INT NOT NULL DEFAULT 0,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE UNIQUE INDEX `uq_apap_ap_id` ON `AccessProfile_Audit_Profile`(`access_profile_id`);



-- Drop tables if they exist to ensure a clean slate
DROP TABLE IF EXISTS `Identity_Accounts`;
DROP TABLE IF EXISTS `Identities`;

-- ===================================================================
-- 1. Create the main 'Identities' table to store the rich user data
-- ===================================================================
CREATE TABLE `Identities` (
    `id` VARCHAR(255) NOT NULL PRIMARY KEY COMMENT 'The unique ID of the identity from SailPoint',
    
    -- Basic Info
    `name` VARCHAR(255) NULL COMMENT 'The unique user name (UID)',
    `email` VARCHAR(255) NULL,
    `firstName` VARCHAR(255) NULL,
    `lastName` VARCHAR(255) NULL,
    `displayName` VARCHAR(255) NULL,
    `inactive` BOOLEAN NULL,
    `isManager` BOOLEAN NULL,
    `status` VARCHAR(100) NULL COMMENT 'e.g., active, inactive',
    `employeeNumber` VARCHAR(100) NULL,
    `created` DATETIME NULL COMMENT 'When the identity was created in SailPoint',
    `modified` DATETIME NULL COMMENT 'When the identity was last modified',
    `roleCount` INT NULL DEFAULT 0,
    `accessProfileCount` INT NULL DEFAULT 0,
    `entitlementCount` INT NULL DEFAULT 0,
    `accessCount` INT NULL DEFAULT 0,
    `accountCount` INT NULL DEFAULT 0,

    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add indexes for common search fields
CREATE INDEX `idx_identities_name` ON `Identities`(`name`);
CREATE INDEX `idx_identities_email` ON `Identities`(`email`);
CREATE INDEX `idx_identities_displayName` ON `Identities`(`displayName`);

CREATE TABLE `Identity_Attributes` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `identity_id` VARCHAR(255) NOT NULL,
    `attribute_name` VARCHAR(255) NOT NULL,
    `attribute_value` TEXT NULL, -- TEXT allows for longer values
    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- An identity should only have one value for a given attribute name
    CONSTRAINT `uq_identity_attribute` UNIQUE (`identity_id`, `attribute_name`),
    
    CONSTRAINT `fk_attribute_to_identity` FOREIGN KEY (`identity_id`) REFERENCES `Identities`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- Create the IdentityAttributes table


CREATE TABLE `Identity_Accounts` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `identity_id` VARCHAR(255) NOT NULL,
    `account_id` VARCHAR(255) NOT NULL,
    `account_name` VARCHAR(255) NULL,
    `native_identity` VARCHAR(255) NULL,
    `source_id` VARCHAR(255) NULL,
    `source_name` VARCHAR(255) NULL,
    `created` DATETIME NULL,
    `privileged` BOOLEAN NULL,
    CONSTRAINT `uq_ia_account_id` UNIQUE (`account_id`),
    CONSTRAINT `fk_account_to_identity` FOREIGN KEY (`identity_id`) REFERENCES `Identities`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Drop tables if they exist to ensure a clean slate
DROP TABLE IF EXISTS `IdentityRoleAssignments`;
DROP TABLE IF EXISTS `IdentityAccessProfileAssignments`;
DROP TABLE IF EXISTS `IdentityEntitlementAssignments`;

CREATE TABLE `IdentityRoleAssignments` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `identity_id` VARCHAR(255) NOT NULL COMMENT 'The ID of the assigned identity',
    `identity_name` VARCHAR(255) NOT NULL COMMENT 'The name/UID of the assigned identity',
    `role_id` VARCHAR(255) NOT NULL COMMENT 'The ID of the assigned role',
    `role_name` VARCHAR(255) NOT NULL COMMENT 'The name of the assigned role',
    `standalone` BOOLEAN NULL COMMENT 'The standalone flag from the access item',
    
    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensures a user can only be assigned a role once
    CONSTRAINT `uq_identity_role_assignment` UNIQUE (`identity_id`, `role_id`),
    
    -- Foreign keys to link back to the primary entity tables
    CONSTRAINT `fk_ira_identity_id` FOREIGN KEY (`identity_id`) REFERENCES `Identities`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_ira_role_id` FOREIGN KEY (`role_id`) REFERENCES `CurrentRoleModel_Roles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ===================================================================
-- 2. Table to map identities to their assigned access profiles
-- ===================================================================
CREATE TABLE `IdentityAccessProfileAssignments` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `identity_id` VARCHAR(255) NOT NULL,
    `identity_name` VARCHAR(255) NOT NULL,
    `access_profile_id` VARCHAR(255) NOT NULL,
    `access_profile_name` VARCHAR(255) NOT NULL,
    `standalone` BOOLEAN NULL,
    
    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT `uq_identity_ap_assignment` UNIQUE (`identity_id`, `access_profile_id`),
    
    CONSTRAINT `fk_iapa_identity_id` FOREIGN KEY (`identity_id`) REFERENCES `Identities`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_iapa_ap_id` FOREIGN KEY (`access_profile_id`) REFERENCES `CurrentRoleModel_AccessProfiles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ===================================================================
-- 3. Table to map identities to their assigned entitlements (direct only)
-- ===================================================================
CREATE TABLE `IdentityEntitlementAssignments` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `identity_id` VARCHAR(255) NOT NULL,
    `identity_name` VARCHAR(255) NOT NULL,
    `entitlement_id` VARCHAR(255) NOT NULL,
    `entitlement_name` VARCHAR(255) NOT NULL,
    `standalone` BOOLEAN NULL,

    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT `uq_identity_ent_assignment` UNIQUE (`identity_id`, `entitlement_id`),
    
    CONSTRAINT `fk_iea_identity_id` FOREIGN KEY (`identity_id`) REFERENCES `Identities`(`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_iea_entitlement_id` FOREIGN KEY (`entitlement_id`) REFERENCES `entitlements`(`entitlement_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add indexes for performance
CREATE UNIQUE INDEX `idx_ia_account_id` ON `Identity_Accounts`(`account_id`);
CREATE INDEX `idx_ia_identity_id` ON `Identity_Accounts`(`identity_id`);
CREATE INDEX `idx_ia_source_name` ON `Identity_Accounts`(`source_name`);
CREATE INDEX `idx_ia_native_identity` ON `Identity_Accounts`(`native_identity`);

DROP TABLE IF EXISTS 
    `Identity_Attributes_Filtered`,
    `Identity_Accounts_Filtered`,
    `IdentityRoleAssignments_Filtered`,
    `IdentityAccessProfileAssignments_Filtered`,
    `IdentityEffectiveEntitlements_Filtered`,
    `Identities_Filtered`;

-- ===================================================================
-- Create the new '_Filtered' tables
-- ===================================================================

CREATE TABLE `Identities_Filtered` LIKE `Identities`;
CREATE TABLE `Identity_Accounts_Filtered` LIKE `Identity_Accounts`;
CREATE TABLE `Identity_Attributes_Filtered` LIKE `Identity_Attributes`;
CREATE TABLE `IdentityRoleAssignments_Filtered` LIKE `IdentityRoleAssignments`;
CREATE TABLE `IdentityAccessProfileAssignments_Filtered` LIKE `IdentityAccessProfileAssignments`;

-- Note: Your DDL did not include a definition for IdentityEffectiveEntitlements, 
-- so I am creating a standard structure for it. Adjust if your original table is different.
CREATE TABLE `IdentityEffectiveEntitlements_Filtered` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `identity_id` VARCHAR(255) NOT NULL,
    `identity_name` VARCHAR(255) NULL,
    `role_id` VARCHAR(255) NULL,
    `role_name` VARCHAR(255) NULL,
    `access_profile_id` VARCHAR(255) NULL,
    `access_profile_name` VARCHAR(255) NULL,
    `entitlement_id` VARCHAR(255) NOT NULL,
    `entitlement_name` VARCHAR(255) NOT NULL,
    `load_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `uq_iee_filtered_map` UNIQUE (`identity_id`, `role_id`,`entitlement_id`),
    CONSTRAINT `uq_iee2_filtered_map` UNIQUE (`identity_id`, `access_profile_id`, `entitlement_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Use your database
USE `bundleBuilder`;

-- Drop tables if they exist to ensure a clean slate
DROP TABLE IF EXISTS `entitlement_exact_correlations`;
DROP TABLE IF EXISTS `entitlement_near_correlations`;

-- ===================================================================
-- 1. Table to store EXACT correlations (Jaccard = 1.0) between two entitlements
-- ===================================================================
CREATE TABLE `entitlement_exact_correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `entitlement_A_name` VARCHAR(255) NOT NULL,
    `entitlement_A_source` VARCHAR(255) NOT NULL,
    `entitlement_B_name` VARCHAR(255) NOT NULL,
    `entitlement_B_source` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL COMMENT 'The number of members in the identical sets',
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ===================================================================
-- 2. Table to store NEAR correlations (Jaccard >= threshold) between two entitlements
-- ===================================================================
CREATE TABLE `entitlement_near_correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `entitlement_A_name` VARCHAR(255) NOT NULL,
    `entitlement_A_source` VARCHAR(255) NOT NULL,
    `entitlement_B_name` VARCHAR(255) NOT NULL,
    `entitlement_B_source` VARCHAR(255) NOT NULL,
    `jaccard_score` DECIMAL(5, 4) NOT NULL,
    `population_A_size` INT NOT NULL,
    `population_B_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS `Attribute_Populations`;

CREATE TABLE `Attribute_Populations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `attribute_name` VARCHAR(255) NOT NULL COMMENT 'e.g., department, jobTitle',
    `attribute_value` TEXT NOT NULL COMMENT 'e.g., Sales, Manager',
    `population_size` INT NOT NULL DEFAULT 0,
    `last_calculated` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Ensure we only have one record per unique attribute/value pair
    CONSTRAINT `uq_attribute_value_pair` UNIQUE (`attribute_name`, `attribute_value`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Table 1: For EXACT (Jaccard = 1.0) correlations
DROP TABLE IF EXISTS `Entitlement_Exact_Correlations`;
CREATE TABLE `Entitlement_Exact_Correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `entitlement_A_id` INT NOT NULL,
    `entitlement_A_name` VARCHAR(255) NOT NULL,
    `entitlement_A_source` VARCHAR(255) NOT NULL,
    `entitlement_B_id` INT NOT NULL,
    `entitlement_B_name` VARCHAR(255) NOT NULL,
    `entitlement_B_source` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL COMMENT 'Since Jaccard is 1.0, populations are identical',
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `uq_ent_exact_pair` UNIQUE (`entitlement_A_id`, `entitlement_B_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 2: For NEAR (Jaccard < 1.0) correlations
DROP TABLE IF EXISTS `Entitlement_Near_Correlations`;
CREATE TABLE `Entitlement_Near_Correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `entitlement_A_id` INT NOT NULL,
    `entitlement_A_name` VARCHAR(255) NOT NULL,
    `entitlement_A_source` VARCHAR(255) NOT NULL,
    `entitlement_B_id` INT NOT NULL,
    `entitlement_B_name` VARCHAR(255) NOT NULL,
    `entitlement_B_source` VARCHAR(255) NOT NULL,
    `jaccard_score` DECIMAL(5, 4) NOT NULL,
    `population_A_size` INT NOT NULL,
    `population_B_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `uq_ent_near_pair` UNIQUE (`entitlement_A_id`, `entitlement_B_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `IdentityEntitlementAssignments_Filtered`
LIKE `IdentityEntitlementAssignments`;


-- Table 1: Stores the summary for each discovered community (potential role)
DROP TABLE IF EXISTS `Potential_Roles`;
CREATE TABLE `Potential_Roles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `community_id` INT NOT NULL COMMENT 'The ID assigned by the Louvain algorithm for a given run',
    `recommendation_score` DECIMAL(10, 4) NOT NULL COMMENT 'The calculated score for ranking roles',
    `avg_internal_jaccard` DECIMAL(5, 4) NOT NULL COMMENT 'The average Jaccard score of all connections within the community',
    `entitlement_count` INT NOT NULL COMMENT 'The number of entitlements in this role',
    `user_footprint` INT NOT NULL COMMENT 'The number of unique users affected by this role',
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 2: The mapping table linking roles to their entitlements
DROP TABLE IF EXISTS `Potential_Role_Entitlements`;
CREATE TABLE `Potential_Role_Entitlements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `potential_role_id` INT NOT NULL COMMENT 'Foreign key to the Potential_Roles table',
    `entitlement_id` INT NOT NULL COMMENT 'The database ID from the main entitlements table',
    `entitlement_name` VARCHAR(255) NOT NULL,
    `entitlement_source` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL,
    `internal_centrality_score` DECIMAL(10, 4) NOT NULL COMMENT 'The centrality of this entitlement within its community',
    
    -- Foreign key constraint to link back to the main community table
    CONSTRAINT `fk_pre_potential_role_id`
        FOREIGN KEY (`potential_role_id`) REFERENCES `Potential_Roles`(`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



-- Table 1: For EXACT (Jaccard = 1.0) correlations between attributes
DROP TABLE IF EXISTS `Attribute_Exact_Correlations`;
CREATE TABLE `Attribute_Exact_Correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `attribute_A_name` VARCHAR(255) NOT NULL,
    `attribute_A_value` VARCHAR(255) NOT NULL,
    `attribute_B_name` VARCHAR(255) NOT NULL,
    `attribute_B_value` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 2: For NEAR (Jaccard < 1.0) correlations between attributes
DROP TABLE IF EXISTS `Attribute_Near_Correlations`;
CREATE TABLE `Attribute_Near_Correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `attribute_A_name` VARCHAR(255) NOT NULL,
    `attribute_A_value` VARCHAR(255) NOT NULL,
    `attribute_B_name` VARCHAR(255) NOT NULL,
    `attribute_B_value` VARCHAR(255) NOT NULL,
    `jaccard_score` DECIMAL(5, 4) NOT NULL,
    `population_A_size` INT NOT NULL,
    `population_B_size` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Table 1: Stores the summary for each discovered attribute community (potential role)
DROP TABLE IF EXISTS `Potential_Attribute_Roles`;
CREATE TABLE `Potential_Attribute_Roles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `community_id` INT NOT NULL,
    `recommendation_score` DECIMAL(10, 4) NOT NULL,
    `avg_internal_jaccard` DECIMAL(5, 4) NOT NULL,
    `attribute_count` INT NOT NULL COMMENT 'The number of attributes in this role',
    `user_footprint` INT NOT NULL COMMENT 'The number of unique users who would have this role',
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table 2: The mapping table linking attribute roles to their member attributes
DROP TABLE IF EXISTS `Potential_Attribute_Role_Members`;
CREATE TABLE `Potential_Attribute_Role_Members` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `potential_attribute_role_id` INT NOT NULL COMMENT 'Foreign key to the Potential_Attribute_Roles table',
    `attribute_name` VARCHAR(255) NOT NULL,
    `attribute_value` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL,
    `internal_centrality_score` DECIMAL(10, 4) NOT NULL COMMENT 'The centrality of this attribute within its community',
    
    CONSTRAINT `fk_parm_potential_role_id`
        FOREIGN KEY (`potential_attribute_role_id`) REFERENCES `Potential_Attribute_Roles`(`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Use your database
USE `bundleBuilder`;

-- This table will store the direct Jaccard similarity between an entitlement and an attribute
DROP TABLE IF EXISTS `Entitlement_to_Attribute_Correlations`;
CREATE TABLE `Entitlement_to_Attribute_Correlations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `entitlement_id` INT NOT NULL COMMENT 'The DB ID from the entitlements table',
    `entitlement_name` VARCHAR(255) NOT NULL,
    `entitlement_source` VARCHAR(255) NOT NULL,
    `attribute_name` VARCHAR(255) NOT NULL,
    `attribute_value` VARCHAR(255) NOT NULL,
    `jaccard_score` DECIMAL(5, 4) NOT NULL,
    `entitlement_population` INT NOT NULL,
    `attribute_population` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure each entitlement-attribute pair is unique
    CONSTRAINT `uq_ent_attr_pair` UNIQUE (`entitlement_id`, `attribute_name`, `attribute_value`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Optional: Drop the table if it already exists to ensure a clean re-creation
DROP TABLE IF EXISTS `Entitlement_Attribute_Differing_UIDs`;

CREATE TABLE `Entitlement_Attribute_Differing_UIDs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Foreign key to link back to the main correlation table
    `correlation_id` INT NOT NULL COMMENT 'Foreign key to the Entitlement_to_Attribute_Correlations table',
    
    -- The user who is the exception
    `uid` VARCHAR(255) NOT NULL COMMENT 'The unique identifier of the user',
    
    -- Flags to indicate which group the user belongs to
    `is_in_attribute_only` BOOLEAN NOT NULL COMMENT 'True if the user has the attribute but not the entitlement',
    `is_in_entitlement_only` BOOLEAN NOT NULL COMMENT 'True if the user has the entitlement but not the attribute',
    
    -- Snapshot of user attributes at the time of analysis for context
    `type` VARCHAR(255) NULL,
    `is_manager` VARCHAR(255) NULL,
    `country` VARCHAR(255) NULL,
    `department` VARCHAR(255) NULL,
    `jobTitle` VARCHAR(255) NULL,
    `location` VARCHAR(255) NULL,
    
    -- Foreign Key Constraint for data integrity
    CONSTRAINT `fk_eadu_correlation_id`
        FOREIGN KEY (`correlation_id`) 
        REFERENCES `Entitlement_to_Attribute_Correlations`(`id`)
        ON DELETE CASCADE -- If the parent correlation is deleted, delete these exception records too
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Optional: Add indexes for faster lookups, which is highly recommended
CREATE INDEX `idx_eadu_correlation_id` ON `Entitlement_Attribute_Differing_UIDs`(`correlation_id`);
CREATE INDEX `idx_eadu_uid` ON `Entitlement_Attribute_Differing_UIDs`(`uid`);


DROP TABLE IF EXISTS `Unified_Role_Members`;
DROP TABLE IF EXISTS `Unified_Discovered_Roles`;

-- 1. Table to store the candidate role summary
CREATE TABLE `Unified_Discovered_Roles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `community_id` INT NOT NULL COMMENT 'Louvain partition ID',
    `role_name` VARCHAR(255) NOT NULL COMMENT 'Dynamic pluralized name, e.g., All Doctors',
    `role_type` VARCHAR(50) NOT NULL COMMENT 'Compound Attribute, Single Attribute, or Pure Entitlement',
    `primary_attribute_name` VARCHAR(255) NULL,
    `primary_attribute_value` VARCHAR(255) NULL,
    `assignment_rule` TEXT NULL COMMENT 'JSON or SQL representation of criteria',
    `avg_internal_jaccard` DECIMAL(5, 4) NOT NULL,
    `recommendation_score` DECIMAL(10, 4) NOT NULL,
    `entitlement_count` INT NOT NULL,
    `attribute_count` INT NOT NULL,
    `user_footprint` INT NOT NULL,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX `idx_udr_comm_id` ON `Unified_Discovered_Roles`(`community_id`);
CREATE INDEX `idx_udr_name` ON `Unified_Discovered_Roles`(`role_name`);

-- 2. Table to store every member node (both Entitlements and Attributes) inside each role
CREATE TABLE `Unified_Role_Members` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `role_id` INT NOT NULL,
    `community_id` INT NOT NULL,
    `node_type` ENUM('ENTITLEMENT', 'ATTRIBUTE') NOT NULL,
    `node_name` VARCHAR(255) NOT NULL,
    `node_attribute_name` VARCHAR(255) NULL COMMENT 'If attribute, the attribute key (e.g. jobTitle)',
    `node_attribute_value` VARCHAR(255) NULL COMMENT 'If attribute, the value (e.g. Doctor)',
    `source_system` VARCHAR(255) NULL COMMENT 'Application name or HRIS',
    `population_size` INT NOT NULL,
    `internal_centrality_score` DECIMAL(10, 4) NOT NULL,
    `is_primary_criteria` BOOLEAN DEFAULT FALSE,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `fk_urm_role_id` FOREIGN KEY (`role_id`) REFERENCES `Unified_Discovered_Roles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX `idx_urm_role_id` ON `Unified_Role_Members`(`role_id`);
CREATE INDEX `idx_urm_node_type` ON `Unified_Role_Members`(`node_type`);
CREATE INDEX `idx_urm_node_name` ON `Unified_Role_Members`(`node_name`);


-- 1. Graph Storage Tables
DROP TABLE IF EXISTS `Graph_Edges`;
DROP TABLE IF EXISTS `Graph_Nodes`;

CREATE TABLE `Graph_Nodes` (
    `node_id` VARCHAR(255) PRIMARY KEY,
    `node_type` ENUM('IDENTITY', 'ATTRIBUTE', 'ENTITLEMENT') NOT NULL,
    `display_label` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL DEFAULT 0,
    `created_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX `idx_gn_type` ON `Graph_Nodes`(`node_type`);

CREATE TABLE `Graph_Edges` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `source_node_id` VARCHAR(255) NOT NULL,
    `target_node_id` VARCHAR(255) NOT NULL,
    `relation_type` ENUM('HAS_ATTRIBUTE', 'HOLDS_ACCESS', 'CORRELATED_WITH') NOT NULL,
    `weight` DECIMAL(5, 4) NOT NULL DEFAULT 1.0000,
    `created_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT `uq_graph_edge` UNIQUE (`source_node_id`, `target_node_id`, `relation_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX `idx_ge_source` ON `Graph_Edges`(`source_node_id`);
CREATE INDEX `idx_ge_target` ON `Graph_Edges`(`target_node_id`);
CREATE INDEX `idx_ge_relation` ON `Graph_Edges`(`relation_type`);

-- 2. Discovered Compound Roles Storage Tables
DROP TABLE IF EXISTS `Tripartite_Role_Attributes`;
DROP TABLE IF EXISTS `Tripartite_Role_Entitlements`;
DROP TABLE IF EXISTS `Tripartite_Discovered_Roles`;

CREATE TABLE `Tripartite_Discovered_Roles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `role_name` VARCHAR(500) NOT NULL,
    `compound_criteria` TEXT NOT NULL COMMENT 'e.g. Country=USA AND Department=Finance AND UserType=Contractor',
    `attribute_count` INT NOT NULL,
    `entitlement_count` INT NOT NULL,
    `role_footprint` INT NOT NULL,
    `avg_coverage` DECIMAL(5, 4) NOT NULL COMMENT 'Recall: % of compound population holding access',
    `avg_purity` DECIMAL(5, 4) NOT NULL COMMENT 'Precision: % of access holders in compound population',
    `avg_jaccard` DECIMAL(5, 4) NOT NULL,
    `missing_identities_count` INT NOT NULL DEFAULT 0,
    `extra_identities_count` INT NOT NULL DEFAULT 0,
    `analysis_timestamp` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `Tripartite_Role_Entitlements` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `role_id` INT NOT NULL,
    `entitlement_name` VARCHAR(255) NOT NULL,
    `entitlement_population` INT NOT NULL,
    `coverage_score` DECIMAL(5, 4) NOT NULL,
    `purity_score` DECIMAL(5, 4) NOT NULL,
    `jaccard_score` DECIMAL(5, 4) NOT NULL,
    `status` ENUM('CORE', 'EVALUATE', 'OUTLIER') NOT NULL,
    CONSTRAINT `fk_tre_role_id` FOREIGN KEY (`role_id`) REFERENCES `Tripartite_Discovered_Roles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- Add unique constraint
ALTER TABLE `Tripartite_Role_Entitlements`
ADD CONSTRAINT `uq_role_entitlement` UNIQUE (`role_id`, `entitlement_name`);

CREATE TABLE `Tripartite_Role_Attributes` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `role_id` INT NOT NULL,
    `attribute_name` VARCHAR(255) NOT NULL,
    `attribute_value` VARCHAR(255) NOT NULL,
    `population_size` INT NOT NULL,
    CONSTRAINT `fk_tra_role_id` FOREIGN KEY (`role_id`) REFERENCES `Tripartite_Discovered_Roles`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



