import { sqliteTable,text,integer } from 'drizzle-orm/sqlite-core';
export const records=sqliteTable('studio_records',{id:text('id').primaryKey(),owner:text('owner').notNull(),kind:text('kind').notNull(),payload:text('payload').notNull(),createdAt:text('created_at').notNull()});
export const audit=sqliteTable('studio_audit',{id:text('id').primaryKey(),owner:text('owner').notNull(),action:text('action').notNull(),recordId:text('record_id').notNull(),at:text('at').notNull()});
export const invoiceCounters=sqliteTable('invoice_counters',{id:text('id').primaryKey(),owner:text('owner').notNull(),year:integer('year').notNull(),next:integer('next').notNull().default(1)});
export const appointmentSlots=sqliteTable('appointment_slots',{id:text('id').primaryKey(),owner:text('owner').notNull(),appointmentId:text('appointment_id').notNull()});

export const fileDeletions=sqliteTable('file_deletions',{key:text('key').primaryKey(),owner:text('owner').notNull()});
