#!/usr/bin/env python3
"""
Скрипт для создания полного бэкапа базы данных SolSpider
Создает дамп всех таблиц и данных в SQL файл
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('backup.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def load_env_variables():
    """Загружает переменные окружения из .env файла"""
    env_file = Path('.env')
    if not env_file.exists():
        logger.error("❌ Файл .env не найден!")
        return None
    
    env_vars = {}
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
        
        # Проверяем обязательные переменные
        required_vars = ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
        for var in required_vars:
            if var not in env_vars:
                logger.error(f"❌ Переменная {var} не найдена в .env файле!")
                return None
        
        logger.info("✅ Переменные окружения загружены")
        return env_vars
    
    except Exception as e:
        logger.error(f"❌ Ошибка чтения .env файла: {e}")
        return None

def create_backup_directory():
    """Создает директорию для бэкапов"""
    backup_dir = Path('backups')
    backup_dir.mkdir(exist_ok=True)
    logger.info(f"📁 Директория бэкапов: {backup_dir.absolute()}")
    return backup_dir

def get_database_stats(env_vars):
    """Получает статистику базы данных перед бэкапом"""
    try:
        import pymysql
        
        connection = pymysql.connect(
            host=env_vars['DB_HOST'],
            port=int(env_vars['DB_PORT']),
            user=env_vars['DB_USER'],
            password=env_vars['DB_PASSWORD'],
            database=env_vars['DB_NAME'],
            charset='utf8mb4'
        )
        
        with connection.cursor() as cursor:
            # Получаем информацию о таблицах
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            stats = {
                'tables': len(tables),
                'table_info': {}
            }
            
            total_rows = 0
            for (table_name,) in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                row_count = cursor.fetchone()[0]
                stats['table_info'][table_name] = row_count
                total_rows += row_count
            
            stats['total_rows'] = total_rows
            
        connection.close()
        return stats
        
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить статистику БД: {e}")
        return None

def create_mysql_backup(env_vars, backup_file):
    """Создает бэкап базы данных с помощью mysqldump"""
    try:
        # Формируем команду mysqldump
        cmd = [
            'mysqldump',
            f'--host={env_vars["DB_HOST"]}',
            f'--port={env_vars["DB_PORT"]}',
            f'--user={env_vars["DB_USER"]}',
            f'--password={env_vars["DB_PASSWORD"]}',
            '--single-transaction',  # Для InnoDB таблиц
            '--routines',           # Включить процедуры и функции
            '--triggers',           # Включить триггеры
            '--events',             # Включить события
            '--hex-blob',           # Для бинарных данных
            '--default-character-set=utf8mb4',
            '--add-drop-table',     # Добавить DROP TABLE
            '--create-options',     # Включить опции CREATE TABLE
            '--extended-insert',    # Оптимизированные INSERT
            '--lock-tables=false',  # Не блокировать таблицы
            env_vars['DB_NAME']
        ]
        
        logger.info("🔄 Запуск mysqldump...")
        logger.info(f"📝 Команда: mysqldump --host={env_vars['DB_HOST']} --user={env_vars['DB_USER']} [опции] {env_vars['DB_NAME']}")
        
        # Выполняем команду и записываем в файл
        with open(backup_file, 'w', encoding='utf-8') as f:
            process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.PIPE,
                text=True
            )
            
            _, stderr = process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ mysqldump выполнен успешно")
                return True
            else:
                logger.error(f"❌ Ошибка mysqldump: {stderr}")
                return False
                
    except FileNotFoundError:
        logger.error("❌ mysqldump не найден! Установите MySQL клиент:")
        logger.error("   Ubuntu/Debian: sudo apt-get install mysql-client")
        logger.error("   CentOS/RHEL: sudo yum install mysql")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка создания бэкапа: {e}")
        return False

def verify_backup(backup_file):
    """Проверяет созданный бэкап"""
    try:
        if not backup_file.exists():
            logger.error("❌ Файл бэкапа не найден!")
            return False
        
        file_size = backup_file.stat().st_size
        if file_size == 0:
            logger.error("❌ Файл бэкапа пустой!")
            return False
        
        # Проверяем содержимое файла
        with open(backup_file, 'r', encoding='utf-8') as f:
            first_lines = f.read(1000)
            if 'MySQL dump' not in first_lines:
                logger.error("❌ Файл бэкапа не содержит заголовок MySQL dump!")
                return False
        
        # Форматируем размер файла
        if file_size < 1024:
            size_str = f"{file_size} байт"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} КБ"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} МБ"
        
        logger.info(f"✅ Бэкап создан успешно: {size_str}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки бэкапа: {e}")
        return False

def main():
    """Основная функция создания бэкапа"""
    logger.info("🚀 Запуск создания бэкапа базы данных SolSpider")
    
    # Загружаем переменные окружения
    env_vars = load_env_variables()
    if not env_vars:
        sys.exit(1)
    
    # Создаем директорию для бэкапов
    backup_dir = create_backup_directory()
    
    # Генерируем имя файла бэкапа
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"solspider_backup_{timestamp}.sql"
    backup_file = backup_dir / backup_filename
    
    logger.info(f"📄 Файл бэкапа: {backup_file}")
    
    # Получаем статистику БД
    stats = get_database_stats(env_vars)
    if stats:
        logger.info("📊 Статистика базы данных:")
        logger.info(f"   📁 Таблиц: {stats['tables']}")
        logger.info(f"   📝 Всего записей: {stats['total_rows']:,}")
        logger.info("   📋 По таблицам:")
        for table, count in stats['table_info'].items():
            logger.info(f"      • {table}: {count:,} записей")
    
    # Создаем бэкап
    logger.info("🔄 Начинаем создание бэкапа...")
    success = create_mysql_backup(env_vars, backup_file)
    
    if not success:
        logger.error("❌ Не удалось создать бэкап!")
        sys.exit(1)
    
    # Проверяем бэкап
    if verify_backup(backup_file):
        logger.info("🎉 Бэкап базы данных создан успешно!")
        logger.info(f"📁 Расположение: {backup_file.absolute()}")
        
        # Инструкции по восстановлению
        logger.info("\n📖 Инструкции по восстановлению:")
        logger.info(f"   mysql -h {env_vars['DB_HOST']} -P {env_vars['DB_PORT']} -u {env_vars['DB_USER']} -p {env_vars['DB_NAME']} < {backup_filename}")
        logger.info("\n💡 Для восстановления в новую БД:")
        logger.info("   1. Создайте новую базу данных")
        logger.info("   2. Обновите .env файл с новыми настройками")
        logger.info("   3. Выполните команду восстановления")
        
    else:
        logger.error("❌ Бэкап создан с ошибками!")
        sys.exit(1)

if __name__ == "__main__":
    main() 