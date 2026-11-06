-- Pokiza AI: faqat-o'qish MariaDB user (sql_query tool uchun)
-- Prod'da root bilan ishga tushiring. <DB_NAME> = site_config.json dagi db_name, <PAROL> = kuchli parol.
-- Keyin parolni "Pokiza AI Sozlamalari" -> "Read-only DB parol" maydoniga kiriting.

CREATE USER IF NOT EXISTS 'pokiza_ai_ro'@'localhost' IDENTIFIED BY '<PAROL>';
CREATE USER IF NOT EXISTS 'pokiza_ai_ro'@'127.0.0.1' IDENTIFIED BY '<PAROL>';
ALTER USER 'pokiza_ai_ro'@'localhost' WITH MAX_USER_CONNECTIONS 5;
ALTER USER 'pokiza_ai_ro'@'127.0.0.1' WITH MAX_USER_CONNECTIONS 5;

-- 1-qadam: GRANT buyruqlarini hosil qilish (natijasini nusxalab, 2-qadamda ishga tushiring).
-- Sezgir jadvallar (user, parol, sessiya, sozlamalar, loglar) ro'yxatdan chiqarilgan.
SELECT CONCAT('GRANT SELECT ON `', TABLE_SCHEMA, '`.`', TABLE_NAME, '` TO ''pokiza_ai_ro''@''', h.host, ''';') AS grant_sql
FROM information_schema.TABLES
JOIN (SELECT 'localhost' AS host UNION ALL SELECT '127.0.0.1') h
WHERE TABLE_SCHEMA = '<DB_NAME>'
  AND TABLE_NAME LIKE 'tab%'
  AND TABLE_NAME NOT IN (
    '__Auth',
    '__UserSettings',
    'tabAI Suhbat',
    'tabAI Xabar',
    'tabAccess Log',
    'tabActivity Log',
    'tabCommunication',
    'tabConnected App',
    'tabDefaultValue',
    'tabDeleted Document',
    'tabDropbox Settings',
    'tabEmail Account',
    'tabEmail Queue',
    'tabEmail Queue Recipient',
    'tabError Log',
    'tabGoogle Settings',
    'tabHas Role',
    'tabIntegration Request',
    'tabLDAP Settings',
    'tabOAuth Authorization Code',
    'tabOAuth Bearer Token',
    'tabOAuth Client',
    'tabPayment Gateway Account',
    'tabPokiza AI Sozlamalari',
    'tabPrepared Report',
    'tabS3 Backup Settings',
    'tabSMS Settings',
    'tabSessions',
    'tabSingles',
    'tabSocial Login Key',
    'tabSystem Settings',
    'tabTelegram Admin',
    'tabTelegram Bot Settings',
    'tabTelegram User',
    'tabToken Cache',
    'tabUser',
    'tabUser Permission',
    'tabVersion',
    'tabWebhook',
    'tabWebhook Request Log'
  );

-- 2-qadam: 1-qadam natijasidagi GRANT qatorlarini ishga tushiring, keyin:
FLUSH PRIVILEGES;

-- Tekshirish (pokiza_ai_ro bilan kirib):
--   SELECT COUNT(*) FROM `tabSales Invoice`;   -> ishlaydi
--   SELECT * FROM `tabUser` LIMIT 1;           -> SELECT command denied
--   UPDATE `tabItem` SET item_name = item_name WHERE 1 = 0;  -> UPDATE command denied
-- Yangi DocType qo'shilganda 1-2 qadamni qayta ishga tushiring.
