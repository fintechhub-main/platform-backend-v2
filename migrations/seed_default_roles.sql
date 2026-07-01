ALTER TABLE custom_roles ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO custom_roles (key, label, color, is_system) VALUES
  ('superadmin',        'Super Admin',      '#7c3aed', TRUE),
  ('admin',             'Admin',            '#2563eb', TRUE),
  ('manager',           'Menejer',          '#0891b2', TRUE),
  ('teacher',           'O''qituvchi',      '#16a34a', TRUE),
  ('assistant_teacher', 'Yordamchi ustoz',  '#0d9488', TRUE),
  ('cashier',           'Kassir',           '#d97706', TRUE),
  ('staff',             'Xodim',            '#475569', TRUE),
  ('student',           'Talaba',           '#6b7280', TRUE)
ON CONFLICT (key) DO UPDATE SET
  label     = EXCLUDED.label,
  color     = EXCLUDED.color,
  is_system = TRUE;
