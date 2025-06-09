-- SQL скрипт для создания базы данных SolSpider
-- Выполните этот скрипт от имени root пользователя MySQL

-- Создание базы данных
CREATE DATABASE IF NOT EXISTS solspider 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

-- Создание пользователя (замените 'your_password' на сильный пароль)
CREATE USER IF NOT EXISTS 'solspider'@'localhost' IDENTIFIED BY 'your_strong_password_here';
CREATE USER IF NOT EXISTS 'solspider'@'%' IDENTIFIED BY 'your_strong_password_here';

-- Предоставление прав пользователю
GRANT ALL PRIVILEGES ON solspider.* TO 'solspider'@'localhost';
GRANT ALL PRIVILEGES ON solspider.* TO 'solspider'@'%';

-- Применение изменений
FLUSH PRIVILEGES;

-- Использование созданной базы данных
USE solspider;

-- Показать статус
SELECT 
    'База данных создана успешно!' as status,
    DATABASE() as current_database,
    USER() as current_user;

-- Примечания:
-- 1. Таблицы будут созданы автоматически при первом запуске бота
-- 2. Убедитесь, что MySQL сервер запущен
-- 3. Обновите .env файл с правильными настройками подключения
-- 4. Используйте сильный пароль вместо 'your_strong_password_here'

-- Пример проверки подключения:
-- mysql -u solspider -p solspider 