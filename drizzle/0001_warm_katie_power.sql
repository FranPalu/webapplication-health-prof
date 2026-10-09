CREATE TABLE `appointment_slots` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`appointment_id` text NOT NULL
);
