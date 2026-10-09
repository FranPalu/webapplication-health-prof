CREATE TABLE `studio_audit` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`action` text NOT NULL,
	`record_id` text NOT NULL,
	`at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `invoice_counters` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`year` integer NOT NULL,
	`next` integer DEFAULT 1 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `studio_records` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`kind` text NOT NULL,
	`payload` text NOT NULL,
	`created_at` text NOT NULL
);
