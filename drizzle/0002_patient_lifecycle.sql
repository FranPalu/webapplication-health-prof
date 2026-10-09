-- Protect records during concurrent patient removal and child creation.
CREATE TABLE file_deletions (key TEXT PRIMARY KEY NOT NULL, owner TEXT NOT NULL);
--> statement-breakpoint
CREATE TRIGGER patient_delete_files BEFORE DELETE ON studio_records WHEN OLD.kind='patients'
BEGIN
 SELECT CASE WHEN EXISTS(SELECT 1 FROM studio_records WHERE owner=OLD.owner AND kind='invoices' AND json_extract(payload,'$.patientId')=OLD.id AND json_extract(payload,'$.status')!='Bozza') THEN RAISE(ABORT,'PATIENT_HAS_ISSUED_INVOICES') END;
 SELECT CASE WHEN EXISTS(SELECT 1 FROM studio_records WHERE owner=OLD.owner AND kind='messages' AND json_extract(payload,'$.patientId')=OLD.id AND json_extract(payload,'$.status')='In elaborazione') THEN RAISE(ABORT,'PATIENT_HAS_PENDING_SENDS') END;
 INSERT OR IGNORE INTO file_deletions(key,owner) SELECT json_extract(payload,'$.key'),owner FROM studio_records WHERE owner=OLD.owner AND kind='documents' AND json_extract(payload,'$.patientId')=OLD.id;
 DELETE FROM appointment_slots WHERE owner=OLD.owner AND appointment_id IN (SELECT id FROM studio_records WHERE owner=OLD.owner AND kind='appointments' AND json_extract(payload,'$.patientId')=OLD.id);
 DELETE FROM studio_records WHERE owner=OLD.owner AND kind IN ('appointments','documents','invoices','messages') AND json_extract(payload,'$.patientId')=OLD.id;
END;
--> statement-breakpoint
CREATE TRIGGER patient_reference_insert BEFORE INSERT ON studio_records
WHEN NEW.kind IN ('appointments','documents','invoices','messages') AND NOT EXISTS(SELECT 1 FROM studio_records WHERE owner=NEW.owner AND id=json_extract(NEW.payload,'$.patientId') AND kind='patients')
BEGIN SELECT RAISE(ABORT,'PATIENT_NOT_FOUND'); END;
--> statement-breakpoint
CREATE TRIGGER patient_reference_update BEFORE UPDATE OF payload ON studio_records
WHEN NEW.kind IN ('appointments','documents','invoices','messages') AND NOT EXISTS(SELECT 1 FROM studio_records WHERE owner=NEW.owner AND id=json_extract(NEW.payload,'$.patientId') AND kind='patients')
BEGIN SELECT RAISE(ABORT,'PATIENT_NOT_FOUND'); END;
