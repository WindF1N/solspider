#!/usr/bin/env python3
"""
Экстренная очистка перегруженной очереди
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import get_db_manager, Token
from datetime import datetime, timedelta
import logging

def emergency_clear_all():
    """Экстренная очистка ВСЕХ зависших токенов"""
    try:
        db_manager = get_db_manager()
        session = db_manager.Session()
        
        # Очищаем ВСЕ токены старше 15 минут в анализе
        fifteen_min_ago = datetime.utcnow() - timedelta(minutes=15)
        
        stuck_tokens = session.query(Token).filter(
            Token.twitter_rating == '⏳ Анализируется...',
            Token.created_at < fifteen_min_ago
        ).all()
        
        print(f"🚨 Найдено {len(stuck_tokens)} токенов старше 15 минут в анализе")
        
        for token in stuck_tokens:
            token.twitter_rating = '🔴 Мало внимания'
            token.twitter_score = 0.0
            token.updated_at = datetime.utcnow()
        
        session.commit()
        print(f"✅ ЭКСТРЕННО ОЧИЩЕНО {len(stuck_tokens)} токенов!")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    emergency_clear_all()
