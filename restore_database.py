#!/usr/bin/env python3
"""
Скрипт для восстановления базы данных SolSpider из бэкапа
Восстанавливает все таблицы и данные из SQL файла
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
        logging.FileHandler('restore.log', encoding='utf-8')
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

def list_available_backups():
    """Показывает доступные файлы бэкапов"""
    backup_dir = Path('backups')
    if not backup_dir.exists():
        logger.error("❌ Директория backups не найдена!")
        return []
    
    backup_files = list(backup_dir.glob('*.sql'))
    if not backup_files:
        logger.error("❌ Файлы бэкапов не найдены в директории backups/")
        return []
    
    # Сортируем по дате создания (новые сначала)
    backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    logger.info("📋 Доступные бэкапы:")
    for i, backup_file in enumerate(backup_files, 1):
        file_size = backup_file.stat().st_size
        if file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} КБ"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} МБ"
        
        # Получаем дату из имени файла или времени создания
        mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
        logger.info(f"   {i}. {backup_file.name} ({size_str}, {mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    
    return backup_files

def choose_backup_file(backup_files):
    """Позволяет пользователю выбрать файл бэкапа"""
    if len(backup_files) == 1:
        logger.info(f"🎯 Автоматически выбран единственный бэкап: {backup_files[0].name}")
        return backup_files[0]
    
    while True:
        try:
            choice = input(f"\n🔢 Выберите номер бэкапа (1-{len(backup_files)}) или 'q' для выхода: ").strip()
            
            if choice.lower() == 'q':
                logger.info("👋 Выход из программы")
                return None
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(backup_files):
                selected_file = backup_files[choice_num - 1]
                logger.info(f"✅ Выбран бэкап: {selected_file.name}")
                return selected_file
            else:
                print(f"❌ Введите число от 1 до {len(backup_files)}")
                
        except ValueError:
            print("❌ Введите корректный номер")
        except KeyboardInterrupt:
            logger.info("\n👋 Прервано пользователем")
            return None

def verify_backup_file(backup_file):
    """Проверяет файл бэкапа перед восстановлением"""
    try:
        if not backup_file.exists():
            logger.error(f"❌ Файл бэкапа не найден: {backup_file}")
            return False
        
        file_size = backup_file.stat().st_size
        if file_size == 0:
            logger.error("❌ Файл бэкапа пустой!")
            return False
        
        # Проверяем содержимое файла
        with open(backup_file, 'r', encoding='utf-8') as f:
            first_lines = f.read(1000)
            if 'MySQL dump' not in first_lines:
                logger.error("❌ Файл не является корректным MySQL дампом!")
                return False
        
        logger.info(f"✅ Файл бэкапа проверен: {file_size / (1024 * 1024):.1f} МБ")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки файла бэкапа: {e}")
        return False

def confirm_restore(env_vars, backup_file):
    """Запрашивает подтверждение восстановления"""
    logger.warning("⚠️  ВНИМАНИЕ! Восстановление базы данных:")
    logger.warning(f"   🗄️  База данных: {env_vars['DB_NAME']}")
    logger.warning(f"   🖥️  Сервер: {env_vars['DB_HOST']}:{env_vars['DB_PORT']}")
    logger.warning(f"   📄 Файл бэкапа: {backup_file.name}")
    logger.warning("   ⚡ ВСЕ ТЕКУЩИЕ ДАННЫЕ БУДУТ УДАЛЕНЫ!")
    
    while True:
        try:
            confirmation = input("\n❓ Продолжить восстановление? (yes/no): ").strip().lower()
            if confirmation in ['yes', 'y', 'да']:
                logger.info("✅ Подтверждение получено")
                return True
            elif confirmation in ['no', 'n', 'нет']:
                logger.info("❌ Восстановление отменено пользователем")
                return False
            else:
                print("❌ Введите 'yes' или 'no'")
        except KeyboardInterrupt:
            logger.info("\n👋 Прервано пользователем")
            return False

def restore_mysql_backup(env_vars, backup_file):
    """Восстанавливает базу данных из бэкапа"""
    try:
        # Формируем команду mysql
        cmd = [
            'mysql',
            f'--host={env_vars["DB_HOST"]}',
            f'--port={env_vars["DB_PORT"]}',
            f'--user={env_vars["DB_USER"]}',
            f'--password={env_vars["DB_PASSWORD"]}',
            '--default-character-set=utf8mb4',
            env_vars['DB_NAME']
        ]
        
        logger.info("🔄 Запуск восстановления MySQL...")
        logger.info(f"📝 Команда: mysql --host={env_vars['DB_HOST']} --user={env_vars['DB_USER']} [опции] {env_vars['DB_NAME']} < {backup_file.name}")
        
        # Выполняем команду
        with open(backup_file, 'r', encoding='utf-8') as f:
            process = subprocess.Popen(
                cmd,
                stdin=f,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Восстановление MySQL выполнено успешно")
                return True
            else:
                logger.error(f"❌ Ошибка восстановления MySQL: {stderr}")
                if stdout:
                    logger.error(f"📄 Вывод: {stdout}")
                return False
                
    except FileNotFoundError:
        logger.error("❌ mysql клиент не найден! Установите MySQL клиент:")
        logger.error("   Ubuntu/Debian: sudo apt-get install mysql-client")
        logger.error("   CentOS/RHEL: sudo yum install mysql")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления: {e}")
        return False

def verify_restore(env_vars):
    """Проверяет успешность восстановления"""
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
            
            if not tables:
                logger.error("❌ Таблицы не найдены после восстановления!")
                return False
            
            logger.info("📊 Результат восстановления:")
            logger.info(f"   📁 Таблиц восстановлено: {len(tables)}")
            
            total_rows = 0
            for (table_name,) in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                row_count = cursor.fetchone()[0]
                logger.info(f"   • {table_name}: {row_count:,} записей")
                total_rows += row_count
            
            logger.info(f"   📝 Всего записей: {total_rows:,}")
            
        connection.close()
        logger.info("✅ Восстановление проверено успешно!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки восстановления: {e}")
        return False

def main():
    """Основная функция восстановления"""
    logger.info("🔄 Запуск восстановления базы данных SolSpider")
    
    # Загружаем переменные окружения
    env_vars = load_env_variables()
    if not env_vars:
        sys.exit(1)
    
    # Показываем доступные бэкапы
    backup_files = list_available_backups()
    if not backup_files:
        sys.exit(1)
    
    # Выбираем файл бэкапа
    backup_file = choose_backup_file(backup_files)
    if not backup_file:
        sys.exit(1)
    
    # Проверяем файл бэкапа
    if not verify_backup_file(backup_file):
        sys.exit(1)
    
    # Запрашиваем подтверждение
    if not confirm_restore(env_vars, backup_file):
        sys.exit(1)
    
    # Выполняем восстановление
    logger.info("🔄 Начинаем восстановление...")
    success = restore_mysql_backup(env_vars, backup_file)
    
    if not success:
        logger.error("❌ Не удалось восстановить базу данных!")
        sys.exit(1)
    
    # Проверяем результат восстановления
    if verify_restore(env_vars):
        logger.info("🎉 База данных восстановлена успешно!")
        logger.info(f"📁 Источник: {backup_file.name}")
        logger.info(f"🗄️  База данных: {env_vars['DB_NAME']}")
        
    else:
        logger.error("❌ Восстановление выполнено с ошибками!")
        sys.exit(1)

if __name__ == "__main__":
    main() 