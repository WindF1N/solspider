#!/usr/bin/env python3
"""
Миграция для добавления поля last_twitter_notification в таблицу tokens на сервере
"""

import os
import sys
from datetime import datetime
import pymysql

def add_last_twitter_notification_column():
    """Добавляет поле last_twitter_notification в таблицу tokens"""
    try:
        # Получаем параметры подключения из переменных окружения
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = int(os.getenv('DB_PORT', '3306'))
        db_user = os.getenv('DB_USER', 'root')
        db_password = os.getenv('DB_PASSWORD', 'password')
        db_name = os.getenv('DB_NAME', 'solspider')
        
        print(f"🔗 Подключение к БД: {db_user}@{db_host}:{db_port}/{db_name}")
        
        # Подключаемся к базе данных
        connection = pymysql.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name,
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        
        # Проверяем существует ли уже поле
        check_query = """
        SELECT COUNT(*) 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = %s 
        AND TABLE_NAME = 'tokens' 
        AND COLUMN_NAME = 'last_twitter_notification'
        """
        
        cursor.execute(check_query, (db_name,))
        column_exists = cursor.fetchone()[0] > 0
        
        if column_exists:
            print("✅ Поле last_twitter_notification уже существует в таблице tokens")
        else:
            print("➕ Добавляем поле last_twitter_notification...")
            
            # Добавляем новое поле
            alter_query = """
            ALTER TABLE tokens 
            ADD COLUMN last_twitter_notification DATETIME NULL 
            COMMENT 'Время последнего уведомления о Twitter активности'
            """
            
            cursor.execute(alter_query)
            connection.commit()
            
            print("✅ Поле last_twitter_notification успешно добавлено в таблицу tokens")
        
        # Проверяем результат
        print("\n📋 Проверяем структуру таблицы...")
        cursor.execute("DESCRIBE tokens")
        columns = cursor.fetchall()
        
        twitter_column = None
        total_columns = len(columns)
        
        for column in columns:
            if column[0] == 'last_twitter_notification':
                twitter_column = column
                break
        
        if twitter_column:
            print(f"✅ Поле найдено: {twitter_column[0]} {twitter_column[1]} {twitter_column[2]} {twitter_column[3]}")
            print(f"📊 Всего полей в таблице tokens: {total_columns}")
        else:
            print("❌ Поле last_twitter_notification не найдено после миграции!")
            return False
        
        # Проверяем количество записей
        cursor.execute("SELECT COUNT(*) FROM tokens")
        token_count = cursor.fetchone()[0]
        print(f"📈 Количество токенов в БД: {token_count}")
        
        cursor.close()
        connection.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        return False

def test_database_operations():
    """Тестирует базовые операции с БД после миграции"""
    try:
        print("\n🧪 Тестирование операций с БД...")
        
        # Импортируем функции для проверки
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from database import get_db_manager
        
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Проверяем что можем создать запрос с новым полем
        from database import Token
        
        test_query = session.query(Token).filter(
            Token.last_twitter_notification.is_(None)
        ).count()
        
        print(f"✅ Тест запроса успешен. Токенов без last_twitter_notification: {test_query}")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        return False

if __name__ == "__main__":
    print("🚀 МИГРАЦИЯ СЕРВЕРА: Добавление поля last_twitter_notification")
    print("=" * 60)
    
    # Загружаем переменные окружения из .env файла
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Переменные окружения загружены из .env")
    except ImportError:
        print("⚠️ python-dotenv не установлен, используем системные переменные")
    
    # Выполняем миграцию
    migration_success = add_last_twitter_notification_column()
    
    if migration_success:
        print("\n🎯 Миграция выполнена успешно!")
        
        # Тестируем операции
        test_success = test_database_operations()
        
        if test_success:
            print("\n🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
            print("🚀 Сервер готов к работе с дедупликацией уведомлений")
            sys.exit(0)
        else:
            print("\n⚠️ Миграция выполнена, но есть проблемы с тестированием")
            sys.exit(1)
    else:
        print("\n💥 Миграция завершилась с ошибкой!")
        sys.exit(1) 