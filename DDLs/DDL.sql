-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------
-- -----------------------------------------------------
-- Schema bundleBuilder
-- -----------------------------------------------------

-- -----------------------------------------------------
-- Schema bundleBuilder
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `bundleBuilder` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci ;
USE `bundleBuilder` ;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`AccessProfile_Audit_Profile`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`AccessProfile_Audit_Profile` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `access_profile_id` VARCHAR(255) NOT NULL,
  `access_profile_name` VARCHAR(255) NOT NULL,
  `last_add_date` DATETIME NULL DEFAULT NULL,
  `last_remove_date` DATETIME NULL DEFAULT NULL,
  `adds_last_30_days` INT NOT NULL DEFAULT '0',
  `removes_last_30_days` INT NOT NULL DEFAULT '0',
  `adds_last_90_days` INT NOT NULL DEFAULT '0',
  `removes_last_90_days` INT NOT NULL DEFAULT '0',
  `adds_last_365_days` INT NOT NULL DEFAULT '0',
  `removes_last_365_days` INT NOT NULL DEFAULT '0',
  `total_adds` INT NOT NULL DEFAULT '0',
  `total_removes` INT NOT NULL DEFAULT '0',
  `median_assignment_duration_days` INT NULL DEFAULT NULL,
  `currently_active_assignments` INT NOT NULL DEFAULT '0',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_apap_ap_id` (`access_profile_id` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Analysis_Results`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Analysis_Results` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `stat_name` VARCHAR(255) NOT NULL COMMENT 'The name of the statistic (e.g., \"Total Roles\", \"Top Assigned Roles\")',
  `category` VARCHAR(255) NOT NULL COMMENT 'A grouping for the stat (e.g., \"Inventory\", \"Population\", \"Role Mining\")',
  `value_1` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Primary item name (e.g., Role Name, Status Flag)',
  `value_2` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Secondary item name (for similarity pairs)',
  `numeric_value_1` BIGINT NULL DEFAULT NULL COMMENT 'For counts, populations, etc.',
  `numeric_value_2` DECIMAL(5,4) NULL DEFAULT NULL COMMENT 'For scores like Jaccard similarity',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'When this record was last calculated',
  PRIMARY KEY (`id`),
  INDEX `idx_ar_stat_name` (`stat_name` ASC) VISIBLE,
  INDEX `idx_ar_category` (`category` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 141
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`ApprovedRoleModel_AccessProfiles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`ApprovedRoleModel_AccessProfiles` (
  `id` VARCHAR(255) NOT NULL COMMENT 'Immutable IT Role ID, e.g., ITR-0001 or GUID',
  `name` VARCHAR(255) NOT NULL,
  `description` TEXT NULL DEFAULT NULL,
  `primary_source` VARCHAR(255) NOT NULL,
  `owner_id` VARCHAR(255) NULL DEFAULT NULL,
  `owner_name` VARCHAR(255) NULL DEFAULT NULL,
  `deploy_target` VARCHAR(50) NOT NULL DEFAULT 'BOTH',
  `status` VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
  `version_number` INT NOT NULL DEFAULT '1',
  `created_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  `last_modified_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `activated_timestamp` TIMESTAMP NULL DEFAULT NULL,
  `deactivated_timestamp` TIMESTAMP NULL DEFAULT NULL,
  `deleted_timestamp` TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_armap_status` (`status` ASC) VISIBLE,
  INDEX `idx_armap_source` (`primary_source` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`ApprovedRoleModel_AccessProfileEntitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`ApprovedRoleModel_AccessProfileEntitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `access_profile_id` VARCHAR(255) NOT NULL,
  `access_profile_name` VARCHAR(255) NOT NULL,
  `entitlement_id` VARCHAR(255) NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `source_id` VARCHAR(255) NULL DEFAULT NULL,
  `source_name` VARCHAR(255) NOT NULL,
  `added_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_arm_ape_ent` (`access_profile_id` ASC, `entitlement_id` ASC) VISIBLE,
  CONSTRAINT `fk_arm_ape_ap_id`
    FOREIGN KEY (`access_profile_id`)
    REFERENCES `bundleBuilder`.`ApprovedRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`ApprovedRoleModel_AuditLog`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`ApprovedRoleModel_AuditLog` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `event_id` VARCHAR(64) NOT NULL COMMENT 'UUID grouping batch publish changes',
  `entity_type` VARCHAR(50) NOT NULL COMMENT 'BUSINESS_ROLE, IT_ROLE, ROLE_ENTITLEMENT, AP_ENTITLEMENT',
  `entity_id` VARCHAR(255) NOT NULL COMMENT 'Role ID or Access Profile ID',
  `entity_name` VARCHAR(255) NOT NULL,
  `version_number` INT NOT NULL DEFAULT '1',
  `action_type` VARCHAR(50) NOT NULL COMMENT 'CREATE, UPDATE, ACTIVATE, DEACTIVATE, DELETE, ADD_ENTITLEMENT, REMOVE_ENTITLEMENT',
  `field_name` VARCHAR(100) NULL DEFAULT NULL COMMENT 'name, description, owner_id, assignment_rule, status, entitlement',
  `old_value` TEXT NULL DEFAULT NULL,
  `new_value` TEXT NULL DEFAULT NULL,
  `changed_by` VARCHAR(255) NOT NULL DEFAULT 'Admin / Role Miner Pipeline',
  `change_reason` VARCHAR(255) NULL DEFAULT NULL,
  `timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_arma_entity` (`entity_type` ASC, `entity_id` ASC) VISIBLE,
  INDEX `idx_arma_action` (`action_type` ASC) VISIBLE,
  INDEX `idx_arma_ver` (`version_number` ASC) VISIBLE,
  INDEX `idx_arma_time` (`timestamp` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`ApprovedRoleModel_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`ApprovedRoleModel_Roles` (
  `id` VARCHAR(255) NOT NULL COMMENT 'Immutable Role ID, e.g., BR-0001 or GUID',
  `name` VARCHAR(255) NOT NULL,
  `description` TEXT NULL DEFAULT NULL,
  `assignment_rule` TEXT NOT NULL,
  `owner_id` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Owner GUID',
  `owner_name` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Owner Full Name',
  `deploy_target` VARCHAR(50) NOT NULL DEFAULT 'BOTH' COMMENT 'BOTH, ISC_CLOUD, IIQ_ONPREM, SKIP',
  `status` VARCHAR(50) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE, DRAFT, DEACTIVATED, DELETED',
  `hierarchy_type` VARCHAR(50) NOT NULL DEFAULT 'STANDARD',
  `parent_role_id` VARCHAR(255) NULL DEFAULT NULL,
   `dimension_attribute` VARCHAR(255) NULL DEFAULT NULL,
   `dimension_value` VARCHAR(255) NULL DEFAULT NULL,
  `hierarchy_type` VARCHAR(50) NOT NULL DEFAULT 'STANDARD',
  `parent_role_id` VARCHAR(255) NULL DEFAULT NULL,
  `dimension_attribute` VARCHAR(255) NULL,
  `dimension_value` VARCHAR(255) NULL DEFAULT NULL,
  `version_number` INT NOT NULL DEFAULT '1',
  `target_population` INT NOT NULL DEFAULT '0',
  `created_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  `last_modified_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `activated_timestamp` TIMESTAMP NULL DEFAULT NULL,
  `deactivated_timestamp` TIMESTAMP NULL DEFAULT NULL,
  `deleted_timestamp` TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_armr_status` (`status` ASC) VISIBLE,
  INDEX `idx_armr_owner` (`owner_id` ASC) VISIBLE,
  INDEX `idx_armr_parent_id` (`parent_role_id` ASC) VISIBLE,
  INDEX `idx_armr_name` (`name` ASC) VISIBLE,
  INDEX `idx_armr_parent_id` (`parent_role_id` ASC))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`ApprovedRoleModel_RoleEntitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`ApprovedRoleModel_RoleEntitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` VARCHAR(255) NOT NULL,
  `role_name` VARCHAR(255) NOT NULL,
  `entitlement_id` VARCHAR(255) NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `source_id` VARCHAR(255) NULL DEFAULT NULL,
  `source_name` VARCHAR(255) NOT NULL,
  `match_type` VARCHAR(50) NOT NULL DEFAULT 'APPROVED_BIRTHRIGHT',
  `added_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_armre_role_ent` (`role_id` ASC, `entitlement_id` ASC) VISIBLE,
  CONSTRAINT `fk_armre_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`ApprovedRoleModel_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Attribute_Exact_Correlations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Attribute_Exact_Correlations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `attribute_A_name` VARCHAR(255) NOT NULL,
  `attribute_A_value` VARCHAR(255) NOT NULL,
  `attribute_B_name` VARCHAR(255) NOT NULL,
  `attribute_B_value` VARCHAR(255) NOT NULL,
  `population_size` INT NOT NULL,
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 181
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Attribute_Near_Correlations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Attribute_Near_Correlations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `attribute_A_name` VARCHAR(255) NOT NULL,
  `attribute_A_value` VARCHAR(255) NOT NULL,
  `attribute_B_name` VARCHAR(255) NOT NULL,
  `attribute_B_value` VARCHAR(255) NOT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL,
  `population_A_size` INT NOT NULL,
  `population_B_size` INT NOT NULL,
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 19
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Attribute_Populations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Attribute_Populations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `attribute_name` VARCHAR(255) NOT NULL COMMENT 'e.g., department, jobTitle',
  `attribute_value` TEXT NOT NULL COMMENT 'e.g., Sales, Manager',
  `population_size` INT NOT NULL DEFAULT '0',
  `last_calculated` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_attribute_value_pair` (`attribute_name` ASC, `attribute_value`(255) ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 2812
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`AuditEventLog`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`AuditEventLog` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `event_id` VARCHAR(255) NOT NULL COMMENT 'The unique ID of the event itself from SailPoint',
  `technical_name` VARCHAR(255) NOT NULL COMMENT 'e.g., ROLE_ADD_PASSED, ENTITLEMENT_REMOVE_PASSED',
  `created_datetime` DATETIME NOT NULL COMMENT 'When the event occurred (UTC)',
  `actor_id` VARCHAR(255) NULL DEFAULT NULL,
  `actor_name` VARCHAR(255) NULL DEFAULT NULL,
  `target_id` VARCHAR(255) NULL DEFAULT NULL,
  `target_name` VARCHAR(255) NULL DEFAULT NULL,
  `object_id` VARCHAR(255) NULL DEFAULT NULL,
  `object_name` VARCHAR(255) NULL DEFAULT NULL,
  `object_type` VARCHAR(100) NULL DEFAULT NULL,
  `attributes_json` JSON NULL DEFAULT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_ael_event_id` (`event_id` ASC) VISIBLE,
  INDEX `idx_ael_technical_name` (`technical_name` ASC) VISIBLE,
  INDEX `idx_ael_created` (`created_datetime` ASC) VISIBLE,
  INDEX `idx_ael_target_name` (`target_name` ASC) VISIBLE,
  INDEX `idx_ael_object_name` (`object_name` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 33
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`AuditEventLog_Attributes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`AuditEventLog_Attributes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `event_id` VARCHAR(255) NOT NULL COMMENT 'The unique ID of the parent event in AuditEventLog',
  `attribute_key` VARCHAR(255) NOT NULL COMMENT 'The name of the attribute (e.g., \"access.id\", \"comment\")',
  `attribute_value` TEXT NULL DEFAULT NULL COMMENT 'The value of the attribute, stored as TEXT to be flexible',
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_aeattr_event_id` (`event_id` ASC) VISIBLE,
  INDEX `idx_aeattr_key_value` (`attribute_key` ASC, `attribute_value`(255) ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 260
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_AccessProfiles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (
  `id` VARCHAR(255) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `description` TEXT NULL DEFAULT NULL,
  `enabled` TINYINT(1) NULL DEFAULT '1',
  `requestable` TINYINT(1) NULL DEFAULT '1',
  `owner_id` VARCHAR(255) NULL DEFAULT NULL,
  `owner_name` VARCHAR(255) NULL DEFAULT NULL,
  `source_id` VARCHAR(255) NULL DEFAULT NULL,
  `source_name` VARCHAR(255) NULL DEFAULT NULL,
  `created` DATETIME NULL DEFAULT NULL,
  `modified` DATETIME NULL DEFAULT NULL,
  `entitlements` JSON NULL DEFAULT NULL COMMENT 'JSON array of Entitlements included in this Access Profile',
  `segments` JSON NULL DEFAULT NULL COMMENT 'JSON array of segment IDs if the Access Profile is assigned to any segments',
  `provisioningCriteria` JSON NULL DEFAULT NULL COMMENT 'JSON object defining the provisioning criteria',
  `additionalOwners` JSON NULL DEFAULT NULL COMMENT 'JSON array of additional Identities or Governance Groups that own this Access Profile',
  `last_add_date` DATETIME NULL DEFAULT NULL COMMENT 'The timestamp of the most recent ADD_PASSED event for this AP',
  `last_add_date_eventId` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The event ID of the most recent ADD_PASSED event',
  `last_remove_date` DATETIME NULL DEFAULT NULL COMMENT 'The timestamp of the most recent REMOVE_PASSED event for this AP',
  `last_remove_date_eventId` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The event ID of the most recent REMOVE_PASSED event',
  PRIMARY KEY (`id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_AccessProfileEntitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_AccessProfileEntitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `access_profile_id` VARCHAR(255) NOT NULL,
  `access_profile_name` VARCHAR(255) NOT NULL,
  `entitlement_id` VARCHAR(255) NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `mapping_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this mapping was created',
  PRIMARY KEY (`id`),
  INDEX `idx_cape_access_profile_id` (`access_profile_id` ASC) VISIBLE,
  INDEX `idx_cape_entitlement_id` (`entitlement_id` ASC) VISIBLE,
  CONSTRAINT `fk_cape_access_profile_id`
    FOREIGN KEY (`access_profile_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 56
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_AccessProfileSimilarity`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_AccessProfileSimilarity` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for this similarity record',
  `access_profile1_id` VARCHAR(255) NOT NULL COMMENT 'ID of the first role (from CurrentRoleModel_Roles)',
  `access_profile1_name` VARCHAR(255) NOT NULL COMMENT 'Name of the first role',
  `access_profile2_id` VARCHAR(255) NOT NULL COMMENT 'ID of the second role (from CurrentRoleModel_Roles)',
  `access_profile2_name` VARCHAR(255) NOT NULL COMMENT 'Name of the second role',
  `jaccard_score` DECIMAL(5,4) NOT NULL COMMENT 'Jaccard similarity score between Role 1 and Role 2 (0.0000 to 1.0000)',
  `ignored` TINYINT(1) NULL DEFAULT '1' COMMENT 'Whether the Access Profile can be requested by users',
  `state` TINYINT(1) NULL DEFAULT '1' COMMENT 'Whether the Access Profile can be requested by users',
  `owner_id` VARCHAR(255) NULL DEFAULT NULL COMMENT 'ID of the Identity that owns this Access Profile',
  `owner_name` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Name of the Identity that owns this Access Profile',
  `additionalOwners` JSON NULL DEFAULT NULL COMMENT 'JSON array of additional Identities or Governance Groups that own this Access Profile',
  `source_id` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Dource ID of the single application Access Profile',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this similarity record was created',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_access_profile_pair_similarity` (`access_profile1_id` ASC, `access_profile2_id` ASC) VISIBLE,
  INDEX `idx_crs_access_profile1_id` (`access_profile1_id` ASC) VISIBLE,
  INDEX `idx_crs_access_profile2_id` (`access_profile2_id` ASC) VISIBLE,
  INDEX `idx_crs_jaccard_score` (`jaccard_score` ASC) VISIBLE,
  INDEX `idx_crs_access_profile1_state` (`state` ASC) VISIBLE,
  INDEX `idx_crs_access_profile1_ignored` (`ignored` ASC) VISIBLE,
  INDEX `idx_crs_access_profile1_owner_id` (`owner_id` ASC) VISIBLE,
  INDEX `idx_crs_access_profile1_owner_name` (`owner_name` ASC) VISIBLE,
  CONSTRAINT `fk_access_profile_similarity_role1`
    FOREIGN KEY (`access_profile1_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_access_profile_similarity_role2`
    FOREIGN KEY (`access_profile2_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_Roles` (
  `id` VARCHAR(255) NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `description` TEXT NULL DEFAULT NULL,
  `enabled` TINYINT(1) NULL DEFAULT '1',
  `requestable` TINYINT(1) NULL DEFAULT '1',
  `owner_id` VARCHAR(255) NULL DEFAULT NULL,
  `owner_name` VARCHAR(255) NULL DEFAULT NULL,
  `created` DATETIME NULL DEFAULT NULL,
  `modified` DATETIME NULL DEFAULT NULL,
  `last_add_date` DATETIME NULL DEFAULT NULL COMMENT 'The timestamp of the most recent ADD_PASSED event for this role',
  `last_add_date_eventId` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The event ID of the most recent ADD_PASSED event',
  `last_remove_date` DATETIME NULL DEFAULT NULL COMMENT 'The timestamp of the most recent REMOVE_PASSED event for this role',
  `last_remove_date_eventId` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The event ID of the most recent REMOVE_PASSED event',
  PRIMARY KEY (`id`),
  INDEX `idx_crmr_name` (`name` ASC) VISIBLE,
  INDEX `idx_crmr_enabled` (`enabled` ASC) VISIBLE,
  INDEX `idx_crmr_requestable` (`requestable` ASC) VISIBLE,
  INDEX `idx_crmr_owner_id` (`owner_id` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_RoleAccessProfiles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_RoleAccessProfiles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` VARCHAR(255) NOT NULL,
  `role_name` VARCHAR(255) NOT NULL,
  `access_profile_id` VARCHAR(255) NOT NULL,
  `access_profile_name` VARCHAR(255) NOT NULL,
  `mapping_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this mapping was created',
  PRIMARY KEY (`id`),
  INDEX `idx_crap_access_profile_id` (`access_profile_id` ASC) VISIBLE,
  INDEX `idx_crap_entitlement_id` (`role_id` ASC) VISIBLE,
  CONSTRAINT `fk_crap_access_profile_id`
    FOREIGN KEY (`access_profile_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_crap_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 21
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`entitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`entitlements` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto-incrementing integer PK',
  `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'The unique string ID from SailPoint',
  `entitlement_name` VARCHAR(255) NOT NULL,
  `source_name` VARCHAR(255) NULL DEFAULT NULL,
  `description` TEXT NULL DEFAULT NULL,
  `owner_name` VARCHAR(255) NULL DEFAULT NULL,
  `owner_id` VARCHAR(255) NULL DEFAULT NULL,
  `population_size` INT NOT NULL DEFAULT '0',
  `is_correlated` TINYINT(1) NOT NULL DEFAULT '0' COMMENT 'Flag to indicate if an exact (Jaccard=1.0) correlation has been found for this entitlement',
  `last_add_date` DATETIME NULL DEFAULT NULL COMMENT 'The timestamp of the most recent ADD_PASSED event for this entitlement',
  `last_add_date_eventId` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The event ID of the most recent ADD_PASSED event',
  `last_remove_date` DATETIME NULL DEFAULT NULL COMMENT 'The timestamp of the most recent REMOVE_PASSED event for this entitlement',
  `last_remove_date_eventId` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The event ID of the most recent REMOVE_PASSED event',
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this record was loaded into the database',
  `creation_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_entitlement_id` (`entitlement_id` ASC) VISIBLE,
  INDEX `idx_entitlements_is_correlated` (`is_correlated` ASC) VISIBLE,
  INDEX `idx_entitlement_owner` (`owner_name` ASC) VISIBLE,
  INDEX `idx_entitlement_name` (`entitlement_name` ASC) VISIBLE,
  INDEX `idx_source_name` (`source_name` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 53610
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_RoleEffectiveEntitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_RoleEffectiveEntitlements` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for this effective entitlement record',
  `role_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Role (from CurrentRoleModel_Roles)',
  `role_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Role',
  `access_profile_id` VARCHAR(255) NULL DEFAULT NULL COMMENT 'ID of the AP (NULL if entitlement is direct)',
  `access_profile_name` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Name of the AP (NULL if entitlement is direct)',
  `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'The string ID of the Entitlement from SailPoint',
  `entitlement_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Entitlement',
  `mapping_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this effective entitlement mapping was created',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_role_ap_entitlement_map` (`role_id` ASC, `access_profile_id` ASC, `entitlement_id` ASC) VISIBLE,
  INDEX `idx_crree_role_id` (`role_id` ASC) VISIBLE,
  INDEX `idx_crree_ap_id` (`access_profile_id` ASC) VISIBLE,
  INDEX `idx_crree_entitlement_id` (`entitlement_id` ASC) VISIBLE,
  INDEX `idx_crree_role_ap_id` (`role_id` ASC, `access_profile_id` ASC) VISIBLE,
  CONSTRAINT `fk_crree_ap_id`
    FOREIGN KEY (`access_profile_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_crree_entitlement_id`
    FOREIGN KEY (`entitlement_id`)
    REFERENCES `bundleBuilder`.`entitlements` (`entitlement_id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_crree_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 73
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_RoleEntitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_RoleEntitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` VARCHAR(255) NOT NULL,
  `role_name` VARCHAR(255) NOT NULL,
  `entitlement_id` VARCHAR(255) NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `mapping_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this mapping was created',
  PRIMARY KEY (`id`),
  INDEX `idx_cre_role_id` (`role_id` ASC) VISIBLE,
  INDEX `idx_cre_entitlement_id` (`entitlement_id` ASC) VISIBLE,
  CONSTRAINT `fk_cre_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 10
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`CurrentRoleModel_RoleSimilarity`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`CurrentRoleModel_RoleSimilarity` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for this similarity record',
  `role1_id` VARCHAR(255) NOT NULL COMMENT 'ID of the first role (from CurrentRoleModel_Roles)',
  `role1_name` VARCHAR(255) NOT NULL COMMENT 'Name of the first role',
  `role2_id` VARCHAR(255) NOT NULL COMMENT 'ID of the second role (from CurrentRoleModel_Roles)',
  `role2_name` VARCHAR(255) NOT NULL COMMENT 'Name of the second role',
  `jaccard_score` DECIMAL(5,4) NOT NULL COMMENT 'Jaccard similarity score between Role 1 and Role 2 (0.0000 to 1.0000)',
  `ignored` TINYINT(1) NULL DEFAULT '1' COMMENT 'Whether the Access Profile can be requested by users',
  `state` TINYINT(1) NULL DEFAULT '1' COMMENT 'Whether the Access Profile can be requested by users',
  `owner_id` VARCHAR(255) NULL DEFAULT NULL COMMENT 'ID of the Identity that owns this Access Profile',
  `owner_name` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Name of the Identity that owns this Access Profile',
  `additionalOwners` JSON NULL DEFAULT NULL COMMENT 'JSON array of additional Identities or Governance Groups that own this Access Profile',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this similarity record was created',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_role_pair_similarity` (`role1_id` ASC, `role2_id` ASC) VISIBLE,
  INDEX `idx_crs_state` (`state` ASC) VISIBLE,
  INDEX `idx_crs_ignored` (`ignored` ASC) VISIBLE,
  INDEX `idx_crs_owner_id` (`owner_id` ASC) VISIBLE,
  INDEX `idx_crs_owner_name` (`owner_name` ASC) VISIBLE,
  INDEX `idx_crs_role1_id` (`role1_id` ASC) VISIBLE,
  INDEX `idx_crs_role2_id` (`role2_id` ASC) VISIBLE,
  INDEX `idx_crs_jaccard_score` (`jaccard_score` ASC) VISIBLE,
  CONSTRAINT `fk_role_similarity_role1`
    FOREIGN KEY (`role1_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_Roles` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_role_similarity_role2`
    FOREIGN KEY (`role2_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Entitlement_Analysis_Profile`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Entitlement_Analysis_Profile` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entitlement_id` INT NOT NULL COMMENT 'Foreign key to the entitlements table',
  `entitlement_name` VARCHAR(255) NOT NULL COMMENT 'Denormalized for easy querying',
  `source_name` VARCHAR(255) NULL DEFAULT NULL,
  `total_population` INT NOT NULL DEFAULT '0' COMMENT 'Total number of unique users with this entitlement',
  `count_direct` INT NOT NULL DEFAULT '0' COMMENT 'Count of assignments that are direct',
  `count_via_ap_only` INT NOT NULL DEFAULT '0' COMMENT 'Count of assignments via an AP, but not a role',
  `count_via_role` INT NOT NULL DEFAULT '0' COMMENT 'Count of assignments via a Role (either directly or through a nested AP)',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_eap_entitlement_id` (`entitlement_id` ASC) VISIBLE,
  INDEX `idx_eap_entitlement_name` (`entitlement_name` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 53610
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Entitlement_to_Attribute_Correlations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Entitlement_to_Attribute_Correlations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entitlement_id` INT NOT NULL COMMENT 'The DB ID from the entitlements table',
  `entitlement_name` VARCHAR(255) NOT NULL,
  `entitlement_source` VARCHAR(255) NOT NULL,
  `attribute_name` VARCHAR(255) NOT NULL,
  `attribute_value` VARCHAR(255) NOT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL,
  `entitlement_population` INT NOT NULL,
  `attribute_population` INT NOT NULL,
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_ent_attr_pair` (`entitlement_id` ASC, `attribute_name` ASC, `attribute_value` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 166
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Entitlement_Attribute_Differing_UIDs`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Entitlement_Attribute_Differing_UIDs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `correlation_id` INT NOT NULL COMMENT 'Foreign key to the Entitlement_to_Attribute_Correlations table',
  `uid` VARCHAR(255) NOT NULL COMMENT 'The unique identifier of the user',
  `is_in_attribute_only` TINYINT(1) NOT NULL COMMENT 'True if the user has the attribute but not the entitlement',
  `is_in_entitlement_only` TINYINT(1) NOT NULL COMMENT 'True if the user has the entitlement but not the attribute',
  `type` VARCHAR(255) NULL DEFAULT NULL,
  `is_manager` VARCHAR(255) NULL DEFAULT NULL,
  `country` VARCHAR(255) NULL DEFAULT NULL,
  `department` VARCHAR(255) NULL DEFAULT NULL,
  `jobTitle` VARCHAR(255) NULL DEFAULT NULL,
  `location` VARCHAR(255) NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_eadu_correlation_id` (`correlation_id` ASC) VISIBLE,
  INDEX `idx_eadu_uid` (`uid` ASC) VISIBLE,
  CONSTRAINT `fk_eadu_correlation_id`
    FOREIGN KEY (`correlation_id`)
    REFERENCES `bundleBuilder`.`Entitlement_to_Attribute_Correlations` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Entitlement_Audit_Profile`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Entitlement_Audit_Profile` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'Using the string ID from the API now',
  `entitlement_name` VARCHAR(255) NOT NULL,
  `last_add_date` DATETIME NULL DEFAULT NULL,
  `last_remove_date` DATETIME NULL DEFAULT NULL,
  `adds_last_30_days` INT NOT NULL DEFAULT '0',
  `removes_last_30_days` INT NOT NULL DEFAULT '0',
  `adds_last_90_days` INT NOT NULL DEFAULT '0',
  `removes_last_90_days` INT NOT NULL DEFAULT '0',
  `adds_last_365_days` INT NOT NULL DEFAULT '0',
  `removes_last_365_days` INT NOT NULL DEFAULT '0',
  `total_adds` INT NOT NULL DEFAULT '0',
  `total_removes` INT NOT NULL DEFAULT '0',
  `median_assignment_duration_days` INT NULL DEFAULT NULL,
  `currently_active_assignments` INT NOT NULL DEFAULT '0',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_eap_entitlement_id` (`entitlement_id` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Entitlement_Exact_Correlations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Entitlement_Exact_Correlations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entitlement_A_id` INT NOT NULL,
  `entitlement_A_name` VARCHAR(255) NOT NULL,
  `entitlement_A_source` VARCHAR(255) NOT NULL,
  `entitlement_B_id` INT NOT NULL,
  `entitlement_B_name` VARCHAR(255) NOT NULL,
  `entitlement_B_source` VARCHAR(255) NOT NULL,
  `population_size` INT NOT NULL COMMENT 'Since Jaccard is 1.0, populations are identical',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_ent_exact_pair` (`entitlement_A_id` ASC, `entitlement_B_id` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 662
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Entitlement_Near_Correlations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Entitlement_Near_Correlations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entitlement_A_id` INT NOT NULL,
  `entitlement_A_name` VARCHAR(255) NOT NULL,
  `entitlement_A_source` VARCHAR(255) NOT NULL,
  `entitlement_B_id` INT NOT NULL,
  `entitlement_B_name` VARCHAR(255) NOT NULL,
  `entitlement_B_source` VARCHAR(255) NOT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL,
  `population_A_size` INT NOT NULL,
  `population_B_size` INT NOT NULL,
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_ent_near_pair` (`entitlement_A_id` ASC, `entitlement_B_id` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 115
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Fuzzy_Discovered_Rules`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Fuzzy_Discovered_Rules` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `entitlement_id` INT NULL DEFAULT NULL,
  `rule_rank` INT NOT NULL COMMENT '1 through 5',
  `rule_type` VARCHAR(50) NOT NULL COMMENT 'e.g., 2_WAY_OR, 3_WAY_AND',
  `rule_logic` TEXT NOT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL,
  `target_population` INT NOT NULL COMMENT 'How many users hold the entitlement',
  `rule_population` INT NOT NULL COMMENT 'How many users match the HR rule',
  `missing_users_count` INT NOT NULL COMMENT 'Has Entitlement, but fails HR rule',
  `extra_users_count` INT NOT NULL COMMENT 'Matches HR rule, but lacks Entitlement',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_fuzzy_ent_name` (`entitlement_name` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 4603
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Fuzzy_Entitlement_Correlations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Fuzzy_Entitlement_Correlations` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `entitlement_a_name` VARCHAR(255) NOT NULL,
  `entitlement_a_id` INT NULL DEFAULT NULL,
  `entitlement_b_name` VARCHAR(255) NOT NULL,
  `entitlement_b_id` INT NULL DEFAULT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL,
  `intersection_size` INT NOT NULL COMMENT 'Users who have BOTH',
  `union_size` INT NOT NULL COMMENT 'Users who have EITHER',
  `missing_b_count` INT NOT NULL COMMENT 'Users with A but missing B',
  `missing_a_count` INT NOT NULL COMMENT 'Users with B but missing A',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_fec_jaccard` (`jaccard_score` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 1639
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Fuzzy_Entitlement_Exceptions`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Fuzzy_Entitlement_Exceptions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `correlation_id` INT NOT NULL,
  `identity_id` VARCHAR(255) NOT NULL,
  `exception_type` VARCHAR(50) NOT NULL COMMENT '\'MISSING_A\' or \'MISSING_B\'',
  PRIMARY KEY (`id`),
  INDEX `fk_fee_corr_id` (`correlation_id` ASC) VISIBLE,
  CONSTRAINT `fk_fee_corr_id`
    FOREIGN KEY (`correlation_id`)
    REFERENCES `bundleBuilder`.`Fuzzy_Entitlement_Correlations` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 3331
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Fuzzy_Rule_Attributes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Fuzzy_Rule_Attributes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `rule_id` INT NOT NULL,
  `attribute_name` VARCHAR(255) NOT NULL,
  `attribute_value` TEXT NOT NULL,
  PRIMARY KEY (`id`),
  INDEX `fk_fra_rule_id` (`rule_id` ASC) VISIBLE,
  CONSTRAINT `fk_fra_rule_id`
    FOREIGN KEY (`rule_id`)
    REFERENCES `bundleBuilder`.`Fuzzy_Discovered_Rules` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 9448
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Fuzzy_Rule_Exceptions`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Fuzzy_Rule_Exceptions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `rule_id` INT NOT NULL,
  `identity_id` VARCHAR(255) NOT NULL,
  `exception_type` VARCHAR(50) NOT NULL COMMENT '\'MISSING_ACCESS\' or \'EXTRA_ACCESS\'',
  PRIMARY KEY (`id`),
  INDEX `fk_fre_rule_id` (`rule_id` ASC) VISIBLE,
  CONSTRAINT `fk_fre_rule_id`
    FOREIGN KEY (`rule_id`)
    REFERENCES `bundleBuilder`.`Fuzzy_Discovered_Rules` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 5616
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Graph_Edges`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Graph_Edges` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `source_node_id` VARCHAR(255) NOT NULL,
  `target_node_id` VARCHAR(255) NOT NULL,
  `relation_type` ENUM('HAS_ATTRIBUTE', 'HOLDS_ACCESS', 'CORRELATED_WITH') NOT NULL,
  `weight` DECIMAL(5,4) NOT NULL DEFAULT '1.0000',
  `created_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_graph_edge` (`source_node_id` ASC, `target_node_id` ASC, `relation_type` ASC) VISIBLE,
  INDEX `idx_ge_source` (`source_node_id` ASC) VISIBLE,
  INDEX `idx_ge_target` (`target_node_id` ASC) VISIBLE,
  INDEX `idx_ge_relation` (`relation_type` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 524707
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Graph_Nodes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Graph_Nodes` (
  `node_id` VARCHAR(255) NOT NULL,
  `node_type` ENUM('IDENTITY', 'ATTRIBUTE', 'ENTITLEMENT') NOT NULL,
  `display_label` VARCHAR(255) NOT NULL,
  `population_size` INT NOT NULL DEFAULT '0',
  `created_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`node_id`),
  INDEX `idx_gn_type` (`node_type` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Identities`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Identities` (
  `id` VARCHAR(255) NOT NULL COMMENT 'The unique ID of the identity from SailPoint',
  `name` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The unique user name (UID)',
  `email` VARCHAR(255) NULL DEFAULT NULL,
  `firstName` VARCHAR(255) NULL DEFAULT NULL,
  `lastName` VARCHAR(255) NULL DEFAULT NULL,
  `displayName` VARCHAR(255) NULL DEFAULT NULL,
  `inactive` TINYINT(1) NULL DEFAULT NULL,
  `isManager` TINYINT(1) NULL DEFAULT NULL,
  `status` VARCHAR(100) NULL DEFAULT NULL COMMENT 'e.g., active, inactive',
  `employeeNumber` VARCHAR(100) NULL DEFAULT NULL,
  `created` DATETIME NULL DEFAULT NULL COMMENT 'When the identity was created in SailPoint',
  `modified` DATETIME NULL DEFAULT NULL COMMENT 'When the identity was last modified',
  `roleCount` INT NULL DEFAULT '0',
  `accessProfileCount` INT NULL DEFAULT '0',
  `entitlementCount` INT NULL DEFAULT '0',
  `accessCount` INT NULL DEFAULT '0',
  `accountCount` INT NULL DEFAULT '0',
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_identities_name` (`name` ASC) VISIBLE,
  INDEX `idx_identities_email` (`email` ASC) VISIBLE,
  INDEX `idx_identities_displayName` (`displayName` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Identities_Filtered`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Identities_Filtered` (
  `id` VARCHAR(255) NOT NULL COMMENT 'The unique ID of the identity from SailPoint',
  `name` VARCHAR(255) NULL DEFAULT NULL COMMENT 'The unique user name (UID)',
  `email` VARCHAR(255) NULL DEFAULT NULL,
  `firstName` VARCHAR(255) NULL DEFAULT NULL,
  `lastName` VARCHAR(255) NULL DEFAULT NULL,
  `displayName` VARCHAR(255) NULL DEFAULT NULL,
  `inactive` TINYINT(1) NULL DEFAULT NULL,
  `isManager` TINYINT(1) NULL DEFAULT NULL,
  `status` VARCHAR(100) NULL DEFAULT NULL COMMENT 'e.g., active, inactive',
  `employeeNumber` VARCHAR(100) NULL DEFAULT NULL,
  `created` DATETIME NULL DEFAULT NULL COMMENT 'When the identity was created in SailPoint',
  `modified` DATETIME NULL DEFAULT NULL COMMENT 'When the identity was last modified',
  `roleCount` INT NULL DEFAULT '0',
  `accessProfileCount` INT NULL DEFAULT '0',
  `entitlementCount` INT NULL DEFAULT '0',
  `accessCount` INT NULL DEFAULT '0',
  `accountCount` INT NULL DEFAULT '0',
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_identities_name` (`name` ASC) VISIBLE,
  INDEX `idx_identities_email` (`email` ASC) VISIBLE,
  INDEX `idx_identities_displayName` (`displayName` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityAccessProfileAssignments`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityAccessProfileAssignments` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `identity_name` VARCHAR(255) NOT NULL,
  `access_profile_id` VARCHAR(255) NOT NULL,
  `access_profile_name` VARCHAR(255) NOT NULL,
  `standalone` TINYINT(1) NULL DEFAULT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_ap_assignment` (`identity_id` ASC, `access_profile_id` ASC) VISIBLE,
  INDEX `fk_iapa_ap_id` (`access_profile_id` ASC) VISIBLE,
  CONSTRAINT `fk_iapa_ap_id`
    FOREIGN KEY (`access_profile_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_iapa_identity_id`
    FOREIGN KEY (`identity_id`)
    REFERENCES `bundleBuilder`.`Identities` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 858
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityAccessProfileAssignments_Filtered`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityAccessProfileAssignments_Filtered` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `identity_name` VARCHAR(255) NOT NULL,
  `access_profile_id` VARCHAR(255) NOT NULL,
  `access_profile_name` VARCHAR(255) NOT NULL,
  `standalone` TINYINT(1) NULL DEFAULT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_ap_assignment` (`identity_id` ASC, `access_profile_id` ASC) VISIBLE,
  INDEX `fk_iapa_ap_id` (`access_profile_id` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 858
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityEffectiveEntitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityEffectiveEntitlements` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Unique identifier for this effective entitlement record',
  `identity_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Idenity (from Identity_Attributes_Filtered)',
  `identity_name` VARCHAR(255) NOT NULL COMMENT 'Name UID of the Identity',
  `access_profile_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Access Profile (from CurrentRoleModel_AccessProfiles) through which the entitlement is granted',
  `access_profile_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Access Profile',
  `role_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Role(from CurrentRoleModel_Roles) through which the entitlement is granted',
  `role_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Role',
  `entitlement_id` VARCHAR(255) NOT NULL COMMENT 'ID of the Entitlement (from entitlements table) that is effectively granted',
  `entitlement_name` VARCHAR(255) NOT NULL COMMENT 'Name of the Entitlement',
  `mapping_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Timestamp when this effective entitlement mapping was created',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_iee_role_ap_entitlement_map` (`identity_id` ASC, `access_profile_id` ASC, `entitlement_id` ASC) VISIBLE,
  UNIQUE INDEX `uq_iee2_role_ap_entitlement_map` (`identity_id` ASC, `role_id` ASC, `entitlement_id` ASC) VISIBLE,
  INDEX `fk_iee_ap_id` (`access_profile_id` ASC) VISIBLE,
  INDEX `fk_iee_r_id` (`role_id` ASC) VISIBLE,
  INDEX `fk_iee_entitlement_id` (`entitlement_id` ASC) VISIBLE,
  CONSTRAINT `fk_iee_ap_id`
    FOREIGN KEY (`access_profile_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_AccessProfiles` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_iee_entitlement_id`
    FOREIGN KEY (`entitlement_id`)
    REFERENCES `bundleBuilder`.`entitlements` (`entitlement_id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_iee_r_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 1253
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityEffectiveEntitlements_Filtered`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityEffectiveEntitlements_Filtered` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `identity_name` VARCHAR(255) NULL DEFAULT NULL,
  `role_id` VARCHAR(255) NULL DEFAULT NULL,
  `role_name` VARCHAR(255) NULL DEFAULT NULL,
  `access_profile_id` VARCHAR(255) NULL DEFAULT NULL,
  `access_profile_name` VARCHAR(255) NULL DEFAULT NULL,
  `entitlement_id` VARCHAR(255) NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_iee_filtered_map` (`identity_id` ASC, `role_id` ASC, `entitlement_id` ASC) VISIBLE,
  UNIQUE INDEX `uq_iee2_filtered_map` (`identity_id` ASC, `access_profile_id` ASC, `entitlement_id` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityEntitlementAssignments`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityEntitlementAssignments` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `identity_name` VARCHAR(255) NOT NULL,
  `entitlement_id` VARCHAR(255) NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `standalone` TINYINT(1) NULL DEFAULT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_ent_assignment` (`identity_id` ASC, `entitlement_id` ASC) VISIBLE,
  INDEX `fk_iea_entitlement_id` (`entitlement_id` ASC) VISIBLE,
  CONSTRAINT `fk_iea_entitlement_id`
    FOREIGN KEY (`entitlement_id`)
    REFERENCES `bundleBuilder`.`entitlements` (`entitlement_id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_iea_identity_id`
    FOREIGN KEY (`identity_id`)
    REFERENCES `bundleBuilder`.`Identities` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 7643
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityEntitlementAssignments_Filtered`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityEntitlementAssignments_Filtered` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `identity_name` VARCHAR(255) NOT NULL,
  `entitlement_id` VARCHAR(255) NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `standalone` TINYINT(1) NULL DEFAULT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_ent_assignment` (`identity_id` ASC, `entitlement_id` ASC) VISIBLE,
  INDEX `fk_iea_entitlement_id` (`entitlement_id` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 7608
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityRoleAssignments`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityRoleAssignments` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL COMMENT 'The ID of the assigned identity',
  `identity_name` VARCHAR(255) NOT NULL COMMENT 'The name/UID of the assigned identity',
  `role_id` VARCHAR(255) NOT NULL COMMENT 'The ID of the assigned role',
  `role_name` VARCHAR(255) NOT NULL COMMENT 'The name of the assigned role',
  `standalone` TINYINT(1) NULL DEFAULT NULL COMMENT 'The standalone flag from the access item',
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_role_assignment` (`identity_id` ASC, `role_id` ASC) VISIBLE,
  INDEX `fk_ira_role_id` (`role_id` ASC) VISIBLE,
  CONSTRAINT `fk_ira_identity_id`
    FOREIGN KEY (`identity_id`)
    REFERENCES `bundleBuilder`.`Identities` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_ira_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`CurrentRoleModel_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 308
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`IdentityRoleAssignments_Filtered`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`IdentityRoleAssignments_Filtered` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL COMMENT 'The ID of the assigned identity',
  `identity_name` VARCHAR(255) NOT NULL COMMENT 'The name/UID of the assigned identity',
  `role_id` VARCHAR(255) NOT NULL COMMENT 'The ID of the assigned role',
  `role_name` VARCHAR(255) NOT NULL COMMENT 'The name of the assigned role',
  `standalone` TINYINT(1) NULL DEFAULT NULL COMMENT 'The standalone flag from the access item',
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_role_assignment` (`identity_id` ASC, `role_id` ASC) VISIBLE,
  INDEX `fk_ira_role_id` (`role_id` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 308
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Identity_Accounts`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Identity_Accounts` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `account_id` VARCHAR(255) NOT NULL,
  `account_name` VARCHAR(255) NULL DEFAULT NULL,
  `native_identity` VARCHAR(255) NULL DEFAULT NULL,
  `source_id` VARCHAR(255) NULL DEFAULT NULL,
  `source_name` VARCHAR(255) NULL DEFAULT NULL,
  `created` DATETIME NULL DEFAULT NULL,
  `privileged` TINYINT(1) NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_ia_account_id` (`account_id` ASC) VISIBLE,
  UNIQUE INDEX `idx_ia_account_id` (`account_id` ASC) VISIBLE,
  INDEX `idx_ia_identity_id` (`identity_id` ASC) VISIBLE,
  INDEX `idx_ia_source_name` (`source_name` ASC) VISIBLE,
  INDEX `idx_ia_native_identity` (`native_identity` ASC) VISIBLE,
  CONSTRAINT `fk_account_to_identity`
    FOREIGN KEY (`identity_id`)
    REFERENCES `bundleBuilder`.`Identities` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 2668
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Identity_Accounts_Filtered`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Identity_Accounts_Filtered` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `account_id` VARCHAR(255) NOT NULL,
  `account_name` VARCHAR(255) NULL DEFAULT NULL,
  `native_identity` VARCHAR(255) NULL DEFAULT NULL,
  `source_id` VARCHAR(255) NULL DEFAULT NULL,
  `source_name` VARCHAR(255) NULL DEFAULT NULL,
  `created` DATETIME NULL DEFAULT NULL,
  `privileged` TINYINT(1) NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_ia_account_id` (`account_id` ASC) VISIBLE,
  UNIQUE INDEX `idx_ia_account_id` (`account_id` ASC) VISIBLE,
  INDEX `idx_ia_identity_id` (`identity_id` ASC) VISIBLE,
  INDEX `idx_ia_source_name` (`source_name` ASC) VISIBLE,
  INDEX `idx_ia_native_identity` (`native_identity` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 2639
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Identity_Attributes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Identity_Attributes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `attribute_name` VARCHAR(255) NOT NULL,
  `attribute_value` TEXT NULL DEFAULT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_attribute` (`identity_id` ASC, `attribute_name` ASC) VISIBLE,
  CONSTRAINT `fk_attribute_to_identity`
    FOREIGN KEY (`identity_id`)
    REFERENCES `bundleBuilder`.`Identities` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 7615
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Identity_Attributes_Filtered`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Identity_Attributes_Filtered` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `identity_id` VARCHAR(255) NOT NULL,
  `attribute_name` VARCHAR(255) NOT NULL,
  `attribute_value` TEXT NULL DEFAULT NULL,
  `load_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_identity_attribute` (`identity_id` ASC, `attribute_name` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 7490
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Potential_Attribute_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Potential_Attribute_Roles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `community_id` INT NOT NULL,
  `recommendation_score` DECIMAL(10,4) NOT NULL,
  `avg_internal_jaccard` DECIMAL(5,4) NOT NULL,
  `attribute_count` INT NOT NULL COMMENT 'The number of attributes in this role',
  `user_footprint` INT NOT NULL COMMENT 'The number of unique users who would have this role',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 27
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Potential_Attribute_Role_Members`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Potential_Attribute_Role_Members` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `potential_attribute_role_id` INT NOT NULL COMMENT 'Foreign key to the Potential_Attribute_Roles table',
  `attribute_name` VARCHAR(255) NOT NULL,
  `attribute_value` VARCHAR(255) NOT NULL,
  `population_size` INT NOT NULL,
  `internal_centrality_score` DECIMAL(10,4) NOT NULL COMMENT 'The centrality of this attribute within its community',
  PRIMARY KEY (`id`),
  INDEX `fk_parm_potential_role_id` (`potential_attribute_role_id` ASC) VISIBLE,
  CONSTRAINT `fk_parm_potential_role_id`
    FOREIGN KEY (`potential_attribute_role_id`)
    REFERENCES `bundleBuilder`.`Potential_Attribute_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 105
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Potential_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Potential_Roles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `community_id` INT NOT NULL COMMENT 'The ID assigned by the Louvain algorithm for a given run',
  `recommendation_score` DECIMAL(10,4) NOT NULL COMMENT 'The calculated score for ranking roles',
  `avg_internal_jaccard` DECIMAL(5,4) NOT NULL COMMENT 'The average Jaccard score of all connections within the community',
  `entitlement_count` INT NOT NULL COMMENT 'The number of entitlements in this role',
  `user_footprint` INT NOT NULL COMMENT 'The number of unique users affected by this role',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 90
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Potential_Role_Entitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Potential_Role_Entitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `potential_role_id` INT NOT NULL COMMENT 'Foreign key to the Potential_Roles table',
  `entitlement_id` INT NOT NULL COMMENT 'The database ID from the main entitlements table',
  `entitlement_name` VARCHAR(255) NOT NULL,
  `entitlement_source` VARCHAR(255) NOT NULL,
  `population_size` INT NOT NULL,
  `internal_centrality_score` DECIMAL(10,4) NOT NULL COMMENT 'The centrality of this entitlement within its community',
  PRIMARY KEY (`id`),
  INDEX `fk_pre_potential_role_id` (`potential_role_id` ASC) VISIBLE,
  CONSTRAINT `fk_pre_potential_role_id`
    FOREIGN KEY (`potential_role_id`)
    REFERENCES `bundleBuilder`.`Potential_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 300
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Role_Audit_Profile`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Role_Audit_Profile` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` VARCHAR(255) NOT NULL,
  `role_name` VARCHAR(255) NOT NULL,
  `last_add_date` DATETIME NULL DEFAULT NULL,
  `last_remove_date` DATETIME NULL DEFAULT NULL,
  `adds_last_30_days` INT NOT NULL DEFAULT '0',
  `removes_last_30_days` INT NOT NULL DEFAULT '0',
  `adds_last_90_days` INT NOT NULL DEFAULT '0',
  `removes_last_90_days` INT NOT NULL DEFAULT '0',
  `adds_last_365_days` INT NOT NULL DEFAULT '0',
  `removes_last_365_days` INT NOT NULL DEFAULT '0',
  `total_adds` INT NOT NULL DEFAULT '0',
  `total_removes` INT NOT NULL DEFAULT '0',
  `median_assignment_duration_days` INT NULL DEFAULT NULL,
  `currently_active_assignments` INT NOT NULL DEFAULT '0',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_rap_role_id` (`role_id` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Role_Entitlement_Exclusions`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Role_Entitlement_Exclusions` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_name` VARCHAR(255) NOT NULL COMMENT 'Target role display name or canonical role identifier',
  `entitlement_name` VARCHAR(255) NOT NULL COMMENT 'Declined entitlement name',
  `source_name` VARCHAR(255) NOT NULL COMMENT 'Application / Source system name in ISC',
  `declined_by` VARCHAR(255) NOT NULL COMMENT 'User GUID or name who rejected the suggestion',
  `decline_reason` TEXT NULL DEFAULT NULL COMMENT 'Business justification (e.g., SoD risk, excessive privilege, outlier access)',
  `decline_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  `is_permanent` TINYINT(1) NULL DEFAULT '1' COMMENT 'If FALSE, may be re-evaluated after expires_at',
  `expires_at` TIMESTAMP NULL DEFAULT NULL COMMENT 'Optional expiration date for temporary exclusions',
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_role_entitlement_exclusion` (`role_name` ASC, `entitlement_name` ASC, `source_name` ASC) VISIBLE,
  INDEX `idx_ree_lookup` (`role_name` ASC, `entitlement_name` ASC, `source_name` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_Discovered_Rules`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_Discovered_Rules` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `rule_type` VARCHAR(50) NOT NULL COMMENT 'e.g., SINGLE, 2_WAY_AND, SUGGESTED_AP',
  `rule_name` VARCHAR(500) NOT NULL,
  `rule_logic` TEXT NULL DEFAULT NULL,
  `population_size` INT NOT NULL,
  `entitlement_count` INT NOT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL DEFAULT '1.0000',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 6265
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_IT_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_IT_Roles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `it_role_name` VARCHAR(255) NOT NULL,
  `approval_status` VARCHAR(50) NOT NULL DEFAULT 'PENDING_REVIEW',
  `deploy_target` VARCHAR(50) NOT NULL DEFAULT 'BOTH',
  `approved_role_name` VARCHAR(255) NULL DEFAULT NULL,
  `owner_id` VARCHAR(255) NULL DEFAULT NULL,
  `owner_name` VARCHAR(255) NULL DEFAULT NULL,
  `primary_source` VARCHAR(255) NOT NULL,
  `description` TEXT NULL DEFAULT NULL,
  `entitlements_count` INT NOT NULL,
  `full_holders_count` INT NOT NULL COMMENT 'Users holding 100% of bundle',
  `partial_holders_count` INT NOT NULL COMMENT 'Users holding some but not all entitlements',
  `bundle_cohesion_score` DECIMAL(5,4) NOT NULL COMMENT 'Average internal Jaccard similarity',
  `admin_notes` TEXT NULL DEFAULT NULL,
  `role_type` VARCHAR(50) NOT NULL DEFAULT 'FUNCTIONAL_BUNDLE',
  `created_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  `reviewed_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_sitr_name` (`it_role_name` ASC) VISIBLE,
  INDEX `idx_sitr_approval` (`approval_status` ASC, `deploy_target` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 545
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_IT_Role_Entitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_IT_Role_Entitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `it_role_id` INT NOT NULL,
  `entitlement_id` INT NULL DEFAULT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `source_name` VARCHAR(255) NULL DEFAULT NULL,
  `assignment_count` INT NOT NULL DEFAULT '0',
  `already_in_role` TINYINT(1) NOT NULL DEFAULT '0',
  `is_included` TINYINT(1) NOT NULL DEFAULT '1',
  `admin_notes` TEXT NULL DEFAULT NULL,
  `reviewed_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `fk_sitr_ent_master` (`it_role_id` ASC) VISIBLE,
  INDEX `idx_sitre_included` (`is_included` ASC) VISIBLE,
  INDEX `idx_sitre_already` (`already_in_role` ASC) VISIBLE,
  CONSTRAINT `fk_sitr_ent_master`
    FOREIGN KEY (`it_role_id`)
    REFERENCES `bundleBuilder`.`Suggested_IT_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 1649
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_IT_Role_Identities`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_IT_Role_Identities` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `it_role_id` INT NOT NULL,
  `identity_id` VARCHAR(255) NOT NULL,
  `held_entitlements_count` INT NOT NULL,
  `coverage_percentage` DECIMAL(5,2) NOT NULL,
  `adoption_status` VARCHAR(50) NOT NULL COMMENT 'FULL_HOLDER (100%), PARTIAL_CANDIDATE (<100%)',
  PRIMARY KEY (`id`),
  INDEX `fk_sitr_id_master` (`it_role_id` ASC) VISIBLE,
  CONSTRAINT `fk_sitr_id_master`
    FOREIGN KEY (`it_role_id`)
    REFERENCES `bundleBuilder`.`Suggested_IT_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 15249
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_Roles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_name` VARCHAR(255) NOT NULL,
  `approval_status` VARCHAR(50) NOT NULL DEFAULT 'PENDING_REVIEW',
  `resolution_action` VARCHAR(50) NOT NULL DEFAULT 'KEEP_AS_SUGGESTED' COMMENT 'KEEP_AS_SUGGESTED, SEPARATE, MAKE_DYNAMIC, CERTIFY, IGNORE' AFTER `approval_status`,
   `hierarchy_type` VARCHAR(50) NOT NULL DEFAULT 'STANDARD' 
        COMMENT 'STANDARD, HIERARCHICAL_PARENT, DYNAMIC_PARENT, DYNAMIC_SUB_TIER' AFTER `resolution_action`,
   `parent_role_id` INT NULL DEFAULT NULL 
        COMMENT 'Self-referencing ID linking sub-dynamic tiers to their parent role' AFTER `hierarchy_type`,
   `dimension_attribute` VARCHAR(255) NULL DEFAULT NULL 
        COMMENT 'e.g., Job_Code for dynamic sub-tiers' AFTER `parent_role_id`,
    `dimension_value` VARCHAR(255) NULL DEFAULT NULL 
        COMMENT 'e.g., 1111 or 2222 for dynamic sub-tiers' AFTER `dimension_attribute`,
  `already_defined` TINYINT(1) NOT NULL DEFAULT '0',
  `deploy_target` VARCHAR(50) NOT NULL DEFAULT 'BOTH',
  `approved_role_name` VARCHAR(255) NULL DEFAULT NULL,
  `owner_id` VARCHAR(255) NULL DEFAULT NULL,
  `owner_name` VARCHAR(255) NULL DEFAULT NULL,
  `description` TEXT NULL DEFAULT NULL,
  `assignment_rule` TEXT NOT NULL,
  `target_population` INT NOT NULL COMMENT 'Total users matching the HR rule',
  `exact_entitlements_count` INT NOT NULL DEFAULT '0',
  `fuzzy_entitlements_count` INT NOT NULL DEFAULT '0',
  `total_entitlements_count` INT NOT NULL DEFAULT '0',
  `avg_jaccard_score` DECIMAL(5,4) NOT NULL DEFAULT '1.0000',
  `admin_notes` TEXT NULL DEFAULT NULL,
  `created_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  `reviewed_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_sr_name` (`role_name` ASC) VISIBLE,
  INDEX `idx_sr_approval` (`approval_status` ASC, `deploy_target` ASC) VISIBLE,
  INDEX `idx_sr_already_def` (`already_defined` ASC) VISIBLE)
  ADD INDEX `idx_sr_parent_id` (`parent_role_id` ASC),
    ADD INDEX `idx_sr_res_action` (`resolution_action` ASC)
ENGINE = InnoDB
AUTO_INCREMENT = 2317
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;

    




-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_Role_Entitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_Role_Entitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` INT NOT NULL,
  `entitlement_id` INT NULL DEFAULT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `source_name` VARCHAR(255) NULL DEFAULT NULL,
  `match_type` VARCHAR(50) NOT NULL COMMENT 'EXACT or FUZZY',
  `already_in_role` TINYINT(1) NOT NULL DEFAULT '0',
  `is_included` TINYINT(1) NOT NULL DEFAULT '1',
  `jaccard_score` DECIMAL(5,4) NOT NULL,
  `missing_users_count` INT NOT NULL DEFAULT '0',
  `extra_users_count` INT NOT NULL DEFAULT '0',
  `admin_notes` TEXT NULL DEFAULT NULL,
  `reviewed_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `fk_sre_role_master` (`role_id` ASC) VISIBLE,
  INDEX `idx_sre_included` (`is_included` ASC) VISIBLE,
  INDEX `idx_sre_already` (`already_in_role` ASC) VISIBLE,
  CONSTRAINT `fk_sre_role_master`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`Suggested_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 5020
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_Role_Identities`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_Role_Identities` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` INT NOT NULL,
  `identity_id` VARCHAR(255) NOT NULL,
  `status` VARCHAR(50) NOT NULL DEFAULT 'ELIGIBLE',
  PRIMARY KEY (`id`),
  INDEX `fk_sri_role_master` (`role_id` ASC) VISIBLE,
  CONSTRAINT `fk_sri_role_master`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`Suggested_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 9211
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_Rule_Attributes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_Rule_Attributes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `rule_id` INT NOT NULL,
  `attribute_name` VARCHAR(255) NOT NULL,
  `attribute_value` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`id`),
  INDEX `fk_sra_rule_id` (`rule_id` ASC) VISIBLE,
  CONSTRAINT `fk_sra_rule_id`
    FOREIGN KEY (`rule_id`)
    REFERENCES `bundleBuilder`.`Suggested_Discovered_Rules` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 7660
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_Rule_Entitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_Rule_Entitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `rule_id` INT NOT NULL,
  `entitlement_id` INT NOT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL DEFAULT '1.0000',
  PRIMARY KEY (`id`),
  INDEX `fk_sre_rule_id` (`rule_id` ASC) VISIBLE,
  INDEX `fk_sre_ent_id` (`entitlement_id` ASC) VISIBLE,
  CONSTRAINT `fk_sre_ent_id`
    FOREIGN KEY (`entitlement_id`)
    REFERENCES `bundleBuilder`.`entitlements` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_sre_rule_id`
    FOREIGN KEY (`rule_id`)
    REFERENCES `bundleBuilder`.`Suggested_Discovered_Rules` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 5492
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Suggested_Rule_Identities`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Suggested_Rule_Identities` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `rule_id` INT NOT NULL,
  `identity_id` VARCHAR(255) NOT NULL,
  PRIMARY KEY (`id`),
  INDEX `fk_sri_rule_id` (`rule_id` ASC) VISIBLE,
  CONSTRAINT `fk_sri_rule_id`
    FOREIGN KEY (`rule_id`)
    REFERENCES `bundleBuilder`.`Suggested_Discovered_Rules` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 26905
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Tripartite_Discovered_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Tripartite_Discovered_Roles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_name` VARCHAR(500) NOT NULL,
  `compound_criteria` TEXT NOT NULL COMMENT 'e.g. Country=USA AND Department=Finance AND UserType=Contractor',
  `attribute_count` INT NOT NULL,
  `entitlement_count` INT NOT NULL,
  `role_footprint` INT NOT NULL,
  `avg_coverage` DECIMAL(5,4) NOT NULL COMMENT 'Recall: % of compound population holding access',
  `avg_purity` DECIMAL(5,4) NOT NULL COMMENT 'Precision: % of access holders in compound population',
  `avg_jaccard` DECIMAL(5,4) NOT NULL,
  `missing_identities_count` INT NOT NULL DEFAULT '0',
  `extra_identities_count` INT NOT NULL DEFAULT '0',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`))
ENGINE = InnoDB
AUTO_INCREMENT = 978
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Tripartite_Role_Attributes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Tripartite_Role_Attributes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` INT NOT NULL,
  `attribute_name` VARCHAR(255) NOT NULL,
  `attribute_value` VARCHAR(255) NOT NULL,
  `population_size` INT NOT NULL,
  PRIMARY KEY (`id`),
  INDEX `fk_tra_role_id` (`role_id` ASC) VISIBLE,
  CONSTRAINT `fk_tra_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`Tripartite_Discovered_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 10148
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Tripartite_Role_Entitlements`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Tripartite_Role_Entitlements` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` INT NOT NULL,
  `entitlement_name` VARCHAR(255) NOT NULL,
  `entitlement_population` INT NOT NULL,
  `coverage_score` DECIMAL(5,4) NOT NULL,
  `purity_score` DECIMAL(5,4) NOT NULL,
  `jaccard_score` DECIMAL(5,4) NOT NULL,
  `status` ENUM('CORE', 'EVALUATE', 'OUTLIER') NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE INDEX `uq_role_entitlement` (`role_id` ASC, `entitlement_name` ASC) VISIBLE,
  CONSTRAINT `fk_tre_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`Tripartite_Discovered_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 2935
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Unified_Discovered_Roles`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Unified_Discovered_Roles` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `community_id` INT NOT NULL COMMENT 'Louvain partition ID',
  `role_name` VARCHAR(255) NOT NULL COMMENT 'Dynamic pluralized name, e.g., All Doctors',
  `role_type` VARCHAR(50) NOT NULL COMMENT 'Compound Attribute, Single Attribute, or Pure Entitlement',
  `primary_attribute_name` VARCHAR(255) NULL DEFAULT NULL,
  `primary_attribute_value` VARCHAR(255) NULL DEFAULT NULL,
  `assignment_rule` TEXT NULL DEFAULT NULL COMMENT 'JSON or SQL representation of criteria',
  `avg_internal_jaccard` DECIMAL(5,4) NOT NULL,
  `recommendation_score` DECIMAL(10,4) NOT NULL,
  `entitlement_count` INT NOT NULL,
  `attribute_count` INT NOT NULL,
  `user_footprint` INT NOT NULL,
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_udr_comm_id` (`community_id` ASC) VISIBLE,
  INDEX `idx_udr_name` (`role_name` ASC) VISIBLE)
ENGINE = InnoDB
AUTO_INCREMENT = 241
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


-- -----------------------------------------------------
-- Table `bundleBuilder`.`Unified_Role_Members`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `bundleBuilder`.`Unified_Role_Members` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `role_id` INT NOT NULL,
  `community_id` INT NOT NULL,
  `node_type` ENUM('ENTITLEMENT', 'ATTRIBUTE') NOT NULL,
  `node_name` VARCHAR(255) NOT NULL,
  `node_attribute_name` VARCHAR(255) NULL DEFAULT NULL COMMENT 'If attribute, the attribute key (e.g. jobTitle)',
  `node_attribute_value` VARCHAR(255) NULL DEFAULT NULL COMMENT 'If attribute, the value (e.g. Doctor)',
  `source_system` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Application name or HRIS',
  `population_size` INT NOT NULL,
  `internal_centrality_score` DECIMAL(10,4) NOT NULL,
  `is_primary_criteria` TINYINT(1) NULL DEFAULT '0',
  `analysis_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_urm_role_id` (`role_id` ASC) VISIBLE,
  INDEX `idx_urm_node_type` (`node_type` ASC) VISIBLE,
  INDEX `idx_urm_node_name` (`node_name` ASC) VISIBLE,
  CONSTRAINT `fk_urm_role_id`
    FOREIGN KEY (`role_id`)
    REFERENCES `bundleBuilder`.`Unified_Discovered_Roles` (`id`)
    ON DELETE CASCADE)
ENGINE = InnoDB
AUTO_INCREMENT = 1573
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_unicode_ci;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;

USE `bundleBuilder`;

-- 1. Add Hierarchy & Dynamic Tier columns to Suggested_Roles
ALTER TABLE `Suggested_Roles`
    ADD COLUMN `resolution_action` VARCHAR(50) NOT NULL DEFAULT 'KEEP_AS_SUGGESTED' 
        COMMENT 'KEEP_AS_SUGGESTED, SEPARATE, MAKE_DYNAMIC, CERTIFY, IGNORE' AFTER `approval_status`,
    ADD COLUMN `hierarchy_type` VARCHAR(50) NOT NULL DEFAULT 'STANDARD' 
        COMMENT 'STANDARD, HIERARCHICAL_PARENT, DYNAMIC_PARENT, DYNAMIC_SUB_TIER' AFTER `resolution_action`,
    ADD COLUMN `parent_role_id` INT NULL DEFAULT NULL 
        COMMENT 'Self-referencing FK pointing sub-dynamic tiers to their parent role' AFTER `hierarchy_type`,
    ADD COLUMN `dimension_attribute` VARCHAR(255) NULL DEFAULT NULL 
        COMMENT 'e.g., Job_Code for dynamic sub-tiers' AFTER `parent_role_id`,
    ADD COLUMN `dimension_value` VARCHAR(255) NULL DEFAULT NULL 
        COMMENT 'e.g., 1111 or 2222 for dynamic sub-tiers' AFTER `dimension_attribute`,
    ADD INDEX `idx_sr_parent_id` (`parent_role_id` ASC);



-- 3. Persistent suppression table for Option 5 (IGNORE)
CREATE TABLE IF NOT EXISTS `Ignored_Suggested_Roles` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `assignment_rule_signature` VARCHAR(500) NOT NULL COMMENT 'Canonical rule string e.g. Job_Code IN (1111, 2222)',
    `role_name` VARCHAR(255) NOT NULL,
    `ignored_by` VARCHAR(255) NOT NULL DEFAULT 'Admin Reviewer',
    `ignore_reason` TEXT NULL DEFAULT NULL,
    `ignored_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uq_ignored_rule_sig` (`assignment_rule_signature` ASC)
) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci;


-- 3. Persistent Suppression Table for IGNORED and SEPARATED Roles (with Reviewer Comment)
CREATE TABLE IF NOT EXISTS `Ignored_Suggested_Roles` (
    `id` INT NOT NULL AUTO_INCREMENT,
    `assignment_rule_signature` VARCHAR(500) NOT NULL COMMENT 'Canonical rule string e.g. Job_Code IN (1111, 2222)',
    `role_name` VARCHAR(255) NOT NULL COMMENT 'Suggested role name at the time of suppression',
    `resolution_type` VARCHAR(50) NOT NULL DEFAULT 'IGNORED' COMMENT 'IGNORED or SEPARATED',
    `ignored_by` VARCHAR(255) NOT NULL DEFAULT 'Admin Reviewer' COMMENT 'Reviewer or Owner who made the decision',
    `ignore_reason` TEXT NULL DEFAULT NULL COMMENT 'Reviewer comment detailing why the role was ignored or separated',
    `ignored_timestamp` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uq_ignored_rule_sig` (`assignment_rule_signature` ASC),
    INDEX `idx_isr_role_name` (`role_name` ASC),
    INDEX `idx_isr_type` (`resolution_type` ASC)
) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
